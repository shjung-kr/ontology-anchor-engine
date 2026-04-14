# main.py

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from backend.conversation.memory import (
    apply_review_decision,
    append_chat_event,
    build_direct_answer,
    build_chat_response,
    classify_user_message,
    load_analysis_snapshot,
    get_run_dir,
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
from backend.l1_sj_engine import run_l1_engine

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
        # cloudflare pages domain
        "https://ontology-anchor-engine.pages.dev",
        ],
    
    allow_methods=["*"],
    allow_headers=["*"],
)

class RawInput(BaseModel):
    raw_data: str


@app.post("/v14/run")
def run_engine(data: RawInput):
    return run_l1_engine(data.raw_data)


@app.get("/domains")
def list_domains():
    return {"domains": [item.model_dump() for item in list_domain_summaries()]}


@app.post("/run")
def run_domain(data: DomainExecutionRequest):
    return run_domain_engine(data)


@app.post("/chat")
def run_chat(data: ChatTurnRequest):
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
def get_run_intent(run_id: str):
    try:
        run_dir = get_run_dir(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run_id, "intent_profile": load_intent_profile(run_dir), **build_chat_response(run_dir)}


@app.get("/overlays/iv")
def get_iv_curated_overlay():
    return load_curated_overlay()


@app.get("/overlays/iv/review-queue")
def get_iv_overlay_review_queue():
    return {"queue": load_review_queue(), "review_state": load_review_state()}


@app.post("/overlays/iv/review")
def decide_iv_overlay_review(data: OverlayReviewDecisionRequest):
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


app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
