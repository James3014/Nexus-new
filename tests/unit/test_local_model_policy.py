import importlib


def test_local_model_policy_routes_search_phase_to_ollama_by_default(monkeypatch):
    monkeypatch.setenv("NEXUS_SEARCH_TIMEOUT_SECONDS", "120")
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="planning",
        context={"reasoning_mode": "ALGEBRAIC"},
    )

    assert decision["model"] == "qwen2.5-coder:7b"
    assert decision["reason_code"] == "scaffolding_speed_optimized_ollama"
    assert decision["timeout_seconds"] == 120


def test_local_model_policy_routes_reproduction_phase_to_ollama_by_default(monkeypatch):
    monkeypatch.setenv("NEXUS_REPRO_TIMEOUT_SECONDS", "180")
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="reproduction",
        context={"reasoning_mode": "ALGEBRAIC"},
    )

    assert decision["model"] == "qwen2.5-coder:7b"
    assert decision["reason_code"] == "repro_logic_extraction_ollama"
    assert decision["timeout_seconds"] == 180


def test_local_model_policy_routes_algebraic_patch_to_ollama_large_by_default(monkeypatch):
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="patch",
        context={"reasoning_mode": "ALGEBRAIC"},
    )

    assert decision["model"] == "qwen2.5-coder:14b"
    assert decision["reason_code"] == "algebraic_precision_requirement_ollama"
    assert decision["timeout_seconds"] == 420


def test_local_model_policy_routes_patch_retry_to_large_model(monkeypatch):
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="patch",
        context={"reasoning_mode": "INTUITIVE", "attempt": 2},
    )

    assert decision["model"] == "qwen2.5-coder:14b"
    assert decision["reason_code"] == "retry_precision_escalation_ollama"
    assert decision["timeout_seconds"] == 420


def test_local_model_policy_routes_name_sanity_retry_to_large_model(monkeypatch):
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="patch",
        context={
            "reasoning_mode": "INTUITIVE",
            "attempt": 1,
            "failure_reason": "NAME_SANITY_ERROR: duplicate class",
        },
    )

    assert decision["model"] == "qwen2.5-coder:14b"
    assert decision["reason_code"] == "name_sanity_retry_precision_ollama"
    assert decision["timeout_seconds"] == 420


def test_model_profile_resolution(monkeypatch):
    import nexus.engine.local_model_policy as policy_module
    importlib.reload(policy_module)
    LocalModelPolicy = policy_module.LocalModelPolicy

    # Test Qwen 7b profile options
    qwen_decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="planning",
        context={},
    )
    assert qwen_decision["model"] == "qwen2.5-coder:7b"
    assert qwen_decision["api_type"] == "generate"
    assert qwen_decision["ollama_options"]["temperature"] == 0.0
    assert qwen_decision["ollama_options"]["num_predict"] == 4096
    assert qwen_decision["ollama_options"]["num_ctx"] == 16384

    # Test Qwen 14b profile options
    qwen14b_decision = LocalModelPolicy.select_model(
        task_type="swe_repair",
        phase="patch",
        context={"attempt": 2},  # trigger escalation to large model
    )
    assert qwen14b_decision["model"] == "qwen2.5-coder:14b"
    assert qwen14b_decision["api_type"] == "generate"
    assert qwen14b_decision["ollama_options"]["temperature"] == 0.2
    assert qwen14b_decision["ollama_options"]["num_predict"] == 8192
    assert qwen14b_decision["ollama_options"]["num_ctx"] == 32768


def test_prompt_builder_adapts_to_model_characteristics():
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    # 預設 System Prompt
    default_prompt = PromptBuilder.build_patch_system_prompt()
    assert "Keep your thinking process extremely brief" not in default_prompt


def test_self_corrector_prevents_warning_accumulation():
    from nexus.services.local_heal.corrector import SelfCorrector
    from nexus.services.local_heal.errors import PatchError, PatchErrorKind

    corrector = SelfCorrector()
    base_prompt = "[TASK] Fix the bug"
    error = PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message="Syntax error at line 5")

    # 第一輪重試
    first_retry = corrector.build_retry_prompt(base_prompt, error)
    assert "⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]" in first_retry
    assert "Syntax error at line 5" in first_retry

    # 第二輪重試：傳入第一輪的 prompt，警告應該被「覆蓋/更新」而不是重複疊加
    new_error = PatchError(kind=PatchErrorKind.NAME_SANITY_ERROR, message="Duplicate definition")
    second_retry = corrector.build_retry_prompt(first_retry, new_error)
    
    # 斷言只出現一次標題，且內容被更新
    assert second_retry.count("⚠️ [NEXUS BATTLESUIT HUD: CRITICAL WARNING - PREVIOUS ATTEMPT FAILED]") == 1
    assert "Duplicate definition" in second_retry
    assert "Syntax error at line 5" not in second_retry

def test_gateway_ollama_options_downscaling_protection(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    # Mock missing engine modules to prevent import error in test environment
    sys.modules["nexus.engine.execution"] = MagicMock()
    sys.modules["nexus.engine.execution.phase_timer"] = MagicMock()
    sys.modules["nexus.engine.patch.apply_engine"] = MagicMock()
    
    monkeypatch.setenv("NEXUS_OLLAMA_NUM_CTX", "12288")
    from nexus.services.gateway import BattlesuitGateway
    
    gateway_inst = BattlesuitGateway.__new__(BattlesuitGateway)
    
    # 測試 7b
    options_7b = gateway_inst._ollama_options("qwen2.5-coder:7b")
    assert options_7b["num_ctx"] == 16384

    # 測試 14b
    options_14b = gateway_inst._ollama_options("qwen2.5-coder:14b")
    assert options_14b["num_ctx"] == 32768

    # 測試如果環境變數設為更大值 65536
    monkeypatch.setenv("NEXUS_OLLAMA_NUM_CTX", "65536")
    options_large_env = gateway_inst._ollama_options("qwen2.5-coder:14b")
    assert options_large_env["num_ctx"] == 65536


