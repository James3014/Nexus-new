#!/usr/bin/env python3
"""Draft, assemble and check Owner-signed grants for agent PRs (#1750 phase 2).

Typical flow on the Owner's Mac:

    python scripts/ops/owner_attestation.py draft --agent nexus-agent-bot \\
        --issue 1750 --path 'nexus/orchestrator/**' --hours 24 --out grant.json
    owner-signer sign grant.json > grant.sig          # Touch ID prompt
    python scripts/ops/owner_attestation.py assemble --payload grant.json \\
        --signature grant.sig --public-key owner.pem   # prints the PR marker

The payload file holds the exact bytes that are signed; the signer shows a
summary parsed from those same bytes, and the trusted merge-lane gate verifies
them against the public key pinned on the base branch.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.trusted_merge_lane_gate import (  # noqa: E402
    ATTESTATION_MAX_LIFETIME,
    ATTESTATION_MAX_PATH_LENGTH,
    ATTESTATION_MAX_PATHS,
    ATTESTATION_PROTECTED_PATTERNS,
    ATTESTATION_SCHEMA,
    LaneBindingError,
    _glob_regex,
    _path_matches,
    canonical_attestation_bytes,
    render_attestation,
    signing_key_id,
    verify_p256_signature,
)

DEFAULT_REPOSITORY = "James3014/Nexus-new"


def _draft(args: argparse.Namespace) -> int:
    if len(set(args.path)) > ATTESTATION_MAX_PATHS:
        raise SystemExit(f"at most {ATTESTATION_MAX_PATHS} paths per grant")
    for pattern in args.path:
        _glob_regex(pattern)
        if len(pattern) > ATTESTATION_MAX_PATH_LENGTH or any(
            c in pattern.split("/", 1)[0] for c in "*?"
        ):
            raise SystemExit(f"path {pattern!r} is too broad or too long; name a directory first")
        if _path_matches(pattern, ATTESTATION_PROTECTED_PATTERNS):
            raise SystemExit(f"path {pattern!r} is protected and can never be granted")
    lifetime = timedelta(hours=args.hours)
    if lifetime <= timedelta(0) or lifetime > ATTESTATION_MAX_LIFETIME:
        raise SystemExit(
            f"--hours must be between 1 and {int(ATTESTATION_MAX_LIFETIME.total_seconds() // 3600)}"
        )
    issued_at = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "repository": args.repository,
        "owner_id": args.repository.split("/", 1)[0],
        "agent_login": args.agent,
        "issue_number": args.issue,
        "allowed_actions": sorted(set(args.action)),
        "allowed_paths": sorted(set(args.path)),
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + lifetime).isoformat(),
        "nonce": f"n-{secrets.token_hex(8)}",
    }
    Path(args.out).write_bytes(canonical_attestation_bytes(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _assemble(args: argparse.Namespace) -> int:
    raw = Path(args.payload).read_bytes()
    payload = json.loads(raw)
    if canonical_attestation_bytes(payload) != raw:
        raise SystemExit("payload file is not in canonical form; re-run draft")
    signature = Path(args.signature).read_text(encoding="ascii").strip()
    pem = Path(args.public_key).read_text(encoding="ascii")
    if not verify_p256_signature(pem, raw, base64.b64decode(signature, validate=True)):
        raise SystemExit("signature does not verify against the given public key")
    envelope = {"payload": payload, "key_id": signing_key_id(pem), "signature": signature}
    print(render_attestation(envelope))
    return 0


def _pin(args: argparse.Namespace) -> int:
    pem = Path(args.public_key).read_text(encoding="ascii")
    print(json.dumps({"key_id": signing_key_id(pem), "public_key_pem": pem}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    draft = sub.add_parser("draft", help="write the canonical payload to sign")
    draft.add_argument("--repository", default=DEFAULT_REPOSITORY)
    draft.add_argument("--agent", required=True, help="the agent's GitHub login")
    draft.add_argument("--issue", required=True, type=int)
    draft.add_argument(
        "--path", required=True, action="append", help="allowed path glob (repeatable)"
    )
    draft.add_argument("--action", action="append", default=["GITHUB_MERGE"])
    draft.add_argument("--hours", type=int, default=24)
    draft.add_argument("--out", required=True)

    assemble = sub.add_parser("assemble", help="verify a signature and print the PR marker")
    assemble.add_argument("--payload", required=True)
    assemble.add_argument(
        "--signature", required=True, help="file holding the base64 DER signature"
    )
    assemble.add_argument("--public-key", required=True, help="PEM public key")

    pin = sub.add_parser("pin", help="print the governance/owner-signing-keys.json entry for a key")
    pin.add_argument("--public-key", required=True)

    args = parser.parse_args(argv)
    try:
        return {"draft": _draft, "assemble": _assemble, "pin": _pin}[args.command](args)
    except LaneBindingError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
