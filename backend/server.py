from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.auth import (
    AuthenticatedUser,
    authenticate_user,
    register_user,
    require_authenticated_user,
    revoke_token,
)
from backend.conversation.memory import (
    apply_review_decision,
    append_chat_event,
    build_direct_answer,
    build_run_summary,
    build_chat_response,
    classify_user_message,
    compare_runs,
    get_run_dir,
    list_run_summaries,
    load_analysis_snapshot,
    load_chat_history,
    load_curated_overlay,
    load_intent_profile,
    load_review_queue,
    load_review_state,
    update_intent_profile,
    utc_now_iso,
    validate_structured_answers,
)
from backend.conversation.models import ChatTurnRequest, OverlayReviewDecisionRequest
from backend.core.domain_models import DomainExecutionRequest
from backend.core.domain_registry import list_domain_summaries
from backend.core.engine import run_domain_engine
from backend.experiment_sets.analysis import analyze_experiment_set
from backend.experiment_sets.models import (
    ExperimentSetAddRunRequest,
    ExperimentSetCreateRequest,
    ExperimentSetUpdateRequest,
)
from backend.experiment_sets.store import (
    add_run_to_experiment_set,
    create_experiment_set,
    get_experiment_set,
    list_experiment_sets,
    update_experiment_set,
)
from backend.l1_sj_engine import run_l1_engine
from backend.user_storage import get_user_runs_dir, user_scope


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="V14.0 SJ Ontology Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ontology-anchor-engine.pages.dev",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RawInput(BaseModel):
    raw_data: str


class RunCompareRequest(BaseModel):
    left_run_id: str
    right_run_id: str


class AuthRegisterRequest(BaseModel):
    user_id: str
    password: str
    display_name: str | None = None


class AuthLoginRequest(BaseModel):
    user_id: str
    password: str


@app.post("/auth/register")
def auth_register(data: AuthRegisterRequest):
    try:
        user = register_user(data.user_id, data.password, display_name=data.display_name)
        session = authenticate_user(data.user_id, data.password)
        return {"user": user, "session": session}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/auth/login")
def auth_login(data: AuthLoginRequest):
    try:
        session = authenticate_user(data.user_id, data.password)
        return {"session": session}
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/logout")
def auth_logout(user: AuthenticatedUser = Depends(require_authenticated_user)):
    revoke_token(user.token)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        run_count = len([path for path in get_user_runs_dir().iterdir() if path.is_dir()])
        return {
            "user": {
                "user_id": user.user_id,
                "display_name": user.display_name,
            },
            "workspace": {
                "run_count": run_count,
                "recent_runs": list_run_summaries(limit=5),
            },
        }


@app.post("/v14/run")
def run_engine(data: RawInput, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return run_l1_engine(data.raw_data)


@app.get("/domains")
def list_domains():
    return {"domains": [item.model_dump() for item in list_domain_summaries()]}


@app.post("/run")
def run_domain(data: DomainExecutionRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            return run_domain_engine(data)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/chat")
def run_chat(data: ChatTurnRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            run_dir = get_run_dir(data.run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        validation_errors = validate_structured_answers(run_dir, data.structured_answers)
        if validation_errors:
            raise HTTPException(status_code=422, detail={"message": "structured answer validation failed", "errors": validation_errors})

        if data.user_text.strip() or data.structured_answers:
            append_chat_event(
                run_dir,
                {
                    "timestamp_utc": utc_now_iso(),
                    "role": "user",
                    "type": "answer",
                    "text": data.user_text,
                    "intent_update": data.intent_update.model_dump(),
                    "structured_answers": [item.model_dump() for item in data.structured_answers],
                },
            )

        profile = update_intent_profile(run_dir, data)
        response = build_chat_response(run_dir)
        chat_mode = classify_user_message(data.user_text, data.structured_answers)
        response["chat_mode"] = chat_mode
        if chat_mode == "direct_question" and data.user_text.strip():
            assistant_reply = build_direct_answer(
                data.user_text,
                snapshot=load_analysis_snapshot(run_dir),
                intent_profile=profile,
                reranked_proposals=response.get("reranked_sj_proposals", []),
                chat_history=load_chat_history(run_dir),
                run_dir=run_dir,
            )
            response["assistant_reply"] = assistant_reply
            if assistant_reply:
                append_chat_event(
                    run_dir,
                    {
                        "timestamp_utc": utc_now_iso(),
                        "role": "assistant",
                        "type": "answer",
                        "text": assistant_reply,
                        "chat_mode": chat_mode,
                    },
                )

        response["intent_profile"] = profile
        return response


@app.get("/runs/{run_id}/intent")
def get_run_intent(run_id: str, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            run_dir = get_run_dir(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"run_id": run_id, "intent_profile": load_intent_profile(run_dir), **build_chat_response(run_dir)}


@app.get("/runs")
def list_runs(limit: int = 50, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return {"runs": list_run_summaries(limit=limit)}


@app.get("/runs/{run_id}/summary")
def get_run_summary(run_id: str, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            run_dir = get_run_dir(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        snapshot = load_analysis_snapshot(run_dir)
        chat_state = build_chat_response(run_dir)
        return {
            **build_run_summary(run_dir),
            "measurement_validation": snapshot.get("measurement_validation", {}),
            "llm_pattern": snapshot.get("llm_pattern", ""),
            "assumptions": (snapshot.get("assumptions", {}) or {}).get("assumptions", []),
            "l1_state": snapshot.get("l1_state", {}),
            "sj_proposals": chat_state.get("reranked_sj_proposals", []),
            "system_narrative": chat_state.get("system_narrative", ""),
            "conversation_state": chat_state,
        }


@app.post("/runs/compare")
def compare_run_pair(data: RunCompareRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            left_run_dir = get_run_dir(data.left_run_id)
            right_run_dir = get_run_dir(data.right_run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return compare_runs(left_run_dir, right_run_dir)


@app.get("/experiment-sets")
def get_experiment_sets(user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return {"sets": [item.model_dump() for item in list_experiment_sets()]}


@app.post("/experiment-sets")
def post_experiment_set(data: ExperimentSetCreateRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return create_experiment_set(data).model_dump()


@app.get("/experiment-sets/{set_id}")
def get_experiment_set_detail(set_id: str, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            return get_experiment_set(set_id).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/experiment-sets/{set_id}")
def patch_experiment_set(set_id: str, data: ExperimentSetUpdateRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            return update_experiment_set(set_id, data).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/experiment-sets/{set_id}/runs")
def post_experiment_set_run(set_id: str, data: ExperimentSetAddRunRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            return add_run_to_experiment_set(set_id, data).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/experiment-sets/{set_id}/analyze")
def post_experiment_set_analyze(set_id: str, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            item = get_experiment_set(set_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return analyze_experiment_set(item).model_dump()


@app.get("/overlays/iv")
def get_iv_curated_overlay(user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return load_curated_overlay()


@app.get("/overlays/iv/review-queue")
def get_iv_overlay_review_queue(user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        return {"queue": load_review_queue(), "review_state": load_review_state()}


@app.post("/overlays/iv/review")
def decide_iv_overlay_review(data: OverlayReviewDecisionRequest, user: AuthenticatedUser = Depends(require_authenticated_user)):
    with user_scope(user.user_id):
        try:
            state = apply_review_decision(
                overlay_type=data.overlay_type,
                target_id=data.target_id,
                decision=data.decision,
                note=data.note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "review_state": state,
            "queue": load_review_queue(),
            "curated_overlay": load_curated_overlay(),
        }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
