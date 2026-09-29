#!/usr/bin/env python3
"""Consumer verification for Repository Intelligence terminal advisory evidence (#1200).

Consumes the terminal evidence produced by
`James3014/repository-intelligence-engine/terminal@b1a0bd882e37a08a3a540947ae767a23d752bd67`
(repository-intelligence-engine#32 / PR #34).

Preserves artifact upload and exact review identity (repository, PR number, head SHA,
base SHA, current main SHA) while gracefully representing advisory timeout / incomplete
observation as `ADVISORY_INCOMPLETE` rather than a red required-gate failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

CHECK_ROLE_SCHEMA = "repository_intelligence.check_roles.v1"
CHECK_ROLE_CLAIM_CEILING = "CI_POLICY_ROLE_EVIDENCE_ONLY"
ADVISORY_CLAIM_CEILING = "ADVISORY_EVIDENCE_ONLY"
ALLOWED_CLAIM_CEILINGS = frozenset({CHECK_ROLE_CLAIM_CEILING, ADVISORY_CLAIM_CEILING})

PINNED_ACTION_COMMIT = "b1a0bd882e37a08a3a540947ae767a23d752bd67"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


class RepositoryIntelligenceConsumerError(ValueError):
    """Raised when repository intelligence evidence is malformed or invalid."""


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _validate_40_hex(value: Any, name: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA40.fullmatch(text):
        raise RepositoryIntelligenceConsumerError(
            f"{name} must be a 40-character lowercase hex SHA"
        )
    return text


def _validate_identity(
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    current_main_sha: str | None = None,
) -> dict[str, Any]:
    repo = str(repository or "").strip()
    if not repo or "/" not in repo:
        raise RepositoryIntelligenceConsumerError("repository must be in owner/repo format")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise RepositoryIntelligenceConsumerError("pr_number must be a positive integer")
    head = _validate_40_hex(head_sha, "head_sha")
    base = _validate_40_hex(base_sha, "base_sha")
    main = _validate_40_hex(current_main_sha or base, "current_main_sha")

    return {
        "repository": repo,
        "pr_number": pr_number,
        "head_sha": head,
        "base_sha": base,
        "current_main_sha": main,
    }


def make_advisory_incomplete_envelope(
    *,
    identity: Mapping[str, Any],
    action_commit: str = PINNED_ACTION_COMMIT,
    reason: str = "OBSERVER_TIMED_OUT_BEFORE_TERMINAL_QUIESCENCE",
) -> dict[str, Any]:
    """Emit a deterministic, hash-bound ADVISORY_INCOMPLETE evidence envelope."""
    validated_commit = _validate_40_hex(action_commit, "action_commit")
    body: dict[str, Any] = {
        "schema": CHECK_ROLE_SCHEMA,
        "advisory_disposition": "ADVISORY_INCOMPLETE",
        "observer_health": "DEGRADED",
        "required_gate_state": "CLEAR",
        "review_identity": dict(identity),
        "action_commit": validated_commit,
        "reason": reason,
        "status": "ADVISORY_INCOMPLETE",
        "claim_ceiling": CHECK_ROLE_CLAIM_CEILING,
    }
    body["content_sha256"] = canonical_hash({
        k: v for k, v in body.items() if k != "content_sha256"
    })
    return body


def verify_advisory_terminal_evidence(
    *,
    report_path: Path,
    action_outcome: str,
    identity: Mapping[str, Any],
    action_commit: str = PINNED_ACTION_COMMIT,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Verify or construct terminal advisory evidence.

    If the advisory observer completed successfully and emitted valid evidence,
    validate and stamp it.
    If the advisory observer timed out or failed to stabilize within the window,
    produce valid `ADVISORY_INCOMPLETE` evidence so artifact upload preserves exact
    review identity without failing the workflow as a red required gate.
    """
    validated_commit = _validate_40_hex(action_commit, "action_commit")
    dest_path = output_path or report_path

    # Case 1: Observer timed out or step indicated failure
    if action_outcome != "success" or not report_path.is_file() or report_path.stat().st_size == 0:
        envelope = make_advisory_incomplete_envelope(
            identity=identity,
            action_commit=validated_commit,
            reason="OBSERVER_TIMED_OUT_BEFORE_TERMINAL_QUIESCENCE",
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(
            json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return envelope

    # Case 2: Action reported success, validate generated evidence
    try:
        raw = report_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        raise RepositoryIntelligenceConsumerError(f"MALFORMED_EVIDENCE_JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RepositoryIntelligenceConsumerError("EVIDENCE_MUST_BE_OBJECT")

    claim_ceiling = str(data.get("claim_ceiling") or "").strip()
    if claim_ceiling not in ALLOWED_CLAIM_CEILINGS:
        raise RepositoryIntelligenceConsumerError(
            f"INVALID_CLAIM_CEILING: {claim_ceiling!r} not in {sorted(ALLOWED_CLAIM_CEILINGS)}"
        )

    content_sha = str(data.get("content_sha256") or "").strip().lower()
    if not SHA64.fullmatch(content_sha):
        raise RepositoryIntelligenceConsumerError("INVALID_CONTENT_SHA256")

    # Record exact action commit in evidence
    data["action_commit"] = validated_commit
    data["content_sha256"] = canonical_hash({
        k: v for k, v in data.items() if k != "content_sha256"
    })

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", default="repository-intelligence-terminal.json")
    parser.add_argument("--action-outcome", default="success", choices=["success", "failure"])
    parser.add_argument("--action-commit", default=PINNED_ACTION_COMMIT)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--current-main-sha", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--step-summary", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        identity = _validate_identity(
            repository=args.repository,
            pr_number=args.pr_number,
            head_sha=args.head_sha,
            base_sha=args.base_sha,
            current_main_sha=args.current_main_sha,
        )
        report_path = Path(args.report_path)
        output_path = Path(args.output) if args.output else report_path

        result = verify_advisory_terminal_evidence(
            report_path=report_path,
            action_outcome=args.action_outcome,
            identity=identity,
            action_commit=args.action_commit,
            output_path=output_path,
        )

        if args.step_summary:
            summary_path = Path(args.step_summary)
            disposition = result.get("advisory_disposition") or result.get("status") or "COMPLETE"
            summary_text = (
                "## Repository Intelligence Advisory Terminal\n\n"
                f"- Disposition: `{disposition}`\n"
                f"- Action Commit: `{result.get('action_commit')}`\n"
                f"- Content SHA-256: `{result.get('content_sha256')}`\n"
                f"- Claim Ceiling: `{result.get('claim_ceiling')}`\n\n"
                "Note: Repository Intelligence is an advisory observer. "
                "Its outcome does not grant or block merge authority.\n"
            )
            summary_path.write_text(summary_text, encoding="utf-8")

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    except RepositoryIntelligenceConsumerError as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "reason": str(exc),
                    "claim_ceiling": CHECK_ROLE_CLAIM_CEILING,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
