"""Read-only, fail-closed Codex/GitHub history coverage receipts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any


class HistoryReceiptError(ValueError):
    """History cannot support a truthful coverage claim."""


_OUTCOMES = {"success", "failure", "timeout", "unavailable"}
_STATUSES = {"complete", "partial", "timeout", "unavailable"}
_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password|bearer)\s*[:=]")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _fail(condition: bool, message: str) -> None:
    if not condition:
        raise HistoryReceiptError(message)


def _bounded_ref(value: Any, *, limit: int = 200) -> str:
    _fail(isinstance(value, str) and bool(value), "evidence reference is required")
    _fail(len(value) <= limit, "evidence reference exceeds bound")
    _fail("\n" not in value and "\r" not in value, "evidence reference must be one line")
    _fail(not _SECRET.search(value), "evidence reference appears to contain a secret")
    return value


def _hash_ids(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _snapshot_hash(*, source: str, cutoff: str, item_ids: list[str]) -> str:
    preimage = json.dumps(
        {"source": source, "cutoff": cutoff, "item_ids": sorted(item_ids)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def collect_history(
    adapter: Any,
    *,
    source: str,
    cutoff: str,
    max_pages: int = 100,
    max_items: int = 1000,
    ref_limit: int = 200,
) -> dict[str, Any]:
    """Collect pages and per-item outcomes without mutating the transport.

    ``adapter.list_page(cursor)`` must return a mapping with ``items`` and
    ``next_cursor`` (or ``None``), and may expose ``status``/``complete``.
    ``adapter.read_item(item_id)`` must return ``outcome`` and bounded refs.
    A transport gap is represented explicitly; it is never converted to zero.
    """
    source = _bounded_ref(source)
    cutoff = _bounded_ref(cutoff)
    _fail(max_pages > 0 and max_items > 0, "collection bounds must be positive")
    list_page: Callable[[Any], Mapping[str, Any]] | None = getattr(adapter, "list_page", None)
    read_item: Callable[[str], Mapping[str, Any]] | None = getattr(adapter, "read_item", None)
    _fail(
        callable(list_page) and callable(read_item), "adapter must provide list_page and read_item"
    )

    cursor: Any = None
    pages = 0
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = 0
    status = "complete"
    transport_gap: str | None = None
    while True:
        if pages >= max_pages:
            status, transport_gap = "partial", "page_bound_exceeded"
            break
        pages += 1
        try:
            page = list_page(cursor)
        except TimeoutError:
            status, transport_gap = "timeout", "list_timeout"
            break
        except Exception as exc:  # adapters must not turn errors into empty history
            status, transport_gap = "unavailable", type(exc).__name__
            break
        _fail(isinstance(page, Mapping), "page response must be an object")
        page_status = page.get("status", "ok")
        if page_status in {"timeout", "unavailable"}:
            status, transport_gap = str(page_status), f"list_{page_status}"
            break
        if page_status == "partial":
            status, transport_gap = "partial", "list_partial"
            break
        _fail(page_status == "ok", "page status is invalid")
        raw_items = page.get("items")
        _fail(isinstance(raw_items, list), "page items are required")
        for raw in raw_items:
            _fail(isinstance(raw, Mapping), "history item must be an object")
            item_id = raw.get("id")
            _fail(isinstance(item_id, str) and bool(item_id), "history item id is required")
            item_id = _bounded_ref(item_id, limit=ref_limit)
            if item_id in seen:
                duplicate_count += 1
                status, transport_gap = "partial", "duplicate_item"
                continue
            seen.add(item_id)
            if len(items) >= max_items:
                status, transport_gap = "partial", "item_bound_exceeded"
                break
            try:
                result = read_item(item_id)
            except TimeoutError:
                result = {"outcome": "timeout", "evidence_ref": f"item:{item_id}"}
            except Exception:
                result = {"outcome": "unavailable", "evidence_ref": f"item:{item_id}"}
            _fail(isinstance(result, Mapping), f"item {item_id} outcome is missing")
            outcome = result.get("outcome")
            _fail(outcome in _OUTCOMES, f"item {item_id} has no valid outcome")
            ref = _bounded_ref(result.get("evidence_ref", f"item:{item_id}"), limit=ref_limit)
            row = {"id": item_id, "outcome": outcome, "evidence_ref": ref}
            category = _bounded_ref(result.get("category", "uncategorized"), limit=80)
            recurrence = result.get("recurrence", 1)
            interventions = result.get("human_interventions", 0)
            _fail(isinstance(recurrence, int) and recurrence >= 1, "recurrence is invalid")
            _fail(
                isinstance(interventions, int) and interventions >= 0,
                "human_interventions is invalid",
            )
            row["category"] = category
            row["recurrence"] = recurrence
            row["human_interventions"] = interventions
            items.append(row)
        if status == "partial":
            break
        next_cursor = page.get("next_cursor")
        if next_cursor is None:
            _fail(
                "complete" in page and page["complete"] is True,
                "missing pagination completion state",
            )
            break
        _fail(isinstance(next_cursor, str) and next_cursor, "pagination cursor is invalid")
        cursor = next_cursor

    counts = {
        outcome: sum(item["outcome"] == outcome for item in items) for outcome in sorted(_OUTCOMES)
    }
    returned = len(items)
    classified = sum(counts.values())
    accounting = {
        "returned_items": returned,
        "classified_items": classified,
        "successes": counts["success"],
        "failures": counts["failure"],
        "timeouts": counts["timeout"],
        "unavailable": counts["unavailable"],
        "duplicates": duplicate_count,
    }
    if status == "complete" and classified != returned:
        status, transport_gap = "partial", "unclassified_item"
    if status == "complete" and (counts["timeout"] or counts["unavailable"]):
        status, transport_gap = "partial", "item_read_incomplete"
    return {
        "schema_version": "codex-dx-history-receipt-v1",
        "source": source,
        "cutoff": cutoff,
        "status": status,
        "snapshot_hash": _snapshot_hash(
            source=source,
            cutoff=cutoff,
            item_ids=[item["id"] for item in items],
        ),
        "transport_gap": transport_gap,
        "pagination": {
            "pages": pages,
            "complete": status == "complete",
            "cursor_hash": _hash_ids([str(cursor)] if cursor else []),
        },
        "items": items,
        "accounting": accounting,
        "coverage": {"claimable": status == "complete", "ceiling": "coverage-bounded taxonomy"},
    }


def validate_history_receipt(receipt: Mapping[str, Any]) -> None:
    """Reject receipts that could imply complete zero coverage dishonestly."""
    _fail(isinstance(receipt, Mapping), "receipt must be an object")
    _fail(
        receipt.get("schema_version") == "codex-dx-history-receipt-v1", "unsupported schema version"
    )
    _fail(receipt.get("status") in _STATUSES, "invalid status")
    _bounded_ref(receipt.get("source"))
    _bounded_ref(receipt.get("cutoff"))
    _fail(
        isinstance(receipt.get("snapshot_hash"), str)
        and _SHA256.fullmatch(receipt["snapshot_hash"]) is not None,
        "snapshot hash is required",
    )
    accounting = receipt.get("accounting")
    _fail(isinstance(accounting, Mapping), "accounting is required")
    accounting_keys = (
        "returned_items",
        "classified_items",
        "successes",
        "failures",
        "timeouts",
        "unavailable",
        "duplicates",
    )
    _fail(
        all(
            isinstance(accounting.get(key), int)
            and not isinstance(accounting.get(key), bool)
            and accounting[key] >= 0
            for key in accounting_keys
        ),
        "accounting values must be nonnegative integers",
    )
    _fail(
        accounting.get("returned_items") == accounting.get("classified_items"),
        "denominator accounting mismatch",
    )
    outcome_total = sum(
        int(accounting.get(key, -1)) for key in ("successes", "failures", "timeouts", "unavailable")
    )
    _fail(outcome_total == accounting.get("classified_items"), "outcome accounting mismatch")
    items = receipt.get("items")
    _fail(isinstance(items, list) and len(items) <= 1000, "items are required and bounded")
    _fail(len(items) == accounting.get("returned_items"), "item denominator mismatch")
    required_item_keys = {
        "id",
        "outcome",
        "category",
        "recurrence",
        "human_interventions",
        "evidence_ref",
    }
    for item in items:
        _fail(
            isinstance(item, Mapping) and set(item) == required_item_keys,
            "history item shape is invalid",
        )
        _bounded_ref(item["id"])
        _bounded_ref(item["evidence_ref"])
        _fail(item["outcome"] in _OUTCOMES, "history item outcome is invalid")
        _bounded_ref(item["category"], limit=80)
        _fail(
            isinstance(item["recurrence"], int)
            and not isinstance(item["recurrence"], bool)
            and item["recurrence"] >= 1,
            "history item recurrence is invalid",
        )
        _fail(
            isinstance(item["human_interventions"], int)
            and not isinstance(item["human_interventions"], bool)
            and item["human_interventions"] >= 0,
            "history item interventions are invalid",
        )
    item_ids = [item["id"] for item in items]
    _fail(len(item_ids) == len(set(item_ids)), "item ids must be unique")
    expected_snapshot_hash = _snapshot_hash(
        source=receipt["source"],
        cutoff=receipt["cutoff"],
        item_ids=item_ids,
    )
    _fail(receipt["snapshot_hash"] == expected_snapshot_hash, "snapshot identity mismatch")
    expected_counts = {
        outcome: sum(item["outcome"] == outcome for item in items) for outcome in _OUTCOMES
    }
    _fail(accounting["successes"] == expected_counts["success"], "success accounting mismatch")
    _fail(accounting["failures"] == expected_counts["failure"], "failure accounting mismatch")
    _fail(accounting["timeouts"] == expected_counts["timeout"], "timeout accounting mismatch")
    _fail(
        accounting["unavailable"] == expected_counts["unavailable"],
        "unavailable accounting mismatch",
    )
    pagination = receipt.get("pagination")
    _fail(isinstance(pagination, Mapping), "pagination is required")
    _fail(
        set(pagination) == {"pages", "complete", "cursor_hash"},
        "pagination shape is invalid",
    )
    _fail(
        isinstance(pagination["pages"], int)
        and not isinstance(pagination["pages"], bool)
        and pagination["pages"] >= 1,
        "pagination pages are invalid",
    )
    _fail(isinstance(pagination["complete"], bool), "pagination completion is invalid")
    _fail(
        isinstance(pagination["cursor_hash"], str)
        and _SHA256.fullmatch(pagination["cursor_hash"]) is not None,
        "pagination cursor hash is invalid",
    )
    coverage = receipt.get("coverage")
    _fail(
        isinstance(coverage, Mapping) and set(coverage) == {"claimable", "ceiling"},
        "coverage is invalid",
    )
    _fail(isinstance(coverage["claimable"], bool), "coverage claimable is invalid")
    _fail(coverage["ceiling"] == "coverage-bounded taxonomy", "coverage ceiling is invalid")
    if receipt["status"] == "complete":
        _fail(receipt.get("transport_gap") is None, "complete receipt cannot have transport gap")
        _fail(coverage["claimable"] is True, "complete receipt is not claimable")
        _fail(pagination.get("complete") is True, "complete receipt has incomplete pagination")
    else:
        _bounded_ref(receipt.get("transport_gap"))
        _fail(coverage["claimable"] is False, "incomplete receipt must be non-claimable")
        _fail(pagination.get("complete") is False, "incomplete receipt has complete pagination")


# Descriptive aliases keep the collector easy to discover for benchmark callers.
collect_history_receipt = collect_history
collect_codex_dx_history = collect_history
