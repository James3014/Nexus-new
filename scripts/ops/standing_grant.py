#!/usr/bin/env python3
"""Operator CLI for the canonical machine-local standing-grant receipt.

This CLI is a carrier/operator surface only. It never selects a route, grants
new actions implicitly, or bypasses the canonical standing-grant evaluator.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.autonomy_goal import (  # noqa: E402
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.orchestrator.standing_grant_store import (  # noqa: E402
    StandingGrantReceipt,
    StandingGrantReceiptError,
    inspect_standing_grant_receipt,
    load_standing_grant_receipt,
    write_standing_grant_receipt,
)


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include timezone")
    return parsed


def _action(value: str) -> AutonomyActionClass:
    try:
        return AutonomyActionClass(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in AutonomyActionClass)
        raise argparse.ArgumentTypeError(
            f"unknown action {value!r}; choose one of: {allowed}"
        ) from exc


def _print(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _context_from_issue(args: argparse.Namespace) -> StandingGrantContext:
    return StandingGrantContext.issue(
        owner_id=args.owner_id,
        coordinator_id=args.coordinator_id,
        repository=RepositoryIdentity(
            repository_id=args.repository_id,
            canonical_remote=args.canonical_remote,
        ),
        thread_id=args.coordination_scope_id,
        goal_id=args.goal_id,
        allowed_actions=tuple(sorted(set(args.action), key=lambda action: action.value)),
        issued_at=args.issued_at,
        expires_at=args.expires_at,
    )


def _issue(args: argparse.Namespace) -> int:
    context = _context_from_issue(args)
    receipt = StandingGrantReceipt.issue(grant_id=args.grant_id, context=context)
    write_standing_grant_receipt(receipt)
    _print({"status": "ISSUED", "grant_id": receipt.grant_id, "receipt_hash": receipt.receipt_hash})
    return 0


def _renew(args: argparse.Namespace) -> int:
    current = load_standing_grant_receipt(now=args.requested_at)
    if current is None:
        raise StandingGrantReceiptError("RECEIPT_MISSING")
    old = current.context
    context = StandingGrantContext.issue(
        owner_id=old.owner_id,
        coordinator_id=old.coordinator_id,
        repository=old.repository,
        thread_id=old.thread_id,
        goal_id=old.goal_id,
        allowed_actions=old.allowed_actions,
        issued_at=args.issued_at,
        expires_at=args.expires_at,
    )
    receipt = StandingGrantReceipt.issue(
        grant_id=args.grant_id,
        context=context,
        supersedes_grant_hash=current.receipt_hash,
    )
    write_standing_grant_receipt(receipt, expected_receipt_hash=current.receipt_hash)
    _print({
        "status": "RENEWED",
        "grant_id": receipt.grant_id,
        "receipt_hash": receipt.receipt_hash,
        "supersedes_grant_hash": current.receipt_hash,
    })
    return 0


def _revoke(args: argparse.Namespace) -> int:
    current = load_standing_grant_receipt(now=args.requested_at)
    if current is None:
        raise StandingGrantReceiptError("RECEIPT_MISSING")
    old = current.context
    context = StandingGrantContext.issue(
        owner_id=old.owner_id,
        coordinator_id=old.coordinator_id,
        repository=old.repository,
        thread_id=old.thread_id,
        goal_id=old.goal_id,
        allowed_actions=old.allowed_actions,
        issued_at=old.issued_at,
        expires_at=old.expires_at,
        revoked_at=args.revoked_at,
        revocation_reason=args.reason,
    )
    receipt = StandingGrantReceipt.issue(
        grant_id=args.grant_id,
        context=context,
        supersedes_grant_hash=current.receipt_hash,
    )
    write_standing_grant_receipt(receipt, expected_receipt_hash=current.receipt_hash)
    _print({
        "status": "REVOKED",
        "grant_id": receipt.grant_id,
        "receipt_hash": receipt.receipt_hash,
        "supersedes_grant_hash": current.receipt_hash,
    })
    return 0


def _inspect(args: argparse.Namespace) -> int:
    result = inspect_standing_grant_receipt(now=args.requested_at)
    _print(result)
    return 0 if result["status"] == "VALID" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="inspect canonical standing-grant status")
    inspect_parser.add_argument("--requested-at", type=_time, default=None)
    inspect_parser.set_defaults(handler=_inspect)

    issue_parser = commands.add_parser("issue", help="issue a new canonical standing grant")
    issue_parser.add_argument("--grant-id", required=True)
    issue_parser.add_argument("--owner-id", required=True)
    issue_parser.add_argument("--coordinator-id", required=True)
    issue_parser.add_argument("--repository-id", required=True)
    issue_parser.add_argument("--canonical-remote", required=True)
    issue_parser.add_argument("--coordination-scope-id", required=True)
    issue_parser.add_argument("--goal-id", required=True)
    issue_parser.add_argument("--action", action="append", type=_action, required=True)
    issue_parser.add_argument("--issued-at", type=_time, required=True)
    issue_parser.add_argument("--expires-at", type=_time, required=True)
    issue_parser.set_defaults(handler=_issue)

    renew_parser = commands.add_parser("renew", help="renew without widening identity/actions")
    renew_parser.add_argument("--grant-id", required=True)
    renew_parser.add_argument("--requested-at", type=_time, required=True)
    renew_parser.add_argument("--issued-at", type=_time, required=True)
    renew_parser.add_argument("--expires-at", type=_time, required=True)
    renew_parser.set_defaults(handler=_renew)

    revoke_parser = commands.add_parser("revoke", help="revoke the current grant with CAS")
    revoke_parser.add_argument("--grant-id", required=True)
    revoke_parser.add_argument("--requested-at", type=_time, required=True)
    revoke_parser.add_argument("--revoked-at", type=_time, required=True)
    revoke_parser.add_argument("--reason", required=True)
    revoke_parser.set_defaults(handler=_revoke)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (StandingGrantReceiptError, ValueError, TypeError) as exc:
        _print({"status": "ERROR", "reason": str(exc) or type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
