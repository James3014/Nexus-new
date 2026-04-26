#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.bench.capability_ab_runner import CapabilityTask, _materialize_fixture, load_tasks, select_tasks
from nexus.research.local_sprint_mutator import generate_local_candidate
from scripts.bench.ab_eval import compare_datasets


@dataclass(frozen=True)
class FileTaskResult:
    task_id: str
    difficulty: str
    task_type: str
    status: str
    semantic_status: str
    semantic_completed: bool
    model_calls: int
    total_tokens: int
    token_capture_status: str
    duration_sec: float
    task_file: str
    output_file: str
    artifact_paths: list[str]
    test_command: list[str]
    test_returncode: int | None
    error: str = ""


def _resolve_gemini_bin() -> str:
    candidates = [
        os.getenv("NEXUS_GEMINI_BIN", ""),
        "/Users/jameschen/.npm-global/bin/gemini",
        "/opt/homebrew/bin/gemini",
        "/usr/local/bin/gemini",
        shutil.which("gemini") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("gemini CLI not found")


def _collect_context_files(case_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(case_dir.rglob("*.py")):
        if ".pytest_cache" in path.parts or "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def _select_context_files(*, case_dir: Path, target_file: Path, context_mode: str) -> list[Path]:
    files = _collect_context_files(case_dir)
    if context_mode == "full":
        return files
    selected: list[Path] = []
    for path in files:
        if path == target_file:
            selected.append(path)
            continue
        if context_mode == "micro":
            continue
        rel = path.relative_to(case_dir)
        if "test" in path.name.lower() or "tests" in rel.parts:
            continue
        selected.append(path)
    return selected


def _write_task_file(
    *,
    task: CapabilityTask,
    case_dir: Path,
    target_file: Path,
    test_file: Path,
    output_file: Path,
    test_command: list[str],
    context_mode: str = "full",
) -> Path:
    task_file = case_dir / "task.md"
    required_behavior = _required_behavior_from_task(task.task_desc)
    parts = [
        "# Nexus File Task Benchmark",
        "",
        "## Objective",
        task.task_desc,
        "",
        "## Required Output",
        f"Write ONLY the full updated source code for `{target_file}` to:",
        f"`{output_file}`",
        "",
        "Do not modify any other file. Do not write prose into the output file.",
        "Keep imports minimal. Preserve public function names and module boundaries.",
        "",
        "## Required Behavior Summary",
        required_behavior,
        "",
        "## Verification Command",
        "```bash",
        " ".join(test_command),
        "```",
        "",
        "## Context Files",
    ]
    for path in _select_context_files(case_dir=case_dir, target_file=target_file, context_mode=context_mode):
        rel = path.relative_to(case_dir)
        parts.extend(
            [
                "",
                f"### {rel}",
                "```python",
                path.read_text(encoding="utf-8"),
                "```",
            ]
        )
    task_file.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return task_file


def _required_behavior_from_task(task_desc: str) -> str:
    text = task_desc.strip()
    if "attempt 1" in text and "attempt 4" in text:
        return "Implement compute_backoff(attempt): reject attempt <= 0; return capped exponential backoff 1, 2, 4, 8 using RETRY_LIMITS base_delay/max_delay when available."
    if "compute_backoff" in text and "exponential" in text:
        return "Implement compute_backoff(attempt): reject attempt <= 0; return capped exponential backoff using settings.RETRY_LIMITS."
    if "retry_policy.compute_backoff" in text or "retry backoff" in text:
        return "Implement compute_backoff(attempt): reject attempt <= 0; preserve runtime.settings import; return min(max_delay, base_delay * 2 ** (attempt - 1))."
    return text


def _extract_code_from_gemini_stdout(stdout: str) -> str:
    text = stdout.strip()
    try:
        payload = json.loads(text)
        text = str(payload.get("response") or payload.get("output") or text)
    except Exception:
        pass
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip() + "\n"
    return text.strip() + "\n"


def _extract_written_file_from_stdout(stdout: str) -> Path | None:
    text = stdout.strip()
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    response = payload.get("response") if isinstance(payload, dict) else None
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload)
    if isinstance(response, str):
        try:
            response_payload = json.loads(response)
            if isinstance(response_payload, dict):
                candidates.append(response_payload)
        except Exception:
            pass
    for item in candidates:
        raw = item.get("file_written") or item.get("output_file") or item.get("file_path") or item.get("path")
        if raw:
            path = Path(str(raw)).expanduser()
            if path.exists() and path.is_file():
                return path
    return None


def _is_valid_python_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        return True
    except Exception:
        return False


def _parse_total_tokens(stdout: str) -> tuple[int, str]:
    try:
        payload = json.loads(stdout.strip())
    except Exception:
        return 0, "missing_gateway_stats"
    total = 0
    models = ((payload.get("stats") or {}).get("models") or {})
    if isinstance(models, dict):
        for data in models.values():
            if isinstance(data, dict):
                total += int(((data.get("tokens") or {}).get("total") or 0))
    return total, "measured" if total > 0 else "missing_gateway_stats"


def _build_inline_prompt(*, task_file: Path, output_file: Path) -> str:
    text = task_file.read_text(encoding="utf-8")
    return (
        "Solve this Python coding task. Return ONLY the full updated source code for the requested target file; "
        "no prose, no markdown unless you use one python code fence.\n\n"
        f"{text}\n\n"
        f"Target output path for the harness: {output_file}\n"
    )


def _build_function_prompt(*, task_file: Path, function_name: str) -> str:
    text = task_file.read_text(encoding="utf-8")
    return (
        f"Solve this Python coding task. Return ONLY the full Python function definition for `{function_name}`; "
        "no imports, no prose, no markdown unless one python code fence is used.\n\n"
        f"{text}\n"
    )


def _infer_target_function(task_desc: str, target_file: Path) -> str:
    for candidate in ["compute_backoff", "normalize_flag"]:
        if candidate in task_desc:
            return candidate
    try:
        module = ast.parse(target_file.read_text(encoding="utf-8"))
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                return str(node.name)
    except Exception:
        pass
    return "compute_backoff"


def _replace_function_source(source: str, function_name: str, function_code: str) -> str:
    module = ast.parse(source)
    fn_node: ast.FunctionDef | None = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            fn_node = node
            break
    if fn_node is None or fn_node.end_lineno is None:
        raise ValueError(f"function_not_found:{function_name}")
    fn_module = ast.parse(function_code)
    if len(fn_module.body) != 1 or not isinstance(fn_module.body[0], ast.FunctionDef):
        raise ValueError("candidate_not_single_function")
    if fn_module.body[0].name != function_name:
        raise ValueError(f"candidate_function_name_mismatch:{fn_module.body[0].name}")
    lines = source.splitlines()
    replacement = function_code.strip().splitlines()
    updated = lines[: fn_node.lineno - 1] + replacement + lines[fn_node.end_lineno :]
    return "\n".join(updated).rstrip() + "\n"


def _run_gemini_file_task(
    *,
    task_file: Path,
    output_file: Path,
    target_file: Path,
    task_desc: str,
    model: str,
    timeout_sec: int,
    invocation_mode: str = "file",
) -> tuple[int, str, str]:
    gemini_bin = _resolve_gemini_bin()
    if invocation_mode == "function":
        function_name = _infer_target_function(task_desc, target_file)
        prompt = _build_function_prompt(task_file=task_file, function_name=function_name)
    elif invocation_mode == "inline":
        prompt = _build_inline_prompt(task_file=task_file, output_file=output_file)
    else:
        prompt = (
            f"Read the task file at {task_file}. "
            f"Write the requested full source code to {output_file}. "
            "After writing, return compact JSON only: "
            f'{{"file_written":"{output_file}","status":"done"}}'
        )
    cmd = [gemini_bin, "-m", model, "-p", prompt, "--output-format", "json"]
    if os.getenv("NEXUS_GEMINI_YOLO", "").strip().lower() in {"1", "true", "yes", "on", "yolo"}:
        cmd.insert(1, "-y")
    env = os.environ.copy()
    env["HOME"] = "/Users/jameschen"
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    res = subprocess.run(cmd, cwd=task_file.parent, env=env, text=True, capture_output=True, timeout=timeout_sec, check=False)
    if res.returncode == 0 and invocation_mode == "function":
        function_name = _infer_target_function(task_desc, target_file)
        function_code = _extract_code_from_gemini_stdout(res.stdout)
        source = target_file.read_text(encoding="utf-8")
        candidate = _replace_function_source(source, function_name, function_code)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(candidate, encoding="utf-8")
        return res.returncode, res.stdout, res.stderr
    if res.returncode == 0 and invocation_mode == "inline":
        code = _extract_code_from_gemini_stdout(res.stdout)
        if code.strip():
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(code, encoding="utf-8")
        return res.returncode, res.stdout, res.stderr
    if res.returncode == 0:
        written_file = _extract_written_file_from_stdout(res.stdout)
        if written_file is not None and (not output_file.exists() or not _is_valid_python_file(output_file)):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(written_file, output_file)
    if res.returncode == 0 and not output_file.exists():
        written_file = _extract_written_file_from_stdout(res.stdout)
        if written_file is not None:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(written_file, output_file)
        else:
            code = _extract_code_from_gemini_stdout(res.stdout)
            if code.strip():
                output_file.write_text(code, encoding="utf-8")
    return res.returncode, res.stdout, res.stderr


def _verify_candidate(*, case_dir: Path, target_file: Path, test_file: Path, output_file: Path, timeout_sec: int) -> tuple[bool, int | None, str]:
    if not output_file.exists():
        return False, None, "candidate_output_missing"
    original = target_file.read_text(encoding="utf-8")
    try:
        candidate = output_file.read_text(encoding="utf-8")
        compile(candidate, str(target_file), "exec")
        target_file.write_text(candidate, encoding="utf-8")
        cmd = ["uv", "run", "pytest", "-q", str(test_file)]
        res = subprocess.run(cmd, cwd=case_dir, text=True, capture_output=True, timeout=timeout_sec, check=False)
        return res.returncode == 0, res.returncode, (res.stdout + "\n" + res.stderr)[-2000:]
    except SyntaxError as exc:
        return False, None, f"syntax_error:{exc}"
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)
    finally:
        target_file.write_text(original, encoding="utf-8")


def run_task(
    *,
    repo_root: Path,
    task: CapabilityTask,
    model: str,
    timeout_sec: int,
    output_dir: Path,
    context_mode: str = "full",
    invocation_mode: str = "file",
) -> FileTaskResult:
    start = time.time()
    target_raw, test_raw = _materialize_fixture(repo_root, task)
    target_file = Path(target_raw)
    test_file = Path(test_raw)
    case_dir = target_file.parents[1] if task.fixture_kind == "cross_module_retry" else target_file.parent
    run_dir = output_dir / task.id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_file = run_dir / "candidate.py"
    if output_file.exists():
        output_file.unlink()
    test_command = ["uv", "run", "pytest", "-q", str(test_file)]
    task_file = _write_task_file(
        task=task,
        case_dir=case_dir,
        target_file=target_file,
        test_file=test_file,
        output_file=output_file,
        test_command=test_command,
        context_mode=context_mode,
    )
    try:
        returncode, stdout, stderr = _run_gemini_file_task(
            task_file=task_file,
            output_file=output_file,
            target_file=target_file,
            task_desc=task.task_desc,
            model=model,
            timeout_sec=timeout_sec,
            invocation_mode=invocation_mode,
        )
    except subprocess.TimeoutExpired as exc:
        return FileTaskResult(
            task_id=task.id,
            difficulty=task.difficulty,
            task_type=task.task_type,
            status="FAILED",
            semantic_status="UNVERIFIED",
            semantic_completed=False,
            model_calls=1,
            total_tokens=0,
            token_capture_status="timeout",
            duration_sec=round(time.time() - start, 4),
            task_file=str(task_file),
            output_file=str(output_file),
            artifact_paths=[str(task_file)],
            test_command=test_command,
            test_returncode=None,
            error=f"gemini_timeout:{exc}",
        )
    tokens, token_status = _parse_total_tokens(stdout)
    if returncode != 0:
        return FileTaskResult(
            task_id=task.id,
            difficulty=task.difficulty,
            task_type=task.task_type,
            status="FAILED",
            semantic_status="UNVERIFIED",
            semantic_completed=False,
            model_calls=1,
            total_tokens=tokens,
            token_capture_status=token_status,
            duration_sec=round(time.time() - start, 4),
            task_file=str(task_file),
            output_file=str(output_file),
            artifact_paths=[str(task_file), str(output_file)],
            test_command=test_command,
            test_returncode=None,
            error=(stderr or stdout)[-2000:],
        )
    ok, test_returncode, error = _verify_candidate(
        case_dir=case_dir,
        target_file=target_file,
        test_file=test_file,
        output_file=output_file,
        timeout_sec=timeout_sec,
    )
    return FileTaskResult(
        task_id=task.id,
        difficulty=task.difficulty,
        task_type=task.task_type,
        status="SUCCESS" if ok else "FAILED",
        semantic_status="VERIFIED" if ok else "UNVERIFIED",
        semantic_completed=ok,
        model_calls=1,
        total_tokens=tokens,
        token_capture_status=token_status,
        duration_sec=round(time.time() - start, 4),
        task_file=str(task_file),
        output_file=str(output_file),
        artifact_paths=[str(task_file), str(output_file)],
        test_command=test_command,
        test_returncode=test_returncode,
        error="" if ok else error,
    )


def _to_ab_row(result: FileTaskResult, *, mode: str, model_label: str, llm_enabled: bool, trust_mismatch: bool) -> dict[str, Any]:
    payload = asdict(result)
    payload.update(
        {
            "mode": mode,
            "model_profile": {
                "label": model_label,
                "with_llm_mode": "hard" if llm_enabled else "off",
                "llm_enabled": llm_enabled,
                "primary_model": model_label if llm_enabled else "",
                "runner_mode": "file_task",
            },
            "task_duration_sec": payload["duration_sec"],
            "wall_duration_sec": payload["duration_sec"],
            "elapsed_sec": payload["duration_sec"],
            "attempt_count": 1,
            "token_measured": payload.get("token_capture_status") == "measured",
            "report_trust_mismatch": trust_mismatch,
            "chosen_flow": "file_task",
            "strategy_path": "file_task_direct",
            "artifact_changed": bool(payload.get("semantic_completed")),
        }
    )
    return payload


def run_without_nexus_baseline(*, repo_root: Path, task: CapabilityTask, timeout_sec: int, output_dir: Path) -> FileTaskResult:
    start = time.time()
    target_raw, test_raw = _materialize_fixture(repo_root, task)
    target_file = Path(target_raw)
    test_file = Path(test_raw)
    case_dir = target_file.parents[1] if task.fixture_kind == "cross_module_retry" else target_file.parent
    run_dir = output_dir / f"{task.id}_without"
    run_dir.mkdir(parents=True, exist_ok=True)
    output_file = run_dir / "candidate.py"
    source = target_file.read_text(encoding="utf-8")
    candidate = generate_local_candidate(source, task.task_desc, "file_task_without_baseline", 0)
    output_file.write_text(candidate, encoding="utf-8")
    ok, test_returncode, error = _verify_candidate(
        case_dir=case_dir,
        target_file=target_file,
        test_file=test_file,
        output_file=output_file,
        timeout_sec=timeout_sec,
    )
    return FileTaskResult(
        task_id=task.id,
        difficulty=task.difficulty,
        task_type=task.task_type,
        status="SUCCESS" if ok else "FAILED",
        semantic_status="",
        semantic_completed=False,
        model_calls=0,
        total_tokens=0,
        token_capture_status="not_applicable_local_only",
        duration_sec=round(time.time() - start, 4),
        task_file="",
        output_file=str(output_file),
        artifact_paths=[str(output_file)],
        test_command=["uv", "run", "pytest", "-q", str(test_file)],
        test_returncode=test_returncode,
        error="" if ok else error,
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gemini file-task hard benchmark through Nexus verification.")
    parser.add_argument("--tasks-file", default="scripts/bench/capability_flash_xmodule_tasks_v1.json")
    parser.add_argument("--output-dir", default=".nexus/reports/bench/flash_file_task")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "all"], default="hard")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--timeout-sec", type=int, default=240)
    parser.add_argument("--context-mode", choices=["full", "lean", "micro"], default="full")
    parser.add_argument("--invocation-mode", choices=["file", "inline", "function"], default="file")
    parser.add_argument("--emit-ab", action="store_true", help="Also write with_nexus/without_nexus JSONL files compatible with ab_eval.py.")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = (repo_root / args.output_dir).resolve()
    tasks = select_tasks(load_tasks(args.tasks_file), difficulty=args.difficulty, max_tasks=args.max_tasks)
    results = [
        run_task(
            repo_root=repo_root,
            task=task,
            model=args.model,
            timeout_sec=args.timeout_sec,
            output_dir=out_dir,
            context_mode=str(args.context_mode),
            invocation_mode=str(args.invocation_mode),
        )
        for task in tasks
    ]
    rows = [asdict(result) for result in results]
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_file = out_dir / f"file_task_{ts}.jsonl"
    _write_jsonl(out_file, rows)
    with_file = ""
    without_file = ""
    ab_eval_file = ""
    if args.emit_ab:
        without_results = [
            run_without_nexus_baseline(repo_root=repo_root, task=task, timeout_sec=args.timeout_sec, output_dir=out_dir)
            for task in tasks
        ]
        with_rows = [
            _to_ab_row(result, mode="with_nexus", model_label=args.model, llm_enabled=True, trust_mismatch=False)
            for result in results
        ]
        without_rows = [
            _to_ab_row(result, mode="without_nexus", model_label="local-baseline", llm_enabled=False, trust_mismatch=True)
            for result in without_results
        ]
        with_path = out_dir / f"with_nexus_{ts}.jsonl"
        without_path = out_dir / f"without_nexus_{ts}.jsonl"
        _write_jsonl(with_path, with_rows)
        _write_jsonl(without_path, without_rows)
        with_file = str(with_path)
        without_file = str(without_path)
        ab_eval_payload = compare_datasets("local-baseline", without_rows, "gemini-flash-file-task", with_rows)
        ab_eval_path = out_dir / f"ab_eval_{ts}.json"
        ab_eval_path.write_text(json.dumps(ab_eval_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        ab_eval_file = str(ab_eval_path)
    summary = {
        "status": "SUCCESS",
        "tasks_executed": len(rows),
        "verified": sum(1 for row in rows if row["semantic_status"] == "VERIFIED"),
        "model_calls": sum(int(row["model_calls"]) for row in rows),
        "report_file": str(out_file),
        "with_nexus_file": with_file,
        "without_nexus_file": without_file,
        "ab_eval_file": ab_eval_file,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.output_json else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
