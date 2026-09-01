from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from nexus_open_swe_runtime import cli
from nexus_open_swe_runtime.opencli_web_model import (
    OPENCLI_WEB_PROTOCOL,
    OpenCLIWebChatModel,
    OpenCLIWebModelError,
)


def _fake_process(monkeypatch: pytest.MonkeyPatch, response: str):
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv, **kwargs):
        args = list(argv)
        calls.append((args, dict(kwargs)))
        if args[1:3] == ["chatgpt", "model"]:
            return SimpleNamespace(returncode=0, stdout='[{"Status":"ok"}]', stderr="")
        if args[1:3] == ["chatgpt", "ask"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([
                    {
                        "conversationId": "web-conversation-1",
                        "conversationUrl": "https://chatgpt.com/c/web-conversation-1",
                        "tool": "chatgpt",
                        "response": response,
                    }
                ]),
                stderr="",
            )
        raise AssertionError(args)

    monkeypatch.setattr(
        "nexus_open_swe_runtime.opencli_web_model.subprocess.run",
        fake_run,
    )
    return calls


def test_build_model_selects_opencli_web_bridge_without_langchain_provider():
    def fail_init(**_kwargs):
        raise AssertionError("init_chat_model must not be used for ChatGPT Web")

    model = cli._build_model(
        {"init_chat_model": fail_init},
        "opencli_chatgpt",
        "very-high",
    )

    assert isinstance(model, OpenCLIWebChatModel)
    assert model.intelligence_level == "very-high"


def test_opencli_web_model_uses_chatgpt_web_and_no_shell(monkeypatch: pytest.MonkeyPatch):
    calls = _fake_process(
        monkeypatch,
        '{"type":"final","content":"bounded answer"}',
    )
    model = OpenCLIWebChatModel(
        executable="/opt/opencli",
        intelligence_level="very-high",
        timeout_seconds=41,
    )

    result = model.invoke([HumanMessage(content="inspect the repository")])

    assert isinstance(result, AIMessage)
    assert result.content == "bounded answer"
    assert calls[0][0] == [
        "/opt/opencli",
        "chatgpt",
        "model",
        "very-high",
        "--site-session",
        "ephemeral",
        "-f",
        "json",
    ]
    ask = calls[1][0]
    assert ask[0:3] == ["/opt/opencli", "chatgpt", "ask"]
    assert "--new" in ask
    assert ask[ask.index("--timeout") + 1] == "41"
    assert calls[1][1]["shell"] is False
    prompt = json.loads(ask[3])
    assert prompt["protocol"] == OPENCLI_WEB_PROTOCOL
    assert prompt["role"] == "model_transport_only"
    assert prompt["messages"][-1]["content"] == "inspect the repository"


def test_opencli_web_model_translates_declared_tool_call(monkeypatch: pytest.MonkeyPatch):
    calls = _fake_process(
        monkeypatch,
        '{"type":"tool_call","name":"read_file","arguments":{"file_path":"README.md"}}',
    )

    @tool
    def read_file(file_path: str) -> str:
        """Read one repository file."""
        return file_path

    model = OpenCLIWebChatModel(executable="opencli", intelligence_level="advanced")
    result = model.bind_tools([read_file]).invoke("inspect README")

    assert result.content == ""
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "read_file"
    assert result.tool_calls[0]["args"] == {"file_path": "README.md"}
    prompt = json.loads(calls[1][0][3])
    assert prompt["tools"][0]["function"]["name"] == "read_file"


def test_opencli_web_model_rejects_undeclared_tool_call(monkeypatch: pytest.MonkeyPatch):
    _fake_process(
        monkeypatch,
        '{"type":"tool_call","name":"shell","arguments":{"cmd":"rm -rf /"}}',
    )

    @tool
    def read_file(file_path: str) -> str:
        """Read one repository file."""
        return file_path

    model = OpenCLIWebChatModel(executable="opencli", intelligence_level="advanced")
    with pytest.raises(OpenCLIWebModelError, match="OPENCLI_WEB_TOOL_CALL_INVALID"):
        model.bind_tools([read_file]).invoke("inspect README")


def test_opencli_web_model_builds_real_deepagents_graph_without_dispatch(tmp_path):
    runtime = cli._load_runtime()
    model = OpenCLIWebChatModel(executable="opencli", intelligence_level="very-high")

    graph = cli.build_semantic_graph(
        model,
        tmp_path,
        runtime,
        "opencli_chatgpt:very-high",
    )
    surface = set(cli.executable_tool_surface(graph))

    assert {"read_file", "ls", "glob", "grep", "record_finding"} <= surface
    assert "task" not in surface
    assert "write_file" not in surface
    assert "edit_file" not in surface


def test_opencli_web_model_fails_closed_on_process_error(monkeypatch: pytest.MonkeyPatch):
    def fake_run(_argv, **_kwargs):
        return SimpleNamespace(returncode=69, stdout="", stderr="browser unavailable")

    monkeypatch.setattr(
        "nexus_open_swe_runtime.opencli_web_model.subprocess.run",
        fake_run,
    )
    model = OpenCLIWebChatModel(executable="opencli", intelligence_level="very-high")

    with pytest.raises(OpenCLIWebModelError, match="OPENCLI_WEB_PROCESS_FAILURE"):
        model.invoke("hello")
