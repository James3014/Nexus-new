"""Repro: a self-hosted contract with ZERO verifier_commands is accepted, and the
CandidateVerifier verifier gate passes vacuously (verifier_gate_passed=True, no evidence).
AGENTS.md: "Completion requires behavioral evidence and applicable verifier".
"""
import sys
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.candidate_verifier import CandidateVerifier

c = SelfHostedTaskContract(
    task_id="t-empty", objective="x", controller_revision="a" * 40, target_base_revision="a" * 40,
    controller_repo_root="/tmp/ctrl-x", target_repo_root="/tmp/tgt-x", target_worktree_root="/tmp/wt-x",
    allowed_files=["src/"], verifier_commands=[])
print("contract accepted with verifier_commands=", c.verifier_commands)
CandidateVerifier.validate_static_contract(c)
print("validate_static_contract: passed (no error)")
passed, evidence, failures = CandidateVerifier._run_verifiers(c, "/tmp", None)
print("_run_verifiers ->", passed, evidence, failures)
