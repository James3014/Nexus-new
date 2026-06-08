import json
from types import SimpleNamespace
from unittest.mock import patch

from nexus.services.gateway import BattlesuitGateway


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

