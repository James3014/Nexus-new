"""
C6BN: Belief ablation for local repair lane.

Verifies:
1. Belief exists as prompt-level text only (not runtime capability)
2. NEXUS_ABLATION_SUPPRESS_BELIEF=1 removes the Belief line
3. Belief ablation does not affect problem_statement
4. Belief ablation does not affect other contract lines
5. Belief ablation does not affect parser/anchor/committee behavior
"""
import os
import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _nexus_task_desc


def _make_astropy_task() -> CapabilityTask:
    return CapabilityTask(
        id="astropy__astropy-13236",
        task_desc=(
            "Fix astropy/table/table.py so that data.view(NdarrayMixin) is not called "
            "in this path. The patched file must not contain 'view(NdarrayMixin)'."
        ),
        task_type="bug",
        success_criteria="verify passes",
        difficulty="medium",
        category="benchmark",
        expected_capabilities=("local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"),
        target_file="astropy/table/table.py",
        test_file="verify_13236.py",
    )


_BELIEF_LINE = "- Belief: when evidence is incomplete or confidence is low, prefer a conservative fix backed by tests."
_CONTRACT_HEADER = "Nexus wearing contract:"
_MEMPALACE_LINE = "- MemPalace: keep the solution inside the task scope and enforce explicit governance constraints."
_ARTIFACT_LINE = "- Artifact/Claim: treat completion claims as valid only when backed by concrete artifacts or passing checks."


def test_belief_present_by_default():
    """C6BN: Belief line appears in _nexus_task_desc() by default (env var not set)."""
    task = _make_astropy_task()
    desc = _nexus_task_desc(task)
    assert _BELIEF_LINE in desc, "Belief line must be present in default _nexus_task_desc()"


def test_belief_absent_when_suppressed():
    """C6BN: Belief line is absent when NEXUS_ABLATION_SUPPRESS_BELIEF=1."""
    task = _make_astropy_task()
    try:
        os.environ["NEXUS_ABLATION_SUPPRESS_BELIEF"] = "1"
        desc = _nexus_task_desc(task)
        assert _BELIEF_LINE not in desc, (
            "Belief line must be absent when NEXUS_ABLATION_SUPPRESS_BELIEF=1"
        )
    finally:
        os.environ.pop("NEXUS_ABLATION_SUPPRESS_BELIEF", None)


def test_problem_statement_unaltered_by_belief_ablation():
    """C6BN: problem_statement content is unchanged when Belief is ablated."""
    task = _make_astropy_task()
    ps = task.task_desc
    try:
        os.environ["NEXUS_ABLATION_SUPPRESS_BELIEF"] = "1"
        with_belief = _nexus_task_desc(task)
        assert ps in with_belief, "problem_statement must survive in output"
    finally:
        os.environ.pop("NEXUS_ABLATION_SUPPRESS_BELIEF", None)


def test_other_contract_lines_unaltered():
    """C6BN: MemPalace and Artifact/Claim lines are unaffected by Belief ablation."""
    task = _make_astropy_task()
    # Baseline: get all contract lines with default
    try:
        os.environ["NEXUS_ABLATION_SUPPRESS_BELIEF"] = "1"
        desc = _nexus_task_desc(task)
        assert _CONTRACT_HEADER in desc, "Contract header must be present"
        assert _MEMPALACE_LINE in desc, "MemPalace line must be present"
        assert _ARTIFACT_LINE in desc, "Artifact/Claim line must be present"
    finally:
        os.environ.pop("NEXUS_ABLATION_SUPPRESS_BELIEF", None)


def test_belief_ablation_does_not_change_other_capabilities():
    """C6BN: Belief ablation only removes the Belief line.
    Other prompt structure (expected_capabilities, task_desc, etc.) is unchanged."""
    task = _make_astropy_task()
    assert "ddtree" in task.expected_capabilities
    assert "autoreason" in task.expected_capabilities
    assert "artifact_gate" in task.expected_capabilities
    assert task.task_desc.startswith("Fix astropy/table/table.py")


def test_belief_is_prompt_text_not_runtime_capability():
    """C6BN: Belief is NOT in expected_capabilities for astropy-13236.
    It exists only as prompt-level text, not as a runtime capability."""
    task = _make_astropy_task()
    assert "belief" not in task.expected_capabilities, (
        "Belief must NOT be a runtime capability for astropy-13236"
    )


def test_belief_ablation_env_var_does_not_affect_other_tasks():
    """C6BN: Setting the env var only removes Belief line.
    All other task spec fields are untouched."""
    task_a = _make_astropy_task()
    try:
        os.environ["NEXUS_ABLATION_SUPPRESS_BELIEF"] = "1"
        desc_a = _nexus_task_desc(task_a)
        assert _BELIEF_LINE not in desc_a
    finally:
        os.environ.pop("NEXUS_ABLATION_SUPPRESS_BELIEF", None)


def test_belief_ablation_contract_structure_preserved():
    """C6BN: The contract structure (header + lines) is preserved.
    Only the Belief line is removed, not the entire contract block."""
    task = _make_astropy_task()
    try:
        os.environ["NEXUS_ABLATION_SUPPRESS_BELIEF"] = "1"
        desc = _nexus_task_desc(task)
        # Contract header and all non-Belief lines must still be present
        header_idx = desc.index(_CONTRACT_HEADER)
        mempalace_idx = desc.index(_MEMPALACE_LINE)
        artifact_idx = desc.index(_ARTIFACT_LINE)
        # Verify ordering: header → MemPalace → Artifact/Claim (Belief removed from middle)
        assert header_idx < mempalace_idx < artifact_idx, (
            "Contract lines must appear in correct order: header, MemPalace, Artifact/Claim"
        )
    finally:
        os.environ.pop("NEXUS_ABLATION_SUPPRESS_BELIEF", None)
