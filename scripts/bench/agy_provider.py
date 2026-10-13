"""``agy`` provider for the same-model A/B lane (issue #1820).

The legacy ``gemini`` CLI is no longer usable, so the lane reaches Gemini through
the ``agy`` print-mode CLI (``agy --print ... --model ... --output-format json``).
The bare arm calls :func:`ask_direct_agy_patch`. The with-Nexus arm model path reaches agy
through the unified runtime using the Workforce binding declared by :func:`configure_agy_lane_env`
(see docs/benchmark/ab_lane_revival_2026-10.md).

Containment: agy runs with ``--mode plan --sandbox`` (no auto-approve), ``--new-project``
(no carried conversation) and an empty temporary working directory, so it has no
repository checkout to read. Permission bypass is never used. The prompt carries only
the task statement, the target source and the visible tests.

Identity and accounts (#1932): every call passes the exact ``--model``, runs under one
account leased from the shared Agy account pool (allowlist + available 5-hour quota window),
and fails closed with ``MODEL_IDENTITY_MISMATCH`` / ``MODEL_IDENTITY_UNOBSERVED`` unless Agy's
own log shows the requested model was served. See :mod:`scripts.bench.agy_account_lease`.
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

from nexus.services.agy_account_pool import AgyAccountPoolError, CrossProcessLeaseCoordinator
from scripts.bench.agy_account_lease import (
    MODEL_IDENTITY_OK,
    POOL_RUNTIME_MISSING,
    AgyAttemptOutcome,
    BenchLeaseConfig,
    assert_contained_agy_argv,
    build_bench_lease_coordinator,
    has_quota_failure_signal,
    has_terminal_quota_log_signal,
    model_identity_verdict,
    parse_agy_model_observation,
    run_with_account_lease,
)

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


AGY_WORKFORCE_BINDINGS_ENV = "NEXUS_BENCH_WORKFORCE_BINDINGS_JSON"
# Controls the lane physically supplies to the candidate generator: the task fixture, the single
# target file, a mandatory pytest command, the edit parser, a response-contract verifier and the
# hidden verifier run after the model call.
AGY_LANE_CONTROLS = (
    "task_card",
    "allowed_files",
    "mandatory_commands",
    "parser",
    "verifier",
    "independent_verification",
)


def agy_workforce_bindings(model: str) -> dict[str, Any]:
    """Channel -> binding mapping for the unified runtime (exact provider + model identity)."""
    return {"online": {"provider": "agy", "model": model, "controls": list(AGY_LANE_CONTROLS)}}


def configure_agy_lane_env(environ: MutableMapping[str, str]) -> str:
    """Bind both arms to one agy model id (same-model check). Returns the model id."""
    model = agy_model(environ)
    environ["NEXUS_AGY_MODEL"] = model
    environ["NEXUS_GEMINI_MODEL_NAME"] = model
    environ["NEXUS_DIRECT_GEMINI_MODEL"] = model
    # With-Nexus arm (issue #1844): route the in-process gateway to agy and declare the
    # Workforce binding for that exact identity. Admission resolves it (agy_flash_38 for
    # gemini-3.8-flash-medium); an unregistered model id is BLOCKed, never substituted.
    environ["NEXUS_OAUTH_PROVIDER"] = "agy"
    environ[AGY_WORKFORCE_BINDINGS_ENV] = json.dumps(agy_workforce_bindings(model), sort_keys=True)
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


def _agy_print_argv(
    *, prompt: str, model: str, timeout: int, agy_bin: str, log_path: Path
) -> list[str]:
    cmd = [
        agy_bin,
        "--new-project",
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        model,
        "--log-file",
        str(log_path),
        "--output-format",
        "json",
        "--print-timeout",
        f"{timeout}s",
        "--print",
        prompt,
    ]
    assert_contained_agy_argv(cmd)
    return cmd


def run_agy_print(
    *,
    prompt: str,
    model: str,
    timeout_sec: int,
    agy_bin: str,
    env: Mapping[str, str],
    log_path: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[Any, bool]:
    """One isolated agy print-mode turn (plan + sandbox, fresh project, empty temp cwd).

    Returns ``(completed_process, workdir_touched)``. Agy writes its log (the observed-model
    witness) to ``log_path``, which lives outside the empty working directory.
    """
    timeout = max(5, int(timeout_sec))
    cmd = _agy_print_argv(
        prompt=prompt, model=model, timeout=timeout, agy_bin=agy_bin, log_path=log_path
    )
    with tempfile.TemporaryDirectory(prefix="nexus-agy-bench-") as cwd:
        try:
            res = runner(
                cmd,
                cwd=cwd,
                env=dict(env),
                capture_output=True,
                text=True,
                timeout=timeout + 15,
                check=False,
            )
        finally:
            touched = any(Path(cwd).iterdir())
        return res, touched


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _agy_envelope(stdout: str) -> dict[str, Any] | None:
    try:
        envelope = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    return envelope if isinstance(envelope, dict) else None


def _envelope_usage(envelope: dict[str, Any]) -> dict[str, Any]:
    usage = envelope.get("usage")
    return usage if isinstance(usage, dict) else {}


def _provider_effect(stdout: str, workdir_touched: bool) -> bool | None:
    """True when the provider answered/billed or touched the workdir; None when unprovable."""
    if workdir_touched:
        return True
    if not str(stdout or "").strip():
        return False
    envelope = _agy_envelope(stdout)
    if envelope is None:
        return None
    usage = _envelope_usage(envelope)
    try:
        tokens = int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return None
    return bool(str(envelope.get("response") or "").strip()) or tokens > 0


def _agy_attempt(
    *, prompt: str, model: str, timeout: int, agy_bin: str, runner: Callable[..., Any]
) -> Callable[[dict[str, str]], AgyAttemptOutcome]:
    def attempt(run_env: dict[str, str]) -> AgyAttemptOutcome:
        with tempfile.TemporaryDirectory(prefix="nexus-agy-bench-log-") as log_dir:
            log_path = Path(log_dir) / "agy.log"
            try:
                res, touched = run_agy_print(
                    prompt=prompt,
                    model=model,
                    timeout_sec=timeout,
                    agy_bin=agy_bin,
                    env=run_env,
                    log_path=log_path,
                    runner=runner,
                )
            except subprocess.TimeoutExpired as exc:
                return AgyAttemptOutcome(
                    result=("timeout", exc, parse_agy_model_observation(_read_text(log_path)))
                )
            log_text = _read_text(log_path)
        observation = parse_agy_model_observation(log_text)
        quota = res.returncode != 0 and (
            has_quota_failure_signal(str(res.stderr or ""))
            or has_terminal_quota_log_signal(log_text)
        )
        return AgyAttemptOutcome(
            result=("completed", res, observation),
            quota_exhausted=quota,
            provider_effect=_provider_effect(str(res.stdout or ""), touched) if quota else True,
        )

    return attempt


def ask_direct_agy_patch(
    *,
    prompt: str,
    timeout_sec: int,
    env: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    coordinator: CrossProcessLeaseCoordinator | None = None,
    lease_config: BenchLeaseConfig | None = None,
) -> tuple[dict[str, Any], str]:
    """Ask agy for a ``{status, patch}`` JSON answer. Same ``(payload, raw)`` shape as the gemini path.

    The call runs under one leased pool account (allowlist + available 5-hour quota window, see
    :mod:`scripts.bench.agy_account_lease`) and fails closed unless Agy's log shows it served
    exactly the requested model.
    """
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
    config = lease_config or BenchLeaseConfig.from_env(values)
    pool_source = "injected"
    if coordinator is None:
        try:
            coordinator, pool_source = build_bench_lease_coordinator(values)
        except (AgyAccountPoolError, OSError, ValueError, KeyError) as exc:
            return {
                "status": "FAIL",
                "error_category": POOL_RUNTIME_MISSING,
                "provider_call_attempted": False,
                "tokens_used": 0,
                "model_name": model,
                "requested_model": model,
            }, f"{type(exc).__name__}: {exc}"
    timeout = max(5, int(timeout_sec))
    start = time.monotonic()
    run = run_with_account_lease(
        model=model,
        attempt=_agy_attempt(
            prompt=prompt, model=model, timeout=timeout, agy_bin=agy_bin, runner=runner
        ),
        base_env=values,
        config=config,
        coordinator=coordinator,
        pool_source=pool_source,
    )
    wall = round(time.monotonic() - start, 4)
    lease_fields = run.public_fields()
    if run.result is None:  # decided before any Agy process started
        return {
            "status": "FAIL",
            "error_category": run.failure_kind,
            "provider_call_attempted": False,
            "tokens_used": 0,
            "model_name": model,
            "requested_model": model,
            "account_eligibility_states": sorted({
                str(info.get("state")) for info in run.eligibility.values()
            }),
            **lease_fields,
        }, run.failure_kind
    kind, res, observation = run.result
    identity = model_identity_verdict(model, observation)
    common = {"model_name": model, "provider_call_attempted": True, **identity, **lease_fields}
    if kind == "timeout":
        payload = {"status": "FAIL", "error_category": "timeout", "tokens_used": 0, **common}
        payload.update(gateway_process_sec=wall, gateway_total_sec=wall, timeout_sec=timeout)
        return payload, _tail(res.stderr or res.stdout)
    timing = {
        "gateway_process_sec": wall,
        "gateway_provider_wait_sec": wall,
        "gateway_total_sec": wall,
    }
    if run.status != "completed":  # quota: rotations spent, or retired after a provider effect
        payload = {
            "status": "FAIL",
            "error_category": run.failure_kind,
            "tokens_used": 0,
            **common,
            **timing,
        }
        return payload, _tail(res.stderr or res.stdout)
    if res.returncode != 0:
        payload = {
            "status": "FAIL",
            "error_category": "cli_error",
            "tokens_used": 0,
            **common,
            **timing,
        }
        return payload, _tail(res.stderr or res.stdout)
    failure = {
        "status": "FAIL",
        "error_category": "parse_failure",
        "tokens_used": 0,
        **common,
        **timing,
    }
    envelope = _agy_envelope(res.stdout)
    if envelope is None:
        return failure, f"ValueError: agy_envelope_not_json: {_tail(res.stdout)}"
    if str(envelope.get("status", "SUCCESS")).upper() != "SUCCESS":
        return failure, f"ValueError: agy_status:{envelope.get('status')}: {_tail(res.stdout)}"
    usage = _envelope_usage(envelope)
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
    conversation = str(envelope.get("conversation_id") or "")
    if identity["model_identity_status"] != MODEL_IDENTITY_OK:
        # The answer cannot be attributed to the requested model: never score it.
        return {
            **failure,
            **token_fields,
            "error_category": identity["model_identity_status"],
            "agy_conversation_id": conversation,
        }, f"{identity['model_identity_status']}: {identity['model_identity_reason']}"
    try:
        payload = _parse_patch_json(raw)
    except Exception as exc:  # noqa: BLE001
        # The model answered (and was billed) but not with the requested JSON: a model failure, not infra.
        return {**failure, **token_fields}, f"{type(exc).__name__}: {_tail(raw)}"
    payload.update(common)
    payload.update(token_fields)
    payload["model_name"] = model
    payload["model_patch_generated"] = bool(payload.get("patch"))
    payload["agy_conversation_id"] = conversation
    payload.update(timing)
    return payload, raw
