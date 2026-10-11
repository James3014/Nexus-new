"""Repro: legacy ControlledIntegrationManager.integrate_task_state (reached by
WorkerCompetitionCoordinator.integrate_winner / MCP nexus_self_hosted_integrate_competition)
merges a Candidate with:
  - no external acceptance receipt,
  - a verified_receipt that says verified=False / verifier_gate_passed=False,
  - promotion_packet.verified_receipt_hash that is NOT the hash of verified_receipt,
  - an 'approved_binding' that is a bare copy of the packet (no approval grant / approver identity).
Contrast: integrate_authorized_task_state requires external_acceptance.passed.
"""
import os, subprocess, sys, tempfile
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.governed_integration import ControlledIntegrationManager

def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout.strip()

root = tempfile.mkdtemp()
ctrl = os.path.join(root, "ctrl"); os.makedirs(ctrl)
git("init", "-q", "-b", "main", cwd=ctrl); git("config", "user.name", "t", cwd=ctrl); git("config", "user.email", "t@t", cwd=ctrl)
open(os.path.join(ctrl, "a.txt"), "w").write("base\n")
git("add", ".", cwd=ctrl); git("commit", "-qm", "base", cwd=ctrl)
base = git("rev-parse", "HEAD", cwd=ctrl)
git("branch", "nexus/integration", cwd=ctrl)
git("checkout", "-q", "-b", "nexus/task/t1", cwd=ctrl)
open(os.path.join(ctrl, "a.txt"), "w").write("UNVERIFIED WORKER OUTPUT\n")
git("commit", "-qam", "candidate", cwd=ctrl)
cand = git("rev-parse", "HEAD", cwd=ctrl)
tree = git("rev-parse", cand + "^{tree}", cwd=ctrl)
git("checkout", "-q", "main", cwd=ctrl)

packet = {"candidate_commit_sha": cand, "candidate_tree_sha": tree,
          "candidate_state_hash": "f" * 64, "verified_receipt_hash": "0" * 64}  # bogus hash
state = {
    "task_id": "t1", "status": "CANDIDATE_COMMITTED", "promotion_status": "APPROVED",
    "contract": {"task_id": "t1", "controller_repo_root": ctrl, "target_base_revision": base,
                 "verifier_commands": []},
    "lease": {"target_branch": "nexus/task/t1"},
    "promotion_packet": packet,
    "approved_binding": dict(packet),             # self-copied, no approval_grant / approver
    "verified_receipt": {"verified": False, "verifier_gate_passed": False, "verifier_evidence": []},
    # no external_acceptance, no integration_authorization
}
r = ControlledIntegrationManager(integration_root=os.path.join(root, "integ")).integrate_task_state(
    state, integration_branch="nexus/integration")
print("merge_performed:", r.merge_performed, "verifier_passed:", r.verifier_passed)
print("nexus/integration now contains candidate:",
      subprocess.run(["git", "merge-base", "--is-ancestor", cand, "nexus/integration"], cwd=ctrl).returncode == 0)
print("a.txt on nexus/integration:", git("show", "nexus/integration:a.txt", cwd=ctrl))

# contrast: authorized path rejects missing acceptance
try:
    ControlledIntegrationManager(integration_root=root).integrate_authorized_task_state(
        {**state, "integration_authorization": {"expected_canonical_head": base}},
        integration_branch="nexus/integration", staging_root=os.path.join(root, "stg"))
except Exception as e:
    print("contrast integrate_authorized_task_state:", type(e).__name__, e)
