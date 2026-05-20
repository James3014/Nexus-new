import pytest
from pathlib import Path
import json
import shutil
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

@pytest.fixture
def temp_project_root(tmp_path):
    """建立臨時專案路徑。"""
    project_root = tmp_path / "test_nexus_project"
    project_root.mkdir()
    return project_root

@pytest.fixture
def memory_store(temp_project_root):
    """建立記憶儲存實體。"""
    return FindingsMemoryStore(temp_project_root)

def test_card_to_dict_conversion():
    """驗證記憶卡轉換字典的精確性。"""
    card = FindingsCard(
        title="Test Logic",
        kind="knowledge",
        tags=["unit-test"],
        body="Body content"
    )
    data = card.to_dict()
    assert data["title"] == "Test Logic"
    assert "unit-test" in data["tags"]
    assert data["kind"] == "knowledge"

def test_memory_store_write_and_read(memory_store):
    """驗證基本的寫入與讀取。"""
    card = FindingsCard(
        title="Hyperparameter Rule",
        kind="knowledge",
        body="LR should be < 0.01 for this dataset."
    )
    path = memory_store.write(card)
    assert Path(path).exists()
    
    # 讀取
    loaded = memory_store.read(card.id, kind="knowledge")
    assert loaded is not None
    assert loaded.title == "Hyperparameter Rule"
    assert loaded.body == "LR should be < 0.01 for this dataset."


def test_memory_store_keeps_json_when_vector_sync_fails(temp_project_root):
    class FailingVectorSync:
        def sync(self, payload):
            raise RuntimeError("vector unavailable")

    store = FindingsMemoryStore(temp_project_root, vector_sync=FailingVectorSync())
    card = FindingsCard(id="syncfail", title="Persistent Finding", kind="knowledge")

    path = Path(store.write(card))

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["title"] == "Persistent Finding"
    assert payload["extra"]["lancedb_synced"] is False
    assert card.extra["lancedb_synced"] is False


def test_memory_store_records_vector_sync_success(temp_project_root):
    class SuccessfulVectorSync:
        def sync(self, payload):
            return True

    store = FindingsMemoryStore(temp_project_root, vector_sync=SuccessfulVectorSync())
    card = FindingsCard(id="synced", title="Indexed Finding", kind="knowledge")

    path = Path(store.write(card))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["extra"]["lancedb_synced"] is True
    assert card.extra["lancedb_synced"] is True

def test_memory_list_recent(memory_store):
    """驗證最近記憶列表功能。"""
    for i in range(5):
        card = FindingsCard(id=f"k{i}", title=f"Card {i}", kind="knowledge")
        memory_store.write(card)
    
    recent = memory_store.list_recent(kind="knowledge", limit=3)
    assert len(recent) == 3
    assert recent[0].title == "Card 4"  # 最新的在前面

def test_memory_promotion(memory_store):
    """驗證記憶提升 (Task -> Global)。"""
    card = FindingsCard(id="p1", title="Global Rule", scope="task", kind="knowledge")
    memory_store.write(card)
    
    # 檢查 task 目錄
    task_path = memory_store.base_path / "task" / "knowledge" / "p1.json"
    assert task_path.exists()
    
    # 執行提升
    success = memory_store.promote_to_global("p1", kind="knowledge")
    assert success
    assert not task_path.exists()
    
    # 檢查 global 目錄
    global_path = memory_store.base_path / "global" / "knowledge" / "p1.json"
    assert global_path.exists()
    
    # 從全域讀取
    loaded = memory_store.read("p1", scope="global", kind="knowledge")
    assert loaded.scope == "global"

def test_keyword_search(memory_store):
    """驗證簡易語義/關鍵字檢索。"""
    card1 = FindingsCard(title="Transformer Rationale", tags=["nlp"], kind="knowledge")
    card2 = FindingsCard(title="ResNet Baseline", tags=["vision"], kind="knowledge")
    memory_store.write(card1)
    memory_store.write(card2)
    
    # 搜尋 "transformer"
    results = memory_store.search("transformer", kind="knowledge")
    assert len(results) == 1
    assert results[0].title == "Transformer Rationale"
    
    # 搜尋 tag "vision"
    results = memory_store.search("vision", kind="knowledge")
    assert len(results) == 1
    assert results[0].title == "ResNet Baseline"
