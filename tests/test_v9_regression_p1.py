import os
import shutil
from pathlib import Path
import pytest
from nexus.engine.coordinator import NexusEngine
from nexus.containers import NexusContainer
from scripts.nexus_cli import NexusCLI

@pytest.fixture
def project_root(tmp_path):
    """建立一個乾淨的模擬專案根目錄。"""
    return tmp_path

def test_run_feature_has_single_finalize_path():
    """檢測 run_feature 是否存在重複的收尾邏輯塊。"""
    coord_path = Path("nexus/engine/coordinator.py")
    if not coord_path.exists():
        # Fallback for CI environments where the test might run from different CWD
        coord_path = Path(__file__).parent.parent / "nexus/engine/coordinator.py"
        
    content = coord_path.read_text()
    
    # 檢查是否還有重複的 Crystallize 標記 (應出現兩次：run_bug 與 run_feature 各一)
    assert content.count("# --- C Stage: Crystallize ---") == 2
    # 檢查是否已移除模擬信號
    assert "# --- Simulation Signal" not in content

def test_clean_does_not_delete_persistent_knowledge_assets(project_root):
    """驗證 nexus:clean 不會誤刪 .nexus/knowledge/ 內的資產。"""
    knowledge_dir = project_root / ".nexus" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    asset_file = knowledge_dir / "test_asset.txt"
    asset_file.write_text("knowledge is power")
    
    # 初始化 CLI 並注入模擬根目錄
    cli = NexusCLI(project_root=project_root)
    
    # 建立主目錄噪音
    (project_root / ".musestate").write_text("noise")
    (project_root / "plan.json").write_text("noise")
    
    # 執行真實 Clean (非 dry-run)
    cli.run_clean(dry_run=False)
    
    # 驗證資產存續
    assert asset_file.exists(), "❌ Knowledge asset was mistakenly deleted!"
    # 驗證噪音被清除
    assert not (project_root / ".musestate").exists(), "❌ Root noise .musestate was NOT deleted!"
    assert not (project_root / "plan.json").exists(), "❌ Root noise plan.json was NOT deleted!"

def test_nexus_metrics_tracking(project_root):
    """驗證 metrics 是否正確寫入 run_dir。"""
    run_dir = project_root / ".nexus" / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    from nexus.services.reporter import Reporter
    reporter = Reporter(project_root=project_root, run_dir=run_dir)
    
    test_metrics = {"tokens_used": 1500, "status": "PASS"}
    reporter.write_metrics(test_metrics)
    
    metrics_file = run_dir / ".nexus_metrics"
    assert metrics_file.exists()
    assert "1500" in metrics_file.read_text()
