from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.bench.nexus_value_comparison_report import RunArm, RunSummary, render_report, summarize_run


@dataclass(frozen=True)
class FocusedRun:
    name: str
    scope: str
    claim_status: str
    focus_arm: str
    summary: RunSummary

    @property
    def arm(self) -> RunArm:
        return self.summary.nexus if self.focus_arm == "nexus" else self.summary.bare

    @property
    def verified_rate(self) -> float:
        return self.arm.verified / self.arm.eligible if self.arm.eligible else 0.0

    @property
    def tokens_per_verified(self) -> float:
        if self.arm.verified <= 0 or self.arm.eligible <= 0 or self.arm.avg_tokens <= 0:
            return 0.0
        return (self.arm.avg_tokens * self.arm.eligible) / self.arm.verified

    @property
    def wall_per_verified(self) -> float:
        if self.arm.verified <= 0 or self.arm.eligible <= 0 or self.arm.avg_wall <= 0:
            return 0.0
        return (self.arm.avg_wall * self.arm.eligible) / self.arm.verified


def parse_run_spec(spec: str) -> tuple[str, Path, str, str, str]:
    parts = spec.split("=", 4)
    if len(parts) != 5:
        raise SystemExit("--run must be name=path=scope=claim_status=focus_arm")
    name, path, scope, claim_status, focus_arm = parts
    if focus_arm not in {"bare", "nexus"}:
        raise SystemExit("--run focus_arm must be bare or nexus")
    return name, Path(path), scope, claim_status, focus_arm


def build_focused_runs(specs: list[str], notes_by_name: dict[str, list[str]]) -> list[FocusedRun]:
    focused: list[FocusedRun] = []
    for spec in specs:
        name, path, scope, claim_status, focus_arm = parse_run_spec(spec)
        summary = summarize_run(name, path, scope=scope, claim_status=claim_status, extra_notes=tuple(notes_by_name.get(name, ())))
        focused.append(FocusedRun(name=name, scope=scope, claim_status=claim_status, focus_arm=focus_arm, summary=summary))
    return focused


def _ratio(numerator: float, denominator: float) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{numerator / denominator:.2f}x"


def _pct_gap(current: float, reference: float) -> str:
    if reference <= 0:
        return "n/a"
    return f"{((current - reference) / reference) * 100:+.1f}%"


def _decision_band(*, current: FocusedRun, reference: FocusedRun) -> str:
    if current.verified_rate >= reference.verified_rate and current.tokens_per_verified <= reference.tokens_per_verified:
        return "beats_reference"
    if current.verified_rate >= reference.verified_rate * 0.9 and (
        reference.tokens_per_verified <= 0 or current.tokens_per_verified <= reference.tokens_per_verified * 1.5
    ):
        return "near_reference"
    if current.verified_rate >= reference.verified_rate * 0.75:
        return "partial_gap"
    return "far_from_reference"


def render_cost_truth_report(
    focused_runs: list[FocusedRun],
    *,
    reference_model: str,
    weak_model_name: str,
) -> str:
    summaries = [item.summary for item in focused_runs]
    base = render_report(summaries)
    by_name = {item.name: item for item in focused_runs}
    reference = by_name.get(reference_model)
    weak = by_name.get(weak_model_name)

    lines = [base, "", "## Weak Model Cost Truth", ""]
    lines.extend(
        [
            "| Model | Focus arm | Verified | Wall/verified | Tokens/verified | Model calls | vs ref verified | vs ref tokens | Decision |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for item in focused_runs:
        arm = item.arm
        decision = ""
        verified_gap = "n/a"
        token_gap = "n/a"
        if reference:
            verified_gap = _pct_gap(item.verified_rate, reference.verified_rate)
            token_gap = _ratio(item.tokens_per_verified, reference.tokens_per_verified)
            decision = _decision_band(current=item, reference=reference)
        lines.append(
            f"| {item.name} | {item.focus_arm} | "
            f"{arm.verified}/{arm.eligible} ({item.verified_rate * 100:.1f}%) | "
            f"{item.wall_per_verified:.2f}s | "
            f"{item.tokens_per_verified:.0f} | "
            f"{arm.avg_model_calls:.2f} | "
            f"{verified_gap} | "
            f"{token_gap} | "
            f"{decision or 'n/a'} |"
        )

    if reference and weak:
        lines.extend(
            [
                "",
                "## Weak Model Decision",
                "",
                f"- reference_model: {reference.name}",
                f"- weak_model: {weak.name}",
                f"- weak_vs_reference_verified_gap: {_pct_gap(weak.verified_rate, reference.verified_rate)}",
                f"- weak_vs_reference_tokens_per_verified: {_ratio(weak.tokens_per_verified, reference.tokens_per_verified)}",
                f"- weak_vs_reference_wall_per_verified: {_ratio(weak.wall_per_verified, reference.wall_per_verified)}",
                f"- decision: {_decision_band(current=weak, reference=reference)}",
            ]
        )
    return "\n".join(lines) + "\n"


def render_cost_truth_json(
    focused_runs: list[FocusedRun],
    *,
    reference_model: str,
    weak_model_name: str,
) -> dict[str, Any]:
    by_name = {item.name: item for item in focused_runs}
    reference = by_name.get(reference_model)
    weak = by_name.get(weak_model_name)
    rows: list[dict[str, Any]] = []
    for item in focused_runs:
        arm = item.arm
        row = {
            "name": item.name,
            "focus_arm": item.focus_arm,
            "verified": arm.verified,
            "eligible": arm.eligible,
            "verified_rate": round(item.verified_rate, 4),
            "wall_per_verified_sec": round(item.wall_per_verified, 4),
            "tokens_per_verified": round(item.tokens_per_verified, 4),
            "avg_model_calls": round(arm.avg_model_calls, 4),
        }
        if reference:
            row["vs_reference_verified_gap_pct"] = round(
                ((item.verified_rate - reference.verified_rate) / reference.verified_rate) * 100, 4
            ) if reference.verified_rate > 0 else None
            row["vs_reference_tokens_ratio"] = round(
                item.tokens_per_verified / reference.tokens_per_verified, 4
            ) if reference.tokens_per_verified > 0 else None
            row["decision"] = _decision_band(current=item, reference=reference)
        rows.append(row)
    payload: dict[str, Any] = {
        "schema_version": "nexus_weak_model_cost_truth_v1",
        "reference_model": reference_model,
        "weak_model_name": weak_model_name,
        "rows": rows,
    }
    if reference and weak:
        payload["weak_model_decision"] = {
            "weak_vs_reference_verified_gap_pct": round(
                ((weak.verified_rate - reference.verified_rate) / reference.verified_rate) * 100, 4
            ) if reference.verified_rate > 0 else None,
            "weak_vs_reference_tokens_ratio": round(
                weak.tokens_per_verified / reference.tokens_per_verified, 4
            ) if reference.tokens_per_verified > 0 else None,
            "weak_vs_reference_wall_ratio": round(
                weak.wall_per_verified / reference.wall_per_verified, 4
            ) if reference.wall_per_verified > 0 else None,
            "decision": _decision_band(current=weak, reference=reference),
        }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render multi-baseline weak-model cost truth from benchmark artifacts.")
    parser.add_argument("--run", action="append", default=[], help="name=path=scope=claim_status=focus_arm")
    parser.add_argument("--note", action="append", default=[], help="name=note")
    parser.add_argument("--reference-model", required=True)
    parser.add_argument("--weak-model-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", help="Optional JSON payload path.")
    args = parser.parse_args(argv)

    notes_by_name: dict[str, list[str]] = {}
    for note in args.note:
        name, sep, text = note.partition("=")
        if not sep:
            raise SystemExit("--note must be name=note")
        notes_by_name.setdefault(name, []).append(text)

    focused_runs = build_focused_runs(list(args.run), notes_by_name)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_cost_truth_report(
            focused_runs,
            reference_model=str(args.reference_model),
            weak_model_name=str(args.weak_model_name),
        ),
        encoding="utf-8",
    )
    if args.output_json:
        json_path = Path(args.output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(
                render_cost_truth_json(
                    focused_runs,
                    reference_model=str(args.reference_model),
                    weak_model_name=str(args.weak_model_name),
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
