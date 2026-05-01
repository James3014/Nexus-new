from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunArm:
    rows: int
    eligible: int
    verified: int
    infra_invalid: tuple[str, ...]
    avg_wall: float
    avg_model_calls: float
    avg_tokens: float


@dataclass(frozen=True)
class RunSummary:
    name: str
    scope: str
    gate_status: str
    claim_status: str
    bare: RunArm
    nexus: RunArm
    notes: tuple[str, ...]

    @property
    def bare_rate(self) -> float:
        return self.bare.verified / self.bare.eligible if self.bare.eligible else 0.0

    @property
    def nexus_rate(self) -> float:
        return self.nexus.verified / self.nexus.eligible if self.nexus.eligible else 0.0

    @property
    def lift(self) -> float:
        return self.nexus_rate - self.bare_rate


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _first_jsonl(run_dir: Path, arm: str) -> Path:
    matches = sorted(run_dir.glob(f"{arm}_*.jsonl"))
    if not matches:
        raise FileNotFoundError(f"missing {arm}_*.jsonl in {run_dir}")
    return matches[-1]


def _number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize_arm(rows: list[dict[str, Any]]) -> RunArm:
    eligible = [row for row in rows if bool(row.get("run_eligible", True))]
    verified = [row for row in eligible if str(row.get("semantic_status") or "") == "VERIFIED"]
    infra = sorted({str(row.get("infra_invalid_reason")) for row in rows if not bool(row.get("run_eligible", True)) and row.get("infra_invalid_reason")})
    return RunArm(
        rows=len(rows),
        eligible=len(eligible),
        verified=len(verified),
        infra_invalid=tuple(infra),
        avg_wall=_avg([_number(row, "wall_duration_sec", "wall_time_sec", "duration_sec") for row in eligible]),
        avg_model_calls=_avg([_number(row, "model_calls") for row in eligible]),
        avg_tokens=_avg([_number(row, "total_tokens", "model_total_tokens") for row in eligible]),
    )


def _markdown_gate(run_dir: Path) -> tuple[str | None, tuple[str, ...]]:
    reports = sorted(run_dir.glob("gemini_nexus_report_*.md"))
    if not reports:
        return None, ()
    text = reports[-1].read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"^- Public claim gate: (PASS|FAIL)\s*$", text, re.MULTILINE)
    failures = re.search(r"^- Public claim gate failures: (.+)$", text, re.MULTILINE)
    return (match.group(1) if match else None), (() if not failures or failures.group(1) == "none" else (failures.group(1),))


def _bundle_gate(run_dir: Path) -> tuple[str | None, tuple[str, ...], str]:
    path = run_dir / "evidence_bundle.json"
    if not path.exists():
        return None, (), ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    gate = payload.get("public_claim_gate") or {}
    failures = gate.get("failures") or ()
    return gate.get("verdict"), tuple(str(item) for item in failures), str(payload.get("schema") or "")


def summarize_run(name: str, run_dir: Path, *, scope: str, claim_status: str, extra_notes: tuple[str, ...] = ()) -> RunSummary:
    bare_rows = _load_jsonl(_first_jsonl(run_dir, "without_nexus"))
    nexus_rows = _load_jsonl(_first_jsonl(run_dir, "with_nexus"))
    markdown_gate, markdown_failures = _markdown_gate(run_dir)
    bundle_gate, bundle_failures, schema = _bundle_gate(run_dir)
    gate_bits = []
    if markdown_gate:
        gate_bits.append(f"markdown {markdown_gate}")
    if bundle_gate:
        gate_bits.append(f"bundle {bundle_gate}")
    if schema:
        gate_bits.append(schema)
    notes = list(extra_notes)
    if markdown_failures:
        notes.append(f"markdown failures: {', '.join(markdown_failures)}")
    if bundle_failures:
        notes.append(f"bundle failures: {', '.join(bundle_failures)}")
    return RunSummary(
        name=name,
        scope=scope,
        gate_status="; ".join(gate_bits) if gate_bits else "not available",
        claim_status=claim_status,
        bare=summarize_arm(bare_rows),
        nexus=summarize_arm(nexus_rows),
        notes=tuple(notes),
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_report(summaries: list[RunSummary]) -> str:
    lines = [
        "# Nexus Public Value Comparison",
        "",
        "## Main Evidence",
        "",
        "| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |",
        "| :--- | :--- | :--- | ---: | ---: | ---: | :--- |",
    ]
    for item in summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.scope,
                    item.gate_status,
                    f"{item.bare.verified}/{item.bare.eligible}, {_pct(item.bare_rate)}",
                    f"{item.nexus.verified}/{item.nexus.eligible}, {_pct(item.nexus_rate)}",
                    _pct(item.lift),
                    item.claim_status,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Cost",
            "",
            "| Model | Wall time | Model calls | Tokens |",
            "| :--- | :--- | :--- | :--- |",
        ]
    )
    for item in summaries:
        lines.append(
            f"| {item.name} | {item.bare.avg_wall:.2f}s -> {item.nexus.avg_wall:.2f}s | "
            f"{item.bare.avg_model_calls:.2f} -> {item.nexus.avg_model_calls:.2f} | "
            f"{item.bare.avg_tokens:.0f} -> {item.nexus.avg_tokens:.0f} |"
        )
    lines.extend(["", "## Claim Boundaries", ""])
    for item in summaries:
        note_text = "; ".join(item.notes) if item.notes else "none"
        lines.append(f"- {item.name}: {note_text}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Nexus multi-model value comparison from benchmark artifacts.")
    parser.add_argument("--run", action="append", default=[], help="name=path=scope=claim_status")
    parser.add_argument("--note", action="append", default=[], help="name=note; can be supplied multiple times")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    notes_by_name: dict[str, list[str]] = {}
    for note in args.note:
        name, sep, text = note.partition("=")
        if not sep:
            raise SystemExit("--note must be name=note")
        notes_by_name.setdefault(name, []).append(text)
    summaries: list[RunSummary] = []
    for spec in args.run:
        parts = spec.split("=", 3)
        if len(parts) != 4:
            raise SystemExit("--run must be name=path=scope=claim_status")
        name, path, scope, claim_status = parts
        summaries.append(summarize_run(name, Path(path), scope=scope, claim_status=claim_status, extra_notes=tuple(notes_by_name.get(name, ()))))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(summaries), encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
