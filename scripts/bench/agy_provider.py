"""``agy`` provider for the same-model A/B lane (issue #1820).

The legacy ``gemini`` CLI is no longer usable, so the lane reaches Gemini through
the ``agy`` print-mode CLI (``agy --print ... --model ... --output-format json``).
The bare arm calls :func:`ask_direct_agy_patch`. The with-Nexus arm model path reaches agy
through the unified runtime, which currently blocks it at Workforce Admission (see docs/benchmark/ab_lane_revival_2026-10.md).

Containment: agy runs with ``--mode plan`` (no auto-approve), ``--new-project``
(no carried conversation) and an empty temporary working directory, so it has no
repository checkout to read. Permission bypass is never used. The prompt carries only
the task statement, the target source and the visible tests.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any, Mapping

# Exact id from ``agy models`` (2026-10-12): gemini-3.8-flash-{high,medium,low}. The tier is
# not documented by the dispatch skill; medium is the neutral middle. Override with NEXUS_AGY_MODEL.
AGY_DEFAULT_MODEL = "gemini-3.8-flash-medium"
AGY_FALLBACK_BIN = "/Users/jameschen/.local/bin/agy"
AGY_MISSING = "agy_missing"


def agy_model(env: Mapping[str, str] | None = None) -> str:
    values = env if env is not None else os.environ
    return str(values.get("NEXUS_AGY_MODEL") or "").strip() or AGY_DEFAULT_MODEL


def resolve_agy_bin(env: Mapping[str, str] | None = None) -> str | None:
    values = env if env is not None else os.environ
    override = str(values.get("NEXUS_AGY_BIN") or "").strip()
    if override:
        found = shutil.which(override) or (override if Path(override).is_file() else None)
        return found
    found = shutil.which("agy", path=values.get("PATH"))
    if found:
        return found
    return AGY_FALLBACK_BIN if Path(AGY_FALLBACK_BIN).is_file() else None


def configure_agy_lane_env(environ: MutableMapping[str, str]) -> str:
    """Bind both arms to one agy model id (same-model check). Returns the model id."""
    model = agy_model(environ)
    environ["NEXUS_AGY_MODEL"] = model
    environ["NEXUS_GEMINI_MODEL_NAME"] = model
    environ["NEXUS_DIRECT_GEMINI_MODEL"] = model
    return model


def _parse_patch_json(text: str) -> dict[str, Any]:
    out = text.strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:json)?\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        start, end = out.find("{"), out.rfind("}")
        if start == -1 or end == -1:
            raise
        payload = json.loads(out[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("patch_json_not_object")
    return payload


def _tail(value: Any, limit: int = 2000) -> str:
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value or "")
    return text[-limit:]


def run_agy_print(
    *,
    prompt: str,
    model: str,
    timeout_sec: int,
    agy_bin: str,
    env: Mapping[str, str],
    runner: Callable[..., Any] = subprocess.run,
) -> Any:
    """One isolated agy print-mode turn (plan mode, fresh project, empty temp cwd)."""
    timeout = max(5, int(timeout_sec))
    cmd = [
        agy_bin,
        "--new-project",
        "--mode",
        "plan",
        "--model",
        model,
        "--output-format",
        "json",
        "--print-timeout",
        f"{timeout}s",
        "--print",
        prompt,
    ]
    with tempfile.TemporaryDirectory(prefix="nexus-agy-bench-") as cwd:
        return runner(
            cmd,
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout + 15,
            check=False,
        )


def ask_direct_agy_patch(
    *,
    prompt: str,
    timeout_sec: int,
    env: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[dict[str, Any], str]:
    """Ask agy for a ``{status, patch}`` JSON answer. Same ``(payload, raw)`` shape as the gemini path."""
    values = dict(env if env is not None else os.environ)
    model = agy_model(values)
    agy_bin = resolve_agy_bin(values)
    if not agy_bin:
        return {
            "status": "FAIL",
            "error_category": AGY_MISSING,
            "tokens_used": 0,
            "model_name": model,
        }, AGY_MISSING
    timeout = max(5, int(timeout_sec))
    start = time.monotonic()
    try:
        res = run_agy_print(
            prompt=prompt,
            model=model,
            timeout_sec=timeout,
            agy_bin=agy_bin,
            env=values,
            runner=runner,
        )
    except subprocess.TimeoutExpired as exc:
        wall = round(time.monotonic() - start, 4)
        payload = {
            "status": "FAIL",
            "error_category": "timeout",
            "tokens_used": 0,
            "model_name": model,
        }
        payload.update(gateway_process_sec=wall, gateway_total_sec=wall, timeout_sec=timeout)
        return payload, _tail(exc.stderr or exc.stdout)
    wall = round(time.monotonic() - start, 4)
    timing = {
        "gateway_process_sec": wall,
        "gateway_provider_wait_sec": wall,
        "gateway_total_sec": wall,
    }
    if res.returncode != 0:
        payload = {
            "status": "FAIL",
            "error_category": "cli_error",
            "tokens_used": 0,
            "model_name": model,
            **timing,
        }
        return payload, _tail(res.stderr or res.stdout)
    failure = {
        "status": "FAIL",
        "error_category": "parse_failure",
        "tokens_used": 0,
        "model_name": model,
        **timing,
    }
    try:
        envelope = json.loads(res.stdout)
        if str(envelope.get("status", "SUCCESS")).upper() != "SUCCESS":
            raise ValueError(f"agy_status:{envelope.get('status')}")
    except Exception as exc:  # noqa: BLE001
        return failure, f"{type(exc).__name__}: {_tail(res.stdout)}"
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    try:
        tokens = int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    token_fields = {
        "tokens_used": tokens,
        "token_capture_status": "measured" if tokens > 0 else "missing_gateway_stats",
        "gateway_stats_present": bool(usage),
        "gateway_usage_metadata_present": bool(usage),
        "gateway_token_source": "usage_metadata" if tokens > 0 else "missing",
    }
    raw = str(envelope.get("response") or "")
    try:
        payload = _parse_patch_json(raw)
    except Exception as exc:  # noqa: BLE001
        # The model answered (and was billed) but not with the requested JSON: a model failure, not infra.
        return {**failure, **token_fields}, f"{type(exc).__name__}: {_tail(raw)}"
    payload.update(token_fields)
    payload["model_name"] = model
    payload["model_patch_generated"] = bool(payload.get("patch"))
    payload["agy_conversation_id"] = str(envelope.get("conversation_id") or "")
    payload.update(timing)
    return payload, raw
