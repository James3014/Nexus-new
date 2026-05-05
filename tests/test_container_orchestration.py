from pathlib import Path
import pytest
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
            mock_voice.assert_any_call(f"Nexus 啟動：偵測到 Bug {bug_id}", urgency="critical")
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


def test_container_engine_phases_all_resolved(tmp_path):
    """確認 P/X/D/R 四階段(以及 A/C 如果有)全部可從容器解析"""
    container = NexusContainer()
    container.project_root.override(tmp_path)
    container.run_dir.override(tmp_path / "run")
    engine = container.engine_factory()
    
    # 檢查核心四相
    assert "P" in engine.phases, "Missing Planner Phase"
    assert "X" in engine.phases or "D" in engine.phases, "Missing Execution/Diagnose Phase"
    assert "R" in engine.phases, "Missing Repair Phase"
    
    # 確保每一個階段都有必要的相依資源
    planner = engine.phases["P"]
    assert planner.predictor is not None

def test_container_orchestrator_returns_dict(tmp_path):
    """確認 run_review() 回傳 dict 不會退化回 bool"""
    container = NexusContainer()
    container.project_root.override(tmp_path)
    # 不直接跑 orchestrator，而是確保建構出的 orchestrator 類別符合契約
    from nexus.core.orchestrator import NexusOrchestrator
    import inspect
    sig = inspect.signature(NexusOrchestrator.run_review)
    assert sig.return_annotation == dict or sig.return_annotation == 'dict', "run_review 必須宣告回傳 dict"

def test_container_service_hubs_consistent(tmp_path):
    """確認 Hub 內的 service 與容器 singleton 為同一實例"""
    container = NexusContainer()
    container.project_root.override(tmp_path)
    container.run_dir.override(tmp_path / "run")
    
    intel_hub = container.intel_hub()
    memory_service = container.memory_service()
    
    # 驗證 IntelHub 內的 context_hub 其 memory_service 屬性與直接從容器拿出來的是同一個 (Singleton)
    assert intel_hub.context_hub.memory_service is memory_service, "Service Hub 沒有正確使用 Singleton"
    assert intel_hub.context_hub.prompt_builder is container.prompt_builder()
    assert intel_hub.context_hub.knowledge_injector is container.knowledge_injector()
    assert intel_hub.context_hub.belief_engine is container.belief_engine()
