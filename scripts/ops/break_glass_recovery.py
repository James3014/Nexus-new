#!/usr/bin/env python3
"""Narrow operator CLI for Nexus #806 break-glass SOURCE_REPAIR evidence.

The CLI does not execute a repair. It re-reads the exact Owner activation comment
from the fixed public GitHub API endpoint, validates its immutable identity/body/
payload hashes, reads fixed Git identity/diff evidence, and advances the one-shot
durable recovery record. It exposes no arbitrary command, merge, push, reload,
release, or standing-grant action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.break_glass_recovery import (  # noqa: E402
    BreakGlassAppliedEvidence,
    BreakGlassVerificationEvidence,
    OwnerActivationEnvelope,
    owner_envelope_from_github_comment,
)
from nexus.orchestrator.break_glass_recovery import (  # noqa: E402
    BreakGlassRecoveryError,
    consume_source_repair_authority,
    inspect_attempt,
    prepare_source_repair,
    record_source_repair_applied,
    record_source_repair_verified,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _fetch_envelope(comment_id: int) -> OwnerActivationEnvelope:
    if comment_id <= 0:
        raise BreakGlassRecoveryError("COMMENT_ID_INVALID")
    url = f"https://api.github.com/repos/James3014/Nexus-new/issues/comments/{comment_id}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "nexus-break-glass-recovery/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:  # nosec B310 - fixed HTTPS host/path
            final_url = response.geturl()
            if final_url != url:
                raise BreakGlassRecoveryError("GITHUB_COMMENT_REDIRECT_REJECTED")
            raw = response.read()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise BreakGlassRecoveryError("GITHUB_COMMENT_FETCH_FAILED") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BreakGlassRecoveryError("GITHUB_COMMENT_MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise BreakGlassRecoveryError("GITHUB_COMMENT_MALFORMED")
    return owner_envelope_from_github_comment(parsed)


def _git(repo_root: Path, *args: str) -> bytes:
    if not repo_root.is_dir():
        raise BreakGlassRecoveryError("REPOSITORY_ROOT_INVALID")
    command = ["git", "-C", str(repo_root), *args]
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BreakGlassRecoveryError("GIT_EVIDENCE_READ_FAILED") from exc
    return completed.stdout


def _git_text(repo_root: Path, *args: str) -> str:
    return _git(repo_root, *args).decode("utf-8", errors="strict").strip()


def _assert_clean_repo(repo_root: Path) -> None:
    status = _git_text(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise BreakGlassRecoveryError("REPOSITORY_NOT_CLEAN")


def _physical_base(repo_root: Path) -> tuple[str, str]:
    _assert_clean_repo(repo_root)
    return (
        _git_text(repo_root, "rev-parse", "HEAD"),
        _git_text(repo_root, "rev-parse", "HEAD^{tree}"),
    )


def _repair_evidence(
    repo_root: Path, envelope: OwnerActivationEnvelope, implementer_id: str
) -> BreakGlassAppliedEvidence:
    _assert_clean_repo(repo_root)
    head = _git_text(repo_root, "rev-parse", "HEAD")
    tree = _git_text(repo_root, "rev-parse", "HEAD^{tree}")
    # Fixed ancestry check; no caller-selected refspec or command surface.
    _git(repo_root, "merge-base", "--is-ancestor", envelope.payload.base_sha, head)
    diff = _git(repo_root, "diff", "--binary", f"{envelope.payload.base_sha}..{head}")
    changed_raw = _git_text(
        repo_root, "diff", "--name-only", f"{envelope.payload.base_sha}..{head}"
    )
    changed = tuple(line for line in changed_raw.splitlines() if line)
    return BreakGlassAppliedEvidence(
        repair_commit_sha=head,
        repair_tree_sha=tree,
        full_diff_sha256=hashlib.sha256(diff).hexdigest(),
        changed_paths=changed,
        implementer_id=implementer_id,
    )


def _validate(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    envelope.payload.assert_current(now=_now())
    _print({
        "status": "VALID",
        "comment_id": envelope.comment_id,
        "comment_body_sha256": envelope.comment_body_sha256,
        "owner_login": envelope.author_login,
        "recovery_id": envelope.payload.recovery_id,
        "attempt_id": envelope.payload.attempt_id,
        "effect_class": envelope.payload.effect_class.value,
        "payload_sha256": envelope.payload_sha256,
    })
    return 0


def _prepare(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    head, tree = _physical_base(args.repo_root)
    result = prepare_source_repair(
        envelope,
        observed_base_sha=head,
        observed_base_tree=tree,
        now=_now(),
    )
    _print(result)
    return 0


def _record_applied(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    applied = _repair_evidence(args.repo_root, envelope, args.implementer_id)
    result = record_source_repair_applied(envelope, applied, now=_now())
    _print(result)
    return 0


def _record_verified(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    physical = _repair_evidence(args.repo_root, envelope, args.implementer_id)
    verification = BreakGlassVerificationEvidence(
        verifier_id=args.verifier_id,
        verifier_evidence_sha256=args.verifier_evidence_sha256,
        verified_commit_sha=physical.repair_commit_sha,
        verified_tree_sha=physical.repair_tree_sha,
        verified_diff_sha256=physical.full_diff_sha256,
    )
    result = record_source_repair_verified(envelope, verification, now=_now())
    _print(result)
    return 0


def _consume(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    result = consume_source_repair_authority(envelope, now=_now())
    _print(result)
    return 0


def _inspect(args: argparse.Namespace) -> int:
    envelope = _fetch_envelope(args.comment_id)
    _print(inspect_attempt(envelope.payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    def activation(command: argparse.ArgumentParser) -> None:
        command.add_argument("--comment-id", type=int, required=True)

    validate = commands.add_parser("validate")
    activation(validate)
    validate.set_defaults(handler=_validate)

    prepare = commands.add_parser("prepare")
    activation(prepare)
    prepare.add_argument("--repo-root", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    applied = commands.add_parser("record-applied")
    activation(applied)
    applied.add_argument("--repo-root", type=Path, required=True)
    applied.add_argument("--implementer-id", required=True)
    applied.set_defaults(handler=_record_applied)

    verified = commands.add_parser("record-verified")
    activation(verified)
    verified.add_argument("--repo-root", type=Path, required=True)
    verified.add_argument("--implementer-id", required=True)
    verified.add_argument("--verifier-id", required=True)
    verified.add_argument("--verifier-evidence-sha256", required=True)
    verified.set_defaults(handler=_record_verified)

    consume = commands.add_parser("consume")
    activation(consume)
    consume.set_defaults(handler=_consume)

    inspect = commands.add_parser("inspect")
    activation(inspect)
    inspect.set_defaults(handler=_inspect)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (BreakGlassRecoveryError, ValueError, TypeError) as exc:
        _print({"status": "ERROR", "reason": str(exc) or type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
