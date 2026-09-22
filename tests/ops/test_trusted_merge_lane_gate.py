from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts.ops.trusted_merge_lane_gate import (
    BINDING_SCHEMA,
    REBIND_SCHEMA,
    LaneBindingError,
    canonical_hash,
    render_binding,
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
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
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
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "base"], check=True, capture_output=True)
    base = _git(repo, "rev-parse", "HEAD")
    card_bytes = card.read_bytes()
    if change_card_on_head:
        card.write_text(card.read_text(encoding="utf-8") + "\nchanged: true\n", encoding="utf-8")
    (repo / "README.md").write_text("head\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "head"], check=True, capture_output=True)
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
    binding["binding_hash"] = canonical_hash({k: v for k, v in binding.items() if k != "binding_hash"})
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
