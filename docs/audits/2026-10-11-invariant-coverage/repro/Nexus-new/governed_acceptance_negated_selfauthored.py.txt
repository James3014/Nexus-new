"""Reproducer: governed independent-acceptance projection accepts
 (a) a comment authored by the implementer itself (acceptance_comment_author is
     never compared to implementer / an allowed reviewer set), whose reviewer
     identity is free text inside the comment body, and
 (b) an explicitly negative verdict, because the verdict test is a substring
     match on "accept candidate" / "blockers: none" ("I do NOT accept candidate"
     contains "accept candidate").
Production path: scripts/ops/github_orchestration_evidence.py:collect_from_github
-> nexus/orchestrator/github_orchestration.py:build_governed_orchestration_evidence
-> _parse_legacy_acceptance. The resulting evidence has independent_acceptance=True
and an independent_acceptance_hash, which the completion loop / MERGE_INTENT trust.
Uses the repo's own valid fixture and changes only the acceptance comment.
"""
import sys

sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.github_orchestration import build_governed_orchestration_evidence  # noqa: E402
from tests.nexus.orchestrator.test_github_orchestration import _compat_projection_inputs  # noqa: E402

v = _compat_projection_inputs()
v["acceptance_comment_author"] = "coordinator-implementer"   # same account as implementer
v["acceptance_comment_body"] = (
    v["acceptance_comment_body"]
    .replace("Verdict: **BLOCKERS: none**", "Verdict: REJECT. I do not accept candidate; blockers: 3 failing tests")
)
assert "blockers: none" not in v["acceptance_comment_body"].lower()
e = build_governed_orchestration_evidence(**v)
print("implementer =", v["implementer"], "| comment author =", v["acceptance_comment_author"])
print("verdict text =", [l for l in v["acceptance_comment_body"].splitlines() if l.startswith("Verdict")][0])
print("PROJECTED independent_acceptance =", e.independent_acceptance,
      "reviewer =", e.candidate.reviewer, "acceptance_hash =", e.independent_acceptance_hash[:16])
