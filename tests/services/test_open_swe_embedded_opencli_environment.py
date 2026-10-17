"""Embedded OpenCLI ChatGPT adapter: child environment must not carry credentials.

Nexus-new#2394, part of the OpenCLI adapter contract
(docs/arch/OPENCLI_CHATGPT_ADAPTER_CONTRACT.md rule 3 and rule 5). The embedded
module only needs ``langchain_core`` for base classes, which CI does not install,
so minimal stand-ins are put in ``sys.modules`` for the duration of the import.
The subprocess that is spawned is a real recording fake ``opencli`` on PATH.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "runtimes/open_swe/nexus_open_swe_runtime/opencli_web_model.py"
)

SENTINELS = {
    "GITHUB_TOKEN": "ghs-sentinel",
    "GH_TOKEN": "gh-sentinel",
    "OPENAI_API_KEY": "sk-sentinel",
    "ANTHROPIC_API_KEY": "ant-sentinel",
    "MY_SECRET": "secret-sentinel",
    "DB_PASSWORD": "pw-sentinel",
    "SERVICE_CREDENTIAL": "cred-sentinel",
    "SOME_TOKEN": "tok-sentinel",
}


class _StubBaseChatModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


def _stub_module(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _load_embedded_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    placeholder = type("Placeholder", (), {})
    stubs = {
        "langchain_core": _stub_module("langchain_core"),
        "langchain_core.language_models": _stub_module("langchain_core.language_models"),
        "langchain_core.language_models.chat_models": _stub_module(
            "langchain_core.language_models.chat_models",
            BaseChatModel=_StubBaseChatModel,
            LanguageModelInput=object,
        ),
        "langchain_core.messages": _stub_module(
            "langchain_core.messages",
            AIMessage=placeholder,
            BaseMessage=placeholder,
            ToolMessage=placeholder,
        ),
        "langchain_core.outputs": _stub_module(
            "langchain_core.outputs", ChatGeneration=placeholder, ChatResult=placeholder
        ),
        "langchain_core.runnables": _stub_module("langchain_core.runnables", Runnable=placeholder),
        "langchain_core.tools": _stub_module("langchain_core.tools", BaseTool=placeholder),
        "langchain_core.utils": _stub_module("langchain_core.utils"),
        "langchain_core.utils.function_calling": _stub_module(
            "langchain_core.utils.function_calling", convert_to_openai_tool=lambda tool: tool
        ),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "nexus_embedded_opencli_web_model_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _recording_opencli(tmp_path: Path) -> tuple[Path, Path]:
    dump = tmp_path / "environ-dump.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "opencli"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        f"with open({str(dump)!r}, 'a') as fh:\n"
        "    fh.write(json.dumps(dict(os.environ)) + '\\n')\n"
        "print('[]')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir, dump


def test_embedded_opencli_child_environment_excludes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_embedded_module(monkeypatch)
    bin_dir, dump = _recording_opencli(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    for name, value in SENTINELS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENCLI_KEEP_ME", "kept")
    monkeypatch.delenv("OPENCLI_PROFILE", raising=False)

    model = module.OpenCLIWebChatModel(profile="lab")
    assert model._run(["opencli", "chatgpt", "status", "-f", "json"]) == "[]\n"

    lines = dump.read_text().splitlines()
    assert len(lines) == 1
    child_env = json.loads(lines[0])
    for name in SENTINELS:
        assert name not in child_env
    assert str(bin_dir) in child_env["PATH"]
    assert child_env["OPENCLI_PROFILE"] == "lab"
    assert child_env["OPENCLI_KEEP_ME"] == "kept"
