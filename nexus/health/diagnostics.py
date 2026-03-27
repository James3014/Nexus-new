from __future__ import annotations

from nexus.core.state_contracts import NexusState

from .models import HealthDiagnosis, HealthSnapshot


class HealthDiagnostics:
    @staticmethod
    def diagnose(state: NexusState, snapshot: HealthSnapshot) -> HealthDiagnosis:
        if snapshot.status == "HEALTHY":
            return HealthDiagnosis(kind="healthy", summary="Health snapshot is healthy.")

        reasons = list(snapshot.reasons)
        signature_based = HealthDiagnostics._diagnose_from_signature(state, reasons)
        if signature_based is not None:
            return signature_based

        explicit_kind = state.metadata.get("health_error_kind")
        if explicit_kind in {
            "environment_failure",
            "research_failure",
            "repair_failure",
            "audit_failure",
            "evidence_failure",
        }:
            return HealthDiagnosis(
                kind=explicit_kind,
                summary=f"Explicit health failure marker: {explicit_kind}.",
                reasons=reasons or [explicit_kind],
            )

        review_status = str(state.metadata.get("last_review_status", "")).upper()
        if review_status in {"REJECTED", "FAILED"}:
            audit_score = snapshot.phase_scores.get("A")
            repair_score = snapshot.phase_scores.get("R")
            if audit_score and audit_score.completeness > 0 and audit_score.score <= 50:
                return HealthDiagnosis(
                    kind="audit_failure",
                    target_phase="A",
                    summary="Audit phase rejected the repair output.",
                    reasons=reasons or ["audit_rejected"],
                )
            return HealthDiagnosis(
                kind="repair_failure",
                target_phase="R",
                summary="Repair attempts completed but failed review.",
                reasons=reasons or ["repair_rejected"],
            )

        x_score = snapshot.phase_scores.get("X")
        if x_score and x_score.completeness > 0 and x_score.score < 50:
            return HealthDiagnosis(
                kind="research_failure",
                target_phase="X",
                summary="Research phase is the dominant weak point.",
                reasons=reasons or ["research_low_signal"],
            )

        if snapshot.confidence < 0.35 and (not reasons or set(reasons) <= {"no_health_signals"}):
            return HealthDiagnosis(
                kind="insufficient_signals",
                summary="Health signals are incomplete; the system cannot diagnose confidently.",
                reasons=reasons or ["signal_confidence_low"],
            )

        if "missing_token_capture" in reasons:
            return HealthDiagnosis(
                kind="evidence_failure",
                summary="Execution evidence is incomplete or token capture is missing.",
                reasons=reasons or ["evidence_missing"],
            )

        return HealthDiagnosis(
            kind="environment_failure",
            summary="Environment or orchestration layer is degraded.",
            reasons=reasons or ["environment_degraded"],
        )

    @staticmethod
    def _diagnose_from_signature(state: NexusState, reasons: list[str]) -> HealthDiagnosis | None:
        signatures = state.metadata.get("fault_signatures") or []
        if not isinstance(signatures, list) or not signatures:
            return None

        first = signatures[0] if isinstance(signatures[0], dict) else {}
        error_type = str(first.get("error_type", "")).strip()
        location = str(first.get("location", ""))
        fault_hash = str(first.get("hash", ""))
        signature_reason = f"fault_signature:{error_type}:{location}" if error_type else "fault_signature:detected"
        if fault_hash:
            reasons = list(reasons) + [f"fault_hash:{fault_hash[:16]}"]
        else:
            reasons = list(reasons)
        reasons.append(signature_reason)

        if error_type in {"ModuleNotFoundError", "ImportError", "FileNotFoundError"}:
            return HealthDiagnosis(
                kind="environment_failure",
                target_phase="P",
                summary="Signature indicates runtime environment dependency failure.",
                reasons=reasons,
            )
        if error_type in {"AssertionError", "TestFailure"}:
            return HealthDiagnosis(
                kind="audit_failure",
                target_phase="A",
                summary="Signature indicates failing verification or audit assertions.",
                reasons=reasons,
            )
        if error_type in {"SyntaxError", "NameError", "TypeError", "AttributeError"}:
            return HealthDiagnosis(
                kind="repair_failure",
                target_phase="R",
                summary="Signature indicates repair-layer implementation failure.",
                reasons=reasons,
            )
        return None
