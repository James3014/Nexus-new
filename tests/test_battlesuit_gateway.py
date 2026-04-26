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
    with patch("nexus.services.gateway.subprocess.run", return_value=fake_proc):
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
    with patch("nexus.services.gateway.subprocess.run", return_value=fake_proc):
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


def test_gateway_ignores_hook_text_after_cli_json():
    cli_stdout = json.dumps(
        {
            "response": "{\"status\":\"PASS\",\"summary\":\"ok\"}",
            "stats": {"models": {}},
        }
    ) + "\nCreated execution plan for SessionEnd"
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")

    gateway = BattlesuitGateway(project_root=".")
    with patch("nexus.services.gateway.subprocess.run", return_value=fake_proc):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert data["summary"] == "ok"
    assert data["gateway_stats_present"] is True
    assert data["gateway_token_source"] == "missing"


def test_gateway_sets_headless_trust_flags_and_neutral_cwd():
    cli_stdout = json.dumps({"response": "{\"status\":\"PASS\",\"summary\":\"ok\"}"})
    fake_proc = SimpleNamespace(returncode=0, stdout=cli_stdout, stderr="")
    captured = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = list(args[0])
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env", {})
        return fake_proc

    gateway = BattlesuitGateway(project_root=".")
    with patch("nexus.services.gateway.subprocess.run", side_effect=fake_run):
        data, _ = gateway.ask_structured(
            "Return pass JSON",
            "{}",
            output_schema={"status": "PASS | FAIL", "summary": "Short explanation"},
        )

    assert data["status"] == "PASS"
    assert "--skip-trust" in captured["cmd"]
    assert captured["env"]["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    assert captured["cwd"] == "/tmp"


def test_gateway_timeout_returns_budget_telemetry(monkeypatch):
    import subprocess

    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "7")
    gateway = BattlesuitGateway(project_root=".")
    with patch("nexus.services.gateway.subprocess.run", side_effect=subprocess.TimeoutExpired(["gemini"], 7)):
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
