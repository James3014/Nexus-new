"""
PR-06 TDD: StateIO 拆層強化
驗證：StateRepository 失敗不影響 MetricsWriter；ContractWriter 可獨立寫出。
"""
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from nexus.core.state_repository import StateRepository
from nexus.core.metrics_writer import MetricsWriter
from nexus.core.contract_writer import ContractWriter
from nexus.core.state_contracts import NexusState


def test_state_failure_isolated_from_metrics(tmp_path):
    """StateRepository 寫入失敗不應影響 MetricsWriter 獨立寫入。"""
    bad_path = tmp_path / "no_such_dir" / ".musestate"
    repo = StateRepository(bad_path)
    state = NexusState(task_id="test-isolated")

    # StateRepository 寫入應失敗（目錄不存在）
    with pytest.raises(Exception):
        repo.save(state)

    # MetricsWriter 獨立寫應仍然可行
    writer = MetricsWriter(tmp_path / ".nexus_metrics")
    writer.write("task-iso", 999)
    assert (tmp_path / ".nexus_metrics").exists()


def test_state_repository_append_mode(tmp_path):
    """StateRepository 應使用 append 模式，保留歷史版本。"""
    repo = StateRepository(tmp_path / ".musestate")
    s1 = NexusState(task_id="state-v1")
    s2 = NexusState(task_id="state-v2")

    repo.save(s1)
    repo.save(s2)

    content = (tmp_path / ".musestate").read_text().strip().split("\n")
    assert len(content) == 2
    # load() 應取最後一個
    loaded = repo.load()
    assert loaded.task_id == "state-v2"


def test_contract_writer_json_format(tmp_path):
    """ContractWriter 寫出的 JSON 必須可被解析。"""
    writer = ContractWriter(tmp_path)
    writer.write("plan.json", {"goal": "修 bug", "priority": 1})
    
    content = json.loads((tmp_path / "plan.json").read_text())
    assert content["goal"] == "修 bug"
    assert content["priority"] == 1


def test_metrics_writer_appends_multi(tmp_path):
    """MetricsWriter 多次寫入應追加，不會覆蓋。"""
    writer = MetricsWriter(tmp_path / ".nexus_metrics")
    writer.write("t1", 100)
    writer.write("t2", 200)

    content = (tmp_path / ".nexus_metrics").read_text()
    assert "t1" in content
    assert "t2" in content
    assert "100" in content
    assert "200" in content
