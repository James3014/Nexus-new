from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _adapter_module():
    assert importlib.util.find_spec("nexus.services.open_swe_external_intelligence") is not None
    return importlib.import_module("nexus.services.open_swe_external_intelligence")


class FakeGraph:
    def __init__(self, *, surface, envelope=None, error=None, hidden_tool=None):
        self.surface = tuple(surface)
        self.envelope = envelope
        self.error = error
        self.hidden_tool = hidden_tool
        self.calls = 0

    def get_graph(self):
        data = SimpleNamespace(tools_by_name={name: object() for name in self.surface})
        return SimpleNamespace(nodes={"tools": SimpleNamespace(data=data)})

    def invoke(self, payload, config=None):
        self.calls += 1
        assert set(payload) == {"messages"}
        assert config == {"recursion_limit": 40}
        if self.error is not None:
            raise self.error
        name = self.hidden_tool or "record_finding"
        args = {"envelope": self.envelope} if name == "record_finding" else {}
        return {
            "messages": [
                SimpleNamespace(
                    tool_calls=[
                        {"name": name, "args": args, "id": "call-1", "type": "tool_call"}
                    ]
                )
            ]
        }


def _transport(tmp_path, graph):
    module = _adapter_module()
    return module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="test-provider",
        model_id="test-model",
        model_factory=lambda _provider, _model: object(),
        graph_factory=lambda _model, _root: graph,
    )


def test_transport_returns_recorded_envelope_and_reconciles_without_redispatch(tmp_path):
    envelope = {"schema": "external_execution_envelope.v1", "binding": {"task": "t1"}}
    graph = FakeGraph(
        surface=("glob", "grep", "ls", "read_file", "record_finding"),
        envelope=envelope,
    )
    transport = _transport(tmp_path, graph)

    first = transport.invoke("prompt")
    reconciled = transport.reconcile("prompt")

    assert first.status == "INTELLIGENCE_COMPLETED"
    assert json.loads(first.raw) == envelope
    assert reconciled == first
    assert graph.calls == 1
    assert first.safe_argv == ("open_swe", "semantic", "<prompt>")


def test_transport_rejects_compiled_mutation_surface(tmp_path):
    module = _adapter_module()
    graph = FakeGraph(
        surface=("glob", "grep", "ls", "read_file", "record_finding", "write_file"),
        envelope={},
    )

    with pytest.raises(module.OpenSWEExternalIntelligenceError, match="OPEN_SWE_TOOL_SURFACE_INVALID"):
        _transport(tmp_path, graph)


def test_hidden_mutation_call_is_not_accepted_as_semantic_result(tmp_path):
    graph = FakeGraph(
        surface=("glob", "grep", "ls", "read_file", "record_finding"),
        hidden_tool="write_file",
    )
    transport = _transport(tmp_path, graph)

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_RESULT_INVALID"
    assert result.retry_safe is False
    assert graph.calls == 1


def test_ambiguous_graph_outcome_reconciles_without_second_invoke(tmp_path):
    graph = FakeGraph(
        surface=("glob", "grep", "ls", "read_file", "record_finding"),
        error=TimeoutError("unknown provider outcome"),
    )
    transport = _transport(tmp_path, graph)

    first = transport.invoke("prompt")
    second = transport.reconcile("prompt")

    assert first.status == second.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first.outcome_unknown is second.outcome_unknown is True
    assert graph.calls == 1


def test_missing_optional_runtime_fails_closed_at_transport_construction(tmp_path, monkeypatch):
    module = _adapter_module()

    def missing_runtime():
        raise ImportError("deepagents unavailable")

    monkeypatch.setattr(module, "_load_runtime", missing_runtime)
    with pytest.raises(
        module.OpenSWEExternalIntelligenceError,
        match="OPEN_SWE_OPTIONAL_DEPENDENCY_MISSING",
    ):
        module.OpenSWEExternalIntelligenceTransport(
            repository_root=tmp_path,
            model_provider="google_genai",
            model_id="gemini-test",
            model_factory=lambda _provider, _model: object(),
        )


def test_open_swe_optional_dependency_contract_is_exactly_pinned():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    block = text.split("open-swe = [", 1)[1].split("]", 1)[0]

    assert block.splitlines() == [
        "",
        '    "deepagents==0.7.6; python_version >= \'3.11\'",',
        '    "google-genai==1.74.0; python_version >= \'3.11\'",',
        '    "langchain-core==1.5.2; python_version >= \'3.11\'",',
        '    "langchain-google-genai==4.3.2; python_version >= \'3.11\'",',
    ]


def test_real_deepagents_toolnode_is_physically_read_only_when_optional_extra_installed(
    tmp_path,
):
    pytest.importorskip("deepagents")
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    module = _adapter_module()
    runtime = module._load_runtime()
    sentinel = tmp_path / "must-not-exist.txt"

    class HostileModel(BaseChatModel):
        model_name: str = "physical-test"
        index: int = 0

        @property
        def _llm_type(self):
            return "task001"

        def _get_ls_params(self, *args, **kwargs):
            return {"ls_provider": "task001", "ls_model_name": self.model_name}

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, **kwargs):
            if self.index == 0:
                object.__setattr__(self, "index", 1)
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": str(sentinel), "content": "forbidden"},
                            "id": "hostile-write",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                message = AIMessage(content="done")
            return ChatResult(generations=[ChatGeneration(message=message)])

    graph = module.build_read_only_semantic_graph(
        HostileModel(),
        tmp_path,
        runtime,
        profile_key="task001:physical-test",
    )
    output = graph.invoke(
        {"messages": [runtime.human_message(content="hostile")]},
        config={"recursion_limit": 40},
    )

    assert module.executable_tool_surface(graph) == (
        "glob",
        "grep",
        "ls",
        "read_file",
        "record_finding",
    )
    assert not sentinel.exists()
    assert any(
        isinstance(message, ToolMessage)
        and message.name == "write_file"
        and "is not a valid tool" in str(message.content)
        for message in output["messages"]
    )
