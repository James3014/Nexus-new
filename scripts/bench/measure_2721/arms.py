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
from scripts.bench.measure_2721.leakage import FLAG_NETWORK_ATTEMPT, FLAG_TIMEOUT, drop_tool_artifacts, lookup_signals
from scripts.bench.measure_2721.materialize import checkout_base, link_venv
from scripts.bench.measure_2721.portable import to_portable_row
from scripts.bench.measure_2721.providers import (
    STATUS_INFRA,
    STATUS_MODEL_FAILED,
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
FLAG_NON_MODEL_SOLVE = "NON_MODEL_SOLVE_PATH"


def _measurement_model() -> str:
    from nexus.executors.claude_measurement_worker import CLAUDE_MEASUREMENT_MODEL

    return CLAUDE_MEASUREMENT_MODEL


# The adapter's own constant: one source of truth for the measured model.
MEASUREMENT_MODEL = _measurement_model()


def claude_status(*, infra: bool, timed_out: bool, completed: bool) -> str:
    """One labelling rule for a Claude attempt in every arm (35's hang test).

    Infra (the adapter's ``claude_infra:*``, e.g. a 429, and the run did not
    complete) wins over a timeout, as in the adapter; the partial diff does not
    matter -- the row is re-run in all arms.
    """
    if infra and not completed:
        return STATUS_INFRA
    if timed_out:
        return STATUS_TIMEOUT
    return STATUS_OK if completed else STATUS_MODEL_FAILED


def outcome_flags(status: Optional[str], served: Any, *, seen: Any = None, fake_arm: bool = False) -> list[str]:
    """Flags derived from the status, identical in every arm: the served-model
    check applies only to a completed real run (a killed run never reports its
    model, which would be a false SERVED_MODEL_MISMATCH); a fake (NOOP) run
    must carry only the fake label."""
    flags = [FLAG_TIMEOUT] if status == STATUS_TIMEOUT else []
    if fake_arm:
        fake_flag = fake_model_flag(seen)
        if fake_flag:
            flags.append(fake_flag)
    elif status == STATUS_OK:
        served_flag = served_model_flag(served)
        if served_flag:
            flags.append(served_flag)
    return flags


def non_model_solve(diff: str, fields: Mapping[str, Any]) -> bool:
    """A non-empty candidate although the measured model made no tool call: the
    change came from somewhere else (a Nexus fast path, a fixture), not the model."""
    if "num_turns" not in fields and "tool_call_count" not in fields:
        return False  # no Claude run recorded (zero-model fakes)
    return bool(diff.strip()) and not int(fields.get("tool_call_count") or 0)


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


def expected_cli_timeout(timeout_seconds: float) -> float:
    """The CLI limit the measurement adapter derives for this cap (M2'): both arms'
    recorded ``cli_timeout_seconds`` must equal it, or the row is INFRA."""
    from nexus.executors.claude_measurement_worker import measurement_cli_timeout

    return measurement_cli_timeout(timeout_seconds)


FAKE_MODEL_PREFIX = "fake-"


def served_model_flag(served: Any) -> Optional[str]:
    """A real row must show exactly the measurement model serving the run, and
    not nothing (driver item 6, 33)."""
    if served is None:
        return None
    return None if list(served) == [MEASUREMENT_MODEL] else FLAG_SERVED_MODEL_MISMATCH


def fake_model_flag(seen: Any) -> Optional[str]:
    """A NOOP (fake CLI) row must show only the fake label, never a real model."""
    labels = list(seen or [])
    return None if labels and all(str(m).startswith(FAKE_MODEL_PREFIX) for m in labels) \
        else FLAG_SERVED_MODEL_MISMATCH


def bare_worktree(task: Mapping[str, Any], root: Path, run_id: str) -> tuple[Path, Path]:
    """The same layout P1 leases (gap review H2): a fresh base-only Controller
    clone and a detached ``git worktree`` of it as the target, venv beside the
    Controller.  Returns (controller, target)."""
    controller = root / "controller"
    checkout_base(Path(task["base_checkout"]), task["base_commit"], controller)
    link_venv(task, controller)
    target = root / "targets" / run_id
    target.parent.mkdir(parents=True)
    git(controller, "worktree", "add", "-q", "--detach", str(target), task["base_commit"])
    if git(target, "rev-parse", "HEAD").strip() != task["base_commit"]:
        raise RuntimeError("BARE target is not at the base commit")
    return controller, target


FLAG_VENV = "VENV_NOT_USABLE"


def venv_problem(task: Mapping[str, Any], observed: Any = None, *, check_observed: bool = False) -> Optional[str]:
    """Why the task venv is not the one both arms must use, else None (8d witness).

    The venv must be set, resolve inside ``NEXUS_MEASUREMENT_READ_ROOTS`` and,
    after the run, be exactly the venv the adapter granted (sidecar ``venv``)."""
    from nexus.executors.claude_measurement_worker import configured_read_roots
    from scripts.bench.measure_2721.gateway_env import measurement_env

    expected = task.get("venv")
    if not expected:
        return "VENV_MISSING"
    real = Path(os.path.realpath(expected))
    roots = configured_read_roots(measurement_env())
    if not any(real == root or root in real.parents for root in roots):
        return "VENV_OUTSIDE_READ_ROOTS"
    if check_observed and observed != str(real):
        return "VENV_MISMATCH"
    return None


def run_bare(task: Mapping[str, Any], repeat: int, run_root: Path, provider: Provider, *,
             timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, keep_workdir: bool = False,
             ledger: Any = None) -> dict[str, Any]:
    """One BARE row.  With a Claude provider the venv is checked before any spend
    (review M1); with a ledger the row is admitted and always charged, also when
    it fails part-way (M3); an unknown cost is charged its reservation (H1)."""
    if isinstance(provider, _claude_provider_type()):
        problem = venv_problem(task)
        if problem:
            row = {"schema": ROW_SCHEMA, "arm": ARM_BARE, "run_id": new_run_id(ARM_BARE, task["task_id"], repeat),
                   "task_id": task["task_id"], "repeat": repeat, "outcome": STATUS_INFRA, "infra": True,
                   "void_reason": problem, "venv_problem": problem, "flags": [FLAG_VENV], "empty": True,
                   "total_cost_usd": 0.0, "model_calls": 0, "total_tokens": None,
                   "read_roots_sha256": _read_roots_sha256()}
            # Same row count in every arm, also for a void row (review M-a).
            append_jsonl(run_root / "rows.jsonl", row)
            append_jsonl(run_root / "rows.portable.jsonl", to_portable_row(row))
            return row
    token = ledger.begin_row() if ledger is not None else None
    spend: dict[str, Any] = {"ran": False, "cost": None, "estimate": 0.0}
    try:
        return _run_bare(task, repeat, run_root, provider, timeout_seconds=timeout_seconds,
                         keep_workdir=keep_workdir, spend=spend)
    finally:
        if ledger is not None:
            ledger.finish_row(token, spend["cost"] if spend["ran"] else 0.0, estimate_usd=spend["estimate"])


def _run_bare(task: Mapping[str, Any], repeat: int, run_root: Path, provider: Provider, *,
              timeout_seconds: float, keep_workdir: bool, spend: dict[str, Any]) -> dict[str, Any]:
    from scripts.bench.measure_2721 import watchdog
    from scripts.bench.measure_2721.common import git_meta_fingerprint, write_diff

    run_id = new_run_id(ARM_BARE, task["task_id"], repeat)
    controller, workdir = bare_worktree(task, run_root / "work" / run_id, run_id)
    git_meta = git_meta_fingerprint(controller, workdir)
    tree_sha = git(workdir, "rev-parse", "HEAD^{tree}").strip()
    prompt = task_prompt(task)
    write_json(run_root / "inputs" / f"{run_id}.json",
               input_capture(ARM_BARE, task, repeat, run_id, prompt=prompt, tree_sha=tree_sha,
                             timeout_seconds=timeout_seconds))
    started_at = watchdog.begin_row(run_root, row_id=run_id, task_id=task["task_id"], arm=ARM_BARE,
                                    cap_s=timeout_seconds)
    started = time.monotonic()
    spend["ran"] = True  # from here on money may have been spent
    result: ProviderResult = provider.run(prompt=prompt, workdir=workdir, timeout_seconds=timeout_seconds,
                                          run_id=run_id, controller=controller)
    # None (timeout, kill, no result message) -> the ledger charges the reservation (H1).
    spend["cost"] = (result.extra or {}).get("total_cost_usd")
    if spend["cost"] is None:
        from scripts.bench.measure_2721.providers import estimate_stream_usd

        spend["estimate"] = estimate_stream_usd((result.extra or {}).get("trace_path"))
    wall = time.monotonic() - started
    tampered = git_meta_fingerprint(controller, workdir) != git_meta
    # #2749: a changed .git/config, info/ or hooks/ means no git command is run.
    diff = "" if tampered else capture_diff(workdir, task["base_commit"])
    diff, tool_artifacts = drop_tool_artifacts(diff)
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
        *outcome_flags(result.status, extra.get("served_models")),
        lookup["flag"],
        FLAG_NETWORK_ATTEMPT if network else None,
        FLAG_GIT_TAMPERED if tampered else None,
        FLAG_SECRET_IN_DIFF if redacted else None,
    ) if flag]
    venv_issue = (
        venv_problem(task, extra.get("venv"), check_observed=True)
        if isinstance(provider, _claude_provider_type()) else None
    )
    if venv_issue:
        flags.append(FLAG_VENV)
    timeout_mismatch = (
        extra.get("cli_timeout_seconds") is not None
        and extra.get("cli_timeout_seconds") != expected_cli_timeout(timeout_seconds)
    )
    if timeout_mismatch:
        flags.append("CLI_TIMEOUT_MISMATCH")
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
        "outcome": "TAMPERED" if tampered else (
            STATUS_INFRA if infra_event or timeout_mismatch or venv_issue else result.status),
        "infra": result.status == STATUS_INFRA or infra_event is not None or timeout_mismatch or bool(venv_issue),
        "venv_problem": venv_issue,
        "read_roots_sha256": _read_roots_sha256(),
        "venv": extra.get("venv"),
        "watchdog_event": infra_event,
        "provider": result.as_dict(),
        "model_calls": result.model_calls,
        "total_tokens": result.total_tokens,
        "diff_path": str(diff_path),
        "tool_artifact_paths": tool_artifacts,
        "non_model_solve_path": non_model_solve(diff, claude_row_fields(extra)),
        **candidate_facts(diff, task),
    }
    if row["non_model_solve_path"]:
        row["flags"].append(FLAG_NON_MODEL_SOLVE)
    append_jsonl(run_root / "rows.jsonl", row)
    append_jsonl(run_root / "rows.portable.jsonl", to_portable_row(row))
    watchdog.end_row(run_root)
    if not keep_workdir:
        shutil.rmtree(run_root / "work" / run_id, ignore_errors=True)
    return row


def _read_roots_sha256() -> str:
    from scripts.bench.measure_2721.gateway_env import read_roots_sha256

    return read_roots_sha256()


def _claude_provider_type() -> type:
    from scripts.bench.measure_2721.providers import ClaudeProvider

    return ClaudeProvider


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
        "venv": extra.get("venv"),
        "seatbelt_sha256": extra.get("seatbelt_sha256"),
        "proxy_denied": [a for a in (extra.get("proxy_attempts") or []) if not a.get("allowed")],
    }


def run_noop(task: Mapping[str, Any], repeat: int, run_root: Path) -> dict[str, Any]:
    """No model, no edit: the S3 NOOP arm.  Must score 0 RESOLVED."""
    from scripts.bench.measure_2721 import watchdog

    run_id = new_run_id(ARM_NOOP, task["task_id"], repeat)
    started_at = watchdog.begin_row(run_root, row_id=run_id, task_id=task["task_id"], arm=ARM_NOOP, cap_s=0.0)
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
        "started_at": started_at,
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
    watchdog.end_row(run_root)
    return row


def load_manifest(path: Path | str, ids: Optional[Sequence[str]] = None) -> list[dict[str, Any]]:
    tasks = list(read_jsonl(path))
    if ids:
        wanted = set(ids)
        tasks = [task for task in tasks if task["task_id"] in wanted]
    return tasks


def main(argv: Sequence[str] | None = None) -> int:
    from scripts.bench.measure_2721.runner import (
        PrepareStop,
        add_common_args,
        add_single_arm_flag,
        prepare,
        single_arm_refusal,
    )

    parser = argparse.ArgumentParser(
        description="Run the BARE or NOOP arm of #2721 on its own (debug; formal "
        "runs go through runner.py)"
    )
    parser.add_argument("arm", choices=[ARM_BARE.lower(), ARM_NOOP.lower()])
    add_common_args(parser)
    parser.add_argument("--provider", choices=["claude", "agy", "fake"], default="fake",
                        help="'fake' makes no model call (default); 'claude' (prereg v0.4) and 'agy' are paid")
    parser.add_argument("--claude-bin", help="absolute, non-symlink claude CLI (same file as the Gateway's)")
    parser.add_argument("--keep-workdir", action="store_true")
    add_single_arm_flag(parser)
    args = parser.parse_args(argv)
    refused = single_arm_refusal(args, paid=args.arm == "bare" and args.provider != "fake")
    if refused is not None:
        print(json.dumps(refused))
        return 2
    try:
        # Same READ_ROOTS as the Gateway, or every Claude row would be void.
        tasks = prepare(args, need_read_roots=args.arm == "bare" and args.provider == "claude")
    except PrepareStop as stop:
        print(json.dumps(stop.payload))
        return stop.code
    run_root = Path(args.run_root)
    provider = (
        build_provider(args.provider, claude_bin=args.claude_bin, trace_dir=run_root / "traces",
                       key_file=args.key_file)
        if args.arm == "bare" else None
    )
    from scripts.bench.measure_2721.budget import BudgetExhausted, SpendLedger

    ledger = SpendLedger(Path(args.spend_ledger), args.budget_usd, args.max_row_usd)
    rows = []
    try:
        for task in tasks:
            for repeat in args.repeats:
                if args.arm == "bare":
                    rows.append(run_bare(task, repeat, run_root, provider, timeout_seconds=args.timeout,
                                         keep_workdir=args.keep_workdir, ledger=ledger))
                else:
                    rows.append(run_noop(task, repeat, run_root))
    except BudgetExhausted as exc:
        print(json.dumps({"stopped": str(exc), "rows": len(rows)}))
        return 75
    print(json.dumps({"rows": len(rows), "rows_path": str(run_root / "rows.jsonl")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
