"""Local Qwen Evidence Gate: verify evidence bundles claim local model involvement."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class LocalQwenEvidenceCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class LocalQwenEvidenceResult:
    checks: list[LocalQwenEvidenceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if not c.passed]


def _extract_row_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extract fields from a single row/bundle for verification."""
    telemetry = row.get("telemetry") or row.get("capability_telemetry") or {}
    receipt = row.get("capability_receipts", [])
    if isinstance(receipt, list) and receipt:
        first_receipt = receipt[0] if isinstance(receipt[0], dict) else {}
        receipt_tel = first_receipt.get("telemetries") or {}
    else:
        receipt_tel = {}

    merged_tel = {**telemetry, **receipt_tel}

    return {
        "provider": row.get("provider") or merged_tel.get("provider") or "",
        "model_name": row.get("model_name") or row.get("ollama_model_name") or merged_tel.get("model_name") or "",
        "model_calls": int(merged_tel.get("model_calls") or row.get("model_calls") or 0),
        "provider_token_count": int(merged_tel.get("provider_token_count") or row.get("provider_token_count") or 0),
        "hidden_verifier": bool(merged_tel.get("hidden_verifier") or row.get("hidden_verifier")),
        "deterministic_fallback": bool(merged_tel.get("deterministic_fallback") or row.get("deterministic_fallback")),
        "public_gate_status": row.get("public_gate_status") or merged_tel.get("public_gate_status") or "",
        "source_origin": row.get("source_origin") or merged_tel.get("source_origin") or "",
    }


def verify_local_qwen_evidence(row: Mapping[str, Any]) -> LocalQwenEvidenceResult:
    """Verify a single evidence bundle row qualifies as local Qwen evidence."""
    fields = _extract_row_fields(row)
    checks: list[LocalQwenEvidenceCheck] = []

    checks.append(LocalQwenEvidenceCheck(
        name="provider_is_ollama",
        passed=fields["provider"].lower() == "ollama",
        detail=f"provider={fields['provider']!r}, expected 'ollama'",
    ))

    checks.append(LocalQwenEvidenceCheck(
        name="model_name_present",
        passed=bool(fields["model_name"]),
        detail=f"model_name={fields['model_name']!r}",
    ))

    checks.append(LocalQwenEvidenceCheck(
        name="model_calls_positive",
        passed=fields["model_calls"] > 0,
        detail=f"model_calls={fields['model_calls']}",
    ))

    checks.append(LocalQwenEvidenceCheck(
        name="provider_token_measured",
        passed=fields["provider_token_count"] > 0,
        detail=f"provider_token_count={fields['provider_token_count']}",
    ))

    checks.append(LocalQwenEvidenceCheck(
        name="hidden_verifier_enabled",
        passed=fields["hidden_verifier"],
        detail=f"hidden_verifier={fields['hidden_verifier']}",
    ))

    checks.append(LocalQwenEvidenceCheck(
        name="no_deterministic_fallback",
        passed=not fields["deterministic_fallback"],
        detail=f"deterministic_fallback={fields['deterministic_fallback']}",
    ))

    if fields["public_gate_status"] and fields["public_gate_status"] != "PASS":
        checks.append(LocalQwenEvidenceCheck(
            name="public_gate_status",
            passed=False,
            detail=f"public_gate_status={fields['public_gate_status']!r}, marked non-claim",
        ))

    if fields["source_origin"].lower() in ("gemini", "gpt", "cloud"):
        checks.append(LocalQwenEvidenceCheck(
            name="not_gemini_locked",
            passed=False,
            detail=f"source_origin={fields['source_origin']!r}, marked non-claim",
        ))

    return LocalQwenEvidenceResult(checks=checks)


def audit_evidence_bundle(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Audit a list of evidence bundle rows and produce a summary."""
    results = []
    for i, row in enumerate(rows):
        result = verify_local_qwen_evidence(row)
        results.append({
            "row_index": i,
            "passed": result.passed,
            "failures": result.failures,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    return {
        "total_rows": total,
        "passed": passed,
        "failed": failed,
        "all_passed": failed == 0,
        "details": results,
    }
