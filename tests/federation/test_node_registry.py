import pytest
import time
from pathlib import Path
from nexus.federation.node_registry import NodeRegistry, NodeRecord

def test_node_registration_and_discovery(tmp_path: Path):
    db_path = tmp_path / "nodes.db"
    registry = NodeRegistry(db_path)
    
    node = NodeRecord(
        node_id="node-1", host="localhost", port=8001,
        status="ONLINE", last_heartbeat=time.time(), load=0.5,
        capabilities=["coder", "planner"]
    )
    
    registry.register(node)
    nodes = registry.discover()
    assert len(nodes) == 1
    assert nodes[0].node_id == "node-1"
    assert "coder" in nodes[0].capabilities

def test_node_pruning(tmp_path: Path):
    db_path = tmp_path / "nodes.db"
    registry = NodeRegistry(db_path)
    
    now = time.time()
    n1 = NodeRecord("n1", "h1", 8001, "ONLINE", now, 0.1, [])
    n2 = NodeRecord("n2", "h2", 8002, "ONLINE", now - 70, 0.5, [])
    n3 = NodeRecord("n3", "h3", 8003, "ONLINE", now - 310, 0.9, [])
    
    registry.register(n1)
    registry.register(n2)
    registry.register(n3)
    
    nodes = registry.discover()
    assert len(nodes) == 2
    
    n2_fetched = registry.get_node("n2")
    assert n2_fetched.status == "DEGRADED"
    
    n3_fetched = registry.get_node("n3")
    assert n3_fetched.status == "OFFLINE"
    
    registry.heartbeat("n3", load=0.2)
    n3_revived = registry.get_node("n3")
    assert n3_revived.status == "ONLINE"
