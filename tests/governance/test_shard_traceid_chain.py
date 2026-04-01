import pytest
import uuid
from nexus.core.state_contracts import NexusState
from nexus.core.task_sharding import TaskSharding

def test_shard_traceid_chain_consistency():
    """核驗分解後的 Shards 是否正確繼承並擴展根 traceid"""
    state = NexusState(task_id="TASK-ROOT-001")
    state.trace_id = "TRACE-ROOT-UUID"
    state.metadata["task_description"] = "具現化核心演算法基礎並完成整合驗測"
    
    dag = TaskSharding.decompose(state)
    
    # 核驗根屬性
    assert dag["parent_task_id"] == "TASK-ROOT-001"
    assert dag["root_trace_id"] == "TRACE-ROOT-UUID"
    
    # 核驗 Shard 鏈路
    shards = dag["shards"]
    assert len(shards) >= 1
    
    for shard_id, config in shards.items():
        assert "traceid" in config
        # Shard traceid 應包含根 traceid 作為前綴以利 OTel 聚合
        assert config["traceid"].startswith("TRACE-ROOT-UUID")
        assert "worktree_path" in config
        assert "goal" in config

def test_shard_parent_task_id_presence():
    """核驗 Shard 是否包含 parent_task_id 指標鏈路"""
    state = NexusState(task_id="TASK-ROOT-999")
    dag = TaskSharding.decompose(state)
    
    assert dag["parent_task_id"] == "TASK-ROOT-999"
