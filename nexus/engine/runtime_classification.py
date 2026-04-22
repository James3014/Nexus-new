from __future__ import annotations


def classify_semantic(semantic_status: str, retryable: bool, blocker_type: str) -> str:
    normalized_status = str(semantic_status or "").strip().upper()
    normalized_blocker = str(blocker_type or "").strip().lower()

    if normalized_status == "VERIFIED":
        return "verified_pass"
    if normalized_status == "BLOCKED" or normalized_blocker == "governance":
        return "governance_state_block"
    if normalized_status == "UNVERIFIED" and bool(retryable):
        return "runtime_defect"
    if normalized_status == "REJECTED":
        return "hallucination_rejected"
    return "runtime_defect"
