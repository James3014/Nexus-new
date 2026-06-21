"""B1-D: Native Validation/Receipt Binding — Bind local_heal results to Nexus validation path."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationReceipt:
    route_id: str
    evidence_packet_id: str
    model_role: str
    model_name: str
    candidate_id: str
    parser_status: str
    patch_apply_status: str
    verifier_status: str
    sandbox_status: str
    compliance_status: str
    claim_status: str
    acceptance_status: str
    final_status: str
    authority_trace: list[str]


class NativeValidationBridge:
    """Bind local_heal result classification to Nexus validation/receipt path."""

    def build_receipt(
        self,
        *,
        route_id: str,
        evidence_packet_id: str,
        model_role: str,
        model_name: str,
        candidate_id: str,
        parser_ok: bool,
        patch_applied: bool,
        verifier_ok: bool,
        sandbox_ok: bool | None = None,
        compliance_ok: bool = True,
        authority_trace: list[str] | None = None,
    ) -> ValidationReceipt:
        parser_status = "pass" if parser_ok else "fail"
        patch_apply_status = "applied" if patch_applied else "not_applied"
        verifier_status = "pass" if verifier_ok else "fail"
        sandbox_status = "pass" if sandbox_ok else ("unavailable" if sandbox_ok is None else "fail")
        compliance_status = "pass" if compliance_ok else "fail"

        # Claim/Acceptance: only if verifier passes
        claim_status = "internal_only" if verifier_ok else "not_accepted"
        acceptance_status = "internal_only" if verifier_ok else "not_accepted"

        # Final status
        if verifier_ok and compliance_ok:
            final_status = "VERIFIER_PASS_INTERNAL_ONLY"
        elif not parser_ok:
            final_status = "PARSER_REJECTED"
        elif not patch_applied:
            final_status = "PATCH_APPLY_FAILED"
        elif not verifier_ok:
            final_status = "VERIFIER_FAIL"
        else:
            final_status = "UNKNOWN"

        trace = authority_trace or []
        trace.append(f"NativeValidationBridge:verifier={verifier_status}:final={final_status}")

        return ValidationReceipt(
            route_id=route_id,
            evidence_packet_id=evidence_packet_id,
            model_role=model_role,
            model_name=model_name,
            candidate_id=candidate_id,
            parser_status=parser_status,
            patch_apply_status=patch_apply_status,
            verifier_status=verifier_status,
            sandbox_status=sandbox_status,
            compliance_status=compliance_status,
            claim_status=claim_status,
            acceptance_status=acceptance_status,
            final_status=final_status,
            authority_trace=trace,
        )
