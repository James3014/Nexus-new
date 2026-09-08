#!/usr/bin/env python3
"""Read-only CLI entry point for the bounded writer-transition service.

The CLI has no authority or fixture switch.  APPLY remains denied until the
source-owned authority/collector surfaces resolve every receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.contracts.state_owner_transition import (
    Operation,
    TransitionValidationError,
    WriterTransitionRequest,
)
from nexus.orchestrator.unified_mcp_gateway import build_source_owned_transition_service


def cohort_status(coordinator: object) -> object:
    """Delegate status to an already-loaded F coordinator.

    This module is a CLI adapter, not an activation authority.  It therefore
    refuses request-selected roots/state and does not infer cohort status from
    one-root transition receipts.
    """
    try:
        from nexus.orchestrator.writer_activation_cohort import (
            WriterActivationCohort,
            status_loaded_cohort,
        )
    except ImportError as exc:  # pragma: no cover - dependency is source-owned
        raise TransitionValidationError("F coordinator unavailable") from exc
    if not isinstance(coordinator, WriterActivationCohort):
        raise TransitionValidationError("source-owned F coordinator required")
    result = status_loaded_cohort(coordinator)
    # ACTIVE is a physical claim.  Re-read it through F's explicit
    # non-mutating reconciliation seam so stale generation/manifest bytes
    # cannot be projected as current status.
    if getattr(result, "state", None) == "ACTIVE":
        readonly = getattr(coordinator, "reconcile_read_only", None)
        if not callable(readonly):
            raise TransitionValidationError("F read-only physical reconciliation unavailable")
        return readonly()
    return result


def cohort_reconcile(coordinator: object) -> object:
    """Delegate restart/lost-ACK recovery to F in the same loaded process."""
    try:
        from nexus.orchestrator.writer_activation_cohort import (
            WriterActivationCohort,
            reconcile_loaded_cohort,
        )
    except ImportError as exc:  # pragma: no cover - dependency is source-owned
        raise TransitionValidationError("F coordinator unavailable") from exc
    if not isinstance(coordinator, WriterActivationCohort):
        raise TransitionValidationError("source-owned F coordinator required")
    return reconcile_loaded_cohort(coordinator)


def _loaded_cohort_from_source() -> object:
    """Resolve the current coordinator through F's source-owned bridge."""
    try:
        from nexus.orchestrator.writer_activation_cohort import (
            get_loaded_writer_activation_cohort,
        )
    except ImportError as exc:  # pragma: no cover - source dependency
        raise TransitionValidationError("source-owned loaded F coordinator unavailable") from exc
    coordinator = get_loaded_writer_activation_cohort()
    if coordinator is None:
        raise TransitionValidationError("source-owned loaded F coordinator unavailable")
    return coordinator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path)
    cohort_mode = parser.add_mutually_exclusive_group()
    cohort_mode.add_argument("--cohort-status", action="store_true")
    cohort_mode.add_argument("--cohort-reconcile", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="perform APPLY only when the strict request operation is APPLY",
    )
    mode.add_argument(
        "--reconcile",
        action="store_true",
        help="perform RECONCILE only when the strict request operation is RECONCILE",
    )
    args = parser.parse_args(argv)
    if args.cohort_status or args.cohort_reconcile:
        if args.apply or args.reconcile:
            parser.error("cohort operations cannot be combined with transition operation flags")
        if args.request is not None:
            parser.error("cohort operations do not accept a request/path selector")
        try:
            coordinator = _loaded_cohort_from_source()
            result = (
                cohort_status(coordinator) if args.cohort_status else cohort_reconcile(coordinator)
            )
            payload = result.to_dict() if hasattr(result, "to_dict") else result
            if not isinstance(payload, dict):
                raise TransitionValidationError("source-owned cohort receipt malformed")
            print(json.dumps(payload, sort_keys=True))
            return (
                0
                if payload.get("state")
                in {"HOLDING", "APPLYING", "REACQUIRING", "ACTIVE", "RELEASED"}
                else 2
            )
        except Exception as exc:
            parser.error(str(exc))
    if args.request is None:
        parser.error("--request is required unless a cohort operation is selected")
    try:
        raw = json.loads(args.request.read_text(encoding="utf-8"))
        request = WriterTransitionRequest.from_mapping(raw)
    except (OSError, ValueError, TypeError, TransitionValidationError) as exc:
        parser.error(f"invalid strict transition request: {exc}")

    # PRELIGHT is the CLI default, even when a request carries APPLY or
    # RECONCILE.  A write/recovery operation requires both the strict request
    # operation and an explicit operator flag.
    if args.apply:
        if request.operation is not Operation.APPLY:
            parser.error("--apply requires request.operation=APPLY")
        operation = "apply"
    elif args.reconcile:
        if request.operation is not Operation.RECONCILE:
            parser.error("--reconcile requires request.operation=RECONCILE")
        operation = "reconcile"
    else:
        operation = "preflight"

    service = build_source_owned_transition_service()
    receipt = getattr(service, operation)(request)
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0 if receipt.state.value in {"PREFLIGHT_READY", "COMMITTED", "RECONCILED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
