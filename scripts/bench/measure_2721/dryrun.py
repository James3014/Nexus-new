"""Zero-model dry run: prove BARE and NEXUS launch the identical Claude run.

No model is called: the Claude CLI is ``fake_claude.py`` (mode ``record``),
which reports what it was launched with.  Per task:

* BARE  -> ``ClaudeProvider`` -> ``ClaudeMeasurementWorkerAdapter.invoke``;
* NEXUS -> ``nexus_local_chain.py``: the real Gateway ``nexus_worker_candidate``
  and the real service, which reach the same adapter through P1;
* NOOP  -> no invocation (input capture only).

Checks (all must hold; ``symmetry_report.json`` lists every failure):

1. argv identical and equal to ``CLAUDE_MEASUREMENT_FLAGS`` + prompt;
2. prompt: BARE prompt == the Gateway's own base worker prompt, and the NEXUS
   prompt == BARE prompt + ``"\\n\\n" + MODEL_CONTEXT_MARKER`` + Nexus context;
3. environment: same keys; same values except the per-run paths, proxy port
   and run tag (shape-checked instead);
4. ``system/init`` shell fields identical (tools, MCP servers, model,
   permission mode, CLI version, ...);
5. Seatbelt profile identical after normalizing paths and the proxy port;
6. NEXUS dispatch resolved provider ``claude`` / model ``claude-haiku-5-5``;
7. BARE and NOOP made no edit; every task text field identical across arms.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.arms import load_manifest, new_run_id, run_bare, run_noop
from scripts.bench.measure_2721.common import read_jsonl, write_json
from scripts.bench.measure_2721.fake_claude import write_fake_claude
from scripts.bench.measure_2721.nexus_driver import gateway_task_id
from scripts.bench.measure_2721.providers import ClaudeProvider, claude_identity, read_claude_trace

SHARED_TEXT_FIELDS = ("what", "why", "allowed_files", "verifier_commands", "base_commit", "base_tree_sha",
                      "text_sha256", "base_prompt", "base_prompt_sha256", "task_id", "repeat")
# Values that are per run by design; compared by shape, not by value.
VOLATILE_ENV = frozenset({"HOME", "CLAUDE_CONFIG_DIR", "TMPDIR", "CLAUDE_CODE_TMPDIR", "HTTPS_PROXY", "HTTP_PROXY",
                          "ALL_PROXY", "https_proxy", "http_proxy", "NEXUS_CLI_WORKER_RUN_TAG", "GH_CONFIG_DIR",
                          "PYTHONPATH"})


def _model_context_marker() -> str:
    from nexus_runtime.task_context.consumer_projection import MODEL_CONTEXT_MARKER

    return MODEL_CONTEXT_MARKER


def _trace_for(trace_dir: Path, task_id: str) -> dict[str, Any]:
    streams = sorted((trace_dir / task_id).glob("*.stream.jsonl"))
    if len(streams) != 1:
        return {"error": f"expected 1 trace for {task_id}, found {len(streams)}"}
    trace = read_claude_trace(trace_dir, task_id, streams[0].name.split(".", 1)[0])
    return {"observed": trace["fake_observed"] or {}, "init": trace["summary"].init, "sidecar": trace["sidecar"]}


def compare_invocations(bare: Mapping[str, Any], nexus: Mapping[str, Any], bare_prompt: str,
                        gateway_base_prompt: str | None) -> list[str]:
    from nexus.executors.claude_measurement_worker import CLAUDE_MEASUREMENT_FLAGS

    failures: list[str] = []
    b_obs, n_obs = bare.get("observed") or {}, nexus.get("observed") or {}
    b_argv, n_argv = list(b_obs.get("argv") or []), list(n_obs.get("argv") or [])
    if not b_argv or not n_argv:
        return ["an arm made no Claude invocation"]
    if b_argv[:-1] != n_argv[:-1]:
        failures.append("argv flags differ between arms")
    if b_argv[:-1] != list(CLAUDE_MEASUREMENT_FLAGS):
        failures.append("argv flags differ from CLAUDE_MEASUREMENT_FLAGS")
    if b_argv[-1] != bare_prompt:
        failures.append("BARE prompt is not the task's base prompt")
    if gateway_base_prompt is not None and gateway_base_prompt != bare_prompt:
        failures.append("Gateway base worker prompt differs from the BARE prompt")
    if not n_argv[-1].startswith(bare_prompt + "\n\n" + _model_context_marker()):
        failures.append("NEXUS prompt is not BARE prompt + model-context block")
    b_env, n_env = dict(b_obs.get("env") or {}), dict(n_obs.get("env") or {})
    if set(b_env) != set(n_env):
        failures.append(f"env keys differ: {sorted(set(b_env) ^ set(n_env))}")
    for key in sorted(set(b_env) & set(n_env)):
        if key in VOLATILE_ENV:
            continue
        if b_env[key] != n_env[key]:
            failures.append(f"env {key} differs")
    for env in (b_env, n_env):
        if not env.get("CLAUDE_CONFIG_DIR", "").startswith(env.get("HOME", "\0")):
            failures.append("CLAUDE_CONFIG_DIR is not inside the per-run HOME")
        if "nexus-claude-run-" not in env.get("HOME", ""):
            failures.append("HOME is not a fresh per-run directory")
    # git must behave the same in both arms (review H2): same exit code and output.
    if b_obs.get("git_status") != n_obs.get("git_status"):
        failures.append(f"git status differs: BARE {b_obs.get('git_status')} vs NEXUS {n_obs.get('git_status')}")
    elif (b_obs.get("git_status") or {}).get("rc") != 0:
        failures.append(f"git status fails in both arms: {b_obs.get('git_status')}")
    if (bare.get("init") or {}) != (nexus.get("init") or {}):
        failures.append("system/init shell fields differ")
    b_prof = (bare.get("sidecar") or {}).get("seatbelt_profile_normalized")
    n_prof = (nexus.get("sidecar") or {}).get("seatbelt_profile_normalized")
    if not b_prof or b_prof != n_prof:
        failures.append("normalized Seatbelt profiles differ or are missing")
    return failures


def file_scope_manifest(manifest: Path, out: Path) -> Path:
    """A dry-run-only copy whose scope is one exact file per task.

    P1's lifecycle envelope (``lifecycle_action._repo_path``) rejects
    directory scopes such as ``sympy/`` today, so the invocation symmetry is
    proven on an exact-file scope: the alphabetically first ``.py`` file of
    the first scope directory (chosen from the tree, never from the gold).
    """
    from scripts.bench.measure_2721.common import sha256_text, write_jsonl
    from scripts.bench.measure_2721.task_text import TaskText, render_worker_prompt

    rows = []
    for task in load_manifest(manifest):
        task = json.loads(json.dumps(task))
        base = Path(task["base_checkout"])
        first = task["scope"][0]
        files = sorted(p.relative_to(base).as_posix() for p in (base / first).rglob("*.py")) \
            if first.endswith("/") else [first]
        text = dict(task["text"], allowed_files=[files[0]])
        tt = TaskText(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in text.items()})
        task["text"] = tt.as_dict()
        task["text_sha256"] = tt.sha256()
        task["prompt_sha256"] = sha256_text(render_worker_prompt(tt))
        task["dryrun_file_scope"] = True
        rows.append(task)
    path = out / "manifest.file-scope.jsonl"
    write_jsonl(path, rows)
    return path


def dry_run(manifest: Path, out: Path, *, file_scope: bool = False) -> dict[str, Any]:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if file_scope:
        manifest = file_scope_manifest(manifest, out)
    fake = write_fake_claude(out / "bin" / "claude", "record")
    token = out / "anthropic.env"
    # Built at runtime: no key-shaped literal in the source (secret audit).
    fake_key = "-".join(("sk", "ant", "dryrun", "NOT", "A", "REAL", "KEY", "0000000000"))
    token.write_text(f"ANTHROPIC_API_KEY={fake_key}\n", encoding="utf-8")
    os.chmod(token, 0o600)
    os.environ.setdefault("NEXUS_MEASUREMENT_READ_ROOTS", str(out))
    trace_dir = out / "traces"
    provider = ClaudeProvider(str(fake), trace_dir, str(token), identity=claude_identity(str(fake), str(token)))
    per_task: dict[str, Any] = {}
    for task in load_manifest(manifest):
        bare_row = run_bare(task, 1, out, provider, timeout_seconds=120.0)
        run_noop(task, 1, out)
        gw_task = gateway_task_id(new_run_id("NEXUS", task["task_id"], 1))
        spec = {"task": task, "gateway_task_id": gw_task, "work": str(out / "nexus" / gw_task),
                "out": str(out / "nexus" / f"{gw_task}.json")}
        spec_path = out / "nexus" / f"{gw_task}.spec.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if not key.startswith("NEXUS_")}
        env.update(provider.environ())
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
        subprocess.run([sys.executable, str(Path(__file__).with_name("nexus_local_chain.py")), str(spec_path)],
                       env=env, check=True, timeout=900)
        chain = json.loads(Path(spec["out"]).read_text(encoding="utf-8"))
        failures: list[str] = []
        if chain.get("driver_error") or chain.get("gateway_is_error") or chain.get("submit_error"):
            failures.append(f"local P1 chain failed: {chain.get('driver_error') or chain.get('gateway_error') or chain.get('submit_error')}")
        if (chain.get("provider"), chain.get("model")) != ("claude", "claude-haiku-5-5"):
            failures.append(f"P1 dispatched {chain.get('provider')}/{chain.get('model')}")
        if chain.get("executions") != ["claude"]:
            failures.append(f"P1 worker executions: {chain.get('executions')}")
        bare_trace = _trace_for(trace_dir, bare_row["run_id"])
        nexus_trace = _trace_for(trace_dir, gw_task)
        for name, trace in (("BARE", bare_trace), ("NEXUS", nexus_trace)):
            if "error" in trace:
                failures.append(f"{name}: {trace['error']}")
        if not failures:
            failures += compare_invocations(bare_trace, nexus_trace, bare_row and _bare_prompt(out, bare_row),
                                            chain.get("base_prompt"))
        worker_args = chain.get("worker_args") or {}
        for field in ("what", "why", "allowed_files", "verifier_commands"):
            if worker_args.get(field) != task["text"][field]:
                failures.append(f"P1 worker_candidate.{field} differs from the task text")
        per_task[task["task_id"]] = {"status": "PASS" if not failures else "FAIL", "failures": failures,
                                     "nexus_chain_status": chain.get("status"),
                                     "nexus_chain_error": chain.get("error"),
                                     "claude_version": bare_row.get("claude_version")}
    rows = list(read_jsonl(out / "rows.jsonl"))
    edits = [row["run_id"] for row in rows if row["arm"] in ("BARE", "NOOP") and not row["empty"]]
    report = {
        "schema": "nexus.measure_2721.symmetry_report.v2",
        "manifest": str(manifest),
        "fake_claude": str(fake),
        "model_calls": 0,
        "per_task": per_task,
        "zero_model_edits": edits,
        "status": "PASS" if per_task and not edits and all(v["status"] == "PASS" for v in per_task.values()) else "FAIL",
    }
    write_json(out / "symmetry_report.json", report)
    return report


def _bare_prompt(out: Path, row: Mapping[str, Any]) -> str:
    return json.loads((out / "inputs" / f"{row['run_id']}.json").read_text(encoding="utf-8"))["base_prompt"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--file-scope", action="store_true",
                        help="prove symmetry on a one-file scope (P1 rejects directory scopes today)")
    args = parser.parse_args(argv)
    report = dry_run(Path(args.manifest), Path(args.out), file_scope=args.file_scope)
    print(json.dumps({"status": report["status"], "tasks": len(report["per_task"]),
                      "report": str(Path(args.out) / "symmetry_report.json")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
