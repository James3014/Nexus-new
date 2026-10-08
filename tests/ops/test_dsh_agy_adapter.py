from __future__ import annotations

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
    tool: bool = False,
    dup_tool: bool = False,
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
    if dup_tool:
        one = tool_schema[1:-1]
        tool_schema = "[" + one + "," + one + "]"
    script.write_text(
        "import { AgyPoolAdapter } from './runtime/node_modules/@nexus/dsh-llm-agy-pilot/index.js';\n"
        "const adapter = new AgyPoolAdapter();\n"
        "const out=[];\n"
        "try {\n"
        f" for await (const event of adapter.stream({{model:{model!r},reasoningEffort:{effort!r},messages:[{{role:'user',content:[{{type:'text',text:'x'}}]}}],tools:{tool_schema}}})) out.push(event);\n"
        " console.log(JSON.stringify({ok:true,out}));\n"
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
