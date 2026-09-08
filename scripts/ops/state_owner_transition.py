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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
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
