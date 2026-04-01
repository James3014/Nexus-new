import pytest
import asyncio
from nexus.core.k8s_swarm_adapter import K8sSwarmAdapter

@pytest.mark.asyncio
async def test_k8s_provisioning_logic():
    adapter = K8sSwarmAdapter()
    node_id = "node-v25-test"
    res = await adapter.provision_node(node_id)
    
    assert res["id"] == node_id
    assert res["status"] == "PodRunning"
    assert node_id in adapter.active_pods

@pytest.mark.asyncio
async def test_k8s_cluster_summary():
    adapter = K8sSwarmAdapter()
    await adapter.provision_node("n1")
    await adapter.provision_node("n2")
    
    status = adapter.get_cluster_status()
    assert status["active_nodes"] == 2
    assert status["orchestration"] == "NexusV25"
