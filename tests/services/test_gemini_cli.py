import json

from nexus.services.gemini_cli import build_gemini_cli_invocation, extract_token_info, has_invalid_session_identifier


def test_gemini_cli_invocation_defaults_to_auto_edit_approval_and_stdin_transport():
    invocation = build_gemini_cli_invocation(
        prompt="system",
        payload="payload",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin="/tmp/node",
        env={"PATH": "/usr/bin", "HOME": "/Users/jameschen"},
    )

    assert invocation.command[:4] == ["/tmp/gemini", "--skip-trust", "--approval-mode", "auto_edit"]
    assert invocation.command_with_node[:5] == ["/tmp/node", "/tmp/gemini", "--skip-trust", "--approval-mode", "auto_edit"]
    assert invocation.prompt_stdin == "payload"
    assert invocation.command[invocation.command.index("-p") + 1] == "system"
    assert invocation.env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    assert invocation.cwd == "/tmp"


def test_gemini_cli_detects_invalid_session_identifier():
    assert has_invalid_session_identifier('Error resuming session: Invalid session identifier "abc"') is True
    assert has_invalid_session_identifier("quota exhausted") is False


def test_gemini_cli_invocation_honors_explicit_approval_override():
    invocation = build_gemini_cli_invocation(
        prompt="system",
        payload="payload",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin="/tmp/node",
        env={"PATH": "/usr/bin", "HOME": "/Users/jameschen", "NEXUS_GATEWAY_APPROVAL_MODE": "plan"},
    )

    assert invocation.command[:4] == ["/tmp/gemini", "--skip-trust", "--approval-mode", "plan"]
    assert invocation.command_with_node[:5] == ["/tmp/node", "/tmp/gemini", "--skip-trust", "--approval-mode", "plan"]


def test_gemini_cli_invocation_can_disable_skip_trust_for_strict_public_lane():
    invocation = build_gemini_cli_invocation(
        prompt="system",
        payload="payload",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin="/tmp/node",
        env={"PATH": "/usr/bin", "HOME": "/Users/jameschen", "NEXUS_GEMINI_SKIP_TRUST": "0"},
    )

    assert "--skip-trust" not in invocation.command
    assert invocation.command[:3] == ["/tmp/gemini", "--approval-mode", "auto_edit"]
    assert invocation.command_with_node is not None
    assert "--skip-trust" not in invocation.command_with_node
    assert invocation.env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"


def test_gemini_cli_invocation_can_inline_payload():
    invocation = build_gemini_cli_invocation(
        prompt="system",
        payload="payload",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin=None,
        env={"PATH": "/usr/bin", "HOME": "/Users/jameschen", "NEXUS_GATEWAY_PROMPT_TRANSPORT": "inline"},
    )

    assert invocation.prompt_stdin is None
    assert invocation.command[invocation.command.index("-p") + 1] == "system\n\npayload"
    assert invocation.transport == "inline"


def test_gemini_cli_invocation_redacts_clean_temp_runner_paths_in_strict_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    runner_root = "/private/tmp/nexus-live-clean-runner-20260514"
    invocation = build_gemini_cli_invocation(
        prompt=f"inspect {runner_root}/.nexus/bench_cases/task/target.py",
        payload=f"cwd={runner_root}",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin=None,
        env={
            "PATH": "/usr/bin",
            "HOME": "/Users/jameschen",
            "NEXUS_OUTBOUND_PROMPT_STRICT": "1",
            "NEXUS_OUTBOUND_PROMPT_LEDGER": str(ledger),
            "NEXUS_OUTBOUND_FORBIDDEN_LITERALS": runner_root,
            "NEXUS_GATEWAY_PROMPT_TRANSPORT": "inline",
        },
        cwd=runner_root,
    )

    outbound = invocation.command[invocation.command.index("-p") + 1]
    assert runner_root not in outbound
    assert "$SANITIZED_RUNNER_ROOT" in outbound
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert record["forbidden_literal_count"] == 0


def test_gemini_cli_invocation_redacts_workspace_paths_before_strict_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    invocation = build_gemini_cli_invocation(
        prompt="inspect /Users/jameschen/Workspace/nexus/secret.py",
        payload="cwd=/Users/jameschen/Workspace/nexus",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin=None,
        env={
            "PATH": "/usr/bin",
            "HOME": "/Users/jameschen",
            "NEXUS_OUTBOUND_PROMPT_STRICT": "1",
            "NEXUS_OUTBOUND_PROMPT_LEDGER": str(ledger),
            "NEXUS_OUTBOUND_FORBIDDEN_LITERALS": "/Users/jameschen/Workspace/nexus",
            "NEXUS_GATEWAY_PROMPT_TRANSPORT": "inline",
        },
    )

    outbound = invocation.command[invocation.command.index("-p") + 1]
    assert "/Users/jameschen/Workspace/nexus" not in outbound
    assert "$SANITIZED_PATH" in outbound
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert record["forbidden_literal_count"] == 0


def test_extract_token_info_prefers_request_local_usage_metadata_over_cumulative_stats():
    info = extract_token_info(
        {
            "stats": {"models": {"flash": {"tokens": {"total": 42}}}},
            "usageMetadata": {"totalTokenCount": 77},
        }
    )

    assert info["total_tokens"] == 77
    assert info["gateway_stats_present"] is True
    assert info["gateway_usage_metadata_present"] is True
    assert info["gateway_token_source"] == "usage_metadata"


def test_extract_token_info_reads_additive_usage_metadata_tokens():
    info = extract_token_info(
        {
            "usageMetadata": {
                "promptTokenCount": 123,
                "candidatesTokenCount": 45,
            },
        }
    )

    assert info["total_tokens"] == 168
    assert info["gateway_stats_present"] is False
    assert info["gateway_usage_metadata_present"] is True
    assert info["gateway_token_source"] == "usage_metadata"
