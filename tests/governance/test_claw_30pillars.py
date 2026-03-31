import pytest
from nexus.core.parity_audit import ParityAuditor, SurfaceViolation
from nexus.core.command_dag import CommandDAG, CommandLockedError
from nexus.core.workspace_prefetch import Prefetcher
from nexus.core.mental_snapshot import MentalSnapshot
from nexus.core.recursive_cost import RecursiveCost
from nexus.core.deferred_loader import lazily_load, build_rg_index
from nexus.core.state_contracts import NexusState

# ⚖️ P0: Parity Audit
def test_parity_audit_violation():
    auditor = ParityAuditor(".")
    before = "def func_a(): pass"
    after = "print('removed func_a')"
    with pytest.raises(SurfaceViolation):
        auditor.audit_surface(before, after)

# 🕹️ P1: Command DAG
def test_command_dag_v22_mappings():
    dag = CommandDAG("R") # REPAIRING
    assert dag.validate("edit_file") is True
    with pytest.raises(CommandLockedError):
        dag.validate("pytest") # pytest forbidden in R stage

# ⚡ P2: MDM Prefetch
def test_prefetcher_indexing(tmp_path):
    # Setup tmp workspace
    (tmp_path / "main.py").write_text("print('nexus')")
    (tmp_path / "package.json").write_text("{}")
    
    prefetcher = Prefetcher(str(tmp_path))
    count = prefetcher.bootstrap()
    assert count >= 2
    assert "main.py" in prefetcher.get_file_list()
    assert prefetcher.get_from_cache("main.py") == "print('nexus')"

# 🧬 P3: Subsystem Snapshot
def test_subsystem_snapshot_enhanced():
    state = NexusState(task_id="st-test")
    state.metadata["read_files_cache"] = {"a.py": "content"}
    snapshot = MentalSnapshot(state)
    sub_data = snapshot.subsystem_snapshot()
    
    assert sub_data["modules_count"] == 1
    assert "skill_wins" in sub_data
    assert sub_data["semantic_vectors"] == "thermal-0x31-8k"

# 🌳 P4: Recursive Cost
def test_recursive_cost_swarm():
    # N=5, C=2000, T=10 -> 100,000
    params = {"n_subagents": 5, "avg_context": 2000, "expected_turns": 10}
    cost = RecursiveCost.estimate_tree("swarm", params)
    assert cost == 100000

# 💤 P5: Deferred Init
def test_deferred_loader_lazy():
    # Only verify wrapper works
    res = build_rg_index()
    assert res["status"] == "INDEXED"
