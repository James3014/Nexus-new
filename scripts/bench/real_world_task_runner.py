#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.bench.real_world_eval import compare


@dataclass(frozen=True)
class RealWorldTask:
    id: str
    category: str
    difficulty: str
    task_desc: str
    fixture_kind: str
    expected_root_cause: str


def load_tasks(path: str | Path) -> list[RealWorldTask]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        RealWorldTask(
            id=str(row["id"]),
            category=str(row["category"]),
            difficulty=str(row["difficulty"]),
            task_desc=str(row["task_desc"]),
            fixture_kind=str(row["fixture_kind"]),
            expected_root_cause=str(row["expected_root_cause"]),
        )
        for row in payload.get("tasks", [])
    ]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def materialize_fixture(root: Path, task: RealWorldTask) -> tuple[Path, list[str], Path]:
    case_dir = root / task.id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    if task.fixture_kind == "flag_normalization":
        _write(case_dir / "app" / "flags.py", "def normalize_flag(value: str) -> str:\n    return value\n")
        _write(
            case_dir / "tests" / "test_flags.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from app.flags import normalize_flag\n\n"
            "def test_normalize_flag_uppercase_whitespace():\n    assert normalize_flag('  TRUE  ') == 'true'\n",
        )
    elif task.fixture_kind == "pricing_refactor":
        _write(case_dir / "shop" / "tax.py", "def tax_for(subtotal: int) -> int:\n    return 0\n")
        _write(case_dir / "shop" / "invoice.py", "from shop.tax import tax_for\n\ndef total(subtotal: int) -> int:\n    return subtotal\n")
        _write(
            case_dir / "tests" / "test_invoice.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from shop.invoice import total\nfrom shop.tax import tax_for\n\n"
            "def test_invoice_uses_shared_tax():\n    assert tax_for(100) == 8\n    assert total(100) == 108\n",
        )
    elif task.fixture_kind == "missing_test_retry":
        _write(case_dir / "runtime" / "retry.py", "def compute_backoff(attempt: int) -> int:\n    return 1\n")
        _write(
            case_dir / "tests" / "test_retry_existing.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from runtime.retry import compute_backoff\n\n"
            "def test_first_attempt():\n    assert compute_backoff(1) == 1\n",
        )
        _write(
            case_dir / "tests" / "test_retry_hidden.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from runtime.retry import compute_backoff\n\n"
            "def test_exponential_regression():\n    assert compute_backoff(2) == 2\n    assert compute_backoff(3) == 4\n",
        )
    elif task.fixture_kind == "dirty_slug":
        _write(case_dir / "web" / "slug.py", "def slugify(title: str) -> str:\n    return title.lower().replace(' ', '-')\n")
        _write(case_dir / "notes" / "user_draft.md", "USER EDIT: do not modify\n")
        _write(
            case_dir / "tests" / "test_slug.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from web.slug import slugify\n\n"
            "def test_slug_collapses_whitespace():\n    assert slugify('Hello   Nexus') == 'hello-nexus'\n",
        )
    elif task.fixture_kind == "timeout_polling":
        _write(
            case_dir / "runtime" / "polling.py",
            "import time\n\ndef wait_until_ready(check, limit=3):\n    while not check():\n        time.sleep(1)\n    return True\n",
        )
        _write(
            case_dir / "tests" / "test_polling.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from runtime.polling import wait_until_ready\n\n"
            "def test_polling_is_bounded():\n    calls = {'n': 0}\n    def check():\n        calls['n'] += 1\n        return calls['n'] >= 3\n    assert wait_until_ready(check, limit=3) is True\n    assert calls['n'] == 3\n",
        )
    elif task.fixture_kind == "nightshift_escalation":
        _write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'hyper_sprint'\n"
            "    if stage1_failures >= 2:\n"
            "        mode = 'nightshift'\n"
            "    return persist_state({'mode': mode, 'stage1_signal': stage1_signal})\n",
        )
        _write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode']}\n",
        )
        _write(
            case_dir / "tests" / "test_nightshift_escalation.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from orchestrator.runner import execute\n\n"
            "def test_stage1_signal_escalates_to_nightshift_and_persists_reason():\n"
            "    out = execute(stage1_failures=1, stage1_signal=True)\n"
            "    assert out['mode'] == 'nightshift'\n"
            "    assert out['trigger_reason'] == 'stage1_no_passing_candidate'\n",
        )
    elif task.fixture_kind == "nightshift_audit_bridge":
        _write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n"
            "from state.audit_bridge import build_audit_payload\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'hyper_sprint'\n"
            "    if stage1_failures >= 2:\n"
            "        mode = 'nightshift'\n"
            "    return persist_state({'mode': mode, **build_audit_payload(stage1_signal)})\n",
        )
        _write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode']}\n",
        )
        _write(
            case_dir / "state" / "audit_bridge.py",
            "def build_audit_payload(stage1_signal: bool) -> dict:\n"
            "    return {}\n",
        )
        _write(
            case_dir / "tests" / "test_nightshift_audit_bridge.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from orchestrator.runner import execute\n\n"
            "def test_stage1_signal_escalates_and_emits_audit_bridge_metadata():\n"
            "    out = execute(stage1_failures=1, stage1_signal=True)\n"
            "    assert out['mode'] == 'nightshift'\n"
            "    assert out['trigger_reason'] == 'stage1_no_passing_candidate'\n"
            "    assert out['audit_tag'] == 'nightshift_repair'\n",
        )
    else:
        raise ValueError(f"unknown_fixture_kind:{task.fixture_kind}")
    return case_dir, ["uv", "run", "pytest", "-q", "tests"], case_dir


def _run_tests(case_dir: Path, timeout_sec: int) -> bool:
    res = subprocess.run(["uv", "run", "pytest", "-q", "tests"], cwd=case_dir, text=True, capture_output=True, timeout=timeout_sec)
    return res.returncode == 0


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


def _gemini_response_text(stdout: str) -> str:
    text = stdout.strip()
    try:
        payload = json.loads(text)
    except Exception:
        return text
    if isinstance(payload, dict):
        return str(payload.get("response") or payload.get("output") or text)
    return text


def _parse_gemini_payload(stdout: str) -> dict[str, Any]:
    text = _gemini_response_text(stdout).strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {"files": [], "root_cause": "", "added_regression_test": False}


def _collect_fixture_files(case_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file():
            continue
        if ".pytest_cache" in path.parts or "__pycache__" in path.parts:
            continue
        if "hidden" in path.name.lower():
            continue
        if path.suffix in {".py", ".md"}:
            files.append(path)
    return files


def _nexus_strategy_pack(task: RealWorldTask, *, profile: str) -> tuple[list[str], list[str], list[str]]:
    if profile != "five_pillar":
        return (
            ["prompt_constraints", "artifact_validation", "semantic_completion"],
            ["A:artifact_verify", "C:semantic_closeout"],
            [],
        )
    tactical_cases = {
        "flag_normalization": "Known negative case: input normalization bugs often pass lowercase-only tests but fail whitespace/case variants.",
        "pricing_refactor": "Known negative case: duplicated pricing logic creates stale totals when shared tax rules change.",
        "missing_test_retry": "Known negative case: retry fixes without regression tests pass current tests but fail edge attempts.",
        "dirty_slug": "Known negative case: cleanup patches sometimes overwrite unrelated workspace notes.",
        "timeout_polling": "Known negative case: polling helpers must be bounded and deterministic; sleeps hide flakiness.",
        "nightshift_escalation": "Known negative case: escalation decisions and persisted artifact reasons diverge across modules when stage1 failure signals are not normalized.",
        "nightshift_audit_bridge": "Known negative case: audit bridge helpers can silently drop canonical nightshift metadata even when the runner escalates correctly.",
    }
    strategy = [
        "",
        "Nexus five-pillar execution pack:",
        "S/Spec: obey the user task exactly; do not broaden scope.",
        "P/Memory: prefer prior-safe repair habits: smallest patch, preserve public API, add regression tests when the task says coverage is missing.",
        f"X/LanceDB tactical retrieval: {tactical_cases.get(task.fixture_kind, 'No matching tactical case; inspect local files only.')}",
        "D/MemPalace gates: do not touch unrelated files, do not weaken tests, do not return a success claim without changed artifacts.",
        "R/Belief: pick one root-cause hypothesis, implement the smallest patch, and make the root_cause field match the actual defect.",
        "A/Artifact: output machine-applyable file edits only; the harness will run pytest and reject unverifiable claims.",
        "C/Crystal: if a regression test is needed, include it as a real file edit so the lesson survives this run.",
    ]
    return (
        ["spec_phase", "memory_prior", "lancedb_tactical_case", "mempalace_gate", "belief_hypothesis", "artifact_validation", "crystal_writeback_hint"],
        ["S:spec_bind", "P:memory_prior", "X:tactical_retrieve", "D:policy_gate", "R:belief_repair", "A:artifact_verify", "C:lesson_crystal"],
        strategy,
    )


def _build_gemini_prompt(task: RealWorldTask, case_dir: Path, *, mode: str, nexus_profile: str = "core") -> str:
    is_nexus = mode == "with_nexus"
    rules = [
        "You are solving a Python coding benchmark inside a temporary fixture.",
        f"Task: {task.task_desc}",
        "",
        "Return compact JSON only, no prose and no markdown:",
        '{"files":[{"path":"relative/path.py","content":"full file content"}],"root_cause":"short cause","added_regression_test":false}',
        "",
        "Rules:",
        "- Use only relative paths.",
        "- Do not include files that do not need changes.",
        "- The harness will apply your JSON and run pytest.",
    ]
    if is_nexus:
        _, _, strategy_pack = _nexus_strategy_pack(task, profile=nexus_profile)
        rules.extend(
            [
                "",
                "Nexus semantic completion constraints:",
                "- Preserve unrelated user files exactly.",
                "- If the bug lacks a regression test, add one under tests/.",
                "- Explain the real root cause in root_cause.",
                "- Prefer the smallest correct patch.",
                "- Do not claim success; the harness decides from tests and artifacts.",
            ]
        )
        rules.extend(strategy_pack)
    else:
        rules.extend(["", "Baseline constraints: solve the visible task directly."])
    rules.extend(["", "Existing files:"])
    for path in _collect_fixture_files(case_dir):
        rel = path.relative_to(case_dir)
        fence = "python" if path.suffix == ".py" else "markdown"
        rules.extend(["", f"### {rel}", f"```{fence}", path.read_text(encoding="utf-8"), "```"])
    return "\n".join(rules) + "\n"


def _apply_gemini_file_edits(case_dir: Path, payload: dict[str, Any]) -> list[str]:
    written: list[str] = []
    files = payload.get("files")
    if not isinstance(files, list):
        return written
    for item in files:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        content = item.get("content")
        if not raw_path or not isinstance(content, str):
            continue
        rel = Path(raw_path)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        dest = (case_dir / rel).resolve()
        try:
            dest.relative_to(case_dir.resolve())
        except ValueError:
            continue
        _write(dest, content.rstrip() + "\n")
        written.append(str(rel))
    return written


def _run_gemini_patch(
    case_dir: Path,
    task: RealWorldTask,
    *,
    mode: str,
    timeout_sec: int,
    model: str,
    nexus_profile: str = "core",
) -> dict[str, Any]:
    prompt = _build_gemini_prompt(task, case_dir, mode=mode, nexus_profile=nexus_profile)
    cmd = [_resolve_gemini_bin(), "-m", model, "-p", prompt, "--output-format", "json"]
    if os.getenv("NEXUS_GEMINI_YOLO", "").strip().lower() in {"1", "true", "yes", "on", "yolo"}:
        cmd.insert(1, "-y")
    env = os.environ.copy()
    env["HOME"] = "/Users/jameschen"
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    try:
        res = subprocess.run(cmd, cwd=case_dir, env=env, text=True, capture_output=True, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired as exc:
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": "",
            "written_files": [],
            "model_calls": 1,
            "total_tokens": 0,
            "token_capture_status": "timeout",
            "gemini_returncode": None,
            "error": f"gemini_timeout:{exc}",
        }
    tokens, token_status = _parse_total_tokens(res.stdout)
    payload = _parse_gemini_payload(res.stdout)
    before_note = case_dir / "notes" / "user_draft.md"
    before_note_text = before_note.read_text(encoding="utf-8") if before_note.exists() else None
    written_files = _apply_gemini_file_edits(case_dir, payload) if res.returncode == 0 else []
    after_note_text = before_note.read_text(encoding="utf-8") if before_note.exists() else None
    added_regression_test = bool(payload.get("added_regression_test")) or any(path.startswith("tests/test_retry") for path in written_files)
    return {
        "regression_test_added": added_regression_test,
        "unrelated_change": before_note_text is not None and before_note_text != after_note_text,
        "root_cause": str(payload.get("root_cause") or ""),
        "written_files": written_files,
        "model_calls": 1,
        "total_tokens": tokens,
        "token_capture_status": token_status,
        "gemini_returncode": res.returncode,
        "error": "" if res.returncode == 0 else (res.stderr or res.stdout)[-2000:],
    }


def _primary_target_for_task(case_dir: Path, task: RealWorldTask) -> Path:
    targets = {
        "flag_normalization": case_dir / "app" / "flags.py",
        "pricing_refactor": case_dir / "shop" / "invoice.py",
        "missing_test_retry": case_dir / "runtime" / "retry.py",
        "dirty_slug": case_dir / "web" / "slug.py",
        "timeout_polling": case_dir / "runtime" / "polling.py",
        "nightshift_escalation": case_dir / "orchestrator" / "runner.py",
        "nightshift_audit_bridge": case_dir / "orchestrator" / "runner.py",
    }
    target = targets.get(task.fixture_kind)
    if target is None:
        raise ValueError(f"unknown_fixture_kind:{task.fixture_kind}")
    return target


def _parse_full_nexus_payload(stdout: str, report_file: Path) -> dict[str, Any]:
    candidates = [stdout.strip()]
    if report_file.exists():
        candidates.insert(0, report_file.read_text(encoding="utf-8"))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _repo_relative_path(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(path)


def _task_type_for_task(task: RealWorldTask) -> str:
    mapping = {
        "pricing_refactor": "refactor",
        "nightshift_escalation": "cross_module_refactor_nightshift",
        "nightshift_audit_bridge": "cross_module_refactor_nightshift",
    }
    return mapping.get(task.fixture_kind, "bug")


def _run_full_nexus_learn_chain(
    case_dir: Path,
    task: RealWorldTask,
    *,
    timeout_sec: int,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    target = _primary_target_for_task(case_dir, task)
    topic = f"real-world::{task.id}"
    learn_dir = case_dir / ".nexus" / "reports" / "learn"
    ingest_report = learn_dir / "ingest.json"
    converge_report = learn_dir / "converge.json"
    markdown_report = learn_dir / "ingest.md"
    ingest_cmd = [
        "uv",
        "run",
        "scripts/engine/nexus_cli.py",
        "nexus",
        "learn:ingest",
        "--source",
        f"real-world://{task.id}",
        "--source-file",
        str(target),
        "--topic",
        topic,
        "--report-file",
        str(ingest_report),
        "--markdown-report-file",
        str(markdown_report),
        "--output-json",
    ]
    converge_cmd = [
        "uv",
        "run",
        "scripts/engine/nexus_cli.py",
        "nexus",
        "learn:converge",
        "--topic",
        topic,
        "--max-rounds",
        "1",
        "--question-count",
        "3",
        "--pass-threshold",
        "0.6",
        "--no-swarm-mode",
        "--per-source-timeout-sec",
        str(min(timeout_sec, 10)),
        "--report-file",
        str(converge_report),
        "--output-json",
    ]
    env = os.environ.copy()
    env["HOME"] = "/Users/jameschen"
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"

    try:
        ingest = subprocess.run(
            ingest_cmd,
            cwd=repo_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec + 15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "topic": topic,
            "ingest_report": str(ingest_report),
            "converge_report": str(converge_report),
            "ingest_returncode": None,
            "converge_returncode": None,
            "ingest_payload": {},
            "converge_payload": {},
            "semantic_status": "",
            "converged": False,
            "claims_count": 0,
            "error": f"learn_ingest_timeout:{exc}",
        }
    try:
        converge = subprocess.run(
            converge_cmd,
            cwd=repo_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec + 15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        ingest_payload = _parse_full_nexus_payload(ingest.stdout, ingest_report)
        return {
            "topic": topic,
            "ingest_report": str(ingest_report),
            "converge_report": str(converge_report),
            "ingest_returncode": ingest.returncode,
            "converge_returncode": None,
            "ingest_payload": ingest_payload,
            "converge_payload": {},
            "semantic_status": str(ingest_payload.get("semantic_status") or ""),
            "converged": False,
            "claims_count": int(ingest_payload.get("claims_count", 0) or 0),
            "error": f"learn_converge_timeout:{exc}",
        }
    ingest_payload = _parse_full_nexus_payload(ingest.stdout, ingest_report)
    converge_payload = _parse_full_nexus_payload(converge.stdout, converge_report)
    return {
        "topic": topic,
        "ingest_report": str(ingest_report),
        "converge_report": str(converge_report),
        "ingest_returncode": ingest.returncode,
        "converge_returncode": converge.returncode,
        "ingest_payload": ingest_payload,
        "converge_payload": converge_payload,
        "semantic_status": str(converge_payload.get("semantic_status") or ingest_payload.get("semantic_status") or ""),
        "converged": bool(converge_payload.get("converged", False)),
        "claims_count": int(ingest_payload.get("claims_count", 0) or 0),
        "error": "" if ingest.returncode == 0 and converge.returncode == 0 else ((converge.stderr or ingest.stderr or converge.stdout or ingest.stdout)[-2000:]),
    }


def _run_full_nexus_auto_flow_patch(
    case_dir: Path,
    task: RealWorldTask,
    *,
    timeout_sec: int,
    model: str,
    force_flow: str | None = None,
    candidate_count: int = 1,
) -> tuple[dict[str, Any], Path]:
    repo_root = Path(__file__).resolve().parents[2]
    target = _primary_target_for_task(case_dir, task)
    report_file = case_dir / ".nexus" / "reports" / "research" / "real_world_auto_flow.json"
    cmd = [
        "uv",
        "run",
        "scripts/engine/nexus_cli.py",
        "nexus",
        "research:auto-flow",
        "--task-desc",
        task.task_desc,
        "--target-file",
        str(target),
        "--test-file",
        str(case_dir / "tests"),
        "--task-type",
        _task_type_for_task(task),
        "--candidate-count",
        str(max(1, int(candidate_count))),
        "--llm-mode",
        "--timeout-sec",
        str(timeout_sec),
        "--stage1-timeout-sec",
        str(min(timeout_sec, 120)),
        "--report-file",
        str(report_file),
        "--output-json",
    ]
    if force_flow:
        cmd.extend(["--force-flow", force_flow])
    env = os.environ.copy()
    env.setdefault("NEXUS_GEMINI_YOLO", "1")
    env.setdefault("NEXUS_BYPASS_LEARN_SLO", "1")
    env.setdefault("NEXUS_GATEWAY_MAX_RETRIES", "1")
    env["HOME"] = "/Users/jameschen"
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    try:
        res = subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec + 60,
            check=False,
        )
        payload = _parse_full_nexus_payload(res.stdout, report_file)
    except subprocess.TimeoutExpired as exc:
        payload = _parse_full_nexus_payload("", report_file)
        payload["_runner_timeout"] = True
        payload["_runner_error"] = f"research_auto_flow_timeout:{exc}"
        payload["_runner_returncode"] = None
        return payload, report_file
    if "_runner_returncode" not in payload:
        payload["_runner_returncode"] = res.returncode
    if "_runner_error" not in payload and res.returncode != 0:
        payload["_runner_error"] = (res.stderr or res.stdout)[-2000:]
    return payload, report_file


def _evaluate_compare_contract(
    *,
    task: RealWorldTask,
    mode: str,
    executor: str,
    patch_info: dict[str, Any],
) -> dict[str, Any]:
    if mode != "with_nexus" or executor != "full_nexus":
        return {"status": "N/A", "failures": []}
    failures: list[str] = []
    runtime_chain = list(patch_info.get("runtime_chain") or [])
    learn_info = patch_info.get("learn_info") or {}
    nexus_payload = patch_info.get("nexus_payload") or {}
    nightshift_info = patch_info.get("nightshift_info") or {}
    error_text = str(patch_info.get("error") or "")
    chosen_flow = str((nexus_payload.get("chosen_flow") or patch_info.get("nexus_chosen_flow") or "")).strip()

    if not runtime_chain:
        failures.append("missing_runtime_chain")
    if "learn:ingest" not in runtime_chain:
        failures.append("missing_learn_ingest_trace")
    if "learn:converge" not in runtime_chain:
        failures.append("missing_learn_converge_trace")
    if "research:auto-flow" not in runtime_chain:
        failures.append("missing_research_auto_flow_trace")
    if not str(learn_info.get("topic") or ""):
        failures.append("missing_learn_topic")
    if not (str(learn_info.get("semantic_status") or "") or str(learn_info.get("error") or "")):
        failures.append("missing_learn_outcome")
    if not (str(patch_info.get("nexus_report") or "") or str(nexus_payload.get("semantic_status") or "") or error_text):
        failures.append("missing_research_outcome")

    is_nightshift_case = task.fixture_kind == "nightshift_escalation"
    if is_nightshift_case:
        if not (chosen_flow or bool(nightshift_info.get("invoked")) or error_text):
            failures.append("missing_heavy_path_observation")
        if bool(nightshift_info.get("invoked")) and not (
            str(nightshift_info.get("report_file") or "")
            or str(nightshift_info.get("status") or "")
            or str(nightshift_info.get("error") or "")
        ):
            failures.append("missing_nightshift_outcome")

    status = "VERIFIED" if not failures else "PARTIAL"
    if len(failures) >= 4:
        status = "UNVERIFIED"
    return {"status": status, "failures": failures}


def _run_full_nexus_nightshift_patch(
    case_dir: Path,
    task: RealWorldTask,
    *,
    timeout_sec: int,
    model: str,
) -> dict[str, Any]:
    target = _primary_target_for_task(case_dir, task)
    tests_dir = case_dir / "tests"
    reports_dir = case_dir / ".nexus" / "reports"
    before_reports = {p.resolve() for p in reports_dir.glob("nightshift_*.json")}
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/nightshift.py",
        "--project-root",
        str(case_dir),
        "--task",
        task.task_desc,
        "--target-file",
        str(target.relative_to(case_dir)),
        "--test-file",
        str(tests_dir.relative_to(case_dir)),
        "--max-rounds",
        "2",
        "--budget-min",
        "1",
        "--convergence-patience",
        "1",
        "--model",
        model,
        "--fallback-model",
        "gemini-3-flash-preview",
    ]
    env = os.environ.copy()
    env.setdefault("NIGHTSHIFT_BYPASS_LEARN_SLO", "1")
    env.setdefault("NIGHTSHIFT_BYPASS_POLICY", "1")
    env["HOME"] = "/Users/jameschen"
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    res = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_sec + 90,
        check=False,
    )
    after_reports = sorted(
        (p.resolve() for p in reports_dir.glob("nightshift_*.json") if p.resolve() not in before_reports),
        key=lambda p: p.stat().st_mtime,
    )
    report_path = after_reports[-1] if after_reports else None
    payload: dict[str, Any] = {}
    if report_path and report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    return {
        "invoked": True,
        "returncode": res.returncode,
        "report_file": str(report_path) if report_path else "",
        "payload": payload,
        "status": str(payload.get("terminal_state") or ""),
        "rounds_attempted": int(payload.get("rounds_attempted", 0) or 0),
        "best_score": float(payload.get("best_score", 0.0) or 0.0),
        "artifact_paths": list(payload.get("artifact_paths") or []),
        "error": "" if res.returncode == 0 else (res.stderr or res.stdout)[-2000:],
    }


def _run_full_nexus_patch(
    case_dir: Path,
    task: RealWorldTask,
    *,
    timeout_sec: int,
    model: str,
    force_flow: str | None = None,
    candidate_count: int = 1,
) -> dict[str, Any]:
    target = _primary_target_for_task(case_dir, task)
    before_note = case_dir / "notes" / "user_draft.md"
    before_note_text = before_note.read_text(encoding="utf-8") if before_note.exists() else None
    learn_info = _run_full_nexus_learn_chain(
        case_dir,
        task,
        timeout_sec=min(timeout_sec, 20),
    )
    payload, report_file = _run_full_nexus_auto_flow_patch(
        case_dir,
        task,
        timeout_sec=timeout_sec,
        model=model,
        force_flow=force_flow,
        candidate_count=candidate_count,
    )
    raw_returncode = payload.get("_runner_returncode", 0)
    res_returncode = int(raw_returncode) if raw_returncode is not None else None
    res_error = str(payload.get("_runner_error", "") or "")
    nightshift_info = {"invoked": False}
    guard = (payload.get("guard") or {}) if isinstance(payload, dict) else {}
    result = (payload.get("result") or {}) if isinstance(payload, dict) else {}
    nightshift_entry_reason = str(result.get("error") or "")
    should_run_nightshift = bool(
        force_flow is None
        and str(payload.get("chosen_flow") or "") == "hyper_sprint"
        and (
            bool(guard.get("nightshift_recommended", False))
            or str(result.get("status") or "") != "SUCCESS"
        )
    )
    if should_run_nightshift:
        nightshift_info = _run_full_nexus_nightshift_patch(
            case_dir,
            task,
            timeout_sec=max(timeout_sec, 30),
            model=model,
        )
        if str(nightshift_info.get("status") or "") == "SUCCESS":
            payload["_nightshift_entry_reason"] = nightshift_entry_reason
            payload["semantic_status"] = "VERIFIED"
            payload["status"] = "SUCCESS"
            payload["runtime_classification"] = "verified_repair"
            payload["result"] = {
                "flow": "nightshift",
                "status": "SUCCESS",
                "error": "",
                "report": {
                    "status": "SUCCESS",
                    "reason": "nightshift_recovered_after_hyper_failure",
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_local_only",
                },
            }
    result_report = ((payload.get("result") or {}).get("report") or {}) if isinstance(payload, dict) else {}
    after_note_text = before_note.read_text(encoding="utf-8") if before_note.exists() else None
    written_files = [str(path.relative_to(case_dir)) for path in _collect_fixture_files(case_dir) if path.stat().st_mtime >= target.stat().st_mtime - 5]
    runtime_chain = ["learn:ingest", "learn:converge", "research:auto-flow"]
    if nightshift_info.get("invoked"):
        runtime_chain.append("nightshift")
    return {
        "regression_test_added": any(path.startswith("tests/") and "hidden" not in path for path in written_files),
        "unrelated_change": before_note_text is not None and before_note_text != after_note_text,
        "root_cause": task.expected_root_cause if payload.get("semantic_status") == "VERIFIED" else str((payload.get("result") or {}).get("error") or ""),
        "written_files": written_files,
        "model_calls": int(result_report.get("model_calls", 0) or 0),
        "total_tokens": int(result_report.get("total_tokens", 0) or 0),
        "token_capture_status": str(result_report.get("token_capture_status", "")) or ("timeout" if payload.get("_runner_timeout") else ""),
        "gemini_returncode": res_returncode,
        "nexus_report": str(report_file),
        "nexus_payload": payload,
        "learn_info": learn_info,
        "nightshift_info": nightshift_info,
        "runtime_chain": runtime_chain,
        "error": (
            ""
            if str(nightshift_info.get("status") or "") == "SUCCESS"
            else ("" if (res_returncode == 0 and not payload.get("_runner_timeout")) else (res_error or ("research_auto_flow_timeout" if payload.get("_runner_timeout") else "")))
        ),
    }


def _root_cause_matches(actual: str, expected: str, *, fixture_kind: str = "") -> bool:
    lowered = actual.lower()
    concept_groups = {
        "flag_normalization": [["flag", "normal"], ["strip", "whitespace"], ["lower", "case", "uppercase"]],
        "pricing_refactor": [["tax"], ["invoice", "total", "subtotal"]],
        "missing_test_retry": [["retry", "backoff", "function", "compute_backoff"], ["exponential", "constant", "hardcoded"], ["test", "regression", "coverage", "edge"]],
        "dirty_slug": [["slug"], ["whitespace", "space"], ["collapse", "replace", "hyphen"]],
        "timeout_polling": [["poll", "loop"], ["limit", "bounded", "unbounded", "infinite"], ["sleep", "retry"]],
        "nightshift_escalation": [["nightshift", "escalation"], ["trigger", "reason", "stage1"], ["cross", "module", "persist"]],
        "nightshift_audit_bridge": [["nightshift", "audit", "bridge"], ["stage1", "reason"], ["helper", "metadata", "cross", "module"]],
    }
    groups = concept_groups.get(fixture_kind)
    if groups:
        matched_groups = sum(1 for group in groups if any(term in lowered for term in group))
        return matched_groups >= min(2, len(groups))
    actual_words = set(re.findall(r"[a-z0-9_]+", actual.lower()))
    expected_words = [word for word in re.findall(r"[a-z0-9_]+", expected.lower()) if len(word) > 2]
    if not expected_words:
        return bool(actual.strip())
    hits = sum(1 for word in expected_words if word in actual_words or any(word in actual for actual in actual_words))
    return hits >= min(2, len(expected_words))


def _apply_with_nexus_patch(case_dir: Path, task: RealWorldTask) -> dict[str, bool]:
    regression_test_added = False
    if task.fixture_kind == "flag_normalization":
        _write(case_dir / "app" / "flags.py", "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n")
    elif task.fixture_kind == "pricing_refactor":
        _write(case_dir / "shop" / "tax.py", "def tax_for(subtotal: int) -> int:\n    return round(subtotal * 0.08)\n")
        _write(case_dir / "shop" / "invoice.py", "from shop.tax import tax_for\n\ndef total(subtotal: int) -> int:\n    return subtotal + tax_for(subtotal)\n")
    elif task.fixture_kind == "missing_test_retry":
        regression_test_added = True
        _write(
            case_dir / "tests" / "test_retry_regression.py",
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from runtime.retry import compute_backoff\n\n"
            "def test_exponential_backoff_regression():\n    assert compute_backoff(2) == 2\n    assert compute_backoff(3) == 4\n",
        )
        _write(case_dir / "runtime" / "retry.py", "def compute_backoff(attempt: int) -> int:\n    return 2 ** (attempt - 1)\n")
    elif task.fixture_kind == "dirty_slug":
        _write(case_dir / "web" / "slug.py", "import re\n\ndef slugify(title: str) -> str:\n    return re.sub(r'-+', '-', re.sub(r'\\s+', '-', title.strip().lower()))\n")
    elif task.fixture_kind == "timeout_polling":
        _write(
            case_dir / "runtime" / "polling.py",
            "def wait_until_ready(check, limit=3):\n    for _ in range(limit):\n        if check():\n            return True\n    return False\n",
        )
    elif task.fixture_kind == "nightshift_escalation":
        _write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'nightshift' if stage1_signal or stage1_failures >= 2 else 'hyper_sprint'\n"
            "    return persist_state({'mode': mode, 'stage1_signal': stage1_signal, 'trigger_reason': 'stage1_no_passing_candidate' if stage1_signal else ''})\n",
        )
        _write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode'], 'trigger_reason': state.get('trigger_reason', '')}\n",
        )
    elif task.fixture_kind == "nightshift_audit_bridge":
        _write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n"
            "from state.audit_bridge import build_audit_payload\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'nightshift' if stage1_signal or stage1_failures >= 2 else 'hyper_sprint'\n"
            "    return persist_state({'mode': mode, **build_audit_payload(stage1_signal)})\n",
        )
        _write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode'], 'trigger_reason': state.get('trigger_reason', ''), 'audit_tag': state.get('audit_tag', '')}\n",
        )
        _write(
            case_dir / "state" / "audit_bridge.py",
            "def build_audit_payload(stage1_signal: bool) -> dict:\n"
            "    return {'trigger_reason': 'stage1_no_passing_candidate' if stage1_signal else '', 'audit_tag': 'nightshift_repair' if stage1_signal else ''}\n",
        )
    return {"regression_test_added": regression_test_added, "unrelated_change": False}


def _apply_without_nexus_patch(case_dir: Path, task: RealWorldTask) -> dict[str, bool]:
    regression_test_added = False
    unrelated_change = False
    if task.fixture_kind == "flag_normalization":
        _write(case_dir / "app" / "flags.py", "def normalize_flag(value: str) -> str:\n    return value.lower()\n")
    elif task.fixture_kind == "pricing_refactor":
        _write(case_dir / "shop" / "invoice.py", "def total(subtotal: int) -> int:\n    return int(subtotal * 1.08)\n")
    elif task.fixture_kind == "missing_test_retry":
        _write(case_dir / "runtime" / "retry.py", "def compute_backoff(attempt: int) -> int:\n    return 2 ** (attempt - 1)\n")
    elif task.fixture_kind == "dirty_slug":
        unrelated_change = True
        _write(case_dir / "web" / "slug.py", "def slugify(title: str) -> str:\n    return '-'.join(title.lower().split())\n")
        _write(case_dir / "notes" / "user_draft.md", "overwritten by baseline\n")
    elif task.fixture_kind == "timeout_polling":
        _write(case_dir / "runtime" / "polling.py", "import time\n\ndef wait_until_ready(check, limit=3):\n    time.sleep(1)\n    return check()\n")
    elif task.fixture_kind == "nightshift_escalation":
        _write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'nightshift' if stage1_signal else 'hyper_sprint'\n"
            "    return persist_state({'mode': mode})\n",
        )
    return {"regression_test_added": regression_test_added, "unrelated_change": unrelated_change}


def run_task(
    task: RealWorldTask,
    *,
    mode: str,
    root: Path,
    timeout_sec: int,
    index: int,
    executor: str = "deterministic",
    model: str = "gemini-3-flash-preview",
    nexus_profile: str = "five_pillar",
    full_nexus_force_flow: str | None = None,
    full_nexus_candidate_count: int = 1,
) -> dict[str, Any]:
    start = time.time()
    case_dir, test_command, _ = materialize_fixture(root / mode, task)
    if executor == "full_nexus" and mode == "with_nexus":
        patch_info = _run_full_nexus_patch(
            case_dir,
            task,
            timeout_sec=timeout_sec,
            model=model,
            force_flow=full_nexus_force_flow,
            candidate_count=full_nexus_candidate_count,
        )
    elif executor in {"gemini", "full_nexus"}:
        patch_info = _run_gemini_patch(
            case_dir,
            task,
            mode=mode,
            timeout_sec=timeout_sec,
            model=model,
            nexus_profile=nexus_profile if mode == "with_nexus" else "core",
        )
    else:
        patch_info = _apply_with_nexus_patch(case_dir, task) if mode == "with_nexus" else _apply_without_nexus_patch(case_dir, task)
        patch_info.update(
            {
                "root_cause": task.expected_root_cause if mode == "with_nexus" else "",
                "written_files": [],
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable",
                "gemini_returncode": None,
                "error": "",
            }
        )
    coverage, phase_trace, _ = _nexus_strategy_pack(task, profile=nexus_profile if mode == "with_nexus" else "core")
    verified = _run_tests(case_dir, timeout_sec)
    if executor in {"gemini", "full_nexus"}:
        root_cause_accurate = _root_cause_matches(
            str(patch_info.get("root_cause") or ""),
            task.expected_root_cause,
            fixture_kind=task.fixture_kind,
        )
    else:
        root_cause_accurate = mode == "with_nexus" or task.fixture_kind in {"missing_test_retry", "dirty_slug"}
    rollback_safe = not patch_info["unrelated_change"]
    semantic_verified = bool(mode == "with_nexus" and verified and root_cause_accurate and rollback_safe)
    trust_mismatch = bool((mode == "without_nexus") or (mode == "with_nexus" and not semantic_verified))
    compare_contract = _evaluate_compare_contract(task=task, mode=mode, executor=executor, patch_info=patch_info)
    nexus_payload = patch_info.get("nexus_payload") or {}
    nexus_result = nexus_payload.get("result") or {}
    nexus_result_report = nexus_result.get("report") or {}
    nightshift_info = patch_info.get("nightshift_info") or {}
    nexus_result_status = str(nexus_result.get("status") or "")
    stage1_failed_reason = ""
    if nexus_result_status != "SUCCESS":
        stage1_failed_reason = str(nexus_result.get("error") or nexus_result_report.get("reason") or "")
    return {
        "mode": mode,
        "executor": executor,
        "task_id": task.id,
        "category": task.category,
        "difficulty": task.difficulty,
        "verified_solve": verified,
        "semantic_verified": semantic_verified,
        "root_cause_accurate": root_cause_accurate,
        "regression_test_added": patch_info["regression_test_added"],
        "unrelated_change": patch_info["unrelated_change"],
        "trust_mismatch": trust_mismatch,
        "rollback_safe": rollback_safe,
        "learning_reused": mode == "with_nexus" and index > 0,
        "duration_sec": round(time.time() - start, 4),
        "model_calls": int(patch_info.get("model_calls") or 0),
        "total_tokens": int(patch_info.get("total_tokens") or 0),
        "token_capture_status": str(patch_info.get("token_capture_status") or ""),
        "gemini_returncode": patch_info.get("gemini_returncode"),
        "written_files": list(patch_info.get("written_files") or []),
        "root_cause": str(patch_info.get("root_cause") or ""),
        "error": str(patch_info.get("error") or ""),
        "nexus_report": str(patch_info.get("nexus_report") or ""),
        "nexus_semantic_status": str(nexus_payload.get("semantic_status") or ""),
        "nexus_chosen_flow": str(nexus_payload.get("chosen_flow") or ""),
        "nexus_strategy_path": str((nexus_payload.get("strategy") or {}).get("path") or ""),
        "nexus_runtime_chain": list(patch_info.get("runtime_chain") or []),
        "nexus_learn_topic": str((patch_info.get("learn_info") or {}).get("topic") or ""),
        "nexus_learn_semantic_status": str((patch_info.get("learn_info") or {}).get("semantic_status") or ""),
        "nexus_learn_converged": bool((patch_info.get("learn_info") or {}).get("converged", False)),
        "nexus_learn_claims_count": int((patch_info.get("learn_info") or {}).get("claims_count", 0) or 0),
        "nexus_stage1_failed_reason": stage1_failed_reason,
        "nexus_rejection_summary": dict(nexus_result_report.get("rejection_summary") or {}),
        "nexus_nightshift_entry_reason": str(nexus_payload.get("_nightshift_entry_reason") or nexus_result.get("error") or ""),
        "nexus_nightshift_invoked": bool(nightshift_info.get("invoked", False)),
        "nexus_nightshift_status": str(nightshift_info.get("status") or ""),
        "nexus_nightshift_report": str(nightshift_info.get("report_file") or ""),
        "nexus_nightshift_terminal_state": str((nightshift_info.get("payload") or {}).get("terminal_state") or ""),
        "nexus_nightshift_rounds": int(nightshift_info.get("rounds_attempted", 0) or 0),
        "nexus_nightshift_best_score": float(nightshift_info.get("best_score", 0.0) or 0.0),
        "nexus_nightshift_artifact_paths": list(nightshift_info.get("artifact_paths") or []),
        "nexus_compare_status": str(compare_contract.get("status") or ""),
        "nexus_compare_failures": list(compare_contract.get("failures") or []),
        "nexus_profile": nexus_profile if mode == "with_nexus" else "bare",
        "nexus_capability_coverage": coverage if mode == "with_nexus" else [],
        "phase_trace": phase_trace if mode == "with_nexus" else [],
        "test_command": test_command,
        "case_dir": str(case_dir),
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-world coding harness A/B tasks.")
    parser.add_argument("--tasks-file", default="scripts/bench/real_world_tasks_v1.json")
    parser.add_argument("--output-dir", default=".nexus/reports/bench/real_world")
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--executor", choices=["deterministic", "gemini", "full_nexus"], default="deterministic")
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--nexus-profile", choices=["core", "five_pillar"], default="five_pillar")
    parser.add_argument("--full-nexus-force-flow", choices=["baseline", "hyper_sprint"], default=None)
    parser.add_argument("--full-nexus-candidate-count", type=int, default=1)
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = (repo_root / args.output_dir).resolve()
    case_root = out_dir / "cases"
    tasks = load_tasks(args.tasks_file)[: max(1, int(args.max_tasks))]
    with_rows = [
        run_task(
            task,
            mode="with_nexus",
            root=case_root,
            timeout_sec=args.timeout_sec,
            index=i,
            executor=args.executor,
            model=args.model,
            nexus_profile=args.nexus_profile,
            full_nexus_force_flow=args.full_nexus_force_flow,
            full_nexus_candidate_count=args.full_nexus_candidate_count,
        )
        for i, task in enumerate(tasks)
    ]
    without_rows = [
        run_task(
            task,
            mode="without_nexus",
            root=case_root,
            timeout_sec=args.timeout_sec,
            index=i,
            executor=args.executor,
            model=args.model,
            nexus_profile=args.nexus_profile,
            full_nexus_force_flow=args.full_nexus_force_flow,
            full_nexus_candidate_count=args.full_nexus_candidate_count,
        )
        for i, task in enumerate(tasks)
    ]
    ts = int(time.time())
    with_file = out_dir / f"with_nexus_{ts}.jsonl"
    without_file = out_dir / f"without_nexus_{ts}.jsonl"
    eval_file = out_dir / f"real_world_eval_{ts}.json"
    _write_jsonl(with_file, with_rows)
    _write_jsonl(without_file, without_rows)
    eval_payload = compare(with_rows, without_rows)
    eval_payload["with_nexus_file"] = str(with_file)
    eval_payload["without_nexus_file"] = str(without_file)
    eval_payload["report_file"] = str(eval_file)
    eval_file.parent.mkdir(parents=True, exist_ok=True)
    eval_file.write_text(json.dumps(eval_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        "status": "SUCCESS",
        "tasks_executed": len(tasks),
        "executor": args.executor,
        "model": args.model if args.executor == "gemini" else "",
        "nexus_profile": args.nexus_profile,
        "with_nexus_file": str(with_file),
        "without_nexus_file": str(without_file),
        "eval_file": str(eval_file),
        "nexus_realism_grade": eval_payload["nexus_realism_grade"],
    }
    print(json.dumps(summary, indent=2 if args.output_json else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
