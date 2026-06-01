import importlib


def test_local_model_policy_routes_search_phase_to_ollama_by_default(monkeypatch):
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
    assert decision["timeout_seconds"] == 600
