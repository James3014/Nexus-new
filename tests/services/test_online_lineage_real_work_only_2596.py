"""#2596: the with_nexus lineage counts only entries that did real work as consumed.

Same rule as nexus-runtime#232 / PR #233: when no bundle entry did real work (for
example a stub-only codeintel run), the lineage used to fall back to every top-level
bundle id, which also lists stub / skipped / failed entries, and reported
``capability_consumed: true`` for a stub.
"""

from __future__ import annotations

from typing import Any

from nexus.services.online_nexus_context import build_online_nexus_context

TASK = "lineage-2596"


def _entry(name: str, status: str, ref: str) -> dict[str, Any]:
    real = status == "REAL_INVOKED"
    return {
        "name": name,
        "status": status,
        "success": real,
        "invoked_real": real,
        "invoked_stub": status == "STUB_INVOKED",
        "skipped": status == "SKIPPED",
        "evidence_ids": [ref],
        "evidence_refs": [ref],
        "physical_callable": f"capability_executor_registry:{name}",
    }


def _bundle(*entries: dict[str, Any]) -> dict[str, Any]:
    ids = [i for e in entries for i in e["evidence_ids"]]
    return {
        "schema": "nexus.capability_evidence_bundle.v1",
        "bundle_hash": "a" * 64,
        "baseline_hash": "b" * 64,
        "task_id": TASK,
        "selected_capabilities": [e["name"] for e in entries],
        "evidence_ids": ids,
        "entries": list(entries),
    }


def _lineage(bundle: dict[str, Any]) -> dict[str, Any]:
    ctx = build_online_nexus_context(
        task_statement="x",
        task_id=TASK,
        plan={
            "capability_evidence_bundle": bundle,
            "selected_capabilities": bundle["selected_capabilities"],
        },
        capability_evidence_bundle=bundle,
    )
    return ctx.lineage


def test_stub_only_bundle_consumes_nothing() -> None:
    lineage = _lineage(_bundle(_entry("codeintel", "STUB_INVOKED", "ev_codeintel_stub")))
    assert lineage["consumed_evidence_ids"] == []
    assert lineage["capability_consumed"] is False


def test_skipped_and_failed_entries_consume_nothing() -> None:
    lineage = _lineage(
        _bundle(
            _entry("memory", "SKIPPED", "ev_memory_skip"),
            _entry("pregate", "INVOKED_NOT_SUCCESS", "ev_pregate_failed"),
        )
    )
    assert lineage["consumed_evidence_ids"] == []
    assert lineage["capability_consumed"] is False


def test_entry_claiming_success_with_stub_status_is_not_consumed() -> None:
    bad = {**_entry("codeintel", "STUB_INVOKED", "ev_codeintel_stub"), "success": True}
    lineage = _lineage(_bundle(bad))
    assert lineage["consumed_evidence_ids"] == []


def test_real_entry_is_consumed_and_stub_is_not() -> None:
    lineage = _lineage(
        _bundle(
            _entry("codeintel", "REAL_INVOKED", "ev_codeintel_real"),
            _entry("memory", "STUB_INVOKED", "ev_memory_stub"),
        )
    )
    assert lineage["consumed_evidence_ids"] == ["ev_codeintel_real"]
    assert lineage["capability_consumed"] is True
