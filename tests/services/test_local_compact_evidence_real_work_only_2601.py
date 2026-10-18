"""#2601: the Local assist evidence view counts only entries that did real work.

Same rule as #2596 (Online with_nexus lineage) and nexus-runtime#232: a row that
claims success but is a stub / skipped / not REAL_INVOKED never has its evidence
ids or consumer payload counted as consumed.
"""

from __future__ import annotations

from typing import Any

from nexus.services.local_assist_service import build_local_compact_evidence

CAP = "memory"


def _entry(status: str, ref: str, **extra: Any) -> dict[str, Any]:
    real = status == "REAL_INVOKED"
    row = {
        "name": CAP,
        "status": status,
        "success": real,
        "invoked_real": real,
        "invoked_stub": status == "STUB_INVOKED",
        "skipped": status == "SKIPPED",
        "evidence_ids": [ref],
        "physical_callable": f"capability_executor_registry:{CAP}",
    }
    row.update(extra)
    return row


def _payload() -> dict[str, Any]:
    return {
        "capability": CAP,
        "payload_hash": "c" * 64,
        "fields": {"hits": 1},
        "markers": [f"{CAP}:payload"],
    }


def _view(*entries: dict[str, Any]) -> dict[str, Any]:
    bundle = {
        "bundle_hash": "a" * 64,
        "baseline_hash": "b" * 64,
        "task_id": "local-2601",
        "selected_capabilities": [CAP],
        "evidence_ids": [i for e in entries for i in e["evidence_ids"]],
        "entries": list(entries),
    }
    return build_local_compact_evidence(bundle=bundle, selected_local_capabilities=[CAP])


def test_stub_claiming_success_is_not_consumed() -> None:
    view = _view(
        _entry("STUB_INVOKED", "ev_memory_stub", success=True, consumer_payload=_payload())
    )
    assert view["consumed_evidence_ids"] == []
    assert view["consumed_capability_payloads"] == []
    assert view["capability_payload_consumed"] is False
    assert view["prompt_section"] == ""


def test_skipped_claiming_success_is_not_consumed() -> None:
    view = _view(_entry("SKIPPED", "ev_memory_skip", success=True))
    assert view["consumed_evidence_ids"] == []


def test_failed_status_claiming_invoked_real_is_not_consumed() -> None:
    view = _view(_entry("INVOKED_NOT_SUCCESS", "ev_memory_failed", invoked_real=True))
    assert view["consumed_evidence_ids"] == []


def test_real_entry_is_still_consumed() -> None:
    view = _view(_entry("REAL_INVOKED", "ev_memory_real", consumer_payload=_payload()))
    assert view["consumed_evidence_ids"] == ["ev_memory_real"]
    assert view["consumed_capability_payloads"]
