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
    bundle_schema: str
    bundle_gate: str
    markdown_gate: str
    disclosure_status: str
    manifest_hash: str
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


def _bundle_gate(run_dir: Path) -> tuple[str | None, tuple[str, ...], str, str, str]:
    path = run_dir / "evidence_bundle.json"
    if not path.exists():
        return None, (), "", "", ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    gate = payload.get("public_claim_gate") or {}
    disclosure = payload.get("public_disclosure_manifest") or {}
    manifest = payload.get("task_manifest") or {}
    failures = gate.get("failures") or ()
    return (
        gate.get("verdict"),
        tuple(str(item) for item in failures),
        str(payload.get("schema") or ""),
        str(disclosure.get("status") or ""),
        str(manifest.get("sha256") or ""),
    )


def summarize_run(name: str, run_dir: Path, *, scope: str, claim_status: str, extra_notes: tuple[str, ...] = ()) -> RunSummary:
    bare_rows = _load_jsonl(_first_jsonl(run_dir, "without_nexus"))
    nexus_rows = _load_jsonl(_first_jsonl(run_dir, "with_nexus"))
    markdown_gate, markdown_failures = _markdown_gate(run_dir)
    bundle_gate, bundle_failures, schema, disclosure_status, manifest_hash = _bundle_gate(run_dir)
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
        bundle_schema=schema,
        bundle_gate=bundle_gate or "",
        markdown_gate=markdown_gate or "",
        disclosure_status=disclosure_status,
        manifest_hash=manifest_hash,
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
    lines.extend(["", "## Final Report Gate", ""])
    failures = final_report_failures(summaries)
    lines.append(f"- Final gate: {'PASS' if not failures else 'FAIL'}")
    lines.append(f"- Final gate failures: {', '.join(failures) if failures else 'none'}")
    lines.append("")
    return "\n".join(lines)


def final_report_failures(summaries: list[RunSummary], *, expected_models: tuple[str, ...] = ()) -> list[str]:
    failures: list[str] = []
    by_name = {item.name: item for item in summaries}
    for model in expected_models:
        if model not in by_name:
            failures.append(f"model_missing:{model}")
    if summaries:
        scopes = {item.scope for item in summaries}
        if len(scopes) != 1:
            failures.append("scope_mismatch")
        manifest_hashes = {item.manifest_hash for item in summaries if item.manifest_hash}
        if len(manifest_hashes) != 1:
            failures.append("manifest_hash_mismatch")
    for item in summaries:
        if item.bundle_schema != "nexus_public_benchmark_evidence_bundle_v2":
            failures.append(f"{item.name}:bundle_schema_not_v2")
        if item.bundle_gate != "PASS" or item.markdown_gate != "PASS":
            failures.append(f"{item.name}:public_gate_not_pass")
        if item.disclosure_status not in {"", "PASS"}:
            failures.append(f"{item.name}:disclosure_not_pass")
        if item.bare.rows != item.nexus.rows or item.bare.eligible != item.bare.rows or item.nexus.eligible != item.nexus.rows:
            failures.append(f"{item.name}:eligibility_incomplete")
    return sorted(set(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Nexus multi-model value comparison from benchmark artifacts.")
    parser.add_argument("--run", action="append", default=[], help="name=path=scope=claim_status")
    parser.add_argument("--note", action="append", default=[], help="name=note; can be supplied multiple times")
    parser.add_argument(
        "--require-final-model",
        action="append",
        default=[],
        help="Require a model name to be present and final-gate eligible. Can be repeated.",
    )
    parser.add_argument("--fail-on-final-gate", action="store_true")
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
    failures = final_report_failures(summaries, expected_models=tuple(args.require_final_model))
    if args.fail_on_final_gate and failures:
        print("final_report_gate=FAIL " + ",".join(failures))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
