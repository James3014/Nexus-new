from pathlib import Path
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from nexus.services.memory_repository import MemoryRepository

@pytest.fixture
def repo(tmp_path):
    return MemoryRepository(tmp_path / "test.db")

def test_memory_repository_init(repo):
    """驗證 MemoryRepository 的初始化狀態。"""
    assert repo.db_path.name == "test.db"
    assert repo._db is None

def test_get_db_connection_fail(repo):
    """驗證當 LanceDB 連線失敗時應拋出 InfrastructureError。"""
    # 確保 lancedb 被模擬
    with patch("nexus.services.memory_repository.lancedb") as mock_lancedb:
        mock_lancedb.connect.side_effect = Exception("DB Fail")
        with pytest.raises(Exception, match="LanceDB connection failed"):
            repo._get_db()

def test_add_rows_and_get_all(repo):
    """驗證資料的新增與獲取流程。"""
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.list_tables.return_value = ["skills"]
    mock_db.open_table.return_value = mock_table
    mock_table.to_pandas.return_value = pd.DataFrame([{"id": "s1", "text": "hello"}])
    
    with patch("nexus.services.memory_repository.lancedb") as mock_lancedb:
        mock_lancedb.connect.return_value = mock_db
        repo._db = mock_db
        
        rows = [{"id": "s1", "text": "hello"}]
        repo.add_rows("skills", rows)
        
        # 應呼叫 table.add
        mock_table.add.assert_called_once_with(rows)
        
        df = repo.get_all_rows("skills")
        assert len(df) == 1
        assert df.iloc[0]["id"] == "s1"


def test_ensure_table_tolerates_concurrent_create_race(repo):
    mock_db = MagicMock()
    mock_db.list_tables.side_effect = [[], ["policy"]]
    mock_db.create_table.side_effect = RuntimeError("Table 'policy' already exists")
    repo._db = mock_db

    repo.ensure_table("policy", [{"condition": "x"}], fts_column="condition")

    mock_db.create_table.assert_called_once()


def test_update_table_replaces_existing_rows(repo):
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.list_tables.return_value = ["policy"]
    mock_db.open_table.return_value = mock_table
    repo._db = mock_db
    df = pd.DataFrame([{"rule_id": "POL-1", "confidence": 0.9}])

    repo.update_table("policy", df)

    mock_table.delete.assert_called_once()
    mock_table.add.assert_called_once_with([{"rule_id": "POL-1", "confidence": 0.9}])
