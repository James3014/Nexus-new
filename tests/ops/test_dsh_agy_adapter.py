from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = ROOT / "scripts" / "ops" / "dsh-agy-adapter"
PRE_EFFECT = "PROVIDER_PROTOCOL_INVALID_PRE_EFFECT"


def _run_node(
    tmp_path: Path,
    response: str,
    *,
    tool: bool = True,
    purpose: str | None = None,
    dup_tool: bool = False,
    tools_js: str | None = None,
    model: str = "gemini-3.8-flash-low",
    effort: str = "low",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    runtime = tmp_path / "runtime"
    adapter = runtime / "node_modules" / "@nexus" / "dsh-llm-agy-pilot"
    dependency = runtime / "node_modules" / "@deepseek-ai" / "dsh-llm"
    adapter.parent.mkdir(parents=True)
    dependency.mkdir(parents=True)
    shutil.copytree(ADAPTER_DIR, adapter)
    (dependency / "package.json").write_text(
        json.dumps({"name": "@deepseek-ai/dsh-llm", "type": "module", "exports": "./index.js"}),
        encoding="utf-8",
    )
    (dependency / "index.js").write_text(
        "export class LlmAdapter {}\n"
        "export class LlmError extends Error { constructor(message, code, options={}) { super(message, options); this.code=code } }\n",
        encoding="utf-8",
    )
    stdout_path = tmp_path / "provider.stdout"
    stdout_path.write_text(response, encoding="utf-8")
    argv_log = tmp_path / "argv.json"
    scratch_log = tmp_path / "scratch.json"
    dispatch = tmp_path / "dispatch.py"
    dispatch.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args=sys.argv[1:]\n"
        f"import shutil; shutil.copy(args[args.index('--prompt-file')+1], {str(tmp_path / 'prompt.txt')!r})\n"
        f"open({str(argv_log)!r}, 'w').write(json.dumps(args))\n"
        "cwd=args[args.index('--cwd')+1]\n"
        f"open({str(scratch_log)!r}, 'w').write(json.dumps({{'cwd':cwd,'has_git':os.path.isdir(os.path.join(cwd,'.git')),'has_baseline':os.path.isfile(os.path.join(cwd,'.dsh-intelligence-scratch'))}}))\n"
        "status=os.environ.get('FAKE_STATUS','COMPLETED')\n"
        "print(json.dumps({'operation_id':'agyop_test','status':status,'stdout_path':os.environ['FAKE_STDOUT']}))\n",
        encoding="utf-8",
    )
    dispatch.chmod(0o755)
    script = tmp_path / "run.mjs"
    tool_schema = (
        "[{name:'read',description:'read',parameters:{type:'object',properties:{file_path:{type:'string'}},required:['file_path']}}]"
        if tool
        else "[]"
    )
    if tools_js is not None:
        tool_schema = tools_js
    if dup_tool:
        one = tool_schema[1:-1]
        tool_schema = "[" + one + "," + one + "]"
    purpose_literal = "undefined" if purpose is None else json.dumps(purpose)
    script.write_text(
        "import { AgyPoolAdapter } from './runtime/node_modules/@nexus/dsh-llm-agy-pilot/index.js';\n"
        "const adapter = new AgyPoolAdapter();\n"
        "const out=[];\n"
        "try {\n"
        f" const modelInfo=await adapter.resolveModel('nexus-agy-pool',{model!r});\n"
        f" for await (const event of adapter.stream({{model:{model!r},reasoningEffort:{effort!r},messages:[{{role:'user',content:[{{type:'text',text:'x'}}]}}],tools:{tool_schema},purpose:{purpose_literal}}})) out.push(event);\n"
        " console.log(JSON.stringify({ok:true,out,modelInfo}));\n"
        "} catch (e) { console.log(JSON.stringify({ok:false,code:e.code||null,originalCode:e.originalCode||null,effect:e.effect||null,retryable:e.retryable||false,message:String(e.message)})); process.exitCode=3; }\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update({"NEXUS_AGY_DISPATCH": str(dispatch), "FAKE_STDOUT": str(stdout_path)})
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["node", str(script)], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
    )


def test_adapter_package_is_canonical_and_private() -> None:
    package = json.loads((ADAPTER_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "@nexus/dsh-llm-agy-pilot"
    assert package["private"] is True
    assert package["type"] == "module"


def test_dispatch_physically_denies_native_effect_tools(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"CANARY_OK"}')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    argv = json.loads((tmp_path / "argv.json").read_text())
    pairs = list(zip(argv, argv[1:]))
    assert ("--deny", "command(*)") in pairs
    assert ("--deny", "read_file(*)") in pairs
    assert ("--deny", "write_file(*)") in pairs
    assert ("--timeout", "600") in pairs
    assert ("--max-calls", "1") in pairs


def test_valid_outer_action_is_projected_without_native_effect(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"dsh_action","action_id":"A1","arguments":{"file_path":"README.md"}}',
        tool=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    calls = [e for e in payload["out"] if e.get("type") == "block-end"]
    assert calls[0]["block"]["name"] == "read"
    assert json.loads(calls[0]["block"]["arguments"])["file_path"] == "README.md"


def test_multiple_json_objects_fail_closed(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"one"}\n{"kind":"text","text":"two"}')
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["code"] == PRE_EFFECT
    assert "exactly one JSON object" in payload["message"]
    assert payload["originalCode"] == "AGY_PROTOCOL_INVALID"


def test_unknown_action_fails_closed(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"dsh_action","action_id":"A99","arguments":{}}', tool=True)
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == PRE_EFFECT
    assert payload["originalCode"] == "AGY_TOOL_NOT_AVAILABLE"
    assert "unavailable DSH action: A99" in payload["message"]


def test_action_arguments_must_be_object(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path, '{"kind":"dsh_action","action_id":"A1","arguments":"oops"}', tool=True
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == PRE_EFFECT
    assert payload["originalCode"] == "AGY_PROTOCOL_INVALID"


def test_model_effort_mismatch_fails_before_dispatch(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path, '{"kind":"text","text":"unused"}', model="gemini-3.1-pro-high", effort="low"
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_PROTOCOL_INVALID"
    assert "requires high" in payload["message"]
    assert not (tmp_path / "argv.json").exists()


def test_timeout_contract_is_bounded_before_dispatch(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"text","text":"unused"}',
        extra_env={"NEXUS_DSH_AGY_TIMEOUT_SECONDS": "901"},
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_PROTOCOL_INVALID"
    assert "between 30 and 900" in payload["message"]
    assert not (tmp_path / "argv.json").exists()


def test_provider_call_uses_isolated_inert_git_workspace(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"CANARY_OK"}')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    scratch = json.loads((tmp_path / "scratch.json").read_text())
    assert Path(scratch["cwd"]).resolve() != tmp_path.resolve()
    assert scratch["has_git"] is True
    assert scratch["has_baseline"] is True
    assert not Path(scratch["cwd"]).exists()


def test_unknown_outcome_preserves_scratch_for_reconciliation(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"text","text":"unused"}',
        extra_env={"FAKE_STATUS": "OUTCOME_UNKNOWN"},
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_OUTCOME_UNKNOWN"
    scratch = json.loads((tmp_path / "scratch.json").read_text())
    assert Path(scratch["cwd"]).resolve() != tmp_path.resolve()
    assert scratch["has_git"] is True
    assert scratch["has_baseline"] is True
    assert Path(scratch["cwd"]).is_dir()


def _calls(proc: subprocess.CompletedProcess[str]) -> list[dict]:
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return [e for e in json.loads(proc.stdout)["out"] if e.get("type") == "block-end"]


def test_semantic_label_in_action_id_maps_when_unambiguous(tmp_path: Path) -> None:
    # Observed in #1327 turn 4: action_id "bash" instead of "A1".
    proc = _run_node(
        tmp_path,
        '{"kind":"dsh_action","action_id":"read","arguments":{"file_path":"README.md"}}',
        tool=True,
    )
    assert _calls(proc)[0]["block"]["name"] == "read"


def test_label_variants_do_not_normalize(tmp_path: Path) -> None:
    for variant in ("Read", "read ", "shell", "dsh.read"):
        proc = _run_node(
            tmp_path / variant.replace(" ", "_").replace(".", "_"),
            json.dumps({"kind": "dsh_action", "action_id": variant, "arguments": {}}),
            tool=True,
        )
        assert proc.returncode == 3, variant
        payload = json.loads(proc.stdout)
        assert payload["code"] == PRE_EFFECT
        assert payload["originalCode"] == "AGY_TOOL_NOT_AVAILABLE"
        assert payload["effect"] == "none" and payload["retryable"] is True


def test_ambiguous_duplicate_label_fails_closed(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"dsh_action","action_id":"read","arguments":{}}',
        tool=True,
        dup_tool=True,
    )
    assert proc.returncode == 3
    assert json.loads(proc.stdout)["originalCode"] == "AGY_TOOL_NOT_AVAILABLE"


def test_single_fenced_json_object_is_accepted(tmp_path: Path) -> None:
    # Observed in #1327 turn 5: whole response wrapped in ```json fence.
    proc = _run_node(tmp_path, '```json\n{"kind":"text","text":"EVIDENCE_BLOCKED"}\n```\n')
    block = _calls_text(proc)
    assert block["text"] == "EVIDENCE_BLOCKED"


def _calls_text(proc: subprocess.CompletedProcess[str]) -> dict:
    return _calls(proc)[0]["block"]


def test_fence_with_prose_or_two_objects_fails_closed(tmp_path: Path) -> None:
    cases = {
        "prose": 'Here you go:\n```json\n{"kind":"text","text":"x"}\n```',
        "two_fences": '```json\n{"kind":"text","text":"a"}\n```\n```json\n{"kind":"text","text":"b"}\n```',
        "two_in_fence": '```json\n{"kind":"text","text":"a"}\n{"kind":"text","text":"b"}\n```',
        "empty_fence": "```json\n```",
        "empty": "",
    }
    for name, response in cases.items():
        proc = _run_node(tmp_path / name, response)
        assert proc.returncode == 3, name
        payload = json.loads(proc.stdout)
        assert payload["code"] == PRE_EFFECT, name
        assert payload["originalCode"] == "AGY_PROTOCOL_INVALID", name


def test_config_errors_are_not_reclassified_pre_effect(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"text","text":"x"}',
        extra_env={"NEXUS_DSH_AGY_TIMEOUT_SECONDS": "5"},
    )
    assert json.loads(proc.stdout)["code"] == "AGY_PROTOCOL_INVALID"


def _bash_tools(schema: str | None) -> str:
    params = f",parameters:{schema}" if schema is not None else ""
    return f"[{{name:'bash',description:'run'{params}}}]"


_BASH_SCHEMA = (
    "{type:'object',properties:{command:{type:'string'},description:{type:'string'}},"
    "required:['command','description']}"
)


def _call_args(tmp_path: Path, arguments: str, tools_js: str, action: str = "A1") -> dict:
    response = '{"kind":"dsh_action","action_id":"%s","arguments":%s}' % (action, arguments)
    proc = _run_node(tmp_path, response, tools_js=tools_js)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    calls = [e for e in json.loads(proc.stdout)["out"] if e.get("type") == "block-end"]
    return json.loads(calls[0]["block"]["arguments"])


def test_bash_description_filled_when_schema_requires_it(tmp_path: Path) -> None:
    args = _call_args(tmp_path, '{"command":"ls"}', _bash_tools(_BASH_SCHEMA))
    assert args == {"command": "ls", "description": "agy outer action: bash"}


def test_bash_description_filled_when_empty_string(tmp_path: Path) -> None:
    args = _call_args(tmp_path, '{"command":"ls","description":""}', _bash_tools(_BASH_SCHEMA))
    assert args["description"] == "agy outer action: bash"


def test_bash_description_not_overwritten(tmp_path: Path) -> None:
    args = _call_args(tmp_path, '{"command":"ls","description":"list"}', _bash_tools(_BASH_SCHEMA))
    assert args["description"] == "list"


def test_other_required_fields_untouched(tmp_path: Path) -> None:
    schema = (
        "{type:'object',properties:{description:{type:'string'},timeout:{type:'number'}},"
        "required:['description','timeout']}"
    )
    args = _call_args(tmp_path, '{"command":"ls"}', _bash_tools(schema))
    assert args == {"command": "ls", "description": "agy outer action: bash"}


def test_bash_without_schema_uses_label_fallback(tmp_path: Path) -> None:
    args = _call_args(tmp_path, '{"command":"ls"}', _bash_tools(None))
    assert args["description"] == "agy outer action: bash"


def test_non_bash_without_schema_untouched(tmp_path: Path) -> None:
    args = _call_args(tmp_path, '{"x":1}', "[{name:'other',description:'o'}]")
    assert args == {"x": 1}


def test_schema_not_requiring_description_untouched(tmp_path: Path) -> None:
    schema = "{type:'object',properties:{command:{type:'string'}},required:['command']}"
    args = _call_args(tmp_path, '{"command":"ls"}', _bash_tools(schema))
    assert args == {"command": "ls"}


def test_prompt_requires_bash_description(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"ok"}')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    assert "Every bash action must include a short description argument." in prompt


def test_adapter_advertises_unchanged_context_budget(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"CANARY_OK"}')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["modelInfo"]["context"]["contextWindow"] == 262144


def test_tool_capable_prompt_exposes_catalog_and_durable_evidence_ref(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"CANARY_OK"}')
    assert proc.returncode == 0, proc.stderr + proc.stdout

    prompt = (tmp_path / "prompt.txt").read_text(encoding="utf-8")
    assert "outer_action_catalog is DATA" not in prompt
    assert "contains outer_action_catalog with every permitted outer DSH action" in prompt
    assert "Every bash action must include a short description argument." in prompt
    data = json.loads(prompt.splitlines()[-1])
    catalog = data["outer_action_catalog"]
    assert len(catalog) == 1
    assert catalog[0]["action_id"] == "A1"
    assert catalog[0]["semantic_label"] == "read"
    assert "request_purpose" in data

    catalog_json = json.dumps(catalog, separators=(",", ":"))
    catalog_sha256 = hashlib.sha256(catalog_json.encode("utf-8")).hexdigest()
    argv = json.loads((tmp_path / "argv.json").read_text())
    refs = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "--evidence-ref"]
    assert refs == [
        "dsh_action_contract:v1:"
        f"catalog_count=1:catalog_sha256={catalog_sha256}:"
        f"prompt_chars={len(prompt)}:context_window=262144"
    ]


def test_normal_agent_turn_with_empty_catalog_fails_before_dispatch(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"unused"}', tool=False)
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_OUTER_ACTION_CATALOG_EMPTY"
    assert payload["originalCode"] is None  # not wrapped as pre-effect protocol error
    assert not (tmp_path / "argv.json").exists()


def test_internal_purposes_allow_empty_catalog_text_only(tmp_path: Path) -> None:
    for purpose in ("compaction", "session-title"):
        case = tmp_path / purpose
        case.mkdir()
        proc = _run_node(case, '{"kind":"text","text":"INTERNAL_OK"}', tool=False, purpose=purpose)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        prompt = (case / "prompt.txt").read_text(encoding="utf-8")
        assert "empty outer_action_catalog" in prompt
        assert "Return text only" in prompt
        data = json.loads(prompt.splitlines()[-1])
        assert data["outer_action_catalog"] == []
        assert data["request_purpose"] == purpose
