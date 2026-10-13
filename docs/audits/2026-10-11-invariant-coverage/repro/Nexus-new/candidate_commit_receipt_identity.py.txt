"""Repro: CandidateCommitter.create_candidate_commit never compares the receipt's identity
(task_id, contract_hash, lease_id) or verifier manifest to the contract/lease it commits for.
candidate_state_hash (the only recomputed binding) covers base/head/diff only, not contract.
A VerifiedCandidateReceipt minted for another task/contract (e.g. one with zero verifiers)
is accepted. Git/worktree collaborator is stubbed; the decision logic is production code.
"""
import sys
from types import SimpleNamespace
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt
from nexus.orchestrator.task_contract import SelfHostedTaskContract

H, C, T = "1" * 40, "2" * 40, "3" * 40
STATE = "9" * 64
class StubWM:
    head = H
    def capture_candidate(self, contract, lease):
        return SimpleNamespace(candidate_state_hash=STATE, collaboration_provenance=None,
                               changed_files=["src/a.py"], untracked_files=[], deleted_files=[],
                               target_head=H)
    def _run_git(self, args, cwd=None, env=None):
        a = list(args)
        if a[:2] == ["diff", "--cached"]:
            return "" if not getattr(self, "added", False) else "src/a.py"
        if a[0] == "add": self.added = True; return ""
        if "commit" in a: self.head = C; return ""
        if a[:2] == ["rev-parse", "HEAD"]: return self.head
        if a[0] == "rev-parse": return T
        if a[:2] == ["diff", "--name-only"]: return "src/a.py"
        if a[:2] == ["status", "--short"]: return ""
        raise AssertionError(a)
    def verify_controller_unchanged(self, contract): return None

contract = SelfHostedTaskContract(task_id="real-task", objective="x", controller_revision="a"*40,
    target_base_revision="a"*40, controller_repo_root="/tmp/c", target_repo_root="/tmp/t",
    target_worktree_root="/tmp/w", allowed_files=["src/"], verifier_commands=["python3 -m pytest tests/"])
lease = SimpleNamespace(target_worktree="/tmp", initial_head=H, lease_id="real-lease")
receipt = VerifiedCandidateReceipt(
    schema="nexus.verified_candidate_receipt.v1", task_id="OTHER-task", contract_hash="0"*64,
    lease_id="other-lease", candidate_state_hash=STATE, scope_gate_passed=True, deletion_gate_passed=True,
    controller_gate_passed=True, protected_contract_gate_passed=True, verifier_gate_passed=True,
    verified=True, candidate_commit_allowed=True, public_claim_allowed=False, production_ready=False,
    failure_reasons=[], verifier_evidence=(), candidate_commit_created=False, merge_performed=False,
    verifier_manifest_sha256="")
import nexus.orchestrator.candidate_commit as cc
cc.get_canonical_git_hooks_dir = lambda p: "/dev/null"
CandidateCommitter._resolve_git_home = staticmethod(lambda: "/tmp")
pkt = CandidateCommitter(StubWM()).create_candidate_commit(contract, lease, receipt)
print("packet task_id:", pkt.task_id, "| receipt task_id:", receipt.task_id)
print("packet contract_hash == contract:", pkt.contract_hash == contract.contract_hash,
      "| receipt.contract_hash:", receipt.contract_hash[:8], "...")
print("receipt verifier_evidence:", receipt.verifier_evidence, "| contract verifiers:", contract.verifier_commands)
print("promotion_status:", pkt.promotion_status, "candidate_commit_sha:", pkt.candidate_commit_sha)
