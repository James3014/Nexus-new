import pytest
import asyncio
from nexus.core.self_evolve_engine import SelfEvolveEngine
from nexus.core.state_contracts import NexusState
from nexus.core.k8s_swarm_adapter import K8sSwarmAdapter
from nexus.core.access_control_list import AccessControlList

# 🧬 Phase S: Self-Evolve Engine Test
def test_self_evolve_cycle():
    state = NexusState(task_id="evo-test")
    state.metadata["aos_score"] = 108
    
    engine = SelfEvolveEngine(state)
    res = engine.run_evolution_cycle(target_aos=120, features=["k8s_swarm"])
    
    assert res["status"] == "EVOLVE_COMPLETE"
    assert res["new_aos"] == 120
    assert state.metadata["aos_score"] == 120

# ☸️ v25: K8s Swarm Adapter Test
@pytest.mark.asyncio
async def test_k8s_provisioning():
    adapter = K8sSwarmAdapter()
    res = await adapter.provision_node("node-v25-001")
    assert res["status"] == "PodRunning"
    assert adapter.get_cluster_status()["active_nodes"] == 1

# 🔐 v25: ACL Test
def test_acl_authorization():
    acl = AccessControlList()
    # Test valid permission
    assert acl.check_permission("agent", "read_file") is True
    # Test restricted permission
    assert acl.check_permission("agent", "run_command") is False
    # Test dynamic rule injection
    acl.add_rule("agent", "run_command")
    assert acl.check_permission("agent", "run_command") is True
