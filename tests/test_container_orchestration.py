import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from nexus.containers import NexusContainer
from nexus.core.state_contracts import NexusState

def test_container_full_orchestration(tmp_path):
    """
    🧪 E2E Integration: 驗證容器依賴鏈與引擎執行的完整性。
    此測試會從 NexusContainer 解析引擎，並模擬執行一次 run_bug。
    """
    # 1. 初始化容器
    container = NexusContainer()
    container.project_root.override(tmp_path)
    container.run_dir.override(tmp_path / "run")
    
    # 2. Mock 外部服務以避免實際調用
    mock_llm = MagicMock()
    # 模擬 LLM 返回 PASS
    mock_llm.ask.return_value = ({"status": "PASS", "tokens_used": 100, "summary": "Test pass"}, "Raw output")
    mock_llm.ask_with_template.return_value = ({"status": "PASS", "tokens_used": 100, "summary": "Test pass"}, "Raw output")
    
    container.llm.override(mock_llm)
    
    # 3. 解析引擎
    engine = container.engine_factory()
    
    # 🕵️ 驗證依賴是否正確注入
    assert engine.reporter is not None
    assert engine.phases.get("P") is not None
    assert engine.phases.get("P").predictor is not None
    
    # 4. 模擬執行 run_bug
    # 我們 mock 一些會產生副作用的 method
    with patch.object(engine.reporter, 'voice_notify') as mock_voice:
        with patch.object(engine.reporter, 'log_trace') as mock_trace:
            # 建立一個測試 bug
            bug_id = "ISSUE-999"
            desc = "Test deep integration"
            
            # 執行 (會走到 P -> X/D -> R)
            # 這裡我們只驗證 P 階段是否能跑完且 reporter 有動作
            engine.run_bug(bug_id, desc)
            
            # 5. 斷言驗證
            mock_voice.assert_any_call(f"Nexus 啟動：偵測到 Bug {bug_id}")
            # coordinator.py:67: self._log_trace("run_bug", bug_id, "START")
            # which calls reporter.log_trace("run_bug", bug_id, "START", 0, 0.0)
            mock_trace.assert_any_call("run_bug", bug_id, "START", 0, 0.0)
            
            # 檢查檔案建立
            assert engine.state_io.state_file.exists()

def test_memory_service_integration(tmp_path):
    """驗證 MemoryService 是否能被 ContextHub 正確調用。"""
    container = NexusContainer()
    container.project_root.override(tmp_path)
    
    hub = container.context_hub()
    memory = container.memory_service()
    
    # 模擬記憶寫入
    reminders_file = tmp_path / "reminders.json"
    with patch.object(memory, 'cached_search') as mock_search:
        mock_search.return_value = [{"id": "m1", "content": "Memory test"}]
        
        # 觸發注入
        # hub._inject_memory_reminders("P") # Private method call for deep test
        hub._inject_memory_reminders("P")
        
        mock_search.assert_called_once()
