from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.ops.trusted_merge_lane_gate import (
    BINDING_SCHEMA,
    REBIND_SCHEMA,
    IssueClosureIntentError,
    LaneBindingError,
    canonical_hash,
    render_binding,
    render_intent,
    validate_event,
)

REPOSITORY = "James3014/Nexus-new"
PR_NUMBER = 1061
TASK_ID = "issue-1023-lane-rebind"
ATTEMPT_ID = "attempt-1"
CARD_PATH = "tasks/campaign/00-card.md"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _repo(tmp_path: Path, *, card_lane: str = "GOVERNED", change_card_on_head: bool = False):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True
    )
    card = repo / CARD_PATH
    card.parent.mkdir(parents=True)
    card.write_text(
        "# Task Card\n\n"
        f"task_id: {chr(96)}{TASK_ID}{chr(96)}\n"
        "contract_kind: TRACKED_TASK_CARD\n"
        f"execution_lane: {card_lane}\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "base"], check=True, capture_output=True
    )
    base = _git(repo, "rev-parse", "HEAD")
    card_bytes = card.read_bytes()
    if change_card_on_head:
        card.write_text(card.read_text(encoding="utf-8") + "\nchanged: true\n", encoding="utf-8")
    (repo / "README.md").write_text("head\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "head"], check=True, capture_output=True
    )
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head, card_bytes


def _event(*, base: str, head: str, body: str | None, number: int = PR_NUMBER):
    return {
        "event_name": "pull_request_target",
        "repository": {"full_name": REPOSITORY},
        "pull_request": {
            "number": number,
            "body": body,
            "base": {"sha": base},
            "head": {"sha": head},
        },
    }


def _binding(
    *,
    lane: str,
    head: str,
    card_bytes: bytes | None = None,
    card_lane: str | None = None,
    issue_number: int = 1023,
    task_id: str = TASK_ID,
    attempt_id: str = ATTEMPT_ID,
    rebind: bool = False,
):
    if card_bytes is None:
        value = {
            "schema": BINDING_SCHEMA,
            "execution_lane": lane,
            "contract_kind": "OWNER_INLINE",
            "owner_id": "James3014",
            "issue_number": None,
            "task_id": None,
            "attempt_id": None,
            "task_card_path": None,
            "task_card_sha256": None,
            "owner_lane_rebind": None,
        }
    else:
        card_hash = hashlib.sha256(card_bytes).hexdigest()
        value = {
            "schema": BINDING_SCHEMA,
            "execution_lane": lane,
            "contract_kind": "TRACKED_TASK_CARD",
            "owner_id": "James3014",
            "issue_number": issue_number,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "task_card_path": CARD_PATH,
            "task_card_sha256": card_hash,
            "owner_lane_rebind": None,
        }
        if rebind:
            record = {
                "schema": REBIND_SCHEMA,
                "repository": REPOSITORY,
                "issue_number": issue_number,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "task_card_path": CARD_PATH,
                "task_card_sha256": card_hash,
                "pull_request_number": PR_NUMBER,
                "expected_pr_head_sha": head,
                "from_lane": "GOVERNED",
                "to_lane": lane,
                "owner_id": "James3014",
                "owner_confirmation": True,
            }
            record["record_hash"] = canonical_hash(record)
            value["owner_lane_rebind"] = record
    value["binding_hash"] = canonical_hash(value)
    return value


def _owner_comment(
    payload: dict[str, object],
    *,
    marker: str,
    comment_id: int,
    owner: str = "James3014",
) -> dict[str, object]:
    payload_hash = canonical_hash(payload)
    return {
        "id": comment_id,
        "html_url": f"https://github.com/James3014/Nexus-new/issues/806#issuecomment-{comment_id}",
        "issue_url": "https://api.github.com/repos/James3014/Nexus-new/issues/806",
        "user": {"login": owner},
        "body": (
            f"{marker}: `{payload_hash}`\n\n"
            "```json\n" + json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n```\n"
        ),
    }


def _break_glass_chain(
    *,
    base: str,
    head: str,
    conclusion: str = "success",
    integration_expires_at: str = "2026-09-30T04:00:00+00:00",
) -> tuple[dict[str, object], dict[int, dict[str, object]]]:
    source = {
        "schema": "nexus.break_glass_owner_activation.v1",
        "repository": REPOSITORY,
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-1218-20260930",
        "attempt_id": "BG-806-1218-A1",
        "failure_class": "GOVERNANCE_PLANE_RECOVERY_REQUIRED",
        "failure_evidence_sha256": "1" * 64,
        "effect_class": "SOURCE_REPAIR",
        "base_sha": "b" * 40,
        "base_tree": "a" * 40,
        "allowed_paths": ["scripts/ops/trusted_merge_lane_gate.py"],
        "forbidden_paths": [".git"],
        "verifier_commands": ["pytest"],
        "issued_at": "2026-09-30T02:00:00+00:00",
        "expires_at": "2026-09-30T03:45:00+00:00",
        "claim_ceiling": "break_glass_source_candidate_only",
    }
    source_hash = canonical_hash(source)
    verification = {
        "schema": "nexus.break_glass_owner_verification.v1",
        "repository": REPOSITORY,
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-1218-20260930",
        "source_attempt_id": "BG-806-1218-A1",
        "source_activation_payload_sha256": source_hash,
        "verified_commit_sha": head,
        "verified_tree_sha": "c" * 40,
        "verified_diff_sha256": "d" * 64,
        "verifier_id": "independent-verifier",
        "checks": [
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "source verification",
                "run_id": 8999,
                "head_sha": head,
                "conclusion": "success",
            }
        ],
        "issued_at": "2026-09-30T02:40:00+00:00",
        "expires_at": "2026-09-30T03:40:00+00:00",
        "claim_ceiling": "source_repair_verification_only",
    }
    verification_hash = canonical_hash(verification)
    integration = {
        "schema": "nexus.break_glass_owner_integration.v1",
        "repository": REPOSITORY,
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-1218-20260930",
        "integration_attempt_id": "BG-806-1218-I1",
        "source_attempt_id": "BG-806-1218-A1",
        "source_activation_payload_sha256": source_hash,
        "verification_payload_sha256": verification_hash,
        "effect_class": "EMERGENCY_INTEGRATION",
        "pr_number": PR_NUMBER,
        "accepted_head_sha": head,
        "accepted_tree_sha": "c" * 40,
        "accepted_diff_sha256": "d" * 64,
        "expected_base_sha": base,
        "merge_method": "merge",
        "checks": [
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "independent source verification",
                "run_id": 9001,
                "head_sha": head,
                "conclusion": conclusion,
            }
        ],
        "issued_at": "2026-09-30T03:00:00+00:00",
        "expires_at": integration_expires_at,
        "claim_ceiling": "emergency_integration_only",
    }
    comments = {
        1231: _owner_comment(
            source,
            marker="Canonical activation payload SHA-256",
            comment_id=1231,
        ),
        1232: _owner_comment(
            verification,
            marker="Canonical verification payload SHA-256",
            comment_id=1232,
        ),
        1234: _owner_comment(
            integration,
            marker="Canonical integration payload SHA-256",
            comment_id=1234,
        ),
    }
    return integration, comments


def _break_glass_binding(
    payload: dict[str, object],
    *,
    payload_hash: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": BINDING_SCHEMA,
        "execution_lane": "BREAK_GLASS",
        "contract_kind": "BREAK_GLASS_OWNER_INTEGRATION",
        "owner_id": "James3014",
        "break_glass_integration": {
            "source_comment_id": 1231,
            "verification_comment_id": 1232,
            "integration_comment_id": 1234,
            "integration_payload_sha256": payload_hash or canonical_hash(payload),
        },
    }
    value["binding_hash"] = canonical_hash(value)
    return value


def _comment_fetcher(comments: dict[int, dict[str, object]]):
    return lambda comment_id: comments[comment_id]


def test_break_glass_owner_integration_passes_with_external_owner_chain(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head=head)
    binding = _break_glass_binding(payload)
    result = validate_event(
        _event(base=base, head=head, body=render_binding(binding)),
        repo_root=repo,
        break_glass_comment_fetcher=_comment_fetcher(comments),
        now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
    )
    assert result["status"] == "PASS"
    assert result["reason"] == "BREAK_GLASS_OWNER_INTEGRATION_VALID"
    assert result["execution_lane"] == "BREAK_GLASS"
    assert result["break_glass_integration"]["integration_attempt_id"] == "BG-806-1218-I1"
    assert result["break_glass_integration"]["verification_comment_id"] == 1232


def test_break_glass_payload_hash_tamper_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head=head)
    binding = _break_glass_binding(payload, payload_hash="0" * 64)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_INTEGRATION_HASH_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_break_glass_exact_subject_mismatch_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head="a" * 40)
    binding = _break_glass_binding(payload)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_HEAD_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_break_glass_expired_authority_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(
        base=base,
        head=head,
        integration_expires_at="2026-09-30T03:20:00+00:00",
    )
    binding = _break_glass_binding(payload)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_INTEGRATION_EXPIRED"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_break_glass_failed_check_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head=head, conclusion="failure")
    binding = _break_glass_binding(payload)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_CHECK_NOT_SUCCESS"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_break_glass_forged_integration_owner_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head=head)
    comments[1234]["user"] = {"login": "attacker"}
    binding = _break_glass_binding(payload)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_COMMENT_OWNER_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_break_glass_forged_verification_owner_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    payload, comments = _break_glass_chain(base=base, head=head)
    comments[1232]["user"] = {"login": "attacker"}
    binding = _break_glass_binding(payload)
    with pytest.raises(LaneBindingError, match="BREAK_GLASS_COMMENT_OWNER_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
            break_glass_comment_fetcher=_comment_fetcher(comments),
            now=datetime(2026, 9, 30, 3, 30, tzinfo=timezone.utc),
        )


def test_pre_enforcement_pr_keeps_compatibility(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    result = validate_event(
        _event(base=base, head=head, body=None, number=1060),
        repo_root=repo,
    )
    assert result["status"] == "PASS"
    assert result["reason"] == "PRE_ENFORCEMENT_PR_COMPATIBILITY"


def test_new_pr_without_typed_binding_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    with pytest.raises(LaneBindingError, match="EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED"):
        validate_event(_event(base=base, head=head, body="DIRECT please"), repo_root=repo)


@pytest.mark.parametrize("lane", ["DIRECT_CANONICAL", "DIRECT_DELEGATED"])
def test_genuine_direct_owner_inline_stays_lightweight(tmp_path: Path, lane: str):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane=lane, head=head)
    result = validate_event(
        _event(base=base, head=head, body=render_binding(binding)),
        repo_root=repo,
    )
    assert result["status"] == "PASS"
    assert result["reason"] == "GENUINE_DIRECT_OWNER_INLINE"
    assert result["execution_lane"] == lane


def test_governed_task_remains_governed_without_rebind(tmp_path: Path):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="GOVERNED")
    binding = _binding(lane="GOVERNED", head=head, card_bytes=card_bytes)
    result = validate_event(
        _event(base=base, head=head, body=render_binding(binding)),
        repo_root=repo,
    )
    assert result["reason"] == "GOVERNED_LANE_UNCHANGED"


@pytest.mark.parametrize("lane", ["DIRECT_CANONICAL", "DIRECT_DELEGATED"])
def test_exact_governed_to_direct_rebind_passes(tmp_path: Path, lane: str):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="GOVERNED")
    binding = _binding(lane=lane, head=head, card_bytes=card_bytes, rebind=True)
    result = validate_event(
        _event(base=base, head=head, body=render_binding(binding)),
        repo_root=repo,
    )
    assert result["status"] == "PASS"
    assert result["reason"] == "OWNER_GOVERNED_TO_DIRECT_REBIND_VALID"


def test_governed_to_direct_without_rebind_blocks(tmp_path: Path):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="GOVERNED")
    binding = _binding(lane="DIRECT_CANONICAL", head=head, card_bytes=card_bytes)
    with pytest.raises(LaneBindingError, match="OWNER_LANE_REBIND_MUST_BE_OBJECT"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
        )


def test_moved_pr_head_blocks_stale_rebind(tmp_path: Path):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="GOVERNED")
    binding = _binding(
        lane="DIRECT_CANONICAL",
        head="b" * 40,
        card_bytes=card_bytes,
        rebind=True,
    )
    with pytest.raises(LaneBindingError, match="OWNER_LANE_REBIND_SUBJECT_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
        )


def test_changed_task_card_blocks_rebind(tmp_path: Path):
    repo, base, head, card_bytes = _repo(
        tmp_path,
        card_lane="GOVERNED",
        change_card_on_head=True,
    )
    binding = _binding(
        lane="DIRECT_CANONICAL",
        head=head,
        card_bytes=card_bytes,
        rebind=True,
    )
    with pytest.raises(LaneBindingError, match="TASK_CARD_CHANGED_DURING_MERGE_ATTEMPT"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
        )


def test_wrong_attempt_or_issue_blocks_exact_rebind(tmp_path: Path):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="GOVERNED")
    binding = _binding(
        lane="DIRECT_CANONICAL",
        head=head,
        card_bytes=card_bytes,
        rebind=True,
    )
    binding["attempt_id"] = "attempt-2"
    binding["binding_hash"] = canonical_hash({
        k: v for k, v in binding.items() if k != "binding_hash"
    })
    with pytest.raises(LaneBindingError, match="OWNER_LANE_REBIND_SUBJECT_MISMATCH"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
        )


def test_tampered_binding_hash_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    binding["binding_hash"] = "0" * 64
    with pytest.raises(LaneBindingError, match="BINDING_HASH_INVALID"):
        validate_event(
            _event(base=base, head=head, body=render_binding(binding)),
            repo_root=repo,
        )


def test_duplicate_binding_blocks(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    rendered = render_binding(_binding(lane="DIRECT_CANONICAL", head=head))
    with pytest.raises(LaneBindingError, match="EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED"):
        validate_event(
            _event(base=base, head=head, body=rendered + "\n" + rendered),
            repo_root=repo,
        )


def test_tracked_task_that_began_direct_needs_no_rebind(tmp_path: Path):
    repo, base, head, card_bytes = _repo(tmp_path, card_lane="DIRECT_CANONICAL")
    binding = _binding(
        lane="DIRECT_CANONICAL",
        head=head,
        card_bytes=card_bytes,
        card_lane="DIRECT_CANONICAL",
    )
    result = validate_event(
        _event(base=base, head=head, body=render_binding(binding)),
        repo_root=repo,
    )
    assert result["reason"] == "TRACKED_TASK_BEGAN_DIRECT"


def test_fixture_1191_negated_close_with_keep_open_blocks_gate(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    intent = render_intent([{"issue": 1188, "on_merge": "KEEP_OPEN"}])
    body = (
        f"{render_binding(binding)}\n\n"
        f"{intent}\n\n"
        "This does not close #1188; the umbrella remains open for its standalone-owner child contracts."
    )
    with pytest.raises(IssueClosureIntentError, match="REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN"):
        validate_event(
            _event(base=base, head=head, body=body),
            repo_root=repo,
        )


def test_fixture_1191_negated_close_without_intent_blocks_gate(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    body = (
        f"{render_binding(binding)}\n\n"
        "This does not close #1188; the umbrella remains open for its standalone-owner child contracts."
    )
    with pytest.raises(
        IssueClosureIntentError, match="UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE"
    ):
        validate_event(
            _event(base=base, head=head, body=body),
            repo_root=repo,
        )


def test_neutral_prose_with_keep_open_passes_gate(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    intent = render_intent([{"issue": 1188, "on_merge": "KEEP_OPEN"}])
    body = (
        f"{render_binding(binding)}\n\n"
        f"{intent}\n\n"
        "#1188 remains open for its standalone-owner child contracts."
    )
    result = validate_event(
        _event(base=base, head=head, body=body),
        repo_root=repo,
    )
    assert result["status"] == "PASS"
    assert result["issue_closure_intent"]["status"] == "PASS"
    assert result["issue_closure_intent"]["intents"] == [
        {"issue_number": 1188, "on_merge": "KEEP_OPEN"}
    ]


def test_explicit_positive_close_passes_gate(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    intent = render_intent([{"issue": 1199, "on_merge": "CLOSE"}])
    body = (
        f"{render_binding(binding)}\n\n"
        f"{intent}\n\n"
        "Closes #1199 with deterministic closure intent guard."
    )
    result = validate_event(
        _event(base=base, head=head, body=body),
        repo_root=repo,
    )
    assert result["status"] == "PASS"
    assert result["issue_closure_intent"]["status"] == "PASS"
    assert result["issue_closure_intent"]["intents"] == [
        {"issue_number": 1199, "on_merge": "CLOSE"}
    ]


def test_unintended_closing_keyword_blocks_gate(tmp_path: Path):
    repo, base, head, _ = _repo(tmp_path)
    binding = _binding(lane="DIRECT_CANONICAL", head=head)
    intent = render_intent([{"issue": 1199, "on_merge": "CLOSE"}])
    body = (
        f"{render_binding(binding)}\n\n"
        f"{intent}\n\n"
        "Closes #1199. Also accidentally fixes #999 without declaring intent."
    )
    with pytest.raises(
        IssueClosureIntentError, match="UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE"
    ):
        validate_event(
            _event(base=base, head=head, body=body),
            repo_root=repo,
        )
