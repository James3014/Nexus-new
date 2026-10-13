"""Repro: SelfHostedTaskService.approve_promotion (reached by legacy MCP
nexus_self_hosted_approve_promotion and CLI run_self_hosted_approve, both of which pass
NO approval_context) marks a Candidate APPROVED:
  - without any approver identity / approval grant,
  - although verified_receipt.verified is False and verifier_gate_passed is False,
  - with verified_receipt_hash that is not the hash of verified_receipt (never recomputed).
"""
import sys, tempfile, pathlib
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

tmp = pathlib.Path(tempfile.mkdtemp())
svc = SelfHostedTaskService(state_dir=tmp / "state", ephemeral=True)
packet = {"candidate_commit_sha": "c" * 40, "candidate_tree_sha": "d" * 40,
          "candidate_state_hash": "e" * 64, "verified_receipt_hash": "f" * 64}
svc._write_state("t-noverify", {
    "task_id": "t-noverify", "status": "CANDIDATE_COMMITTED",
    "promotion_status": "PENDING_HUMAN_APPROVAL", "promotion_packet": packet,
    "verified_receipt": {"verified": False, "verifier_gate_passed": False,
                         "failure_reasons": ["verifier_failed:pytest"]},
    "merge_performed": False, "push_performed": False})
out = svc.approve_promotion("t-noverify", **packet)
print("status:", out["status"], "promotion_status:", out["promotion_status"])
print("approval_grant:", (out.get("approved_binding") or {}).get("approval_grant"))
print("verified_receipt.verified:", out["verified_receipt"]["verified"])
