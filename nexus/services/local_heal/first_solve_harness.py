"""
H8-9 First Solve Harness

Inert deterministic first solve path.
No real model. No patches applied. No network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SolveAttemptReceipt:
    task_id: str = ""
    candidate_id: str = ""
    selected_candidate_hash: str = ""
    solve_attempted: bool = True
    real_model_used: bool = False
    fake_candidate_used: bool = True
    local_model_called: bool = False
    local_model_loaded: bool = False
    model_loaded: bool = False
    model_called: bool = False
    provider_call_allowed: bool = False
    network_allowed: bool = False
    candidate_output_isolated: bool = True
    verifier_result: str = "not_run"
    patch_applied: bool = False
    task_solved: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    evidence_refs: tuple[str, ...] = ()
    route_truth_source: str = "CapabilityPlanner"


def run_first_solve_harness(
    task_id: str,
    problem_statement: str,
    evidence_refs: tuple[str, ...],
    candidate_id: str,
    candidate_patch_or_output: str,
    selected_candidate_hash: str,
) -> SolveAttemptReceipt:
    if not evidence_refs:
        raise ValueError("evidence_refs required")
    if not candidate_id:
        raise ValueError("candidate_id required")
    if not selected_candidate_hash:
        raise ValueError("selected_candidate_hash required")
    return SolveAttemptReceipt(
        task_id=task_id,
        candidate_id=candidate_id,
        selected_candidate_hash=selected_candidate_hash,
        evidence_refs=evidence_refs,
    )
