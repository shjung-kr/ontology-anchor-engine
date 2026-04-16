#!/usr/bin/env python3
"""
Convert chat evaluation JSON report into a compact Markdown summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


SCORING_AXES = (
    "question_fit",
    "evidence_use",
    "depth",
    "accuracy_guardedness",
    "naturalness",
    "actionability",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize chat evaluation JSON as Markdown.")
    parser.add_argument("report", help="Path to chat_eval_report.json")
    parser.add_argument(
        "--output",
        default="",
        help="Optional markdown output path. Defaults to <report>.md",
    )
    return parser.parse_args()


def md_table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def format_score_row(name: str, scores: Dict[str, Any]) -> List[Any]:
    return [name] + [scores.get(axis, "-") for axis in SCORING_AXES]


def build_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Chat Eval Summary")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report.get('generated_at_utc', '')}`")
    lines.append(f"- benchmark_file: `{report.get('benchmark_file', '')}`")
    lines.append(f"- judge_mode: `{report.get('judge_mode', '')}`")
    lines.append("")

    strategies = report.get("strategies", {}) or {}
    headers = ["strategy"] + list(SCORING_AXES)
    strategy_rows = []
    for strategy, payload in strategies.items():
        merged = ((payload.get("summary", {}) or {}).get("average_scores", {}) or {}).get("merged", {})
        strategy_rows.append(format_score_row(strategy, merged))
    lines.append("## Overall Scores")
    lines.append("")
    lines.append(md_table(headers, strategy_rows))
    lines.append("")

    comparison = report.get("comparison", {}) or {}
    if comparison:
        delta = comparison.get("delta", {}) or {}
        improvement = comparison.get("improvement_percent", {}) or {}
        lines.append("## Improvement vs Rule-Based")
        lines.append("")
        rows = []
        for axis in SCORING_AXES:
            rows.append([axis, delta.get(axis, "-"), improvement.get(axis, "-")])
        lines.append(md_table(["axis", "delta", "improvement_percent"], rows))
        lines.append("")

    for strategy, payload in strategies.items():
        summary = payload.get("summary", {}) or {}
        lines.append(f"## {strategy}")
        lines.append("")
        lines.append(f"- case_count: `{summary.get('case_count', 0)}`")
        lines.append(f"- ontology_leak_rate: `{summary.get('ontology_leak_rate', 0.0)}`")
        lines.append(f"- repeated_opening_rate: `{summary.get('repeated_opening_rate', 0.0)}`")
        lines.append("")

        by_category = summary.get("by_category", {}) or {}
        if by_category:
            category_rows = [format_score_row(category, scores) for category, scores in by_category.items()]
            lines.append("### By Category")
            lines.append("")
            lines.append(md_table(headers, category_rows))
            lines.append("")

        cases = payload.get("cases", []) or []
        weakest = sorted(
            cases,
            key=lambda item: sum((item.get("scores", {}) or {}).get("merged", {}).get(axis, 0) for axis in SCORING_AXES),
        )[:5]
        if weakest:
            lines.append("### Lowest-Scoring Cases")
            lines.append("")
            rows = []
            for item in weakest:
                merged = (item.get("scores", {}) or {}).get("merged", {})
                total = round(sum(merged.get(axis, 0) for axis in SCORING_AXES), 3)
                rows.append([item.get("case_id"), item.get("category"), total, item.get("question")])
            lines.append(md_table(["case_id", "category", "total_score", "question"], rows))
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = parse_args()
    report_path = Path(args.report)
    output_path = Path(args.output) if args.output else report_path.with_suffix(".md")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    markdown = build_markdown(report)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"saved_markdown={output_path}")


if __name__ == "__main__":
    main()
