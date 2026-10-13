"""Reproducer: PR-number-based legacy exemption in trusted_merge_lane_gate.

Any PR numbered < 1061 PASSes with no binding, no Issue-closure-intent check and
no Task Card check, for ANY head SHA (the exemption is not bound to the head that
existed at cut-over). 48 such PRs are still open on James3014/Nexus-new
(gh api repos/James3014/Nexus-new/pulls?state=open). Pushing new commits to one
of them (synchronize) and editing the body to close a governed Issue keeps PASS.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/user/Nexus-new")
from scripts.ops.trusted_merge_lane_gate import validate_event, LaneBindingError  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    repo = Path(t)
    subprocess.run(["git", "-C", t, "init", "-q"], check=True)
    head = "f" * 40  # never even resolved: exemption returns before any git access
    base = "e" * 40
    body = "Closes #900 Fixes #901  (governed Issues; no NEXUS_MERGE_LANE_V1, no NEXUS_ISSUE_INTENT_V1)"
    for number in (1017, 1061):
        ev = {"event_name": "pull_request_target", "repository": {"full_name": "James3014/Nexus-new"},
              "pull_request": {"number": number, "body": body, "base": {"sha": base}, "head": {"sha": head}}}
        try:
            r = validate_event(ev, repo_root=repo)
            print(f"PR #{number}:", r["status"], r["reason"])
        except LaneBindingError as exc:
            print(f"PR #{number}: BLOCK", exc)
