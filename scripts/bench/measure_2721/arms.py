"""BARE and NOOP arms: one session per (task, repeat), same text and scope.

Every run writes:
* ``inputs/<run_id>.json``: exactly what the arm was given (prompt, text,
  scope, base tree).  The dry run diffs these across arms.
* ``diffs/<run_id>.diff``: the final candidate diff against the base commit.
* one row in ``rows.jsonl`` (arm label in clear: these rows are *not* the
  blinded scorer input; ``blind.py`` produces that).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import (
    append_jsonl,
    capture_diff,
    diff_paths,
    git,
    read_jsonl,
    sha256_text,
    write_json,
)
from scripts.bench.measure_2721.leakage import FLAG_NETWORK_ATTEMPT, FLAG_TIMEOUT, lookup_signals
from scripts.bench.measure_2721.materialize import checkout_base, link_venv
from scripts.bench.measure_2721.providers import (
    STATUS_INFRA,
    STATUS_OK,
    STATUS_TIMEOUT,
    Provider,
    ProviderResult,
    build_provider,
)
from scripts.bench.measure_2721.scope import is_test_path, out_of_scope
from scripts.bench.measure_2721.task_text import render_worker_prompt

ROW_SCHEMA = "nexus.measure_2721.arm_row.v1"
DEFAULT_TIMEOUT_SECONDS = 900.0  # runtime coordinator default worker timeout (P1)
ARM_BARE = "BARE"
ARM_NOOP = "NOOP"
ARM_NEXUS = "NEXUS"


def new_run_id(arm: str, task_id: str, repeat: int) -> str:
    return f"m2721-{arm.lower()}-{task_id}-r{repeat}-{secrets.token_hex(3)}"


def task_prompt(task: Mapping[str, Any]) -> str:
    """The rendered base prompt, cross-checked against the materialized copy."""
    prompt = render_worker_prompt(task["text"])
    if sha256_text(prompt) != task["prompt_sha256"]:
        raise RuntimeError(f"{task['task_id']}: prompt drifted from the manifest")
    return prompt


def input_capture(arm: str, task: Mapping[str, Any], repeat: int, run_id: str, *,
                  prompt: Optional[str], tree_sha: str, timeout_seconds: float) -> dict[str, Any]:
    return {
        "schema": "nexus.measure_2721.arm_input.v1",
        "arm": arm,
        "run_id": run_id,
        "task_id": task["task_id"],
        "repeat": repeat,
        "base_commit": task["base_commit"],
        "base_tree_sha": tree_sha,
        "what": task["text"]["what"],
        "why": task["text"]["why"],
        "allowed_files": list(task["text"]["allowed_files"]),
        "verifier_commands": list(task["text"]["verifier_commands"]),
        "text_sha256": task["text_sha256"],
        "base_prompt": prompt,
        "base_prompt_sha256": sha256_text(prompt) if prompt is not None else None,
        "timeout_seconds": timeout_seconds,
        "agy_run_settings": agy_run_settings_in_effect(),
    }


def agy_run_settings_in_effect() -> Any:
    """The Agy run settings this host's Nexus code writes for an implementation run.

    Both arms must run under the same settings (e.g. the web-fetch deny rules);
    the NEXUS value is authoritative only when the driver runs on the Gateway host.
    """
    try:
        from nexus.executors.agy_write_admission import agy_run_settings
    except Exception:  # pragma: no cover - outside a Nexus venv
        return None
    return agy_run_settings(read_only=False)


def candidate_facts(diff: str, task: Mapping[str, Any]) -> dict[str, Any]:
    paths = diff_paths(diff)
    return {
        "diff_sha256": sha256_text(diff),
        "diff_bytes": len(diff.encode("utf-8")),
        "changed_paths": paths,
        "out_of_scope_paths": out_of_scope(paths, task["scope"]),
        "test_paths_touched": [path for path in paths if is_test_path(path)],
        "empty": not diff.strip(),
    }


FLAG_SERVED_MODEL_MISMATCH = "SERVED_MODEL_MISMATCH"
FLAG_GIT_TAMPERED = "GIT_METADATA_TAMPERED"
FLAG_SECRET_IN_DIFF = "SECRET_REDACTED_FROM_DIFF"
MEASUREMENT_MODEL = "claude-haiku-5-5"


def redact_diff(diff: str, key_file: Optional[str] = None) -> tuple[str, bool]:
    """Remove key-shaped strings and the measurement key from a candidate diff
    (an agent could write ``env`` into a file); True when anything was removed."""
    from nexus.executors.claude_measurement_worker import (
        MEASUREMENT_ANTHROPIC_ENV_FILE_ENV,
        measurement_claude_api_key,
        redact_secrets,
    )

    raw = diff.encode("utf-8", errors="surrogateescape")
    key = measurement_claude_api_key({MEASUREMENT_ANTHROPIC_ENV_FILE_ENV: key_file} if key_file else None)
    cleaned = redact_secrets(raw, (key,) if key else ())
    return cleaned.decode("utf-8", errors="surrogateescape"), cleaned != raw


def served_model_flag(served: Any) -> Optional[str]:
    """Both arms must show exactly the measurement model serving the run (driver item 6)."""
    if served is None:
        return None
    return None if list(served) == [MEASUREMENT_MODEL] else FLAG_SERVED_MODEL_MISMATCH


def run_bare(task: Mapping[str, Any], repeat: int, run_root: Path, provider: Provider, *,
             timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, keep_workdir: bool = False) -> dict[str, Any]:
    from scripts.bench.measure_2721 import watchdog
    from scripts.bench.measure_2721.common import git_meta_fingerprint, write_diff

    run_id = new_run_id(ARM_BARE, task["task_id"], repeat)
    workdir = run_root / "work" / run_id / "repo"
    checkout_base(Path(task["base_checkout"]), task["base_commit"], workdir)
    link_venv(task, workdir)
    git_meta = git_meta_fingerprint(workdir)
    tree_sha = git(workdir, "rev-parse", "HEAD^{tree}").strip()
    prompt = task_prompt(task)
    write_json(run_root / "inputs" / f"{run_id}.json",
               input_capture(ARM_BARE, task, repeat, run_id, prompt=prompt, tree_sha=tree_sha,
                             timeout_seconds=timeout_seconds))
    watchdog.begin_row(run_root, row_id=run_id, task_id=task["task_id"], arm=ARM_BARE, cap_s=timeout_seconds)
    started = time.monotonic()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result: ProviderResult = provider.run(prompt=prompt, workdir=workdir, timeout_seconds=timeout_seconds,
                                          run_id=run_id)
    wall = time.monotonic() - started
    tampered = git_meta_fingerprint(workdir) != git_meta
    # #2749: a changed .git/config, info/ or hooks/ means no git command is run.
    diff = "" if tampered else capture_diff(workdir, task["base_commit"])
    diff, redacted = redact_diff(diff, getattr(provider, "key_file", None))
    watchdog.mark_snapshot(run_root)
    diff_path = run_root / "diffs" / f"{run_id}.diff"
    write_diff(diff_path, diff)
    extra = result.extra or {}
    lookup = lookup_signals(
        [extra.get("response_text") or "", extra.get("stderr_tail") or "", extra.get("tool_inputs_text") or ""],
        repo=task.get("repo", ""), denied_actions=extra.get("denied_actions") or ())
    network = [a for a in (extra.get("proxy_attempts") or []) if not a.get("allowed")]
    infra_event = watchdog.infra_event_for(run_root, run_id)
    flags = [flag for flag in (
        FLAG_TIMEOUT if result.status == STATUS_TIMEOUT else None,
        lookup["flag"],
        FLAG_NETWORK_ATTEMPT if network else None,
        served_model_flag(extra.get("served_models")) if result.status == STATUS_OK else None,
        FLAG_GIT_TAMPERED if tampered else None,
        FLAG_SECRET_IN_DIFF if redacted else None,
    ) if flag]
    row = {
        "schema": ROW_SCHEMA,
        "arm": ARM_BARE,
        "flags": flags,
        **claude_row_fields(extra),
        "lookup": lookup,
        "run_id": run_id,
        "task_id": task["task_id"],
        "repeat": repeat,
        "started_at": started_at,
        "wall_seconds": round(wall, 3),
        "outcome": "TAMPERED" if tampered else (STATUS_INFRA if infra_event else result.status),
        "infra": result.status == STATUS_INFRA or infra_event is not None,
        "watchdog_event": infra_event,
        "provider": result.as_dict(),
        "model_calls": result.model_calls,
        "total_tokens": result.total_tokens,
        "diff_path": str(diff_path),
        "non_model_solve_path": False,
        **candidate_facts(diff, task),
    }
    append_jsonl(run_root / "rows.jsonl", row)
    watchdog.end_row(run_root)
    if not keep_workdir:
        shutil.rmtree(workdir.parent, ignore_errors=True)
    return row


def claude_row_fields(extra: Mapping[str, Any]) -> dict[str, Any]:
    """Per-row model/cost/identity fields of a Claude run (empty otherwise)."""
    if "claude_version" not in extra:
        return {}
    usage = extra.get("usage") or {}
    return {
        "claude_version": extra.get("claude_version"),
        "claude_executable": extra.get("claude_executable"),
        "account": extra.get("account"),
        "worker_span_ms": extra.get("worker_span_ms"),
        "num_turns": extra.get("num_turns"),
        "tool_call_count": extra.get("tool_call_count"),
        "total_cost_usd": extra.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "models_seen": extra.get("models_seen"),
        "served_models": extra.get("served_models"),
        "cli_timeout_seconds": extra.get("cli_timeout_seconds"),
        "key_label": extra.get("key_label"),
        "api_key_sha256_12": extra.get("api_key_sha256_12"),
        "seatbelt_sha256": extra.get("seatbelt_sha256"),
        "proxy_denied": [a for a in (extra.get("proxy_attempts") or []) if not a.get("allowed")],
    }


def run_noop(task: Mapping[str, Any], repeat: int, run_root: Path) -> dict[str, Any]:
    """No model, no edit: the S3 NOOP arm.  Must score 0 RESOLVED."""
    run_id = new_run_id(ARM_NOOP, task["task_id"], repeat)
    tree_sha = git(Path(task["base_checkout"]), "rev-parse", "HEAD^{tree}").strip()
    write_json(run_root / "inputs" / f"{run_id}.json",
               input_capture(ARM_NOOP, task, repeat, run_id, prompt=task_prompt(task), tree_sha=tree_sha,
                             timeout_seconds=0.0))
    diff = ""
    diff_path = run_root / "diffs" / f"{run_id}.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_bytes(b"")
    row = {
        "schema": ROW_SCHEMA,
        "arm": ARM_NOOP,
        "flags": [],
        "run_id": run_id,
        "task_id": task["task_id"],
        "repeat": repeat,
        "wall_seconds": 0.0,
        "outcome": STATUS_OK,
        "infra": False,
        "provider": None,
        "model_calls": 0,
        "total_tokens": 0,
        "diff_path": str(diff_path),
        "non_model_solve_path": False,
        **candidate_facts(diff, task),
    }
    append_jsonl(run_root / "rows.jsonl", row)
    return row


def load_manifest(path: Path | str, ids: Optional[Sequence[str]] = None) -> list[dict[str, Any]]:
    tasks = list(read_jsonl(path))
    if ids:
        wanted = set(ids)
        tasks = [task for task in tasks if task["task_id"] in wanted]
    return tasks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the BARE or NOOP arm of #2721")
    parser.add_argument("arm", choices=[ARM_BARE.lower(), ARM_NOOP.lower()])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--repeats", type=int, nargs="+", default=[1])
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--provider", choices=["claude", "agy", "fake"], default="fake",
                        help="'fake' makes no model call (default); 'claude' (prereg v0.4) and 'agy' are paid")
    parser.add_argument("--claude-bin", help="absolute, non-symlink claude CLI (same file as the Gateway's)")
    parser.add_argument("--key-file", default=os.path.expanduser("~/.config/nexus-measure-2721/anthropic.env"),
                        help="0600 KEY=value file with ANTHROPIC_API_KEY (read only by the adapter)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args(argv)
    run_root = Path(args.run_root)
    tasks = load_manifest(args.manifest, args.ids)
    provider = (
        build_provider(args.provider, claude_bin=args.claude_bin, trace_dir=run_root / "traces",
                       key_file=args.key_file)
        if args.arm == "bare" else None
    )
    rows = []
    for task in tasks:
        for repeat in args.repeats:
            if args.arm == "bare":
                rows.append(run_bare(task, repeat, run_root, provider, timeout_seconds=args.timeout,
                                     keep_workdir=args.keep_workdir))
            else:
                rows.append(run_noop(task, repeat, run_root))
    print(json.dumps({"rows": len(rows), "rows_path": str(run_root / "rows.jsonl")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
