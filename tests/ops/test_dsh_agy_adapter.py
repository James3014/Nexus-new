from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = ROOT / "scripts" / "ops" / "dsh-agy-adapter"


def _run_node(
    tmp_path: Path, response: str, *, tool: bool = False, model: str = "gemini-3.8-flash-low",
    effort: str = "low", extra_env: dict[str, str] | None = None,
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
        if tool else "[]"
    )
    script.write_text(
        "import { AgyPoolAdapter } from './runtime/node_modules/@nexus/dsh-llm-agy-pilot/index.js';\n"
        "const adapter = new AgyPoolAdapter();\n"
        "const out=[];\n"
        "try {\n"
        f" for await (const event of adapter.stream({{model:{model!r},reasoningEffort:{effort!r},messages:[{{role:'user',content:[{{type:'text',text:'x'}}]}}],tools:{tool_schema}}})) out.push(event);\n"
        " console.log(JSON.stringify({ok:true,out}));\n"
        "} catch (e) { console.log(JSON.stringify({ok:false,code:e.code||null,message:String(e.message)})); process.exitCode=3; }\n",
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
    assert payload["code"] == "AGY_PROTOCOL_INVALID"


def test_unknown_action_fails_closed(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"dsh_action","action_id":"A99","arguments":{}}', tool=True)
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_TOOL_NOT_AVAILABLE"


def test_action_arguments_must_be_object(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"dsh_action","action_id":"A1","arguments":"oops"}', tool=True)
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["code"] == "AGY_PROTOCOL_INVALID"


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
        tmp_path, '{"kind":"text","text":"unused"}',
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
