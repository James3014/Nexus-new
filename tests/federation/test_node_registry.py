import pytest
import sqlite3
import time
import json
from pathlib import Path
from nexus.federation.node_registry import NodeRegistry, NodeRecord

@pytest.fixture
def temp_db(tmp_path):
    return tmp_path / "nodes.db"

@pytest.fixture
def registry(temp_db):
    return NodeRegistry(temp_db)

def test_node_registration(registry, temp_db):
    node = NodeRecord(
        node_id="node-1",
        host="localhost",
        port=8001,
        status="ONLINE",
        last_heartbeat=time.time(),
        load=0.1,
        capabilities=["cpu", "gpu"],
        tls_fingerprint="sha256:abc"
    )
    registry.register(node)
    
    # Verify in DB
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.execute("SELECT * FROM nodes WHERE node_id='node-1'")
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "localhost"
        assert row[2] == 8001
        assert "cpu" in row[6]

def test_node_discovery(registry):
    node1 = NodeRecord("node-1", "h1", 8001, "ONLINE", time.time(), 0.1, ["c1"])
    node2 = NodeRecord("node-2", "h2", 8002, "OFFLINE", time.time(), 0.1, ["c2"])
    
    registry.register(node1)
    registry.register(node2)
    
    nodes = registry.discover()
    assert len(nodes) == 1
    assert nodes[0].node_id == "node-1"

def test_node_heartbeat_updates_load(registry):
    node = NodeRecord("node-1", "h1", 8001, "ONLINE", time.time(), 0.1, [])
    registry.register(node)
    
    registry.heartbeat("node-1", load=0.5)
    
    updated = registry.get_node("node-1")
    assert updated.load == 0.5
    assert updated.status == "ONLINE"

def test_node_pruning_degraded_and_offline(registry):
    now = time.time()
    # Node 1: stale > 60s -> DEGRADED
    node1 = NodeRecord("node-1", "h1", 8001, "ONLINE", now - 70, 0.1, [])
    # Node 2: stale > 300s -> OFFLINE
    node2 = NodeRecord("node-2", "h2", 8002, "ONLINE", now - 350, 0.1, [])
    # Node 3: fresh
    node3 = NodeRecord("node-3", "h3", 8003, "ONLINE", now, 0.1, [])
    
    registry.register(node1)
    registry.register(node2)
    registry.register(node3)
    
    # Pruning happens during discover or get_node
    registry.discover()
    
    n1 = registry.get_node("node-1")
    n2 = registry.get_node("node-2")
    n3 = registry.get_node("node-3")
    
    assert n1.status == "DEGRADED"
    assert n2.status == "OFFLINE"
    assert n3.status == "ONLINE"

def test_node_deregistration(registry):
    node = NodeRecord("node-1", "h1", 8001, "ONLINE", time.time(), 0.1, [])
    registry.register(node)
    registry.deregister("node-1")
    
    assert registry.get_node("node-1") is None
