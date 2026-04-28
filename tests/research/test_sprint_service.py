from pathlib import Path

from nexus.research.sprint_service import (
    CandidateEval,
    InPlaceSprintExecutor,
    SprintConfig,
    _build_llm_candidate_prompt,
    _build_value_task_contract,
    _candidate_code_from_llm_output,
    _select_candidate_with_routing_layers,
    run_hyper_sprint,
    write_sprint_report,
)


def _write_ready_learn_slo(tmp_path: Path) -> None:
    phase_slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    phase_slo.parent.mkdir(parents=True, exist_ok=True)
    phase_slo.write_text(
        '{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}',
        encoding="utf-8",
    )


def test_select_candidate_with_routing_layers_uses_autoreason_and_ddtree(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTOREASON_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_DDTREE_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_DDTREE_MAX_CANDIDATES", "2")
    learning_trace = {}
    candidates = [
        CandidateEval(seed=1, score=0.2, source="local", hint="weak"),
        CandidateEval(seed=2, score=0.8, source="llm", hint="better", stdout="pytest passed"),
        CandidateEval(seed=3, score=0.5, source="local", hint="middle"),
    ]

    best, active = _select_candidate_with_routing_layers(
        candidates,
        task="fix hard bug",
        learning_trace=learning_trace,
    )

    assert best.seed == 2
    assert [item.seed for item in active] == [2, 3]
    assert learning_trace["ddtree"]["actual_saved_steps"] == 1
    assert learning_trace["autoreason"]["enabled"] is True
    assert learning_trace["autoreason"]["winner"] == "llm:2"


def test_select_candidate_with_routing_layers_uses_config_flags_without_env(monkeypatch):
    monkeypatch.delenv("NEXUS_AUTOREASON_EXECUTOR", raising=False)
    monkeypatch.delenv("NEXUS_DDTREE_EXECUTOR", raising=False)
    learning_trace = {}
    candidates = [
        CandidateEval(seed=1, score=0.2, source="local", hint="weak"),
        CandidateEval(seed=2, score=0.8, source="llm", hint="better", stdout="pytest passed"),
        CandidateEval(seed=3, score=0.5, source="local", hint="middle"),
    ]

    best, active = _select_candidate_with_routing_layers(
        candidates,
        task="repair timeout",
        learning_trace=learning_trace,
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        ddtree_max_candidates=2,
    )

    assert best.seed == 2
    assert [item.seed for item in active] == [2, 3]
    assert learning_trace["ddtree"]["enabled"] is True
    assert learning_trace["autoreason"]["enabled"] is True


def test_run_hyper_sprint_collects_pool_when_route_enables_ddtree(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "local"

        def generate(self, *_args, seed=0, **_kwargs):
            return f"print({seed})\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            seed = kwargs["seed"]
            return CandidateEval(
                seed=seed,
                score=1.0,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
                stdout="pytest passed" if seed == 2 else "",
            )

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(
        task="repair timeout",
        target_file="demo.py",
        candidate_count=3,
        llm_mode=False,
        safe_mode=True,
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        ddtree_max_candidates=2,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.attempt_count == 2
    assert res.learning_trace["ddtree"]["eligible"] is True
    assert res.learning_trace["ddtree"]["actual_saved_steps"] == 1
    assert res.learning_trace["autoreason"]["enabled"] is True


def test_run_hyper_sprint_success_local(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=2, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.winner_source == "local"
    assert res.model_calls == 0
    assert res.total_tokens == 0
    assert res.token_capture_status == "not_applicable_local_only"
    assert res.promotable is True
    assert res.attempt_count == 1
    assert "retrieval_hits" in res.learning_trace


def test_run_hyper_sprint_collects_error_codes(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "untrusted_test"

        def generate(self, *args, **kwargs):
            return "print('y')\n", {"source": "untrusted_test", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=0.0,
                candidate_code="print('x')\n",
                source=kwargs["source"],
                error="command timed out after 20 seconds",
            )

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "FAILED"
    assert "test_timeout" in res.error_codes
    assert "stage1_failed" in res.error_codes


def test_run_hyper_sprint_semantic_guard_for_feature(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "untrusted_test"

        def generate(self, *args, **kwargs):
            return "print('y')\n", {"source": "untrusted_test", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **_kwargs):
            raise AssertionError("Executor should not be called when semantic guard rejects candidate")

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="implement parser", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "FAILED"
    assert "semantic_guard" in res.error_codes
    assert res.rejection_summary.get("semantic_guard_low_delta_feature", 0) >= 1


def test_run_hyper_sprint_learning_trace_persist_path(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    class FakeStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def search(self, *_args, **_kwargs):
            return []

        def write(self, *_args, **_kwargs):
            return "ok"

    class FakePalace:
        def __init__(self, *_args, **_kwargs):
            pass

        def verify(self, cards):
            return cards

        def trigger_arweave_distillation(self, _data):
            return "ARW-test"

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)
    monkeypatch.setattr("nexus.research.findings_memory.FindingsMemoryStore", FakeStore)
    monkeypatch.setattr("nexus.services.mem_palace.MemPalace", FakePalace)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.learning_trace.get("mempalace_verified") is True
    assert res.learning_trace.get("memory_written") is True
    assert res.learning_trace.get("arweave_tx_id") == "ARW-test"
    assert res.learning_trace.get("learn_phase_bridge", {}).get("entries_written") == 6


def test_write_sprint_report(tmp_path: Path):
    target = tmp_path / "x.py"
    target.write_text("print('x')\n", encoding="utf-8")
    cfg = SprintConfig(task="x", target_file="x.py")
    # minimal run path with monkeypatch-free failure due to missing swarm dirs still yields reportable result
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    report_path = write_sprint_report(repo_root=tmp_path, result=res, report_file=".nexus/reports/research/sprint-test.json")
    assert report_path.exists()
    assert "sprint-test.json" in str(report_path)


def test_llm_quota_falls_back_to_local(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            raise RuntimeError("HTTP 429 quota exhausted")

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.winner_source == "local"
    assert "quota" in res.error_codes
    assert "llm_fallback_local" in res.error_codes
    assert res.total_tokens == 0


def test_llm_mode_propagates_token_observability(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {
                "source": "llm",
                "model_calls": 1,
                "quota_backoffs": 0,
                "tokens_used": 222,
                "token_capture_status": "measured",
                "gateway_stats_present": True,
                "gateway_usage_metadata_present": False,
                "gateway_token_source": "stats",
                "gateway_prompt_chars": 10,
                "gateway_payload_chars": 20,
                "gateway_total_chars": 30,
                "gateway_timeout_sec": 60,
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.total_tokens == 222
    assert res.token_capture_status == "measured"
    assert res.gateway_stats_present is True
    assert res.gateway_usage_metadata_present is False
    assert res.gateway_token_source == "stats"
    assert res.gateway_prompt_chars == 10
    assert res.gateway_payload_chars == 20
    assert res.gateway_total_chars == 30
    assert res.gateway_timeout_sec == 60


def test_compact_gateway_prompt_is_shorter(monkeypatch):
    source = "def normalize_flag(text):\n    return text\n"
    full = _build_llm_candidate_prompt(source_code=source, task="Fix flaky websocket timeout", mutation_hint="baseline")
    monkeypatch.setenv("NEXUS_GATEWAY_COMPACT_PROMPT", "1")
    compact = _build_llm_candidate_prompt(source_code=source, task="Fix flaky websocket timeout", mutation_hint="baseline")

    assert len(compact) < len(full)
    assert "target_snippet" in compact
    assert source in compact


def test_llm_candidate_prompt_can_include_tests(monkeypatch):
    source = "def normalize_flag(text):\n    return text\n"
    tests = "def test_normalize_flag():\n    assert normalize_flag(' YES ') == 'yes'\n"
    full = _build_llm_candidate_prompt(
        source_code=source,
        task="Fix text normalization",
        mutation_hint="baseline",
        test_source=tests,
    )
    monkeypatch.setenv("NEXUS_GATEWAY_COMPACT_PROMPT", "1")
    compact = _build_llm_candidate_prompt(
        source_code=source,
        task="Fix text normalization",
        mutation_hint="baseline",
        test_source=tests,
    )

    assert "[CURRENT TESTS]" in full
    assert tests in full
    assert "Tests:" in compact
    assert tests in compact
    assert "patch=<full updated target file>" in compact


def test_value_task_contract_includes_artifact_and_override_rules():
    artifact_contract = _build_value_task_contract(
        source_code="def verified_claims(claims):\n    pass\n",
        task="Fix artifact claim rollup",
        test_source="assert verified_claims([{'id':'a','artifact':'x'}]) == ['a']",
    )
    override_contract = _build_value_task_contract(
        source_code="def merge_limits(defaults, override):\n    pass\n",
        task="Fix override handling",
        test_source="assert merge_limits({'timeout': 10}, {'timeout': None}) == {'timeout': 10}",
    )

    assert "Use singular field 'artifact'" in artifact_contract
    assert "return the claim ids" in artifact_contract
    assert "preserve the existing default" in override_contract


def test_hidden_verifier_mode_omits_initial_test_source(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def normalize(text):\n    return text\n", encoding="utf-8")
    test_file = tmp_path / "test_demo.py"
    test_file.write_text("def test_contract():\n    assert True\n", encoding="utf-8")
    captured: dict[str, str] = {}

    class FakeGenerator:
        def generate(self, *, source_code, task, mutation_hint, seed, test_source=""):
            captured["test_source"] = test_source
            raise RuntimeError("stop")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FakeGenerator())

    cfg = SprintConfig(
        task="fix hidden verifier",
        target_file=str(target),
        test_file=str(test_file),
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert captured["test_source"] == ""


def test_llm_edit_protocol_replaces_unique_snippet():
    source = "def normalize(text):\n    return text\n"
    code, reason = _candidate_code_from_llm_output(
        source,
        {
            "operation": "replace",
            "target_snippet": "return text",
            "replacement": "return text.strip().lower()",
        },
    )

    assert reason == ""
    assert code == "def normalize(text):\n    return text.strip().lower()\n"


def test_llm_edit_protocol_accepts_full_patch_operation():
    source = "def normalize(text):\n    return text\n"
    code, reason = _candidate_code_from_llm_output(
        source,
        {
            "operation": "full_patch",
            "replacement": "def normalize(text):\n    return text.strip().lower()\n",
        },
    )

    assert reason == ""
    assert code == "def normalize(text):\n    return text.strip().lower()\n"


def test_llm_edit_protocol_rejects_ambiguous_snippet():
    source = "x = 1\nx = 1\n"
    code, reason = _candidate_code_from_llm_output(
        source,
        {
            "operation": "replace",
            "target_snippet": "x = 1",
            "replacement": "x = 2",
        },
    )

    assert code is None
    assert reason == "llm_target_snippet_not_unique"


def test_llm_generator_applies_edit_protocol(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def normalize(text):\n    return text\n", encoding="utf-8")
    captured = {}

    class FakeGateway:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_structured(self, **kwargs):
            captured["payload"] = kwargs["payload"]
            captured["schema"] = kwargs["output_schema"]
            return (
                {
                    "status": "APPROVED",
                    "operation": "replace",
                    "target_snippet": "return text",
                    "replacement": "return text.strip().lower()",
                    "tokens_used": 55,
                    "token_capture_status": "measured",
                    "gateway_stats_present": True,
                    "gateway_token_source": "stats",
                },
                "{}",
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            assert kwargs["code"] == "def normalize(text):\n    return text.strip().lower()\n"
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix normalize", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_patch_generated is True
    assert res.gateway_token_source == "stats"
    assert "one small edit" in captured["payload"]
    assert "target_snippet" in captured["schema"]


def test_llm_mode_estimates_tokens_when_gateway_stats_missing(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGateway:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_structured(self, **_kwargs):
            return (
                {
                    "status": "APPROVED",
                    "patch": "print('ok')\n",
                    "tokens_used": 0,
                    "token_capture_status": "unknown",
                    "gateway_stats_present": False,
                    "gateway_usage_metadata_present": False,
                    "gateway_token_source": "missing",
                    "gateway_prompt_chars": 11,
                    "gateway_payload_chars": 22,
                    "gateway_total_chars": 33,
                    "gateway_timeout_sec": 7,
                },
                "print('ok')\n",
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.total_tokens > 0
    assert res.token_capture_status in {"measured", "estimated"}
    assert res.gateway_token_source == "missing"
    assert res.gateway_total_chars == 33
    assert res.gateway_timeout_sec == 7


def test_llm_failure_preserves_gateway_token_source(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGateway:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_structured(self, **_kwargs):
            return (
                {
                    "status": "FAIL",
                    "summary": "no patch",
                    "tokens_used": 333,
                    "token_capture_status": "measured",
                    "gateway_stats_present": True,
                    "gateway_usage_metadata_present": False,
                    "gateway_token_source": "stats",
                    "gateway_prompt_chars": 44,
                    "gateway_payload_chars": 55,
                    "gateway_total_chars": 99,
                    "gateway_timeout_sec": 12,
                },
                "{}",
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.total_tokens == 333
    assert res.token_capture_status == "measured"
    assert res.gateway_stats_present is True
    assert res.gateway_token_source == "stats"
    assert res.gateway_total_chars == 99
    assert res.gateway_timeout_sec == 12
    assert res.fallback_used is True


def test_llm_model_name_can_be_overridden(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    captured = {}

    class FakeGateway:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_structured(self, **kwargs):
            captured["model_name"] = kwargs["model_name"]
            return (
                {"status": "APPROVED", "patch": "print('ok')\n", "tokens_used": 5, "token_capture_status": "measured"},
                "print('ok')\n",
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3.1-pro-preview")
    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert captured["model_name"] == "gemini-3.1-pro-preview"
    assert res.model_name == "gemini-3.1-pro-preview"
    assert res.model_patch_generated is True


def test_llm_gateway_fail_payload_falls_back_to_local(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeGateway:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_structured(self, **_kwargs):
            return (
                {"status": "FAIL", "summary": "Gateway Exhausted: TIMEOUT", "error_category": "timeout"},
                "TIMEOUT",
            )

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.total_tokens > 0
    assert res.token_capture_status == "estimated"
    assert res.gateway_error_category == "timeout"
    assert res.winner_source == "local"
    assert "llm_error" in res.error_codes


def test_llm_self_heal_repairs_failed_candidate(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def normalize(text):\n    return text\n", encoding="utf-8")
    calls = {"llm": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            calls["llm"] += 1
            if calls["llm"] == 1:
                return "def normalize(text):\n    return text.strip()\n", {
                    "source": "llm",
                    "model_calls": 1,
                    "quota_backoffs": 0,
                    "tokens_used": 10,
                    "token_capture_status": "measured",
                    "gateway_token_source": "stats",
                    "model_patch_generated": True,
                }
            assert "Previous candidate failed verification" in kwargs["task"]
            return "def normalize(text):\n    return text.strip().lower()\n", {
                "source": "llm",
                "model_calls": 1,
                "quota_backoffs": 0,
                "tokens_used": 20,
                "token_capture_status": "measured",
                "gateway_token_source": "stats",
                "model_patch_generated": True,
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            if "lower()" in kwargs["code"]:
                return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])
            return CandidateEval(
                seed=kwargs["seed"],
                score=0.4,
                stdout="expected lower-case normalized text",
                candidate_code=kwargs["code"],
                source=kwargs["source"],
            )

    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix normalize", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls["llm"] == 2
    assert res.model_calls == 2
    assert res.total_tokens == 30
    assert res.winner_source == "llm_self_heal"
    assert "llm_self_heal_attempted" in res.error_codes
    assert len(res.candidates) == 2


def test_llm_self_heal_runs_before_local_guard_fallback(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def build():\n    return []\n", encoding="utf-8")
    calls = {"llm": 0, "local": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            calls["llm"] += 1
            if calls["llm"] == 1:
                return "def build():\n    return []\n", {
                    "source": "llm",
                    "model_calls": 1,
                    "tokens_used": 10,
                    "token_capture_status": "measured",
                    "model_patch_generated": True,
                }
            assert "Previous candidate failed verification" in kwargs["task"]
            return "def build():\n    items = ['artifact']\n    return items\n", {
                "source": "llm",
                "model_calls": 1,
                "tokens_used": 20,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            calls["local"] += 1
            return "def build():\n    return ['local']\n", {"source": "local"}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            score = 1.0 if "artifact" in kwargs["code"] else 0.0
            return CandidateEval(seed=kwargs["seed"], score=score, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="add feature artifact", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.winner_source == "llm_self_heal"
    assert calls == {"llm": 2, "local": 0}


def test_contract_feature_allows_one_line_artifact_fix(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def verified_claims(claims):\n    return []\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "def verified_claims(claims):\n    return [claim['id'] for claim in claims if claim.get('artifact')]\n", {
                "source": "llm",
                "model_calls": 1,
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(
        task="Implement an evidence artifact claim rollup",
        target_file="demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.winner_source == "llm"


def test_failed_local_fallback_gets_emergency_baseline_attempt(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    calls = {"local": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            raise RuntimeError("gateway_error")

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            calls["local"] += 1
            return f"print('local-{calls['local']}')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            score = 1.0 if kwargs["hint"] == "emergency_fallback" else 0.4
            return CandidateEval(seed=kwargs["seed"], score=score, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls["local"] == 2
    assert res.attempt_count == 2


def test_local_contract_fallback_repairs_phase_evidence_fields(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def phase_ready(phase):\n    return phase.get('status') == 'pass'\n", encoding="utf-8")
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "\n".join(
            [
                "from demo import phase_ready",
                "",
                "def test_phase_contract():",
                "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True",
                "    assert phase_ready({'status': 'pass', 'reason': ''}) is False",
                "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': 'missing'}) is False",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "def phase_ready(phase):\n    return phase.get('status') == 'pass'\n", {
                "source": "llm",
                "model_calls": 1,
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)

    cfg = SprintConfig(
        task="Implement a phased report summary where each phase must include status, evidence path, and failure reason before verified.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.fallback_used is True
    assert res.winner_source == "local"


def test_llm_mode_blocked_by_learn_slo_guard(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert "learn_slo_block" in res.error_codes
    assert res.learning_trace.get("learn_slo_guard", {}).get("active") is True


def test_benchmark_can_force_llm_despite_learn_slo_guard(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {
                "source": "llm",
                "model_calls": 1,
                "quota_backoffs": 0,
                "tokens_used": 111,
                "token_capture_status": "measured",
            }

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setenv("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.total_tokens == 111
    assert "learn_slo_block" not in res.error_codes
    assert res.learning_trace.get("learn_slo_guard", {}).get("reason") == "benchmark_force_llm_despite_learn_slo"


def test_llm_mode_can_force_inplace_executor(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    calls = {"inplace": 0, "swarm": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {
                "source": "llm",
                "model_calls": 1,
                "quota_backoffs": 0,
                "tokens_used": 1,
                "token_capture_status": "measured",
            }

    class FakeInPlaceExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["inplace"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    class FakeSwarmExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["swarm"] += 1

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeInPlaceExecutor)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeSwarmExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls == {"inplace": 1, "swarm": 0}


def test_local_mode_uses_inplace_executor(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    calls = {"inplace": 0, "swarm": 0}

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeInPlaceExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["inplace"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    class FakeSwarmExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["swarm"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeInPlaceExecutor)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeSwarmExecutor)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert calls["inplace"] == 1
    assert calls["swarm"] == 0


def test_inplace_executor_rejects_no_change_candidate(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    ex = InPlaceSprintExecutor(
        repo_root=tmp_path,
        target_file="demo.py",
        pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1"],
        timeout_sec=5,
    )
    ev = ex.evaluate_candidate(seed=0, hint="h", code="print('x')\n", source="local")
    assert ev.score == 0.2
    assert ev.error == "no_change_candidate"


def test_inplace_executor_rejects_syntax_error(tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    ex = InPlaceSprintExecutor(
        repo_root=tmp_path,
        target_file="demo.py",
        pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1"],
        timeout_sec=5,
    )
    ev = ex.evaluate_candidate(seed=0, hint="h", code="def broken(:\n    pass\n", source="local")
    assert ev.score == 0.0
    assert ev.error.startswith("syntax_error:")
