from pathlib import Path
import os
import shutil
import pytest
from nexus.engine.coordinator import NexusEngine


@pytest.fixture
def project_root(tmp_path):
    """建立一個乾淨的模擬專案根目錄。"""
    return tmp_path

def test_run_feature_has_single_finalize_path():
    """檢測收尾邏輯是否已模組化並保持單一路徑。"""
    pipeline_path = Path("nexus/engine/pipeline.py")
    if not pipeline_path.exists():
        pipeline_path = Path(__file__).parent.parent / "nexus/engine/pipeline.py"
        
    content = pipeline_path.read_text()
    
    # 檢查是否已在 pipeline 中定義 Crystallize 標記 (應出現一次)
    assert content.count("# --- C Stage: Crystallize ---") == 1
    
    # 檢查 coordinator 是否已不再包含重複邏輯
    coord_path = Path("nexus/engine/coordinator.py")
    if not coord_path.exists():
        coord_path = Path(__file__).parent.parent / "nexus/engine/coordinator.py"
    coord_content = coord_path.read_text()
    assert "# --- C Stage: Crystallize ---" not in coord_content


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
