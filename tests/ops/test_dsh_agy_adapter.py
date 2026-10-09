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
    script: list[dict] | None = None,
    wait: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.Popen[str]:
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
    script_file = tmp_path / "attempts.json"
    script_file.write_text(json.dumps(script or []), encoding="utf-8")
    counter_file = tmp_path / "counter.txt"
    attempts_log = tmp_path / "attempts.log"
    dispatch = tmp_path / "dispatch.py"
    dispatch.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args=sys.argv[1:]\n"
        f"script=json.load(open({str(script_file)!r}))\n"
        f"counter={str(counter_file)!r}\n"
        "n=int(open(counter).read()) if os.path.exists(counter) else 0\n"
        "n+=1\n"
        "open(counter,'w').write(str(n))\n"
        "step=(script[min(n-1,len(script)-1)] if script else {})\n"
        f"open({str(attempts_log)!r}, 'a').write(json.dumps({{'n':n,'args':args,'prompt':args[args.index('--prompt-file')+1]}})+'\\n')\n"
        "if step.get('start_fail'):\n"
        "    sys.stderr.write('NEXUS_AGY_DISPATCH '+json.dumps(step['start_fail'])+'\\n')\n"
        "    sys.exit(75)\n"
        f"import shutil; shutil.copy(args[args.index('--prompt-file')+1], {str(tmp_path / 'prompt.txt')!r})\n"
        f"open({str(argv_log)!r}, 'w').write(json.dumps(args))\n"
        "cwd=args[args.index('--cwd')+1]\n"
        f"open({str(scratch_log)!r}, 'w').write(json.dumps({{'cwd':cwd,'has_git':os.path.isdir(os.path.join(cwd,'.git')),'has_baseline':os.path.isfile(os.path.join(cwd,'.dsh-intelligence-scratch'))}}))\n"
        "status=os.environ.get('FAKE_STATUS','COMPLETED')\n"
        "stdout_path=step.get('stdout_path') or os.environ['FAKE_STDOUT']\n"
        "if 'response' in step:\n"
        f"    stdout_path={str(tmp_path / 'step.stdout')!r}\n"
        "    open(stdout_path,'w').write(step['response'])\n"
        "rec={'operation_id':'agyop_test','status':step.get('status',status),'stdout_path':stdout_path}\n"
        "rec.update(step.get('record',{}))\n"
        "print(json.dumps(rec))\n",
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
        "const calls = Number(process.env.FAKE_CALLS ?? '1');\n"
        "const runs = [];\n"
        "const parallel = process.env.FAKE_PARALLEL === '1';\n"
        "const runOne = async () => {\n"
        " const out=[];\n"
        " try {\n"
        f" const modelInfo=await adapter.resolveModel('nexus-agy-pool',{model!r});\n"
        f" for await (const event of adapter.stream({{model:{model!r},reasoningEffort:{effort!r},sessionId:process.env.FAKE_SESSION_ID,messages:[{{role:'user',content:[{{type:'text',text:'x'}}]}}],tools:{tool_schema},purpose:{purpose_literal}}})) out.push(event);\n"
        " runs.push({ok:true,out,modelInfo});\n"
        " } catch (e) { runs.push({ok:false,code:e.code||null,attempts:e.attempts||null,failureKind:e.failureKind||null,originalCode:e.originalCode||null,effect:e.effect||null,retryable:e.retryable||false,message:String(e.message)}); }\n"
        "};\n"
        "if (parallel) await Promise.all(Array.from({ length: calls }, runOne));\n"
        "else for (let i = 0; i < calls; i++) await runOne();\n"
        "if (calls === 1) { console.log(JSON.stringify(runs[0])); if (!runs[0].ok) process.exitCode = 3; }\n"
        "else { console.log(JSON.stringify(runs)); }\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update({
        "NEXUS_AGY_DISPATCH": str(dispatch),
        "FAKE_STDOUT": str(stdout_path),
        "NEXUS_DSH_AGY_RETRY_BACKOFF_MS": "1,1",
        "NEXUS_DSH_AGY_BUDGET_DIR": str(tmp_path / "budget"),
    })
    if extra_env:
        env.update(extra_env)
    if not wait:
        return subprocess.Popen(
            ["node", str(script)],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
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


def test_provider_call_cap_blocks_fourth_physical_dispatch(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path,
        '{"kind":"text","text":"OK"}',
        extra_env={
            "FAKE_CALLS": "4",
            "NEXUS_DSH_AGY_MAX_PROVIDER_CALLS": "3",
            "FAKE_SESSION_ID": "session-cap-main",
        },
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    runs = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [run["ok"] for run in runs] == [True, True, True, False]
    fourth = runs[3]
    assert fourth["code"] == "AGY_PROVIDER_CALL_CAP_EXHAUSTED"
    assert fourth["effect"] == "none"
    assert fourth["retryable"] is False
    # Physical negative control: the fourth call never reaches the dispatcher.
    assert (tmp_path / "counter.txt").read_text() == "3"


def test_provider_call_cap_absent_keeps_existing_behavior(tmp_path: Path) -> None:
    proc = _run_node(tmp_path, '{"kind":"text","text":"OK"}', extra_env={"FAKE_CALLS": "4"})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    runs = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [run["ok"] for run in runs] == [True, True, True, True]
    assert (tmp_path / "counter.txt").read_text() == "4"


def _budget_record_path(budget: Path, session_id: str) -> Path:
    return budget / (hashlib.sha256(session_id.encode("utf-8")).hexdigest() + ".json")


def _capped(
    tmp_path: Path,
    name: str,
    calls: int,
    *,
    cap: str = "3",
    session: str | None = "S-1",
    extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        "FAKE_CALLS": str(calls),
        "NEXUS_DSH_AGY_MAX_PROVIDER_CALLS": cap,
        "NEXUS_DSH_AGY_BUDGET_DIR": str(tmp_path / "shared"),
    }
    if session is not None:
        env["FAKE_SESSION_ID"] = session
    env.update(extra or {})
    return _run_node(tmp_path / name, '{"kind":"text","text":"OK"}', extra_env=env)


def _runs(proc: subprocess.CompletedProcess[str]) -> list[dict]:
    # Exit 3 is the harness's documented failed-run signal; the JSON payload carries the verdict.
    assert proc.returncode in (0, 3), proc.stderr + proc.stdout
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    return data if isinstance(data, list) else [data]


def _dispatches(tmp_path: Path, name: str) -> int:
    counter = tmp_path / name / "counter.txt"
    return int(counter.read_text()) if counter.exists() else 0


def test_session_budget_survives_process_restart_and_blocks_fourth_dispatch(tmp_path: Path) -> None:
    first = _capped(tmp_path, "a", 3)
    assert [run["ok"] for run in _runs(first)] == [True, True, True]
    assert _dispatches(tmp_path, "a") == 3
    # Process B is a fresh adapter (restart) with the same session: zero fourth dispatch.
    run = _runs(_capped(tmp_path, "b", 1))[0]
    assert run["ok"] is False
    assert run["code"] == "AGY_PROVIDER_CALL_CAP_EXHAUSTED"
    assert run["effect"] == "none"
    assert run["retryable"] is False
    assert _dispatches(tmp_path, "b") == 0


def test_session_budget_is_isolated_and_legacy_stays_unlimited(tmp_path: Path) -> None:
    assert [run["ok"] for run in _runs(_capped(tmp_path, "a", 1, cap="1", session="S-iso-a"))] == [
        True
    ]
    assert [run["ok"] for run in _runs(_capped(tmp_path, "b", 1, cap="1", session="S-iso-b"))] == [
        True
    ]
    legacy = _run_node(
        tmp_path / "legacy", '{"kind":"text","text":"OK"}', extra_env={"FAKE_CALLS": "4"}
    )
    assert [run["ok"] for run in _runs(legacy)] == [True, True, True, True]
    assert _dispatches(tmp_path, "legacy") == 4


def test_capped_session_without_identity_fails_closed_before_dispatch(tmp_path: Path) -> None:
    run = _runs(_capped(tmp_path, "a", 1, session=None))[0]
    assert run["ok"] is False
    assert run["code"] == "AGY_PROVIDER_BUDGET_SESSION_REQUIRED"
    assert _dispatches(tmp_path, "a") == 0


def test_capped_session_cannot_increase_or_disappear_on_restart(tmp_path: Path) -> None:
    assert _runs(_capped(tmp_path, "a", 1, cap="3"))[0]["ok"] is True
    raised = _runs(_capped(tmp_path, "b", 1, cap="5"))[0]
    assert raised["code"] == "AGY_PROVIDER_BUDGET_CAP_MISMATCH"
    removed = _runs(_capped(tmp_path, "c", 1, cap="", session="S-1"))[0]
    assert removed["code"] == "AGY_PROVIDER_BUDGET_CAP_REMOVED"
    assert _dispatches(tmp_path, "b") == 0
    assert _dispatches(tmp_path, "c") == 0


def test_same_session_concurrent_calls_cannot_exceed_cap(tmp_path: Path) -> None:
    runs = _runs(_capped(tmp_path, "a", 2, cap="1", extra={"FAKE_PARALLEL": "1"}))
    assert sorted(run["ok"] for run in runs) == [False, True]
    assert _dispatches(tmp_path, "a") == 1


def test_corrupt_budget_record_fails_closed(tmp_path: Path) -> None:
    budget = tmp_path / "shared"
    budget.mkdir()
    _budget_record_path(budget, "S-bad").write_text("{not json", encoding="utf-8")
    run = _runs(_capped(tmp_path, "a", 1, session="S-bad"))[0]
    assert run["code"] == "AGY_PROVIDER_BUDGET_STATE_INVALID"
    assert _dispatches(tmp_path, "a") == 0


def test_stale_budget_lock_fails_closed_without_stealing(tmp_path: Path) -> None:
    budget = tmp_path / "shared"
    budget.mkdir()
    lock = budget / (hashlib.sha256(b"S-lock").hexdigest() + ".lock")
    lock.write_text("", encoding="utf-8")
    run = _runs(_capped(tmp_path, "a", 1, session="S-lock"))[0]
    assert run["code"] == "AGY_PROVIDER_BUDGET_LOCK_TIMEOUT"
    assert lock.exists()
    assert _dispatches(tmp_path, "a") == 0


def test_two_processes_same_session_cap1_cannot_double_dispatch(tmp_path: Path) -> None:
    budget = tmp_path / "shared"
    base_env = {
        "FAKE_CALLS": "1",
        "NEXUS_DSH_AGY_MAX_PROVIDER_CALLS": "1",
        "FAKE_SESSION_ID": "S-two-proc",
        "NEXUS_DSH_AGY_BUDGET_DIR": str(budget),
    }
    procs = [
        _run_node(tmp_path / name, '{"kind":"text","text":"OK"}', extra_env=base_env, wait=False)
        for name in ("a", "b")
    ]
    results = []
    for proc in procs:
        out, err = proc.communicate()
        other = [
            line for line in err.splitlines() if not line.startswith("NEXUS_DSH_AGY_OPERATION ")
        ]
        assert other == [], err
        results.append(json.loads(out.strip().splitlines()[-1]))
    assert sorted(run["ok"] for run in results) == [False, True]
    # Total physical dispatcher effects across both processes must not exceed the cap.
    assert _dispatches(tmp_path, "a") + _dispatches(tmp_path, "b") == 1


def test_budget_record_with_inconsistent_purpose_sum_fails_closed(tmp_path: Path) -> None:
    budget = tmp_path / "shared"
    budget.mkdir()
    record = {
        "schema": "nexus.dsh_agy_provider_budget.v1",
        "limit": 3,
        "used": 1,
        "purposes": {"agent": 2},
    }
    _budget_record_path(budget, "S-sum").write_text(json.dumps(record), encoding="utf-8")
    run = _runs(_capped(tmp_path, "a", 1, session="S-sum"))[0]
    assert run["code"] == "AGY_PROVIDER_BUDGET_STATE_INVALID"
    assert _dispatches(tmp_path, "a") == 0


def test_uncapped_resume_fails_closed_when_budget_dir_is_unreadable(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    (locked / "budget").mkdir(parents=True)
    locked.chmod(0o000)
    try:
        run = _runs(
            _run_node(
                tmp_path / "a",
                '{"kind":"text","text":"OK"}',
                extra_env={
                    "FAKE_CALLS": "1",
                    "FAKE_SESSION_ID": "S-acl",
                    "NEXUS_DSH_AGY_BUDGET_DIR": str(locked / "budget"),
                },
            )
        )[0]
    finally:
        locked.chmod(0o755)
    assert run["code"] == "AGY_PROVIDER_BUDGET_STATE_INVALID"
    assert _dispatches(tmp_path, "a") == 0


def test_uncapped_call_fails_closed_when_budget_path_is_not_a_directory(tmp_path: Path) -> None:
    bogus = tmp_path / "budget-file"
    bogus.write_text("", encoding="utf-8")
    run = _runs(
        _run_node(
            tmp_path / "a",
            '{"kind":"text","text":"OK"}',
            extra_env={
                "FAKE_CALLS": "1",
                "FAKE_SESSION_ID": "S-file",
                "NEXUS_DSH_AGY_BUDGET_DIR": str(bogus),
            },
        )
    )[0]
    assert run["code"] == "AGY_PROVIDER_BUDGET_STATE_INVALID"
    assert _dispatches(tmp_path, "a") == 0


def test_adapter_emits_operation_marker_without_prompt_content(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path, '{"kind":"text","text":"OK"}', extra_env={"FAKE_SESSION_ID": "S-marker"}
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    markers = [
        line for line in proc.stderr.splitlines() if line.startswith("NEXUS_DSH_AGY_OPERATION ")
    ]
    assert len(markers) == 1
    marker_json = markers[0][len("NEXUS_DSH_AGY_OPERATION ") :]
    assert json.loads(marker_json) == {
        "schema": "nexus.dsh_agy_operation_marker.v1",
        "dsh_session_id": "S-marker",
        "operation_id": "agyop_test",
        "purpose": "agent",
    }
    assert "dsh_action" not in marker_json


def _evidence_args(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, arg in enumerate(argv) if arg == "--evidence-ref"]


def _session_ref(session: str, purpose: str) -> str:
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
    return f"dsh_session:v1:session_sha256={digest}:purpose={purpose}"


def test_dispatch_argv_binds_session_hash_and_purpose(tmp_path: Path) -> None:
    for name, purpose, label in (
        ("agent", None, "agent"),
        ("title", "session-title", "session-title"),
        ("compact", "compaction", "compaction"),
    ):
        proc = _run_node(
            tmp_path / name,
            '{"kind":"text","text":"OK"}',
            purpose=purpose,
            extra_env={"FAKE_SESSION_ID": "S-bind-argv"},
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        argv = json.loads((tmp_path / name / "argv.json").read_text())
        refs = _evidence_args(argv)
        assert _session_ref("S-bind-argv", label) in refs
        assert all("S-bind-argv" not in arg for arg in argv)


def test_invalid_or_absent_session_adds_no_session_ref(tmp_path: Path) -> None:
    absent = _run_node(tmp_path / "absent", '{"kind":"text","text":"OK"}')
    assert absent.returncode == 0, absent.stderr + absent.stdout
    assert not any(
        ref.startswith("dsh_session:v1:")
        for ref in _evidence_args(json.loads((tmp_path / "absent" / "argv.json").read_text()))
    )
    unsafe = _run_node(
        tmp_path / "unsafe",
        '{"kind":"text","text":"OK"}',
        extra_env={"FAKE_SESSION_ID": "bad id with spaces"},
    )
    assert unsafe.returncode == 0, unsafe.stderr + unsafe.stdout
    assert not any(
        ref.startswith("dsh_session:v1:")
        for ref in _evidence_args(json.loads((tmp_path / "unsafe" / "argv.json").read_text()))
    )


def test_single_dispatch_carries_contract_and_session_evidence_together(tmp_path: Path) -> None:
    proc = _run_node(
        tmp_path, '{"kind":"text","text":"CANARY_OK"}', extra_env={"FAKE_SESSION_ID": "S-both"}
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    refs = _evidence_args(json.loads((tmp_path / "argv.json").read_text()))
    contract = [ref for ref in refs if ref.startswith("dsh_action_contract:v1:")]
    assert len(contract) == 1
    assert _session_ref("S-both", "agent") in refs
    assert len(refs) == 2
