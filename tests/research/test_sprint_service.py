from pathlib import Path

from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.research.sprint_service import (
    CandidateEval,
    InPlaceSprintExecutor,
    LLMCandidateGenerator,
    SprintConfig,
    _build_llm_candidate_prompt,
    _build_value_task_contract,
    _candidate_code_from_llm_output,
    _select_candidate_with_routing_layers,
    _should_try_local_preflight_before_llm,
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


def test_select_candidate_with_routing_layers_keeps_verified_candidate_over_shadow(monkeypatch):
    monkeypatch.delenv("NEXUS_DDTREE_EXECUTOR", raising=False)
    learning_trace = {}
    candidates = [
        CandidateEval(seed=0, score=1.0, source="llm", hint="verified patch"),
        CandidateEval(
            seed=1000,
            score=0.4,
            source="local_hidden_shadow",
            hint="very specific shadow verifier evidence " * 8,
            stdout="pytest failure evidence\n" * 20,
        ),
    ]

    best, active = _select_candidate_with_routing_layers(
        candidates,
        task="implement artifact-backed claim verification",
        learning_trace=learning_trace,
        enable_autoreason_executor=True,
        enable_ddtree_executor=False,
    )

    assert best.source == "llm"
    assert [item.source for item in active] == ["llm", "local_hidden_shadow"]
    assert learning_trace["autoreason"]["winner"] == "local_hidden_shadow:1000"
    assert learning_trace["autoreason"]["winner_overridden_by_score_guard"] is True
    assert learning_trace["autoreason"]["score_guard_winner"] == "llm:0"


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
            score = 1.0 if seed == 2 else (0.8 if seed == 0 else 0.5)
            return CandidateEval(
                seed=seed,
                score=score,
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


def test_run_hyper_sprint_uses_local_support_pool_for_ddtree_cost_cap(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    llm_calls: list[int] = []

    class FakeLLMGenerator:
        model_chain = ["gemini-3-flash-preview"]

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *_args, seed=0, **_kwargs):
            llm_calls.append(seed)
            return "print('llm')\n", {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 17,
                "token_capture_status": "measured",
            }

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *_args, seed=0, **_kwargs):
            return f"print('support-{seed}')\n", {"source": "local", "model_calls": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            stdout = "pytest passed" if kwargs["source"] == "llm" else ""
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
                stdout=stdout,
            )

    monkeypatch.setenv(
        "NEXUS_ROUTE_COST_CONTROLS",
        '{"ddtree_mixed_candidate_pool": true, "candidate_cap": 3, "context_mode": "compact"}',
    )
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "0")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    _write_ready_learn_slo(tmp_path)

    cfg = SprintConfig(
        task="repair ddtree route oracle",
        target_file="demo.py",
        candidate_count=3,
        llm_mode=True,
        safe_mode=True,
        enable_autoreason_executor=False,
        enable_ddtree_executor=True,
        ddtree_max_candidates=2,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert llm_calls == [0]
    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.winner_source == "llm"
    assert res.learning_trace["candidate_pool_policy"]["enabled"] is True
    assert res.learning_trace["ddtree"]["eligible"] is True
    assert res.learning_trace["ddtree"]["actual_saved_steps"] == 1
    assert "llm:0" in res.learning_trace["ddtree"]["selected_candidate_ids"]


def test_run_hyper_sprint_uses_local_support_pool_for_autoreason_cost_cap(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    llm_calls: list[int] = []

    class FakeLLMGenerator:
        model_chain = ["gemini-3-flash-preview"]

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *_args, seed=0, **_kwargs):
            llm_calls.append(seed)
            return "print('llm')\n", {
                "source": "llm",
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "tokens_used": 17,
                "token_capture_status": "measured",
            }

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *_args, seed=0, **_kwargs):
            return f"print('support-{seed}')\n", {"source": "local", "model_calls": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(
                seed=kwargs["seed"],
                score=1.0,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
                stdout="pytest passed",
            )

    monkeypatch.setenv(
        "NEXUS_ROUTE_COST_CONTROLS",
        '{"autoreason_mixed_candidate_pool": true, "context_mode": "compact"}',
    )
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "0")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    _write_ready_learn_slo(tmp_path)

    cfg = SprintConfig(
        task="repair autoreason route oracle",
        target_file="demo.py",
        candidate_count=3,
        llm_mode=True,
        safe_mode=True,
        enable_autoreason_executor=True,
        enable_ddtree_executor=False,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert llm_calls == [0]
    assert res.status == "SUCCESS"
    assert res.model_calls == 1
    assert res.winner_source == "llm"
    assert res.learning_trace["candidate_pool_policy"]["enabled"] is True
    assert res.learning_trace["autoreason"]["enabled"] is True
    assert res.learning_trace["autoreason"]["winner"] == "llm:0"


def test_run_hyper_sprint_applies_distant_scout_hint(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")
    hints = []

    class FakeGenerator:
        source = "local"

        def generate(self, *_args, seed=0, **kwargs):
            hints.append(kwargs["mutation_hint"])
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(
        task="repair timeout",
        target_file="demo.py",
        candidate_count=1,
        llm_mode=False,
        safe_mode=True,
        distant_scout_plan={
            "status": "READY",
            "recommended_family": "flow:architecture_timeout_policy_seam",
            "forbidden_families": ["flow:retry_delay"],
            "target_boundary": "repair_timeout_policy",
        },
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert "distant_scout_recommended_family=flow:architecture_timeout_policy_seam" in hints[0]
    assert "distant_scout_forbidden_families=flow:retry_delay" in hints[0]
    assert res.learning_trace["distant_scout_execution"]["applied"] is True


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


def test_should_try_local_preflight_before_llm_skips_claim_evidence_contracts():
    assert (
        _should_try_local_preflight_before_llm(
            task="Fix claim verification so only fully supported successful claims are accepted.",
            source_code="def verified_claims(claims):\n    return claims\n",
        )
        is False
    )


def test_should_try_local_preflight_before_llm_keeps_deterministic_contracts():
    assert (
        _should_try_local_preflight_before_llm(
            task="Repair secret redaction for a credential scrubber.",
            source_code="def redact(secret):\n    return secret\n",
        )
        is True
    )


def test_should_try_local_preflight_before_llm_keeps_governance_action_filter():
    assert (
        _should_try_local_preflight_before_llm(
            task="Repair governance action filter; reason governance_block for destructive actions.",
            source_code="def rlm_harder_v2_filter_action(action):\n    return {'allowed': True, 'reason': 'ok'}\n",
        )
        is True
    )


def test_should_try_local_preflight_before_llm_keeps_rlm_evidence_memory_and_second_round_contracts():
    assert _should_try_local_preflight_before_llm(
        task="Repair RLM evidence gap.",
        source_code="def rlm_harder_v2_verified_claims(claims):\n    return []\n",
    )
    assert _should_try_local_preflight_before_llm(
        task="Repair RLM evidence replay.",
        source_code="def rlm_harder_v2_accept_receipt(receipt):\n    return True\n",
    )
    assert _should_try_local_preflight_before_llm(
        task="Repair memory selection.",
        source_code="def rlm_harder_v2_select_memory_hits(items, task_type, keywords):\n    return items\n",
    )
    assert _should_try_local_preflight_before_llm(
        task="Repair second round settings merge.",
        source_code="def rlm_harder_v2_merge_settings(defaults, override):\n    return defaults\n",
    )
    assert _should_try_local_preflight_before_llm(
        task="Repair governance scope decision.",
        source_code="def rlm_harder_v2_scope_decision(request):\n    return {'allowed': True, 'reason': 'approved'}\n",
    )
    assert _should_try_local_preflight_before_llm(
        task="Repair belief budget selection.",
        source_code="def rlm_harder_v2_repair_budget(confidence, risk):\n    return {'rounds': 1, 'needs_evidence': False}\n",
    )


def test_local_mutator_patches_rlm_governance_filter_action():
    source = "def rlm_harder_v2_filter_action(action):\n    return {'allowed': True, 'reason': 'ok'}\n"

    patched = generate_local_candidate(
        source,
        task="Repair governance action filter; block destructive tools and forbidden paths.",
        mutation_hint="local_preflight_before_llm",
        seed=0,
    )
    namespace: dict[str, object] = {}
    exec(patched, namespace)
    fn = namespace["rlm_harder_v2_filter_action"]

    assert fn({"tool": "read_file"}) == {"allowed": True, "reason": "ok"}
    assert fn({"tool": "run_command", "cmd": "rm -rf .nexus"}) == {
        "allowed": False,
        "reason": "governance_block",
    }
    assert fn({"tool": "delete_file", "path": "logs/run.json"}) == {
        "allowed": False,
        "reason": "governance_block",
    }
    assert fn({"tool": "write_file", "path": "benchmarks/result.json"}) == {
        "allowed": False,
        "reason": "governance_block",
    }


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


def test_run_hyper_sprint_rejects_hidden_verifier_placeholder_only(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("def accept(report):\n    return True\n", encoding="utf-8")

    class FakeGenerator:
        source = "local_hidden_shadow"

        def generate(self, *args, **kwargs):
            return (
                "def accept(report):\n    return True\n\n"
                "# Structural placeholder for feature/refactor\n"
                "_NEXUS_TASK_SENTINEL = 123\n",
                {"source": "local_hidden_shadow", "model_calls": 0, "quota_backoffs": 0},
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **_kwargs):
            raise AssertionError("placeholder-only candidates must be rejected before pytest")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="Fix hidden report_path contract", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "FAILED"
    assert "semantic_guard" in res.error_codes
    assert res.rejection_summary.get("semantic_guard_placeholder_only", 0) >= 1


def test_run_hyper_sprint_rejects_syntax_warning_candidate(monkeypatch, tmp_path: Path):
    target = tmp_path / "demo.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")

    class FakeGenerator:
        source = "llm"

        def generate(self, *args, **kwargs):
            return (
                "def value():\n"
                "    try:\n"
                "        return 1\n"
                "    finally:\n"
                "        return 2\n",
                {"source": "llm", "model_calls": 1, "quota_backoffs": 0},
            )

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **_kwargs):
            raise AssertionError("SyntaxWarning candidates must be rejected before pytest")

    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix value", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "FAILED"
    assert "semantic_guard" in res.error_codes
    assert res.rejection_summary.get("semantic_guard_syntax_warning", 0) >= 1


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


def test_hidden_verifier_shadow_can_be_disabled_for_model_required_benchmark(monkeypatch, tmp_path: Path):
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
                "tokens_used": 42,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    class FakeLocalGenerator:
        source = "local_hidden_shadow"

        def generate(self, *args, **kwargs):
            raise AssertionError("model-required benchmark must not replace LLM delivery with hidden shadow")

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.winner_source == "llm"
    assert res.fallback_used is False
    assert res.model_calls == 1


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


def test_value_task_contract_includes_nightshift_report_path_rule():
    contract = _build_value_task_contract(
        source_code="def rlm_harder_v2_accept_nightshift(report):\n    pass\n",
        task="Accept Nightshift recovery only when escalation was invoked, recovered, and produced a report path.",
        test_source=(
            "assert rlm_harder_v2_accept_nightshift({'recommended': True, 'invoked': True, "
            "'recovered': True, 'report_path': 'reports/nightshift.json'}) is True"
        ),
    )

    assert "non-empty report_path" in contract
    assert "Reject boolean-only Nightshift recovery" in contract


def test_value_task_contract_names_parse_config_defaults():
    contract = _build_value_task_contract(
        source_code="def parse_config(data):\n    return {'strict': bool(data.get('strict', False)), 'retries': data.get('retries', 0)}\n",
        task="Sync configuration docs and strict parser defaults where history-like examples conflict with the new canonical behavior.",
        test_source="assert parse_config({}) == {'strict': True, 'retries': 3}",
    )

    assert "strict=True and retries=3" in contract
    assert "explicit inputs are preserved" in contract


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


def test_llm_generator_uses_unified_runtime_on_revisioned_workspace(monkeypatch, tmp_path: Path):
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True)
    monkeypatch.setattr(generator, "_workspace_revision", lambda: "revision-001")
    monkeypatch.setattr(
        generator.gateway,
        "ask_structured",
        lambda *_args, **_kwargs: (
            {
                "status": "APPROVED",
                "operation": "replace",
                "target_snippet": "return text",
                "replacement": "return text.strip()",
            },
            "raw-candidate",
        ),
    )

    code, metadata = generator.generate(
        source_code="def normalize(text):\n    return text\n",
        task="fix normalize",
        mutation_hint="strip whitespace",
        seed=7,
    )

    receipt = metadata["unified_runtime_receipt"]
    assert code == "def normalize(text):\n    return text.strip()\n"
    assert receipt["schema"] == "nexus.unified_runtime.receipt.v1"
    assert receipt["task_id"].startswith("sprint-")
    assert receipt["workspace_revision"] == "revision-001"
    assert receipt["receipt_complete"] is False
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_llm_generator_can_route_local_assist_into_online_context(monkeypatch, tmp_path: Path):
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    monkeypatch.setenv("NEXUS_ONLINE_LOCAL_ASSIST", "1")
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-hybrid-001"
    generator.local_service = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _request: "local diagnosis: prefer strip")
    )
    online_calls: list[tuple[tuple, dict]] = []

    def _online_call(*args, **kwargs):
        online_calls.append((args, kwargs))
        return (
            {
                "status": "APPROVED",
                "operation": "replace",
                "target_snippet": "return text",
                "replacement": "return text.strip()",
            },
            "raw-candidate",
        )

    monkeypatch.setattr(generator.gateway, "ask_structured", _online_call)
    code, metadata = generator.generate(
        source_code="def normalize(text):\n    return text\n",
        task="fix normalize",
        mutation_hint="strip whitespace",
        seed=8,
    )

    receipt = metadata["unified_runtime_receipt"]
    assert code.endswith("return text.strip()\n")
    assert receipt["local"]["status"] == "SUCCEEDED"
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert "local diagnosis: prefer strip" in online_calls[0][0][0]
    assert receipt["claim_boundary"]["local_online_continuation"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


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


def test_model_required_blocks_local_final_delivery_after_llm_attempt(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            raise RuntimeError("gateway_error")

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "print('ok')\n", {"source": "local", "model_calls": 0, "quota_backoffs": 0}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="fix", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "FAILED"
    assert res.reason == "model_required_model_delivery_failed"
    assert res.winner_source == "model_required_no_model_candidate"
    assert res.model_calls == 1
    assert "model_required_model_delivery_failed" in res.error_codes
    assert "model_required_local_support_not_delivery" in res.error_codes
    assert res.patch == ""


def test_model_required_does_not_promote_local_guard_fallback_after_llm_patch_failed(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("def build():\n    return []\n", encoding="utf-8")

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            return "def build():\n    return []\n", {
                "source": "llm",
                "model_calls": 1,
                "tokens_used": 10,
                "token_capture_status": "measured",
                "model_patch_generated": True,
            }

    class FakeLocalGenerator:
        source = "local"

        def generate(self, *args, **kwargs):
            return "def build():\n    return ['local']\n", {"source": "local"}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            score = 1.0 if "local" in kwargs["code"] else 0.0
            return CandidateEval(seed=kwargs["seed"], score=score, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "0")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="add feature artifact", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "FAILED"
    assert res.reason == "model_required_model_delivery_failed"
    assert res.winner_source == "llm"
    assert res.final_score == 0.0
    assert res.model_calls == 1
    assert res.fallback_used is True
    assert "model_required_local_support_not_delivery" in res.error_codes
    assert "local" not in res.winner_source
    assert "local" not in res.patch


def test_model_required_self_heal_can_use_local_support_without_promoting_it(monkeypatch, tmp_path: Path):
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
            assert "[NEXUS LOCAL SUPPORT CANDIDATE]" in kwargs["task"]
            return "def build():\n    return ['artifact']\n", {
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
            return "def build():\n    return ['artifact']\n", {"source": "local"}

    class FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            score = 1.0 if "artifact" in kwargs["code"] else 0.0
            return CandidateEval(seed=kwargs["seed"], score=score, candidate_code=kwargs["code"], source=kwargs["source"])

    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(task="add feature artifact", target_file="demo.py", candidate_count=1, llm_mode=True, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.winner_source == "llm_self_heal"
    assert res.model_calls == 2
    assert calls == {"llm": 2, "local": 1}
    assert "model_required_local_support_hint" in res.error_codes


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
    assert res.winner_source == "local_preflight"


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
    assert res.fallback_used is False
    assert res.winner_source == "local_preflight"


def test_hidden_verifier_mode_adds_local_shadow_for_llm_visible_pass(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def merge_limits(defaults, override):\n"
        "    result = defaults\n"
        "    result.update(override or {})\n"
        "    return result\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import merge_limits\n\n"
        "def test_merge_limits_overrides_plain_values():\n"
        "    assert merge_limits({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n",
        encoding="utf-8",
    )

    calls = {"llm": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            calls["llm"] += 1
            return (
                "def merge_limits(defaults, override):\n"
                "    result = defaults.copy()\n"
                "    result.update(override or {})\n"
                "    return result\n",
                {
                    "source": "llm",
                    "model_calls": 1,
                    "tokens_used": 10,
                    "token_capture_status": "measured",
                    "model_patch_generated": True,
                },
            )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_AUTOREASON_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)

    cfg = SprintConfig(
        task="Repair merge_limits so override None preserves defaults and inputs are not mutated.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=3,
        llm_mode=True,
        safe_mode=True,
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls["llm"] == 0
    assert res.fallback_used is False
    assert res.winner_source == "local_hidden_contract_fast_path"
    assert "value is not None" in (res.patch or "")
    assert "hidden_contract_fast_path_success" in res.error_codes


def test_hidden_verifier_mode_uses_fast_path_for_remaining_ms_contract(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def remaining_ms(start_ms, now_ms, timeout_ms):\n"
        "    return timeout_ms - now_ms - start_ms\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import remaining_ms\n\n"
        "def test_remaining_ms_simple_elapsed_case():\n"
        "    assert remaining_ms(100, 125, 50) == 25\n",
        encoding="utf-8",
    )

    calls = {"llm": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            calls["llm"] += 1
            return (
                "def remaining_ms(start_ms, now_ms, timeout_ms):\n"
                "    return timeout_ms - (now_ms - start_ms)\n",
                {
                    "source": "llm",
                    "model_calls": 1,
                    "tokens_used": 10,
                    "token_capture_status": "measured",
                    "model_patch_generated": True,
                },
            )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)

    cfg = SprintConfig(
        task="Repair remaining_ms so elapsed is clamped and timeout never goes below zero.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls["llm"] == 0
    assert res.winner_source == "local_hidden_contract_fast_path"
    assert "elapsed = max(0, now_ms - start_ms)" in (res.patch or "")
    assert "return max(0, timeout_ms - elapsed)" in (res.patch or "")


def test_hidden_verifier_mode_uses_fast_path_for_belief_budget_contract(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def rlm_harder_v2_repair_budget(confidence, risk):\n"
        "    return {'rounds': 1, 'needs_evidence': False}\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import rlm_harder_v2_repair_budget\n\n"
        "def test_low_confidence_high_risk_requires_more_evidence():\n"
        "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
        "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n",
        encoding="utf-8",
    )

    calls = {"llm": 0}

    class FakeLLMGenerator:
        source = "llm"

        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *args, **kwargs):
            calls["llm"] += 1
            return (
                "def rlm_harder_v2_repair_budget(confidence, risk):\n"
                "    if confidence == 'low' or risk == 'high':\n"
                "        return {'rounds': 3, 'needs_evidence': True}\n"
                "    return {'rounds': 1, 'needs_evidence': False}\n",
                {
                    "source": "llm",
                    "model_calls": 1,
                    "tokens_used": 10,
                    "token_capture_status": "measured",
                    "model_patch_generated": True,
                },
            )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "1")
    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)

    cfg = SprintConfig(
        task="Fix repair budget selection so low confidence or medium/high risk requires evidence.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert calls["llm"] == 0
    assert res.winner_source == "local_hidden_contract_fast_path"
    assert "confidence < 0.8" in (res.patch or "")
    assert "risk_level in {'medium', 'high'}" in (res.patch or "")


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
                "gateway_total_sec": 1.2,
                "gateway_process_sec": 1.1,
                "gateway_provider_wait_sec": 1.1,
                "gateway_parse_sec": 0.1,
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
    assert res.executor_selected == "inplace"
    assert res.executor_forced_inplace is True
    assert res.executor_init_sec >= 0
    assert res.learning_trace["executor"]["selected"] == "inplace"
    assert res.gateway_total_sec == 1.2
    assert res.gateway_provider_wait_sec == 1.1


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


def test_local_mode_can_opt_into_swarm_executor(monkeypatch, tmp_path: Path):
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

    class FakeSwarmExecutor:
        def __init__(self, *_args, **_kwargs):
            calls["swarm"] += 1

        def evaluate_candidate(self, **kwargs):
            return CandidateEval(seed=kwargs["seed"], score=1.0, candidate_code="print('ok')\n", source=kwargs["source"])

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.InPlaceSprintExecutor", FakeInPlaceExecutor)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeSwarmExecutor)

    cfg = SprintConfig(task="fix bug", target_file="demo.py", candidate_count=1, llm_mode=False, safe_mode=True)
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    assert res.status == "SUCCESS"
    assert calls["swarm"] == 1
    assert calls["inplace"] == 0


def test_run_hyper_sprint_uses_local_preflight_before_expensive_llm(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "FIELD = 'status'\n\n"
        "def build_response(value):\n"
        "    return {FIELD: value}\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import build_response\n\n"
        "def test_uses_canonical_result_field():\n"
        "    assert build_response('ok') == {'result': 'ok'}\n",
        encoding="utf-8",
    )

    class FailIfCalledLLM:
        model_chain = ["fake-gemini"]

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called when local preflight verifies the patch")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FailIfCalledLLM())

    cfg = SprintConfig(
        task="Sync code and docs after a renamed public field; infer the canonical field from contract text",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )

    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 0
    assert res.fallback_used is False
    assert res.winner_source == "local_preflight"
    assert "local_preflight_before_llm_success" in res.error_codes


def test_run_hyper_sprint_uses_local_preflight_for_governance_redaction(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def redact(record):\n"
        "    return dict(record)\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import redact\n\n"
        "def test_redacts_secret_fields():\n"
        "    assert redact({'token': 'abc', 'name': 'ok'}) == {'token': '[REDACTED]', 'name': 'ok'}\n",
        encoding="utf-8",
    )

    class FailIfCalledLLM:
        model_chain = ["fake-gemini"]

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called for deterministic redaction preflight")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FailIfCalledLLM())

    cfg = SprintConfig(
        task="Refactor a credential scrubber while preserving secret redaction",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )

    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 0
    assert res.winner_source == "local_preflight"


def test_run_hyper_sprint_uses_local_preflight_for_rlm_governance_guard(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def rlm_harder_v2_filter_action(action):\n"
        "    return {'allowed': True, 'reason': 'ok'}\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import rlm_harder_v2_filter_action\n\n"
        "def test_governance_guard_contract():\n"
        "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
        "    assert rlm_harder_v2_filter_action({'tool': 'delete_file', 'path': 'logs/run.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        "    assert rlm_harder_v2_filter_action({'tool': 'write_file', 'path': 'benchmarks/result.json'}) == {'allowed': False, 'reason': 'governance_block'}\n",
        encoding="utf-8",
    )

    class FailIfCalledLLM:
        model_chain = ["fake-gemini"]

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called for deterministic governance guard preflight")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FailIfCalledLLM())

    cfg = SprintConfig(
        task="Repair governance action filter; reason governance_block for destructive actions.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )

    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 0
    assert res.winner_source == "local_preflight"
    assert "local_preflight_before_llm_success" in res.error_codes


def test_run_hyper_sprint_uses_local_preflight_for_rlm_evidence_gap(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def rlm_harder_v2_verified_claims(claims):\n"
        "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import rlm_harder_v2_verified_claims\n\n"
        "def test_requires_artifact_reference():\n"
        "    claims = [{'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'}, {'id': 'b', 'status': 'pass'}]\n"
        "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n",
        encoding="utf-8",
    )

    class FailIfCalledLLM:
        model_chain = ["fake-gemini"]

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called for deterministic evidence-gap preflight")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FailIfCalledLLM())

    cfg = SprintConfig(
        task="Repair RLM evidence gap so verified claims require non-empty artifact references.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )

    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 0
    assert res.winner_source == "local_preflight"


def test_run_hyper_sprint_uses_local_preflight_for_rlm_memory_contract(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text(
        "def rlm_harder_v2_select_memory_hits(items, task_type, keywords):\n"
        "    return [item for item in items if item.get('task_type') == task_type]\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "from demo import rlm_harder_v2_select_memory_hits\n\n"
        "def test_requires_type_and_keyword_overlap():\n"
        "    items = [{'id': 'old', 'task_type': 'bug', 'keywords': ['invoice']}, {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket']}]\n"
        "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket']) == [items[1]]\n",
        encoding="utf-8",
    )

    class FailIfCalledLLM:
        model_chain = ["fake-gemini"]

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM should not be called for deterministic memory preflight")

    monkeypatch.setenv("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", lambda *_args, **_kwargs: FailIfCalledLLM())

    cfg = SprintConfig(
        task="Repair RLM memory selection so hits require task type and keyword overlap.",
        target_file="demo.py",
        test_file="test_demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True,
    )

    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)

    assert res.status == "SUCCESS"
    assert res.model_calls == 0
    assert res.winner_source == "local_preflight"


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


def test_truncate_redundant_tests():
    from nexus.research.sprint_service import _truncate_redundant_tests
    
    # Test short file is not truncated
    short_source = "def test_short():\n    assert True\n"
    assert _truncate_redundant_tests(short_source, "fix it") == short_source
    
    # Test long file is truncated correctly
    long_source_lines = [
        "import sys",
        "from demo import normalize_flag",
        "",
        "def test_unrelated_one():",
        "    assert normalize_flag('abc') == 'abc'",
        "",
        "def test_normalize_flag_whitespace():",
        "    assert normalize_flag('  YES  ') == 'yes'",
        "",
        "def test_unrelated_two():",
        "    assert normalize_flag('123') == '123'",
        ""
    ]
    # Pad to over 80 lines to trigger truncation
    long_source = "\n".join(long_source_lines) + "\n" * 80
    
    truncated = _truncate_redundant_tests(long_source, "Fix normalize_flag_whitespace bug")
    
    assert "def test_normalize_flag_whitespace():" in truncated
    assert "test_unrelated_one" not in truncated
    assert "test_unrelated_two" not in truncated
    assert "Truncated other passing tests" in truncated


def test_run_hyper_sprint_self_heals_when_llm_first_round_falls_back_to_local_for_model_required(monkeypatch, tmp_path: Path):
    _write_ready_learn_slo(tmp_path)
    target = tmp_path / "demo.py"
    target.write_text("print('x')\n", encoding="utf-8")

    llm_calls = []

    class FakeLLMGenerator:
        model_chain = ["qwen2.5-coder:14b"]
        def __init__(self, *args, **kwargs):
            pass

        def generate(self, *args, **kwargs):
            llm_calls.append(kwargs.get("mutation_hint", ""))
            # 第一次調用（沒有 "self_heal" 標記）拋出 exception，模擬超時
            if "self_heal" not in kwargs.get("mutation_hint", ""):
                raise RuntimeError("HTTP 500 Ollama timeout simulating exception")
            # 第二次調用（自癒調用）成功生成
            return "print('success')\n", {
                "source": "llm_self_heal",
                "model_calls": 1,
                "model_name": "qwen2.5-coder:14b",
                "tokens_used": 150,
                "token_capture_status": "measured"
            }

    class FakeLocalGenerator:
        source = "local"
        def __init__(self, *args, **kwargs):
            pass
        def generate(self, *args, **kwargs):
            return "print('local')\n", {"source": "local", "model_calls": 0}

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate_candidate(self, **kwargs):
            # 只有 llm_self_heal 生成的 patch 才給過
            score = 1.0 if kwargs["source"] == "llm_self_heal" else 0.0
            return CandidateEval(
                seed=kwargs["seed"],
                score=score,
                candidate_code=kwargs["code"],
                source=kwargs["source"],
                error="test failed" if score == 0.0 else ""
            )

    monkeypatch.setenv("NEXUS_REQUIRE_MODEL_PARTICIPATION", "1")
    monkeypatch.setenv("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "model_participation_only")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("nexus.research.sprint_service.LLMCandidateGenerator", FakeLLMGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.LocalCandidateGenerator", FakeLocalGenerator)
    monkeypatch.setattr("nexus.research.sprint_service.SprintExecutor", FakeExecutor)

    cfg = SprintConfig(
        task="fix",
        target_file="demo.py",
        candidate_count=1,
        llm_mode=True,
        safe_mode=True
    )
    res = run_hyper_sprint(repo_root=tmp_path, config=cfg)
    
    assert res.status == "SUCCESS"
    assert res.winner_source == "llm_self_heal"
    assert any("self_heal_after_pytest_failed" in h for h in llm_calls)
