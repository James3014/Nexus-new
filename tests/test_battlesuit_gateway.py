import json
from types import SimpleNamespace
from unittest.mock import patch

from nexus.services.gateway import BattlesuitGateway
import pytest


@pytest.fixture(autouse=True)
def setup_default_provider(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    monkeypatch.setenv("NEXUS_PREFER_AGY", "0")


def _bind_valid_online_decision(gateway, provider="gemini"):
    from nexus.services.online_execution_policy import (
        DEFAULT_APPROVED_PROVIDERS,
        ONLINE_READY,
        OnlineExecutionDecision,
    )

    gateway.bind_online_execution_decision(
        OnlineExecutionDecision(
            online_policy="auto",
            online_execution_requested=True,
            online_execution_authorized=True,
            online_authorization_source="cli_task_policy",
            approved_online_providers=DEFAULT_APPROVED_PROVIDERS,
            preflight_status=ONLINE_READY,
            requested_provider=provider,
            physical_invocation_allowed=True,
        )
    )


def test_gateway_uses_response_key_from_gemini_cli_json():
    cli_stdout = json.dumps(
        {
            "session_id": "test-session",
            "response": "```json\n{\"status\":\"PASS\",\"summary\":\"ok\"}\n```",
            "stats": {
                "models": {
                    "gemini-2.5-flash": {
                        "tokens": {
                            "total": 42,
                        }
                    }
                }
            },
        }
    )
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", return_value=fake_proc):
        data, raw_output = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert data["summary"] == "ok"
    assert data["tokens_used"] == 42
    assert data["token_capture_status"] == "measured"
    assert data["gateway_stats_present"] is True
    assert data["gateway_usage_metadata_present"] is False
    assert data["gateway_token_source"] == "stats"
    assert data["gateway_prompt_chars"] > 0
    assert data["gateway_payload_chars"] > 0
    assert data["gateway_total_chars"] == data["gateway_prompt_chars"] + data["gateway_payload_chars"]
    assert data["gateway_timeout_sec"] > 0


def test_gateway_reads_usage_metadata_tokens():
    cli_stdout = json.dumps(
        {
            "response": "{\"status\":\"PASS\",\"summary\":\"ok\"}",
            "usageMetadata": {"totalTokenCount": 77},
        }
    )
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", return_value=fake_proc):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["tokens_used"] == 77
    assert data["token_capture_status"] == "measured"
    assert data["gateway_stats_present"] is False
    assert data["gateway_usage_metadata_present"] is True
    assert data["gateway_token_source"] == "usage_metadata"


def test_gateway_downgrades_cumulative_stats_outlier_to_estimate():
    cli_stdout = json.dumps(
        {
            "response": "{\"status\":\"PASS\",\"summary\":\"ok\"}",
            "stats": {
                "models": {
                    "gemini-3-flash-preview": {
                        "tokens": {
                            "total": 999999,
                        }
                    }
                }
            },
        }
    )
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", return_value=fake_proc):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["tokens_used"] < 1000
    assert data["token_capture_status"] == "estimated"
    assert data["gateway_stats_present"] is True
    assert data["gateway_token_source"] == "estimated_from_stats_outlier"
    assert data["gateway_token_outlier_reason"] == "stats_outlier_possible_cumulative"
    assert data["raw_provider_total_tokens"] == 999999
    assert data["raw_provider_token_source"] == "stats"
    assert data["provider_stats_cumulative_suspected"] is True
    assert data["token_accounting_failure_class"] == "provider_stats_outlier"


def test_gateway_ignores_hook_text_after_cli_json():
    cli_stdout = json.dumps(
        {
            "response": "{\"status\":\"PASS\",\"summary\":\"ok\"}",
            "stats": {"models": {}},
        }
    ) + "\nCreated execution plan for SessionEnd"
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", return_value=fake_proc):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert data["summary"] == "ok"
    assert data["gateway_stats_present"] is True
    assert data["gateway_token_source"] == "missing"


def test_gateway_sets_headless_trust_flags_and_project_cwd(tmp_path):
    cli_stdout = json.dumps({"response": "{\"status\":\"PASS\",\"summary\":\"ok\"}"})
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")
    captured = {}

    def fake_run(command, **kwargs):
        captured["cmd"] = list(command)
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env", {})
        return fake_proc

    gateway = BattlesuitGateway(project_root=tmp_path)
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", side_effect=fake_run):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert "--skip-trust" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--approval-mode") + 1] == "auto_edit"
    assert captured["env"]["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    assert captured["cwd"] == str(tmp_path.resolve())


def test_gateway_system_instruction_disables_tools():
    gateway = BattlesuitGateway(project_root=".")
    instruction = gateway._build_system_instruction({"status": "PASS | FAIL"})

    assert "Do not use tools" in instruction
    assert "Return ONLY valid JSON" in instruction


def test_gateway_timeout_returns_budget_telemetry(monkeypatch):
    import subprocess

    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "7")
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", side_effect=subprocess.TimeoutExpired(["gemini"], 7)):
        data, raw = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "FAIL"
    assert data["error_category"] == "timeout"
    assert data["gateway_prompt_chars"] > 0
    assert data["gateway_payload_chars"] > 0
    assert data["gateway_timeout_sec"] == 7
    assert raw == "TIMEOUT"


def test_gateway_timeout_override_can_extend_budget(monkeypatch):
    cli_stdout = json.dumps({"response": "{\"status\":\"PASS\",\"summary\":\"ok\"}"})
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")
    captured = {}

    def fake_run(_command, **kwargs):
        captured["timeout_sec"] = kwargs.get("timeout_sec")
        return fake_proc

    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "180")
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout", side_effect=fake_run):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert data["gateway_timeout_sec"] == 180
    assert captured["timeout_sec"] == 180


def test_gateway_model_selector_ollama_dynamic_routing(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_OLLAMA_SMALL_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")

    gateway = BattlesuitGateway(project_root=".")
    
    # 規劃/重現/定位等前期階段
    assert gateway.model_selector("P") == "qwen2.5-coder:7b"
    assert gateway.model_selector("R") == "qwen2.5-coder:7b"
    assert gateway.model_selector("X") == "qwen2.5-coder:7b"
    
    # 代碼生成/修復/診斷等後期精確階段
    assert gateway.model_selector("A") == "qwen2.5-coder:14b"
    assert gateway.model_selector("D") == "qwen2.5-coder:14b"
    assert gateway.model_selector("C") == "qwen2.5-coder:14b"


def test_gateway_oauth_provider_auto_detect_ollama_available(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "auto")
    with patch("nexus.services.gateway.BattlesuitGateway._ollama_available", return_value=True):
        gateway = BattlesuitGateway(project_root=".")
        assert gateway.oauth_provider == "ollama"


def test_gateway_oauth_provider_auto_detect_ollama_unavailable(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "auto")
    with patch("nexus.services.gateway.BattlesuitGateway._ollama_available", return_value=False):
        gateway = BattlesuitGateway(project_root=".")
        assert gateway.oauth_provider == "gemini"


def _gateway_authority(provider="gemini", model="gemini-3-flash-preview", **overrides):
    authority = {
        "schema": "nexus.gateway_invocation_authority.v1",
        "status": "ALLOW",
        "gate_passed": True,
        "resolved_provider": provider,
        "resolved_model": model,
    }
    authority.update(overrides)
    return authority


def test_gateway_accepts_one_call_with_exact_authority(monkeypatch):
    cli_stdout = json.dumps({"response": '{"status":"PASS"}'})
    calls = []
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    authority = _gateway_authority()

    def fake_run(command, **kwargs):
        calls.append((list(command), kwargs))
        return SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    with patch("nexus.services.gateway._run_cli_with_hard_timeout", side_effect=fake_run):
        data, raw = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS"},
            gateway_invocation_authority=authority,
        )

    assert data["status"] == "PASS"
    assert raw
    assert len(calls) == 1
    assert not hasattr(gateway, "_gateway_invocation_authority")


@pytest.mark.parametrize(
    ("authority", "error"),
    [
        (_gateway_authority(provider="agy"), "gateway_invocation_authority_provider_mismatch"),
        (_gateway_authority(model="other-model"), "gateway_invocation_authority_model_mismatch"),
        ({"schema": "nexus.gateway_invocation_authority.v1"}, "gateway_invocation_authority_status_not_allow"),
    ],
)
def test_gateway_authority_failures_make_zero_physical_calls(authority, error):
    calls = []
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)

    def fake_run(*_args, **_kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0, stdout='{"response":"must-not-run"}', stderr="")

    with patch("nexus.services.gateway._run_cli_with_hard_timeout", side_effect=fake_run):
        data, raw = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            model_name="gemini-3-flash-preview",
            gateway_invocation_authority=authority,
        )

    assert data["status"] == "FAILED"
    assert data["error"] == error
    assert raw == error
    assert data["invoked"] is False
    assert data["provider_call_count"] == 0
    assert calls == []
    assert data["gateway_invocation_authority"] == authority


def test_gateway_malformed_non_mapping_authority_is_zero_call():
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    with patch("nexus.services.gateway._run_cli_with_hard_timeout") as run:
        data, raw = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            gateway_invocation_authority=["malformed"],  # type: ignore[arg-type]
        )

    assert data["status"] == "FAILED"
    assert data["error"] == "gateway_invocation_authority_malformed"
    assert data["invoked"] is False
    assert data["provider_call_count"] == 0
    assert raw == data["error"]
    run.assert_not_called()


def test_exact_gemini_authority_blocks_agy_substitution(monkeypatch):
    monkeypatch.setenv("NEXUS_PREFER_AGY", "1")
    gateway = BattlesuitGateway(project_root=".")
    _bind_valid_online_decision(gateway)
    registered_calls = []
    cli_stdout = json.dumps({"response": '{"status":"PASS"}'})

    def fail_registered(**_kwargs):
        registered_calls.append(True)
        raise AssertionError("authority admitted gemini but agy was selected")

    with patch.object(gateway, "_ask_via_registered_print_cli", side_effect=fail_registered), patch(
        "nexus.services.gateway._run_cli_with_hard_timeout",
        return_value=SimpleNamespace(returncode=0, stdout=cli_stdout, stderr=""),
    ):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            gateway_invocation_authority=_gateway_authority(),
        )

    assert data["status"] == "PASS"
    assert registered_calls == []


@pytest.mark.parametrize("provider", ["codex", "opencode"])
def test_exact_registered_provider_authority_routes_only_that_provider(provider):
    gateway = BattlesuitGateway(project_root=".")
    gateway.oauth_provider = provider
    _bind_valid_online_decision(gateway, provider=provider)
    observed = []
    model = "provider-model"

    def fake_registered(**kwargs):
        observed.append(kwargs)
        return {"status": "APPROVED"}, "registered-raw"

    with patch.object(gateway, "_ask_via_registered_print_cli", side_effect=fake_registered), patch(
        "nexus.services.gateway.resolve_binary",
        side_effect=AssertionError("registered authority resolved Gemini binaries"),
    ):
        data, raw = gateway.ask_structured(
            "Return provider result",
            "{}",
            model_name=model,
            gateway_invocation_authority=_gateway_authority(provider=provider, model=model),
        )

    assert data["status"] == "APPROVED"
    assert raw == "registered-raw"
    assert observed and observed[0]["provider"] == provider


@pytest.mark.parametrize("provider", ["agy", "grok", "openai"])
def test_authority_registered_provider_without_model_binding_makes_zero_physical_calls(provider):
    gateway = BattlesuitGateway(project_root=".")
    gateway.oauth_provider = provider
    _bind_valid_online_decision(gateway, provider=provider)
    model = "provider-model"

    with patch.object(gateway, "_ask_via_registered_print_cli") as registered, patch(
        "nexus.services.gateway.resolve_binary"
    ) as resolve_binary, patch("nexus.services.gateway._run_cli_with_hard_timeout") as run:
        data, raw = gateway.ask_structured(
            "Return provider result",
            "{}",
            model_name=model,
            gateway_invocation_authority=_gateway_authority(provider=provider, model=model),
        )

    assert data["error"] == "gateway_invocation_authority_model_binding_unsupported"
    assert data["invoked"] is False
    assert data["provider_call_count"] == 0
    assert raw == data["error"]
    registered.assert_not_called()
    resolve_binary.assert_not_called()
    run.assert_not_called()
