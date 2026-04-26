from nexus.services.gemini_cli import build_gemini_cli_invocation, extract_token_info


def test_gemini_cli_invocation_defaults_to_plan_approval_and_stdin_transport():
    invocation = build_gemini_cli_invocation(
        prompt="system",
        payload="payload",
        model_name="gemini-3-flash-preview",
        gemini_entry="/tmp/gemini",
        node_bin="/tmp/node",
        env={"PATH": "/usr/bin", "HOME": "/Users/jameschen"},
    )

    assert invocation.command[:4] == ["/tmp/gemini", "--skip-trust", "--approval-mode", "plan"]
    assert invocation.command_with_node[:5] == ["/tmp/node", "/tmp/gemini", "--skip-trust", "--approval-mode", "plan"]
    assert invocation.prompt_stdin == "payload"
    assert invocation.command[invocation.command.index("-p") + 1] == "system"
    assert invocation.env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    assert invocation.cwd == "/tmp"


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


def test_extract_token_info_prefers_stats_over_usage_metadata():
    info = extract_token_info(
        {
            "stats": {"models": {"flash": {"tokens": {"total": 42}}}},
            "usageMetadata": {"totalTokenCount": 77},
        }
    )

    assert info["total_tokens"] == 119
    assert info["gateway_stats_present"] is True
    assert info["gateway_usage_metadata_present"] is True
    assert info["gateway_token_source"] == "stats"
