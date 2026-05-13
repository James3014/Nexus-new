from nexus.services.gemini_cli import build_gemini_cli_invocation, extract_token_info


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
