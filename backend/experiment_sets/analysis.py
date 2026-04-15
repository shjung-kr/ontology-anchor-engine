from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Dict, List

from backend.conversation.memory import build_run_summary, compare_runs, get_run_dir, utc_now_iso
from backend.experiment_sets.models import ExperimentSet, SetComparison
from backend.experiment_sets.store import save_experiment_set


def analyze_experiment_set(item: ExperimentSet) -> ExperimentSet:
    runs = item.runs
    comparisons: List[SetComparison] = []
    pair_results: List[Dict] = []

    for left, right in combinations(runs, 2):
        left_dir = get_run_dir(left.run_id)
        right_dir = get_run_dir(right.run_id)
        result = compare_runs(left_dir, right_dir)
        pair_results.append(result)
        changed_variables = [entry.get("field", "") for entry in result.get("changed_items", []) if isinstance(entry, dict)]
        observed_differences = [entry.get("field", "") for entry in result.get("changed_items", []) if isinstance(entry, dict)]
        interpretation_delta = []
        if result.get("left_run", {}).get("top_claim") != result.get("right_run", {}).get("top_claim"):
            interpretation_delta.append("top_claim_changed")
        comparisons.append(
            SetComparison(
                left_run_id=left.run_id,
                right_run_id=right.run_id,
                comparison_purpose=item.experiment_goal,
                changed_variables=changed_variables,
                observed_differences=observed_differences,
                interpretation_delta=interpretation_delta,
                decision_impact=_summarize_decision_impact(item.experiment_goal, result),
            )
        )

    summaries = [build_run_summary(get_run_dir(run.run_id)) for run in runs]
    top_claims = [summary.get("top_claim") for summary in summaries if summary.get("top_claim")]
    coverage = [summary.get("coverage_status") for summary in summaries]
    fallback_active = sum(1 for summary in summaries if summary.get("fallback_status") == "fallback_active")

    item.comparison_pairs = comparisons
    item.analysis_artifacts = {
        "generated_at_utc": utc_now_iso(),
        "run_summaries": summaries,
        "pair_results": pair_results,
        "top_claims": top_claims,
        "coverage_statuses": coverage,
        "fallback_active_count": fallback_active,
    }
    item.set_level_summary = _build_set_level_summary(item, summaries, pair_results)
    item.decision_status = _infer_decision_status(item, summaries, pair_results)
    item.updated_at_utc = utc_now_iso()

    return save_experiment_set(item)


def _summarize_decision_impact(goal: str, result: Dict) -> str:
    changed = [item.get("field") for item in result.get("changed_items", []) if isinstance(item, dict)]
    if goal == "artifact_rejection":
        return "artifact risk changed" if "fallback_status" in changed or "confirmed_conditions" in changed else "limited artifact impact"
    if goal == "next_experiment_planning":
        return "next experiment priority changed" if changed else "same planning direction"
    if goal == "mechanism_identification":
        return "mechanism ranking changed" if "top_claim" in changed else "mechanism remained stable"
    return "comparison recorded"


def _build_set_level_summary(item: ExperimentSet, summaries: List[Dict], pair_results: List[Dict]) -> str:
    run_count = len(summaries)
    top_claims = [summary.get("top_claim") for summary in summaries if summary.get("top_claim")]
    unique_claims = sorted(set(top_claims))
    fallback_count = sum(1 for summary in summaries if summary.get("fallback_status") == "fallback_active")
    changed_pair_count = sum(1 for pair in pair_results if pair.get("changed_items"))
    return (
        f"goal={item.experiment_goal}; runs={run_count}; "
        f"unique_top_claims={', '.join(unique_claims) if unique_claims else '(none)'}; "
        f"fallback_active={fallback_count}; changed_pairs={changed_pair_count}"
    )


def _infer_decision_status(item: ExperimentSet, summaries: List[Dict], pair_results: List[Dict]) -> str:
    if not summaries:
        return "draft"
    if item.experiment_goal == "mechanism_identification":
        top_claims = [summary.get("top_claim") for summary in summaries if summary.get("top_claim")]
        if len(set(top_claims)) == 1 and top_claims:
            return "supported"
    if item.experiment_goal == "artifact_rejection":
        if all(summary.get("fallback_status") != "fallback_active" for summary in summaries):
            return "supported"
    if pair_results:
        return "in_progress"
    return "inconclusive"
