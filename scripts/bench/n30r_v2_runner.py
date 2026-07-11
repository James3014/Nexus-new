"""N30R V2 Paired Evaluation Runner.

Bare lane: direct Ollama call → parse SEARCH/REPLACE → apply → verifier
Core lane: production LocalModelExecutor with OllamaLocalModelProvider
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import (
    OllamaLocalModelProvider,
    LocalModelProviderRequest,
    LocalModelProviderResponse,
)
from scripts.bench.n30r_contracts import sha256_str, sha256_hex

logger = logging.getLogger(__name__)
ProviderFn = Callable[[str, str, str], str]


def _check_environment() -> dict:
    """Check Python runtime environment and return a receipt dict.

    Fails closed on interpreter mismatch, missing deps, or dependency warnings.
    """
    project_root = Path(__file__).resolve().parents[2]
    expected_venv_python = str(project_root / ".venv" / "bin" / "python")
    actual_python = os.path.realpath(sys.executable)
    expected_resolved = os.path.realpath(expected_venv_python)
    venv_match = actual_python == expected_resolved

    receipt = {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "virtualenv_active": sys.prefix != sys.base_prefix,
        "project_venv_expected": expected_venv_python,
        "project_venv_resolved": expected_resolved,
        "project_venv_match": venv_match,
        "lancedb_available": False,
        "lancedb_version": "",
        "requests_version": "",
        "urllib3_version": "",
        "charset_normalizer_version": "",
        "dependency_warning_count": 0,
        "environment_valid": False,
    }

    if not venv_match:
        logger.error(
            "Python interpreter mismatch: expected %s (resolved %s), got %s",
            expected_venv_python, expected_resolved, actual_python,
        )
        return receipt

    import warnings
    warning_count = 0
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            import importlib.metadata as _im
            import lancedb as _l
            receipt["lancedb_available"] = True
            receipt["lancedb_version"] = _l.__version__
            import requests as _r
            receipt["requests_version"] = _r.__version__
            import urllib3 as _u
            receipt["urllib3_version"] = _u.__version__
            import charset_normalizer as _cn
            receipt["charset_normalizer_version"] = _cn.__version__

            for warning in w:
                w_class = warning.category.__name__
                if "DependencyWarning" in w_class or "RequestsDependencyWarning" in w_class:
                    warning_count += 1
        except (ImportError, AttributeError, Exception) as e:
            logger.error("Dependency import failed: %s", e)
            return receipt

    receipt["dependency_warning_count"] = warning_count
    if warning_count > 0:
        logger.error("Dependency warning detected: %d warnings", warning_count)
        return receipt

    receipt["environment_valid"] = True
    return receipt


def _patch_verifier_command(cmd: tuple[str, ...]) -> list[str]:
    """Replace 'python3' in verifier command with sys.executable."""
    cmd_list = list(cmd)
    if cmd_list and cmd_list[0] in ("python", "python3"):
        cmd_list[0] = sys.executable
    return cmd_list


# Shared provider options used by both Bare and Core arms for parity
_SHARED_PROVIDER_OPTIONS: dict = {
    "temperature": 0.0,
    "top_p": 1.0,
    "num_ctx": 8192,
    "num_predict": 512,
    "seed": 0,  # Will be overridden per-call
}
_SHARED_PROVIDER_TIMEOUT: float = 120.0


def _make_provider_options(seed: int) -> dict:
    """Return a fresh copy of shared provider options with seed applied."""
    opts = dict(_SHARED_PROVIDER_OPTIONS)
    opts["seed"] = seed
    return opts


def _ollama_provider_with_metrics(model: str, system: str, user: str, seed: int) -> tuple[str, dict]:
    """Direct Ollama provider for bare arm — returns (response_text, ollama_metrics_dict)."""
    import json as _json
    import urllib.request as _urllib
    opts = _make_provider_options(seed)
    payload = _json.dumps({
        "model": model,
        "system": system,
        "prompt": user,
        "stream": False,
        "options": opts,
    })
    req = _urllib.Request(
        "http://localhost:11434/api/generate",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with _urllib.urlopen(req, timeout=_SHARED_PROVIDER_TIMEOUT) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
            metrics = {
                "ollama_total_duration": data.get("total_duration", 0),
                "ollama_load_duration": data.get("load_duration", 0),
                "ollama_prompt_eval_count": data.get("prompt_eval_count", 0),
                "ollama_prompt_eval_duration": data.get("prompt_eval_duration", 0),
                "ollama_eval_count": data.get("eval_count", 0),
                "ollama_eval_duration": data.get("eval_duration", 0),
                "ollama_done_reason": data.get("done_reason", ""),
                "ollama_metrics_available": True,
            }
            return data.get("response", ""), metrics
    except Exception as e:
        raise RuntimeError(f"Ollama call failed: {e}")


def _ollama_provider(model: str, system: str, user: str) -> str:
    """Legacy bare wrapper — delegates to _ollama_provider_with_metrics, discards metrics."""
    text, _ = _ollama_provider_with_metrics(model, system, user, seed=0)
    return text


def _materialize_task(task_dict: dict) -> Any:
    """Convert manifest task dict to N30RTaskSpec."""
    from scripts.bench.n30r_contracts import N30RTaskSpec
    return N30RTaskSpec(
        task_id=task_dict.get("task_id", ""),
        source_relpath=task_dict.get("source_relpath", ""),
        task_statement=task_dict.get("task_statement", ""),
        verifier_command=tuple(task_dict.get("verifier_command", [])),
        expected_failure_signature=task_dict.get("expected_failure_signature", ""),
    )


def _read_fixture_original(relpath: str) -> str:
    root = Path(__file__).resolve().parents[2]
    fixture_path = root / relpath
    source = fixture_path.read_text(encoding="utf-8")
    mod: dict = {}
    exec(source, mod)
    return mod.get("ORIGINAL", source)


def _run_verifier(source: str, verifier_cmd: tuple[str, ...], work_dir: str) -> tuple[int, str, str]:
    src_path = os.path.join(work_dir, "f.py")
    with open(src_path, "w") as f:
        f.write(source)
    actual_cmd = _patch_verifier_command(verifier_cmd)
    result = subprocess.run(
        actual_cmd, capture_output=True, text=True,
        cwd=work_dir, timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def _strip_fences(text: str) -> str:
    """Strip markdown code fences and backtick wrappers from a search/replace block."""
    t = text.strip()
    if t.startswith("```"):
        t = t[3:]
        if t.startswith("python\n"):
            t = t[7:]
        elif t.startswith("python"):
            t = t[6:]
        if t.endswith("```"):
            t = t[:-3]
    elif t.startswith("`") and t.endswith("`"):
        t = t[1:-1]
    return t.strip()


def _parse_search_replace(output: str) -> tuple[list[dict], str]:
    """Parse SEARCH/REPLACE blocks from model output."""
    blocks = []
    remaining = output
    while True:
        search_start = remaining.find("SEARCH:")
        if search_start == -1:
            break
        replace_start = remaining.find("REPLACE:", search_start)
        if replace_start == -1:
            break
        search_text = _strip_fences(remaining[search_start + 7:replace_start])
        block_end = remaining.find("```", replace_start + 8)
        if block_end == -1:
            bare_replace = remaining[replace_start + 8:].strip()
            replace_text = _strip_fences(bare_replace)
            remaining = ""
        else:
            replace_text = _strip_fences(remaining[replace_start + 8:block_end])
            next_start = remaining.find("```", block_end + 3)
            remaining = remaining[next_start + 3:] if next_start != -1 else ""
        blocks.append({"search": search_text, "replace": replace_text})
    parser_status = "success" if blocks else "no_blocks"
    return blocks, parser_status


def _apply_search_replace(source: str, blocks: list[dict]) -> tuple[str, str]:
    patched = source
    for block in blocks:
        search = block.get("search", "")
        replace = block.get("replace", "")
        if not search:
            return source, "empty_search"
        if search not in patched:
            return source, "search_mismatch"
        patched = patched.replace(search, replace, 1)
    return patched, "applied"


def _verify_original_fails(task_dict: dict, work_dir: str) -> bool:
    orig = _read_fixture_original(task_dict["source_relpath"])
    verifier_cmd = tuple(task_dict.get("verifier_command", []))
    ec, _, _ = _run_verifier(orig, verifier_cmd, work_dir)
    return ec != 0


def run_bare_row(task_dict: dict, seed: int, run_id: str) -> dict:
    """Run a single Bare row: direct model → parse → apply → verifier.

    Timing boundary: monotonic from start of source_read through verifier completion.
    This matches Core arm's end-to-end boundary for fair comparison.
    """
    # === E2E start — includes source read, prompt build, provider call, parse, apply, verifier ===
    t_e2e_start = time.monotonic()

    orig = _read_fixture_original(task_dict["source_relpath"])
    task_statement = task_dict.get("task_statement", "")
    verifier_cmd = tuple(task_dict.get("verifier_command", []))

    t_prepare_done = time.monotonic()
    source_prepare_sec = round(t_prepare_done - t_e2e_start, 4)

    system_prompt = "You are a code repair assistant."
    user_prompt = (
        f"Fix the following code bug.\n\n"
        f"Task: {task_statement}\n\n"
        f"Source code:\n```\n{orig}\n```\n\n"
        f"Return the fix using SEARCH/REPLACE blocks:\n"
        f"SEARCH:\n<exact code to replace>\nREPLACE:\n<replacement code>\n"
    )
    prompt_build_sec = round(time.monotonic() - t_prepare_done, 4)

    # Provider options — shared with Core arm
    provider_opts = _make_provider_options(seed)

    # === Provider call ===
    t_provider_start = time.monotonic()
    ollama_metrics: dict = {
        "ollama_total_duration": 0, "ollama_load_duration": 0,
        "ollama_prompt_eval_count": 0, "ollama_prompt_eval_duration": 0,
        "ollama_eval_count": 0, "ollama_eval_duration": 0,
        "ollama_done_reason": "", "ollama_metrics_available": False,
    }
    try:
        raw_output, ollama_metrics = _ollama_provider_with_metrics(
            "qwen2.5-coder:7b-instruct", system_prompt, user_prompt, seed=seed
        )
    except Exception as e:
        t_provider_end = time.monotonic()
        provider_wall_sec = round(t_provider_end - t_provider_start, 4)
        end_to_end_sec = round(t_provider_end - t_e2e_start, 4)
        return {
            "task_id": task_dict["task_id"],
            "arm_id": "N30R_A_7B_BARE",
            "trial_index": 0,
            "task_seed": seed,
            "model_requested": "qwen2.5-coder:7b-instruct",
            "model_actual": "qwen2.5-coder:7b-instruct",
            "provider_actual": "ollama",
            "provider_options": provider_opts,
            "task_statement_sha256": sha256_str(task_statement),
            "source_fixture_sha256": task_dict.get("source_fixture_sha256", ""),
            "verifier_contract_sha256": task_dict.get("verifier_contract_sha256", ""),
            "execution_completed": False,
            "contract_valid": True,
            "model_call_count": 1,
            "model_response_received": False,
            "raw_output_length": 0,
            "raw_output_sha256": "",
            "candidate_hash": "",
            "candidate_isolated": False,
            "apply_status": "none",
            "verifier_reached": False,
            "verifier_status": "not_run",
            "semantic_retry_count": 0,
            "wall_time_sec": end_to_end_sec,
            "end_to_end_sec": end_to_end_sec,
            "provider_wall_sec": provider_wall_sec,
            "non_provider_sec": round(end_to_end_sec - provider_wall_sec, 4),
            "source_prepare_sec": source_prepare_sec,
            "prompt_build_sec": prompt_build_sec,
            "parse_sec": 0.0,
            "apply_sec": 0.0,
            "verifier_sec": 0.0,
            "result_finalize_sec": 0.0,
            "prompt_system_chars": len(system_prompt),
            "prompt_user_chars": len(user_prompt),
            "prompt_total_chars": len(system_prompt) + len(user_prompt),
            "response_chars": 0,
            **ollama_metrics,
            "timed_out": True,
            "timeout_stage": "model_call",
            "protocol_parse_success": False,
            "terminal_status": "MODEL_TIMEOUT",
            "solved": False,
            "armor_oracle_status": "NOT_APPLICABLE",
        }

    t_provider_end = time.monotonic()
    provider_wall_sec = round(t_provider_end - t_provider_start, 4)

    if not raw_output or not raw_output.strip():
        end_to_end_sec = round(t_provider_end - t_e2e_start, 4)
        return {
            "task_id": task_dict["task_id"],
            "arm_id": "N30R_A_7B_BARE",
            "trial_index": 0,
            "task_seed": seed,
            "model_requested": "qwen2.5-coder:7b-instruct",
            "model_actual": "qwen2.5-coder:7b-instruct",
            "provider_actual": "ollama",
            "provider_options": provider_opts,
            "task_statement_sha256": sha256_str(task_statement),
            "source_fixture_sha256": task_dict.get("source_fixture_sha256", ""),
            "verifier_contract_sha256": task_dict.get("verifier_contract_sha256", ""),
            "execution_completed": True,
            "contract_valid": True,
            "model_call_count": 1,
            "model_response_received": True,
            "raw_output_length": 0,
            "raw_output_sha256": "",
            "candidate_hash": "",
            "candidate_isolated": False,
            "apply_status": "none",
            "verifier_reached": False,
            "verifier_status": "not_run",
            "semantic_retry_count": 0,
            "wall_time_sec": end_to_end_sec,
            "end_to_end_sec": end_to_end_sec,
            "provider_wall_sec": provider_wall_sec,
            "non_provider_sec": round(end_to_end_sec - provider_wall_sec, 4),
            "source_prepare_sec": source_prepare_sec,
            "prompt_build_sec": prompt_build_sec,
            "parse_sec": 0.0,
            "apply_sec": 0.0,
            "verifier_sec": 0.0,
            "result_finalize_sec": 0.0,
            "prompt_system_chars": len(system_prompt),
            "prompt_user_chars": len(user_prompt),
            "prompt_total_chars": len(system_prompt) + len(user_prompt),
            "response_chars": 0,
            **ollama_metrics,
            "timed_out": False,
            "timeout_stage": "",
            "protocol_parse_success": False,
            "terminal_status": "INFRA_INVALID",
            "solved": False,
            "armor_oracle_status": "NOT_APPLICABLE",
        }

    # === Parse ===
    t_parse_start = time.monotonic()
    blocks, parser_status = _parse_search_replace(raw_output)
    protocol_success = parser_status == "success"
    parse_sec = round(time.monotonic() - t_parse_start, 4)

    candidate_hash = ""
    apply_status = "none"
    verifier_reached = False
    verifier_status = "not_run"
    terminal = "PROTOCOL_INVALID"
    solved = False
    apply_sec = 0.0
    verifier_sec = 0.0

    if blocks:
        with tempfile.TemporaryDirectory() as td:
            t_apply_start = time.monotonic()
            patched, apply_status = _apply_search_replace(orig, blocks)
            candidate_hash = sha256_str(patched)
            apply_sec = round(time.monotonic() - t_apply_start, 4)
            if apply_status == "applied":
                t_verifier_start = time.monotonic()
                ec, _, _ = _run_verifier(patched, verifier_cmd, td)
                verifier_sec = round(time.monotonic() - t_verifier_start, 4)
                verifier_reached = True
                verifier_status = "pass" if ec == 0 else "fail"
                terminal = "VERIFIED_SOLVE" if verifier_status == "pass" else "VERIFIED_FAIL"
                solved = verifier_status == "pass"
            elif apply_status == "search_mismatch":
                terminal = "APPLY_INVALID"
    else:
        terminal = "PROTOCOL_INVALID"

    t_e2e_end = time.monotonic()
    end_to_end_sec = round(t_e2e_end - t_e2e_start, 4)
    result_finalize_sec = round(t_e2e_end - (t_provider_end + parse_sec + apply_sec + verifier_sec), 4)

    return {
        "task_id": task_dict["task_id"],
        "arm_id": "N30R_A_7B_BARE",
        "trial_index": 0,
        "task_seed": seed,
        "model_requested": "qwen2.5-coder:7b-instruct",
        "model_actual": "qwen2.5-coder:7b-instruct",
        "provider_actual": "ollama",
        "provider_options": provider_opts,
        "task_statement_sha256": sha256_str(task_statement),
        "source_fixture_sha256": task_dict.get("source_fixture_sha256", ""),
        "verifier_contract_sha256": task_dict.get("verifier_contract_sha256", ""),
        "execution_completed": True,
        "contract_valid": True,
        "model_call_count": 1,
        "model_response_received": bool(raw_output),
        "raw_output_length": len(raw_output),
        "raw_output_sha256": sha256_str(raw_output),
        "candidate_hash": candidate_hash,
        "candidate_isolated": bool(blocks),
        "apply_status": apply_status,
        "verifier_reached": verifier_reached,
        "verifier_status": verifier_status,
        "semantic_retry_count": 0,
        # Fair timing fields
        "wall_time_sec": end_to_end_sec,
        "end_to_end_sec": end_to_end_sec,
        "provider_wall_sec": provider_wall_sec,
        "non_provider_sec": round(end_to_end_sec - provider_wall_sec, 4),
        "source_prepare_sec": source_prepare_sec,
        "prompt_build_sec": prompt_build_sec,
        "parse_sec": parse_sec,
        "apply_sec": apply_sec,
        "verifier_sec": verifier_sec,
        "result_finalize_sec": max(result_finalize_sec, 0.0),
        # Prompt size metrics
        "prompt_system_chars": len(system_prompt),
        "prompt_user_chars": len(user_prompt),
        "prompt_total_chars": len(system_prompt) + len(user_prompt),
        "response_chars": len(raw_output),
        # Ollama native metrics
        **ollama_metrics,
        "timed_out": False,
        "timeout_stage": "",
        "protocol_parse_success": protocol_success,
        "terminal_status": terminal,
        "solved": solved,
        "armor_oracle_status": "NOT_APPLICABLE",
    }


def run_core_row(task_dict: dict, seed: int, run_id: str) -> dict:
    """Run a single Core row: production LocalModelExecutor path."""
    from nexus.services.local_heal.local_model_capability_wiring import (
        project_planner_capabilities_for_local_executor,
    )
    from nexus.services.local_heal.local_model_source_anchor import (
        build_local_model_source_anchor,
    )

    # === E2E start — includes source read through receipt finalization ===
    t_e2e_start = time.monotonic()

    task_id = task_dict.get("task_id", "")
    source_relpath = task_dict.get("source_relpath", "")
    task_statement = task_dict.get("task_statement", "")

    root = Path(__file__).resolve().parents[2]
    fixture_path = root / source_relpath
    source_content = fixture_path.read_text(encoding="utf-8")
    mod: dict = {}
    exec(source_content, mod)
    orig = mod.get("ORIGINAL", source_content)

    workspace = tempfile.mkdtemp(prefix=f"n30r-core-{task_id}-")
    target_relpath = "f.py"
    with open(os.path.join(workspace, target_relpath), "w") as f:
        f.write(orig)

    t_source_done = time.monotonic()
    source_prepare_sec = round(t_source_done - t_e2e_start, 4)

    # Planner
    t_planner_start = time.monotonic()
    from nexus.engine.capability_planner import CapabilityPlanner
    planner = CapabilityPlanner()

    # Back up environment variables
    env_keys = [
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL",
        "NEXUS_C15_SECONDARY_PROPOSER_MODEL",
        "NEXUS_C15_DELEGATED_RETRY_CANDIDATE_MODELS",
    ]
    backup_env = {k: os.environ[k] for k in env_keys if k in os.environ}

    # Set environment variables — parity with Bare for provider options injected via signal_snapshot
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "localheal_pipeline"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER"] = "ollama"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b-instruct"
    os.environ["NEXUS_C15_SECONDARY_PROPOSER_MODEL"] = "qwen2.5-coder:7b-instruct"
    os.environ["NEXUS_C15_DELEGATED_RETRY_CANDIDATE_MODELS"] = "qwen2.5-coder:7b-instruct"

    try:
        plan = planner.plan(
            task_desc=task_statement,
            task_type="swe_bounded_repair",
            route={"task_id": task_id, "task_desc": task_statement,
                   "task_type": "swe_bounded_repair",
                   "difficulty": task_dict.get("difficulty", "medium"), "route_features": {}},
            pillars={}, codeintel={}, phase_trace={},
            budget={"max_cost": 20}, skills=[],
        )
        signal_snapshot = plan.signal_snapshot
        signal_snapshot["provider_timeout_sec"] = _SHARED_PROVIDER_TIMEOUT
        signal_snapshot["difficulty"] = task_dict.get("difficulty", "medium")
        # Inject shared provider options for parity
        signal_snapshot["provider_options"] = _make_provider_options(seed)
    except Exception:
        signal_snapshot = {
            "ssd_route_map": {"capability_reasons": {}},
            "provider_timeout_sec": _SHARED_PROVIDER_TIMEOUT,
            "provider_options": _make_provider_options(seed),
        }

    planner_sec = round(time.monotonic() - t_planner_start, 4)

    t_localization_start = time.monotonic()
    projection = project_planner_capabilities_for_local_executor(signal_snapshot)
    verifier_cmd = tuple(task_dict.get("verifier_command", []))
    target_symbol = ""
    locked_search = ""
    source_anchor_hash = ""
    try:
        anchor = build_local_model_source_anchor(
            source_root=workspace, target_file=target_relpath,
            target_symbol=target_symbol, locked_search="",
        )
        source_anchor_hash = anchor.span_hash
        if anchor.span_start and anchor.span_end:
            lines = orig.splitlines()
            locked_search = "\n".join(lines[anchor.span_start - 1:anchor.span_end])
    except Exception:
        pass
    anchor_localization_sec = round(time.monotonic() - t_localization_start, 4)

    evidence_refs = (f"v2:{run_id}:source", f"v2:{run_id}:localization")

    executor_request = LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement=task_statement,
        repo_root=workspace,
        target_file=target_relpath,
        selected_capabilities=projection.selected_capabilities,
        evidence_refs=evidence_refs,
        receipt_context={},
        route_context={
            "signal_snapshot": signal_snapshot,
            "verifier_command": list(verifier_cmd),
            "target_symbol": target_symbol,
            "locked_search": locked_search,
            "difficulty": task_dict.get("difficulty", "medium"),
            "python_executable": sys.executable,
            "llm_call_ledger": {},
        },
        model_name="qwen2.5-coder:7b-instruct",
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    provider = OllamaLocalModelProvider()

    try:
        t_executor_start = time.monotonic()
        executor_response = LocalModelExecutor.run(
            executor_request, provider=provider
        )
        t_executor_end = time.monotonic()
        executor_sec = round(t_executor_end - t_executor_start, 4)

        t_e2e_end = time.monotonic()
        end_to_end_sec = round(t_e2e_end - t_e2e_start, 4)

        meta = (
            executor_response.raw_model_metadata
            if isinstance(executor_response.raw_model_metadata, dict)
            else {}
        )

        raw_output = executor_response.candidate_patch or ""
        candidate_hash = meta.get("selected_candidate_hash", "") or meta.get("candidate_hash", "")
        candidate_isolated = meta.get("candidate_isolated", False)
        apply_status = meta.get("isolated_apply_status", "")
        verifier_result = meta.get("isolated_verifier_status", "")
        semantic_retry_count = meta.get("semantic_retry_count", 0)

        # Extract phase timing from metadata if available
        prompt_build_sec = round(float(meta.get("prompt_build_sec", 0.0)), 4)
        provider_wall_sec = round(float(meta.get("provider_elapsed_sec", 0.0)), 4)

        phase_reproduction_sec = round(float(meta.get("phase_reproduction_sec", 0.0)), 4)
        phase_planning_sec = round(float(meta.get("phase_planning_sec", 0.0)), 4)
        phase_localization_sec = round(float(meta.get("phase_localization_sec", 0.0)), 4)
        phase_patch_synthesis_sec = round(float(meta.get("phase_patch_synthesis_sec", 0.0)), 4)
        phase_verification_sec = round(float(meta.get("phase_verification_sec", 0.0)), 4)

        # Extract Ollama native metrics from last provider response
        ollama_metrics: dict = {
            "ollama_total_duration": meta.get("ollama_total_duration", 0),
            "ollama_load_duration": meta.get("ollama_load_duration", 0),
            "ollama_prompt_eval_count": meta.get("ollama_prompt_eval_count", 0),
            "ollama_prompt_eval_duration": meta.get("ollama_prompt_eval_duration", 0),
            "ollama_eval_count": meta.get("ollama_eval_count", 0),
            "ollama_eval_duration": meta.get("ollama_eval_duration", 0),
            "ollama_done_reason": meta.get("ollama_done_reason", ""),
            "ollama_metrics_available": meta.get("ollama_metrics_available", False),
        }

        # Prompt size from meta if available
        prompt_total_chars = meta.get("prompt_total_chars", 0)
        response_chars = len(raw_output)

        non_provider_sec = round(end_to_end_sec - provider_wall_sec, 4) if provider_wall_sec > 0 else end_to_end_sec

        verifier_reached = bool(verifier_result)
        if verifier_result == "pass":
            terminal = "VERIFIED_SOLVE"
            solved = True
        elif verifier_reached:
            terminal = "VERIFIED_FAIL"
            solved = False
        elif candidate_hash:
            terminal = "APPLY_INVALID"
            solved = False
        elif raw_output:
            terminal = "PROTOCOL_INVALID"
            solved = False
        else:
            terminal = "INFRA_INVALID"
            solved = False

        armor_oracle_status = "FULL_ARMOR_PATH_ACCEPTED" if (
            raw_output and candidate_hash
        ) else "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING"

        profile_selected = meta.get("initial_execution_profile", "unknown")
        profile_final = meta.get("final_execution_profile", "unknown")
        escalation_count = int(meta.get("profile_escalation_count", 0) or 0)
        escalation_reasons = list(meta.get("profile_escalation_reasons", []) or [])
        ledger = meta.get("llm_call_ledger", {})
        if not isinstance(ledger, dict):
            ledger = {}
        by_phase = ledger.get("by_phase", {})
        llm_call_planning = int(by_phase.get("planning", 0) or 0)
        llm_call_spec_gen = int(by_phase.get("spec_gen", 0) or 0)
        llm_call_patch = int(by_phase.get("patch", 0) or 0)
        llm_call_retry = int(by_phase.get("retry", 0) or 0)
        llm_call_judge = int(by_phase.get("judge", 0) or 0)
        llm_call_proposer = int(by_phase.get("proposer", 0) or 0)
        llm_call_total = int(ledger.get("total_calls", 0) or 0)

        return {
            "task_id": task_id,
            "arm_id": "N30R_B_7B_REAL_CORE",
            "trial_index": 0,
            "task_seed": seed,
            "model_requested": "qwen2.5-coder:7b-instruct",
            "model_actual": "qwen2.5-coder:7b-instruct",
            "provider_actual": "ollama",
            "provider_options": _make_provider_options(seed),
            "task_statement_sha256": sha256_str(task_statement),
            "source_fixture_sha256": task_dict.get("source_fixture_sha256", ""),
            "verifier_contract_sha256": task_dict.get("verifier_contract_sha256", ""),
            "execution_completed": True,
            "contract_valid": True,
            "model_call_count": max(1 + semantic_retry_count, llm_call_total) if llm_call_total else 1 + semantic_retry_count,
            "model_response_received": bool(raw_output),
            "raw_output_length": len(raw_output),
            "raw_output_sha256": sha256_str(raw_output) if raw_output else "",
            "candidate_hash": candidate_hash,
            "candidate_isolated": candidate_isolated,
            "apply_status": apply_status or "none",
            "verifier_reached": verifier_reached,
            "verifier_status": verifier_result or "not_run",
            "semantic_retry_count": semantic_retry_count,
            "profile_selected": profile_selected,
            "final_profile": profile_final,
            "profile_attempts": list(meta.get("profile_attempts", []) or []),
            "escalation_count": escalation_count,
            "escalation_reasons": escalation_reasons,
            "llm_call_planning": llm_call_planning,
            "llm_call_spec_gen": llm_call_spec_gen,
            "llm_call_patch": llm_call_patch,
            "llm_call_retry": llm_call_retry,
            "llm_call_judge": llm_call_judge,
            "llm_call_proposer": llm_call_proposer,
            "llm_call_total": llm_call_total,
            "ledger_authoritative": bool(ledger.get("authoritative", False)),
            "ledger_source": str(ledger.get("source", "unknown")),
            # Fair timing fields
            "wall_time_sec": end_to_end_sec,
            "end_to_end_sec": end_to_end_sec,
            "provider_wall_sec": provider_wall_sec,
            "non_provider_sec": non_provider_sec,
            "source_prepare_sec": source_prepare_sec,
            "planner_sec": planner_sec,
            "anchor_localization_sec": anchor_localization_sec,
            "prompt_build_sec": prompt_build_sec,
            "executor_sec": executor_sec,
            "phase_reproduction_sec": phase_reproduction_sec,
            "phase_planning_sec": phase_planning_sec,
            "phase_localization_sec": phase_localization_sec,
            "phase_patch_synthesis_sec": phase_patch_synthesis_sec,
            "phase_verification_sec": phase_verification_sec,
            # Prompt size metrics
            "prompt_total_chars": prompt_total_chars,
            "response_chars": response_chars,
            # Ollama native metrics
            **ollama_metrics,
            "timed_out": False,
            "timeout_stage": "",
            "protocol_parse_success": bool(raw_output),
            "terminal_status": terminal,
            "solved": solved,
            "armor_oracle_status": armor_oracle_status,
        }
    finally:
        # Restore environment variables
        for k in env_keys:
            if k in backup_env:
                os.environ[k] = backup_env[k]
            else:
                os.environ.pop(k, None)


def run_evaluation(
    manifest: dict[str, Any],
    jsonl_out: str | None,
    summary_out: str | None,
) -> dict[str, Any]:
    """Execute paired evaluation with environment preflight."""
    import json as _json

    env_receipt = _check_environment()
    env_receipt_sha256 = sha256_str(_json.dumps(env_receipt, sort_keys=True, default=str))

    if not env_receipt["environment_valid"]:
        logger.error("Environment check failed — aborting evaluation")
        fail_row = {
            "env_receipt": env_receipt,
            "env_receipt_sha256": env_receipt_sha256,
        }
        result = {
            "experiment_id": manifest.get("experiment_id", ""),
            "run_id": str(int(time.time())),
            "total_rows": 0,
            "status": "ENVIRONMENT_INVALID",
            "valid_rows": 0,
            "invalid_rows": -1,
            "effectiveness": "V2_INVALID",
            "metrics": {},
            "env_receipt": env_receipt,
            "env_receipt_sha256": env_receipt_sha256,
        }
        if summary_out:
            os.makedirs(os.path.dirname(summary_out) or ".", exist_ok=True)
            with open(summary_out, "w") as f:
                _json.dump(result, f, indent=2, default=str)
        if jsonl_out:
            os.makedirs(os.path.dirname(jsonl_out) or ".", exist_ok=True)
            with open(jsonl_out, "w") as f:
                pass
        print(f"ENVIRONMENT_INVALID: {_json.dumps(env_receipt, indent=2)}")
        return result

    tasks = manifest["tasks"]
    base_seed = manifest.get("base_seed", 4200)
    run_id = str(int(time.time()))

    rows = []
    for task_dict in tasks:
        order = task_dict["execution_order"]
        seed = task_dict["task_seed"]

        for idx, arm_id in enumerate(order):
            print(f"\n[{arm_id}] {task_dict['task_id']} (seed={seed}, order={idx})")
            sys.stdout.flush()

            if arm_id == "N30R_A_7B_BARE":
                row = run_bare_row(task_dict, seed, run_id)
            else:
                row = run_core_row(task_dict, seed, run_id)

            row["env_receipt"] = env_receipt
            row["env_receipt_sha256"] = env_receipt_sha256
            rows.append(row)
            print(f"  terminal={row['terminal_status']} solved={row['solved']} "
                  f"candidate={row['candidate_hash'][:12] if row['candidate_hash'] else 'none'}")
            sys.stdout.flush()

    # Write JSONL
    if jsonl_out:
        os.makedirs(os.path.dirname(jsonl_out) or ".", exist_ok=True)
        with open(jsonl_out, "w") as f:
            for row in rows:
                f.write(_json.dumps(row, default=str) + "\n")
        print(f"\nResults: {jsonl_out}")

    # Compute summary metrics
    from scripts.bench.n30r_v2_paired_eval import (
        validate_results, compute_metrics, classify_effectiveness,
    )
    task_map = {t["task_id"]: t for t in tasks}

    # Write temp JSONL for validation
    tmp_jsonl = jsonl_out or f"/tmp/n30r_v2_rows_{run_id}.jsonl"
    if not jsonl_out:
        with open(tmp_jsonl, "w") as f:
            for row in rows:
                f.write(_json.dumps(row, default=str) + "\n")

    validation = validate_results(manifest, tmp_jsonl)
    metrics = validation.get("metrics", {})
    effectiveness = validation.get("effectiveness", "V2_INVALID")

    paired_summary = {
        "experiment_id": manifest.get("experiment_id", ""),
        "run_id": run_id,
        "total_rows": len(rows),
        "status": validation.get("status", ""),
        "valid_rows": validation.get("valid_rows", 0),
        "invalid_rows": validation.get("invalid_rows", 0),
        "effectiveness": effectiveness,
        "metrics": metrics,
    }

    if summary_out:
        os.makedirs(os.path.dirname(summary_out) or ".", exist_ok=True)
        with open(summary_out, "w") as f:
            _json.dump(paired_summary, f, indent=2, default=str)
        print(f"Summary: {summary_out}")

    return paired_summary
