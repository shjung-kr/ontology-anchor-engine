#!/usr/bin/env python3
"""
Compare rule-based chat answers and LLM-context chat answers on a fixed benchmark.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.conversation.memory import (  # noqa: E402
    build_chat_response,
    build_direct_answer,
    get_run_dir,
    load_analysis_snapshot,
    load_chat_history,
    load_intent_profile,
)
from backend.llm_adapter import DEFAULT_MODEL, _get_openai_client  # noqa: E402


STRATEGIES = ("rule_based", "llm_context")
SCORING_AXES = (
    "question_fit",
    "evidence_use",
    "depth",
    "accuracy_guardedness",
    "naturalness",
    "actionability",
)


@dataclass
class EvalCase:
    case_id: str
    run_id: str
    category: str
    question: str
    expected_elements: Dict[str, List[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chat quality against a benchmark.")
    parser.add_argument(
        "--benchmark",
        default=str(REPO_ROOT / "data" / "evals" / "chat_eval_questions.json"),
        help="Path to benchmark JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "evals" / "results" / "chat_eval_report.json"),
        help="Path to save evaluation report JSON.",
    )
    parser.add_argument(
        "--judge-mode",
        choices=("heuristic", "llm", "both"),
        default="both",
        help="Scoring mode. 'both' stores heuristic, llm, and merged scores when LLM judge is available.",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=STRATEGIES,
        default=list(STRATEGIES),
        help="Strategies to evaluate.",
    )
    return parser.parse_args()


def load_benchmark(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"] = [EvalCase(**item) for item in payload.get("cases", [])]
    return payload


def generate_answer(case: EvalCase, strategy: str) -> Dict[str, Any]:
    run_dir = get_run_dir(case.run_id)
    snapshot = load_analysis_snapshot(run_dir)
    intent_profile = load_intent_profile(run_dir)
    chat_state = build_chat_response(run_dir)
    reranked = chat_state.get("reranked_sj_proposals", []) or []
    chat_history = load_chat_history(run_dir)
    answer = build_direct_answer(
        case.question,
        snapshot=snapshot,
        intent_profile=intent_profile,
        reranked_proposals=reranked,
        chat_history=chat_history,
        run_dir=run_dir,
        prefer_llm=(strategy == "llm_context"),
    )
    return {
        "answer": answer,
        "snapshot": snapshot,
        "intent_profile": intent_profile,
        "chat_state": chat_state,
    }


def heuristic_scores(case: EvalCase, answer: str, generated: Dict[str, Any]) -> Dict[str, Any]:
    text = (answer or "").strip()
    lowered = text.lower()
    expected = case.expected_elements or {}
    must = [item.lower() for item in expected.get("must", [])]
    should = [item.lower() for item in expected.get("should", [])]
    avoid = [item.lower() for item in expected.get("avoid", [])]

    def hit_ratio(items: List[str]) -> float:
        if not items:
            return 1.0
        hits = sum(1 for item in items if item and item in lowered)
        return hits / len(items)

    must_ratio = hit_ratio(must)
    should_ratio = hit_ratio(should)
    avoid_hits = sum(1 for item in avoid if item and item in lowered)
    ontology_leak = bool(re.search(r"\b[a-z_]+\.[a-z0-9_.-]+\b", text))
    sentence_count = len([part for part in re.split(r"[.!?\n]+", text) if part.strip()])
    explanation_markers = sum(1 for token in ("왜냐하면", "즉", "따라서", "의미", "뜻", "because", "therefore") if token in text)

    proposals = (generated.get("chat_state", {}) or {}).get("reranked_sj_proposals", []) or []
    top_proposal = proposals[0] if proposals else {}
    matched_features = top_proposal.get("matched_features", []) or []
    assumptions = top_proposal.get("sj_assumptions", []) or []
    grounding_hits = 0
    for item in list(matched_features) + list(assumptions):
        suffix = str(item).split(".", 1)[-1].replace("_", " ").lower()
        if suffix and suffix in lowered:
            grounding_hits += 1

    scores = {
        "question_fit": clamp_score(round(2 + 3 * ((must_ratio * 0.7) + (should_ratio * 0.3)))),
        "evidence_use": clamp_score(round(1 + min(4, grounding_hits + must_ratio * 2))),
        "depth": clamp_score(round(1 + min(4, (sentence_count / 2) + explanation_markers + should_ratio))),
        "accuracy_guardedness": clamp_score(5 - min(2, avoid_hits) - (1 if "확실" in text and "가능" not in text and "불확실" not in text else 0)),
        "naturalness": clamp_score(5 - (2 if ontology_leak else 0) - (1 if "현재 run 기준 최상위 해석은" in text else 0)),
        "actionability": clamp_score(
            3
            if case.category not in {"next_experiment", "turn_on_reduction"}
            else round(1 + min(4, should_ratio * 2 + sum(1 for token in ("비교", "변경", "split", "측정", "실험") if token in text)))
        ),
    }
    return {
        "scores": scores,
        "notes": {
            "must_ratio": round(must_ratio, 3),
            "should_ratio": round(should_ratio, 3),
            "avoid_hits": avoid_hits,
            "ontology_leak": ontology_leak,
            "sentence_count": sentence_count,
            "grounding_hits": grounding_hits,
        },
    }


def clamp_score(value: float) -> int:
    return max(1, min(5, int(value)))


def llm_judge_scores(case: EvalCase, answer: str) -> Optional[Dict[str, Any]]:
    client = _get_openai_client()
    if client is None:
        return None

    prompt = {
        "task": "Score the answer for a scientific chat benchmark.",
        "scale": "Each score must be an integer from 1 to 5.",
        "case": {
            "category": case.category,
            "question": case.question,
            "expected_elements": case.expected_elements,
        },
        "criteria": {
            "question_fit": "Did the answer directly address the user's question?",
            "evidence_use": "Did the answer use relevant evidence from the analysis context?",
            "depth": "Did the answer explain meaning, conditions, or causal structure beyond a shallow summary?",
            "accuracy_guardedness": "Did the answer stay consistent with evidence and acknowledge uncertainty appropriately?",
            "naturalness": "Was the answer natural and readable, without ontology-ID leakage or mechanical repetition?",
            "actionability": "If the question asked for next steps or changes, was the answer specific and actionable?",
        },
        "answer": answer,
        "output_format": {
            "scores": {axis: 1 for axis in SCORING_AXES},
            "rationale": "short explanation",
        },
    }

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict evaluator for scientific QA outputs. Return JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        raw_scores = payload.get("scores", {})
        scores = {axis: clamp_score(raw_scores.get(axis, 3)) for axis in SCORING_AXES}
        return {"scores": scores, "rationale": payload.get("rationale", "")}
    except Exception as exc:
        return {"scores": None, "rationale": f"llm_judge_error: {exc}"}


def merge_scores(heuristic: Dict[str, int], llm_scores: Optional[Dict[str, int]]) -> Dict[str, int]:
    if not llm_scores:
        return heuristic
    merged: Dict[str, int] = {}
    for axis in SCORING_AXES:
        merged[axis] = clamp_score(round((heuristic[axis] + llm_scores[axis]) / 2))
    return merged


def average_scores(items: List[Dict[str, int]]) -> Dict[str, float]:
    if not items:
        return {axis: 0.0 for axis in SCORING_AXES}
    return {axis: round(mean(item[axis] for item in items), 3) for axis in SCORING_AXES}


def summarize_strategy(case_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_scores = [item["scores"]["merged"] for item in case_results]
    heuristic_scores_list = [item["scores"]["heuristic"] for item in case_results]
    llm_scores_list = [item["scores"]["llm"] for item in case_results if item["scores"].get("llm")]
    by_category: Dict[str, List[Dict[str, int]]] = defaultdict(list)
    ontology_leak_count = 0
    repeated_opening_count = 0
    for item in case_results:
        by_category[item["category"]].append(item["scores"]["merged"])
        if item["scores"]["heuristic_notes"].get("ontology_leak"):
            ontology_leak_count += 1
        if "현재 run 기준 최상위 해석은" in item["answer"]:
            repeated_opening_count += 1
    return {
        "case_count": len(case_results),
        "average_scores": {
            "merged": average_scores(merged_scores),
            "heuristic": average_scores(heuristic_scores_list),
            "llm": average_scores(llm_scores_list) if llm_scores_list else None,
        },
        "by_category": {
            category: average_scores(scores)
            for category, scores in sorted(by_category.items())
        },
        "ontology_leak_rate": round(ontology_leak_count / len(case_results), 3) if case_results else 0.0,
        "repeated_opening_rate": round(repeated_opening_count / len(case_results), 3) if case_results else 0.0,
    }


def build_comparison(strategy_reports: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not {"rule_based", "llm_context"}.issubset(strategy_reports):
        return {}
    baseline = strategy_reports["rule_based"]["summary"]["average_scores"]["merged"]
    candidate = strategy_reports["llm_context"]["summary"]["average_scores"]["merged"]
    delta = {axis: round(candidate[axis] - baseline[axis], 3) for axis in SCORING_AXES}
    improvement = {
        axis: round(((candidate[axis] - baseline[axis]) / baseline[axis]) * 100, 2) if baseline[axis] else None
        for axis in SCORING_AXES
    }
    return {
        "delta": delta,
        "improvement_percent": improvement,
    }


def main() -> None:
    args = parse_args()
    benchmark_path = Path(args.benchmark)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmark = load_benchmark(benchmark_path)
    strategy_reports: Dict[str, Dict[str, Any]] = {}

    for strategy in args.strategies:
        case_results: List[Dict[str, Any]] = []
        for case in benchmark["cases"]:
            generated = generate_answer(case, strategy)
            answer = generated["answer"]
            heuristic = heuristic_scores(case, answer, generated)
            llm_result = None
            if args.judge_mode in {"llm", "both"}:
                llm_result = llm_judge_scores(case, answer)
            merged = merge_scores(heuristic["scores"], llm_result.get("scores") if llm_result and llm_result.get("scores") else None)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "run_id": case.run_id,
                    "category": case.category,
                    "question": case.question,
                    "answer": answer,
                    "scores": {
                        "heuristic": heuristic["scores"],
                        "heuristic_notes": heuristic["notes"],
                        "llm": llm_result.get("scores") if llm_result and llm_result.get("scores") else None,
                        "llm_rationale": llm_result.get("rationale") if llm_result else None,
                        "merged": merged,
                    },
                }
            )
        strategy_reports[strategy] = {
            "summary": summarize_strategy(case_results),
            "cases": case_results,
        }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "benchmark_file": str(benchmark_path),
        "judge_mode": args.judge_mode,
        "strategies": strategy_reports,
        "comparison": build_comparison(strategy_reports),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["comparison"], ensure_ascii=False, indent=2))
    print(f"saved_report={output_path}")


if __name__ == "__main__":
    main()
