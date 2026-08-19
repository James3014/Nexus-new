import json
from pathlib import Path

import pytest

from scripts.bench.codex_dx_history import (
    HistoryReceiptError,
    collect_history,
    validate_history_receipt,
)


class Adapter:
    def __init__(self, pages, outcomes=None):
        self.pages = pages
        self.outcomes = outcomes or {}

    def list_page(self, cursor):
        return self.pages[0] if cursor is None else self.pages[1]

    def read_item(self, item_id):
        return self.outcomes.get(
            item_id,
            {"outcome": "failure", "evidence_ref": f"item:{item_id}"},
        )


def test_complete_schema_and_denominator_accounting():
    receipt = collect_history(
        Adapter(
            [{"items": [{"id": "a"}], "next_cursor": None, "complete": True}],
            {"a": {"outcome": "success", "evidence_ref": "item:a"}},
        ),
        source="codex-app:list_threads",
        cutoff="2026-08-10T00:00:00Z",
    )
    assert receipt["status"] == "complete"
    assert receipt["accounting"]["returned_items"] == 1
    assert receipt["accounting"]["classified_items"] == 1
    validate_history_receipt(receipt)
    schema = json.loads(Path("docs/benchmark/codex_dx_history_receipt_v1.schema.json").read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(receipt)
    assert schema["properties"]["schema_version"]["const"] == receipt["schema_version"]
    assert schema["properties"]["status"]["enum"] == [
        "complete",
        "partial",
        "timeout",
        "unavailable",
    ]


def test_partial_pagination_duplicate_and_transport_states():
    adapter = Adapter([
        {"items": [{"id": "a"}], "next_cursor": "x"},
        {"items": [{"id": "a"}], "next_cursor": None},
    ])
    receipt = collect_history(adapter, source="github", cutoff="cutoff")
    assert receipt["status"] == "partial"
    assert receipt["transport_gap"] == "duplicate_item"
    assert receipt["coverage"]["claimable"] is False
    validate_history_receipt(receipt)


def test_timeout_and_unavailable_are_not_zero_failures():
    class TimedOut(Adapter):
        def list_page(self, cursor):
            raise TimeoutError

    class Unavailable(Adapter):
        def list_page(self, cursor):
            raise ConnectionError("transport offline")

    for adapter, status in ((TimedOut([]), "timeout"), (Unavailable([]), "unavailable")):
        receipt = collect_history(adapter, source="codex", cutoff="cutoff")
        assert receipt["status"] == status
        assert receipt["accounting"]["returned_items"] == 0
        assert receipt["accounting"]["failures"] == 0
        assert receipt["coverage"]["claimable"] is False
        validate_history_receipt(receipt)


def test_per_item_transport_gap_makes_complete_listing_nonclaimable():
    adapter = Adapter(
        [{"items": [{"id": "a"}], "next_cursor": None, "complete": True}],
        {"a": {"outcome": "timeout", "evidence_ref": "item:a"}},
    )
    receipt = collect_history(adapter, source="codex", cutoff="cutoff")
    assert receipt["status"] == "partial"
    assert receipt["transport_gap"] == "item_read_incomplete"
    assert receipt["coverage"]["claimable"] is False
    validate_history_receipt(receipt)


def test_missing_identity_and_secret_reference_fail_closed():
    with pytest.raises(HistoryReceiptError, match="evidence reference"):
        collect_history(Adapter([]), source="", cutoff="cutoff")
    adapter = Adapter(
        [{"items": [{"id": "a"}], "next_cursor": None}],
        {"a": {"outcome": "failure", "evidence_ref": "token=secret"}},
    )
    with pytest.raises(HistoryReceiptError, match="secret"):
        collect_history(adapter, source="codex", cutoff="cutoff")
    adapter = Adapter(
        [{"items": [{"id": "a"}], "next_cursor": None, "complete": True}],
        {
            "a": {
                "outcome": "failure",
                "evidence_ref": "item:a",
                "category": "token=secret",
            }
        },
    )
    with pytest.raises(HistoryReceiptError, match="secret"):
        collect_history(adapter, source="codex", cutoff="cutoff")


def test_missing_per_item_outcome_fails_closed():
    adapter = Adapter(
        [{"items": [{"id": "a"}], "next_cursor": None}],
        {"a": {"evidence_ref": "item:a"}},
    )
    with pytest.raises(HistoryReceiptError, match="valid outcome"):
        collect_history(adapter, source="codex", cutoff="cutoff")


def test_missing_pagination_completion_fails_closed():
    adapter = Adapter([{"items": [], "next_cursor": None, "complete": False}])
    with pytest.raises(HistoryReceiptError, match="pagination completion"):
        collect_history(adapter, source="codex", cutoff="cutoff")


def test_unknown_or_partial_page_status_cannot_become_complete():
    partial = Adapter([{"status": "partial", "items": []}])
    receipt = collect_history(partial, source="codex", cutoff="cutoff")
    assert receipt["status"] == "partial"
    assert receipt["transport_gap"] == "list_partial"
    with pytest.raises(HistoryReceiptError, match="page status"):
        collect_history(
            Adapter([{"status": "error", "items": [], "complete": True}]),
            source="codex",
            cutoff="cutoff",
        )


def test_item_and_page_bounds_create_partial_nonclaimable_receipts():
    page_bounded = collect_history(
        Adapter([{"items": [], "next_cursor": "more"}]),
        source="codex",
        cutoff="cutoff",
        max_pages=1,
    )
    assert page_bounded["transport_gap"] == "page_bound_exceeded"
    assert page_bounded["coverage"]["claimable"] is False

    item_bounded = collect_history(
        Adapter([{"items": [{"id": "a"}, {"id": "b"}], "next_cursor": None}]),
        source="codex",
        cutoff="cutoff",
        max_items=1,
    )
    assert item_bounded["transport_gap"] == "item_bound_exceeded"
    assert item_bounded["accounting"]["returned_items"] == 1


def test_validator_rejects_outcome_and_pagination_mismatch():
    receipt = collect_history(
        Adapter([{"items": [{"id": "a"}], "next_cursor": None, "complete": True}]),
        source="codex",
        cutoff="cutoff",
    )
    receipt["accounting"]["failures"] = 0
    with pytest.raises(HistoryReceiptError, match="outcome accounting"):
        validate_history_receipt(receipt)

    receipt = collect_history(
        Adapter([{"items": [], "next_cursor": None, "complete": True}]),
        source="codex",
        cutoff="cutoff",
    )
    receipt["pagination"]["complete"] = False
    with pytest.raises(HistoryReceiptError, match="incomplete pagination"):
        validate_history_receipt(receipt)


def test_validator_rejects_incomplete_item_and_nonmapping_coverage():
    receipt = collect_history(
        Adapter([{"items": [{"id": "a"}], "next_cursor": None, "complete": True}]),
        source="codex",
        cutoff="cutoff",
    )
    receipt["items"][0] = {"id": "a"}
    with pytest.raises(HistoryReceiptError, match="item shape"):
        validate_history_receipt(receipt)

    receipt = collect_history(
        Adapter([{"items": [], "next_cursor": None, "complete": True}]),
        source="codex",
        cutoff="cutoff",
    )
    receipt["coverage"] = "claimable"
    with pytest.raises(HistoryReceiptError, match="coverage"):
        validate_history_receipt(receipt)


def test_validator_recomputes_snapshot_identity():
    receipt = collect_history(
        Adapter([{"items": [{"id": "a"}], "next_cursor": None, "complete": True}]),
        source="codex",
        cutoff="cutoff",
    )
    receipt["source"] = "github"
    with pytest.raises(HistoryReceiptError, match="snapshot identity"):
        validate_history_receipt(receipt)


def test_snapshot_identity_uses_unambiguous_structured_preimage():
    receipt = collect_history(
        Adapter([{"items": [], "next_cursor": None, "complete": True}]),
        source="a|b",
        cutoff="c",
    )
    receipt["source"] = "a"
    receipt["cutoff"] = "b|c"
    with pytest.raises(HistoryReceiptError, match="snapshot identity"):
        validate_history_receipt(receipt)
