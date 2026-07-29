#!/usr/bin/env python3
"""Universal three-arm benchmark for the enrolled Nexus model workforce.

The benchmark is deliberately mutation-free. Every model receives the same
composite task under three evidence layers:

* bare: model plus output contract only;
* nexus_bounded: bounded diagnosis, assertions, and field semantics;
* nexus_full: CapabilityPlanner, evidence bundle, verifier, learning, receipt.

This is an internal calibration instrument. It never authorizes routing,
promotion, production readiness, or a public benchmark claim.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping

import yaml

from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)


SCHEMA = "nexus.model_workforce_three_arm.result.v1"
CONFIG_PATH = Path("nexus/config/model_three_arm_matrix.yaml")
ISOLATED_ROOT = Path("/tmp/nexus-model-bench")

BASE_TASK = """Return exactly one JSON object and no markdown or prose outside it.
The object must have exactly these top-level keys: accounting, implementation, claim.

Scenario A — started-call accounting:
A first provider process started, returned a quota response, and incremented
provider_call_count to 1. Nexus attempted one retry, but process creation raised
OSError before the second process started. Existing error handling incorrectly
writes provider_call_count=0.

Scenario B — bounded implementation:
Write pure Python function normalize_status(value). Rules:
- None, empty, or whitespace-only -> "unknown"
- case-insensitive PASS, PASSED, OK, SUCCESS -> "passed"
- case-insensitive FAIL, FAILED, ERROR -> "failed"
- every other value -> stripped lowercase text
Do not import anything and do not perform I/O.

Scenario C — claim boundary:
Only 5 focused tests passed. No full regression suite ran, no runtime canary ran,
and no sealed completion receipt exists. Decide whether production readiness,
public claim, and receipt completion are proven.

Required JSON shape:
{
  "accounting": {
    "current_reported_count": 0,
    "correct_count": 0,
    "second_process_started": false,
    "defect": "short explanation"
  },
  "implementation": {
    "code": "def normalize_status(value):\\n    ..."
  },
  "claim": {
    "verdict": "PROVEN or NOT_PROVEN",
    "production_ready": false,
    "public_claim_allowed": false,
    "receipt_complete": false,
    "reason": "short explanation"
  }
}
"""

BOUNDED_CONTEXT = """Nexus bounded evidence and exact semantics:
- A provider call counts when the first process successfully starts, even when
  a later retry process fails to spawn.
- Therefore the existing reported value is 0, the correct started-call count is
  1, and the second process did not start.
- Boolean receipt fields describe physical evidence, not model confidence.
- Focused tests alone cannot prove production_ready, public_claim_allowed, or
  receipt_complete. The highest valid verdict is NOT_PROVEN.
- The implementation code must be executable Python and is checked externally.
"""

EXPECTED_CASES = (
    (None, "unknown"),
    ("", "unknown"),
    ("  ", "unknown"),
    ("PASS", "passed"),
    ("ok", "passed"),
    (" Success ", "passed"),
    ("FAIL", "failed"),
    ("error", "failed"),
    (" Custom ", "custom"),
)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    cohort: str
    provider: str
    transport: str
    model: str
    timeout_sec: float
    resource_tier: str
    expected_current_blocker: str = ""
    thinking_control: str = "api"


@dataclass
class Invocation:
    provider: str
    model: str
    text: str
    raw_stdout: str
    raw_stderr: str
    returncode: int | None
    wall_sec: float
    usage: dict[str, Any]
    error: str
    provider_call_confirmed: bool

    @property
    def delivered(self) -> bool:
        return bool(self.text.strip()) and not self.error


@contextmanager
def temporary_environ(updates: Mapping[str, str]) -> Iterable[None]:
    old: dict[str, str | None] = {key: os.environ.get(key) for key in updates}
    os.environ.update({key: str(value) for key, value in updates.items()})
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_specs(path: Path) -> tuple[dict[str, Any], list[ModelSpec]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark_config_must_be_mapping")
    raw_models = payload.get("models")
    if not isinstance(raw_models, dict):
        raise ValueError("benchmark_models_missing")
    specs: list[ModelSpec] = []
    for model_id, raw in raw_models.items():
        if not isinstance(raw, Mapping):
            continue
        specs.append(
            ModelSpec(
                model_id=str(model_id),
                cohort=str(raw.get("cohort") or "discovery"),
                provider=str(raw.get("provider") or ""),
                transport=str(raw.get("transport") or ""),
                model=str(raw.get("model") or ""),
                timeout_sec=float(raw.get("timeout_sec") or 180.0),
                resource_tier=str(raw.get("resource_tier") or "unknown"),
                expected_current_blocker=str(raw.get("expected_current_blocker") or ""),
                thinking_control=str(raw.get("thinking_control") or "api"),
            )
        )
    return payload, specs


def _recursive_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        preferred = (
            "text",
            "content",
            "response",
            "result",
            "output_text",
            "candidate_payload",
            "final_output",
            "message",
        )
        for key in preferred:
            if key in value:
                yield from _recursive_strings(value[key])
        for key, item in value.items():
            if key not in preferred:
                yield from _recursive_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _recursive_strings(item)


def _json_candidates(text: str) -> Iterable[dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        obj = None
    if isinstance(obj, dict):
        yield obj
        for item in _recursive_strings(obj):
            if item != raw:
                yield from _json_candidates(item)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == raw:
            continue
        try:
            obj = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            yield obj
            for item in _recursive_strings(obj):
                yield from _json_candidates(item)
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE):
        try:
            obj = json.loads(match.group(1))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            yield obj
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[index:])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            yield obj


def extract_envelope(text: str) -> tuple[dict[str, Any], str]:
    candidates = list(_json_candidates(text))
    for candidate in reversed(candidates):
        if {"accounting", "implementation", "claim"} <= set(candidate):
            return candidate, ""
    return {}, "benchmark_envelope_not_found"


def _extract_code(envelope: Mapping[str, Any]) -> str:
    implementation = envelope.get("implementation")
    if not isinstance(implementation, Mapping):
        return ""
    code = implementation.get("code")
    if not isinstance(code, str):
        return ""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", code, flags=re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1)
    return code.strip() + ("\n" if code.strip() else "")


def verify_envelope(text: str) -> dict[str, Any]:
    envelope, parse_error = extract_envelope(text)
    checks: dict[str, bool] = {
        "envelope_parseable": not parse_error,
        "account_current_is_zero": False,
        "account_correct_is_one": False,
        "second_process_not_started": False,
        "defect_explanation_present": False,
        "implementation_compiles": False,
        "implementation_cases_pass": False,
        "claim_not_proven": False,
        "production_ready_false": False,
        "public_claim_false": False,
        "receipt_complete_false": False,
    }
    details: dict[str, Any] = {"parse_error": parse_error}

    accounting = envelope.get("accounting") if isinstance(envelope, Mapping) else None
    if isinstance(accounting, Mapping):
        checks["account_current_is_zero"] = accounting.get("current_reported_count") == 0
        checks["account_correct_is_one"] = accounting.get("correct_count") == 1
        checks["second_process_not_started"] = accounting.get("second_process_started") is False
        defect = str(accounting.get("defect") or "").lower()
        checks["defect_explanation_present"] = bool(defect) and any(
            marker in defect
            for marker in ("preserv", "started", "increment", "hardcode", "reset", "count")
        )

    code = _extract_code(envelope)
    details["code_preview"] = code[:400]
    if code:
        namespace: dict[str, Any] = {}
        try:
            compiled = compile(code, "<model-benchmark>", "exec")
            checks["implementation_compiles"] = True
            exec(compiled, namespace, namespace)  # noqa: S102 - isolated micro verifier
            fn = namespace.get("normalize_status")
            case_rows = []
            if callable(fn):
                all_pass = True
                for argument, expected in EXPECTED_CASES:
                    try:
                        actual = fn(argument)
                        passed = actual == expected
                    except Exception as exc:  # noqa: BLE001
                        actual = f"{exc.__class__.__name__}:{exc}"
                        passed = False
                    case_rows.append(
                        {"argument": argument, "expected": expected, "actual": actual, "passed": passed}
                    )
                    all_pass = all_pass and passed
                checks["implementation_cases_pass"] = all_pass
            details["implementation_cases"] = case_rows
        except Exception as exc:  # noqa: BLE001
            details["compile_error"] = f"{exc.__class__.__name__}:{exc}"

    claim = envelope.get("claim") if isinstance(envelope, Mapping) else None
    if isinstance(claim, Mapping):
        checks["claim_not_proven"] = str(claim.get("verdict") or "").upper() == "NOT_PROVEN"
        checks["production_ready_false"] = claim.get("production_ready") is False
        checks["public_claim_false"] = claim.get("public_claim_allowed") is False
        checks["receipt_complete_false"] = claim.get("receipt_complete") is False

    passed_count = sum(1 for value in checks.values() if value)
    total_count = len(checks)
    return {
        "passed": passed_count == total_count,
        "passed_count": passed_count,
        "total_count": total_count,
        "score": round(passed_count / total_count, 4),
        "checks": checks,
        "details": details,
        "envelope": envelope,
    }


def _binary_for(spec: ModelSpec) -> str:
    names = {
        "codex_cli": "codex",
        "agy_cli": "agy",
        "grok_cli": "grok",
        "gemini_cli": "gemini",
        "opencode_cli": "opencode",
        "mimo_cli": "mimo",
    }
    name = names.get(spec.transport, "")
    if not name:
        return ""
    binary = shutil.which(name)
    if binary:
        return binary
    fallbacks = {
        "codex": "~/.npm-global/bin/codex",
        "agy": "~/.local/bin/agy",
        "grok": "~/.grok/bin/grok",
        "gemini": "~/.npm-global/bin/gemini",
        "opencode": "~/.opencode/bin/opencode",
        "mimo": "~/.mimocode/bin/mimo",
    }
    fallback = Path(fallbacks[name]).expanduser()
    return str(fallback) if fallback.is_file() else ""


def _subprocess_command(spec: ModelSpec, prompt: str, isolated_dir: Path) -> list[str]:
    binary = _binary_for(spec)
    if not binary:
        return []
    timeout_label = f"{max(1, int(spec.timeout_sec - 10))}s"
    if spec.transport == "codex_cli":
        return [
            binary,
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--color",
            "never",
            "--json",
            "-C",
            str(isolated_dir),
            "-m",
            spec.model,
            prompt,
        ]
    if spec.transport == "agy_cli":
        return [
            binary,
            "--new-project",
            "--add-dir",
            str(isolated_dir),
            "--mode",
            "plan",
            "--print-timeout",
            timeout_label,
            "--print",
            prompt,
        ]
    if spec.transport == "grok_cli":
        return [
            binary,
            "--cwd",
            str(isolated_dir),
            "--permission-mode",
            "plan",
            "--disable-web-search",
            "--no-memory",
            "--no-subagents",
            "--max-turns",
            "1",
            "--output-format",
            "json",
            "-m",
            spec.model,
            "-p",
            prompt,
        ]
    if spec.transport == "gemini_cli":
        return [
            binary,
            "-m",
            spec.model,
            "-p",
            prompt,
            "--approval-mode",
            "plan",
            "--sandbox",
            "-o",
            "json",
        ]
    if spec.transport == "opencode_cli":
        return [
            binary,
            "run",
            "--format",
            "json",
            "--thinking=false",
            "--dir",
            str(isolated_dir),
            "-m",
            spec.model,
            prompt,
        ]
    if spec.transport == "mimo_cli":
        return [
            binary,
            "run",
            "--pure",
            "--format",
            "json",
            "--thinking=false",
            "--dir",
            str(isolated_dir),
            "-m",
            spec.model,
            prompt,
        ]
    return []


def _extract_usage_from_json(value: Any) -> dict[str, Any]:
    best: dict[str, Any] = {}
    if isinstance(value, Mapping):
        tokens = value.get("tokens") if isinstance(value.get("tokens"), Mapping) else None
        usage = value.get("usage") if isinstance(value.get("usage"), Mapping) else None
        candidate = tokens or usage
        if isinstance(candidate, Mapping):
            normalized = {
                "input_tokens": int(candidate.get("input") or candidate.get("input_tokens") or 0),
                "output_tokens": int(candidate.get("output") or candidate.get("output_tokens") or 0),
                "reasoning_tokens": int(candidate.get("reasoning") or candidate.get("reasoning_tokens") or 0),
                "total_tokens": int(candidate.get("total") or candidate.get("total_tokens") or 0),
            }
            if sum(normalized.values()) >= sum(int(v or 0) for v in best.values() if isinstance(v, int)):
                best = normalized
        for item in value.values():
            child = _extract_usage_from_json(item)
            if int(child.get("total_tokens") or 0) >= int(best.get("total_tokens") or 0):
                best = child
    elif isinstance(value, list):
        for item in value:
            child = _extract_usage_from_json(item)
            if int(child.get("total_tokens") or 0) >= int(best.get("total_tokens") or 0):
                best = child
    return best


def _usage_from_stdout(stdout: str) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    for line in str(stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        child = _extract_usage_from_json(obj)
        if int(child.get("total_tokens") or 0) >= int(usage.get("total_tokens") or 0):
            usage = child
    return usage


def invoke_subprocess(spec: ModelSpec, prompt: str, isolated_dir: Path) -> Invocation:
    command = _subprocess_command(spec, prompt, isolated_dir)
    if not command:
        return Invocation(
            provider=spec.provider,
            model=spec.model,
            text="",
            raw_stdout="",
            raw_stderr="",
            returncode=None,
            wall_sec=0.0,
            usage={},
            error="provider_binary_not_found",
            provider_call_confirmed=False,
        )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(isolated_dir),
            capture_output=True,
            text=True,
            timeout=spec.timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return Invocation(
            provider=spec.provider,
            model=spec.model,
            text="",
            raw_stdout=str(exc.stdout or ""),
            raw_stderr=str(exc.stderr or ""),
            returncode=None,
            wall_sec=round(time.monotonic() - started, 3),
            usage={},
            error="provider_timeout",
            provider_call_confirmed=True,
        )
    except OSError as exc:
        return Invocation(
            provider=spec.provider,
            model=spec.model,
            text="",
            raw_stdout="",
            raw_stderr=str(exc),
            returncode=None,
            wall_sec=round(time.monotonic() - started, 3),
            usage={},
            error="provider_process_error",
            provider_call_confirmed=False,
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    envelope, _ = extract_envelope(stdout)
    model_text = json.dumps(envelope, ensure_ascii=False) if envelope else stdout
    error = "" if completed.returncode == 0 and bool(stdout.strip()) else "provider_subprocess_failed"
    if not envelope:
        combined = f"{stdout}\n{stderr}".lower()
        if any(marker in combined for marker in ("insufficient account balance", "payment required", "402")):
            error = "provider_balance_blocked"
        elif any(marker in combined for marker in ("requires a newer version", "please upgrade to the latest app or cli")):
            error = "provider_client_upgrade_required"
        elif any(marker in combined for marker in ("unsupported_client", "client is no longer supported")):
            error = "provider_client_unsupported"
        elif any(marker in combined for marker in ("unsupported model", "model not found", "unknown model")):
            error = "provider_model_unavailable"
        elif any(marker in combined for marker in ("not logged in", "login required", "unauthorized", "401")):
            error = "provider_auth_blocked"
        elif completed.returncode == 0:
            error = "benchmark_envelope_not_found"
    return Invocation(
        provider=spec.provider,
        model=spec.model,
        text=model_text,
        raw_stdout=stdout,
        raw_stderr=stderr,
        returncode=completed.returncode,
        wall_sec=round(time.monotonic() - started, 3),
        usage=_usage_from_stdout(stdout),
        error=error,
        provider_call_confirmed=True,
    )


def invoke_ollama(spec: ModelSpec, prompt: str) -> Invocation:
    provider = OllamaLocalModelProvider()
    effective_prompt = prompt
    if spec.thinking_control == "prompt_no_think":
        effective_prompt = prompt.rstrip() + "\n\n/no_think"
    started = time.monotonic()
    with temporary_environ(
        {
            "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
            "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
            "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        }
    ):
        response = provider.generate(
            LocalModelProviderRequest(
                task_id=f"u3a-{spec.model_id}-{hashlib.sha256(effective_prompt.encode()).hexdigest()[:8]}",
                prompt=effective_prompt,
                evidence_refs=("benchmark:u3a:bounded",),
                model_name=spec.model,
                timeout_sec=spec.timeout_sec,
                max_output_chars=16000,
                options={
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict": 1200,
                },
                think=False,
                phase="benchmark",
                attempt_id="u3a-v1",
                execution_profile="benchmark",
            )
        )
    usage = {
        "input_tokens": response.ollama_prompt_eval_count,
        "output_tokens": response.ollama_eval_count,
        "total_tokens": response.ollama_prompt_eval_count + response.ollama_eval_count,
        "load_duration_ns": response.ollama_load_duration,
        "total_duration_ns": response.ollama_total_duration,
    }
    envelope, _ = extract_envelope(response.output_text)
    model_text = json.dumps(envelope, ensure_ascii=False) if envelope else response.output_text
    error = response.error
    if not error and not envelope:
        error = "benchmark_envelope_not_found"
    return Invocation(
        provider=spec.provider,
        model=spec.model,
        text=model_text,
        raw_stdout=response.output_text,
        raw_stderr="",
        returncode=0 if response.model_called and not response.error else None,
        wall_sec=round(time.monotonic() - started, 3),
        usage=usage,
        error=error,
        provider_call_confirmed=bool(response.provider_invoked and response.model_called),
    )


def invoke_model(spec: ModelSpec, prompt: str, isolated_dir: Path) -> Invocation:
    if spec.transport == "ollama_http":
        return invoke_ollama(spec, prompt)
    return invoke_subprocess(spec, prompt, isolated_dir)


def _arm_prompt(arm: str) -> str:
    if arm == "bare":
        return BASE_TASK
    if arm == "nexus_bounded":
        return BASE_TASK + "\n\n" + BOUNDED_CONTEXT
    raise ValueError(f"unsupported_direct_arm:{arm}")


def _invocation_payload(invocation: Invocation, verification: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider": invocation.provider,
        "model": invocation.model,
        "provider_call_confirmed": invocation.provider_call_confirmed,
        "output_delivered": invocation.delivered,
        "error": invocation.error,
        "returncode": invocation.returncode,
        "wall_sec": invocation.wall_sec,
        "usage": invocation.usage,
        "verification": dict(verification),
        "stdout_sha256": hashlib.sha256(invocation.raw_stdout.encode()).hexdigest(),
        "stderr_tail": invocation.raw_stderr[-800:],
        "raw_preview": invocation.raw_stdout[:800],
    }


def run_direct_arm(spec: ModelSpec, arm: str, isolated_dir: Path) -> dict[str, Any]:
    invocation = invoke_model(spec, _arm_prompt(arm), isolated_dir)
    verification = verify_envelope(invocation.text)
    return {
        "arm": arm,
        **_invocation_payload(invocation, verification),
        "receipt_complete": False,
        "capability_closure_complete": False,
        "public_claim_allowed": False,
    }


def _extract_runtime_text(context: Mapping[str, Any]) -> str:
    online = context.get("online") if isinstance(context.get("online"), Mapping) else {}
    online_response = online.get("response") if isinstance(online.get("response"), Mapping) else {}
    for key in ("response", "raw_response", "output_text", "response_text"):
        value = online_response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    local = context.get("local") if isinstance(context.get("local"), Mapping) else {}
    local_response = local.get("response") if isinstance(local.get("response"), Mapping) else {}
    for key in ("response_text", "output_text", "response", "raw_response"):
        value = local_response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _full_verifier(context: Mapping[str, Any]) -> dict[str, Any]:
    verification = verify_envelope(_extract_runtime_text(context))
    return {
        "task_id": context["task_id"],
        "invoked": True,
        "gate_passed": bool(verification["passed"]),
        "outcome_contributed": bool(verification["passed"]),
        "evidence_refs": [f"verifier:{context['task_id']}:u3a-composite"],
        "verification": verification,
    }


def _full_learning(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": context["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"learning:{context['task_id']}:benchmark-observed"],
    }


def run_full_online(spec: ModelSpec, isolated_dir: Path) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def invoker(context: Mapping[str, Any]) -> dict[str, Any]:
        prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
        capability = context.get("capability_evidence_bundle")
        bounded = {
            "planner_decision_id": context.get("planner_decision_id"),
            "baseline_hash": context.get("baseline_hash"),
            "selected_capabilities": (
                context.get("planner", {}).get("selected_capabilities", [])
                if isinstance(context.get("planner"), Mapping)
                else []
            ),
            "codeintel": context.get("codeintel", {}),
            "evidence_summary": (
                capability.get("summary", {}) if isinstance(capability, Mapping) else {}
            ),
        }
        full_prompt = (
            prompt
            + "\n\n[NEXUS_FULL_CONTEXT]\n"
            + json.dumps(bounded, ensure_ascii=False, sort_keys=True, default=str)
            + "\n\n"
            + BOUNDED_CONTEXT
        )
        captured["prompt_chars"] = len(full_prompt)
        invocation = invoke_model(spec, full_prompt, isolated_dir)
        captured["invocation"] = invocation
        return normalize_online_invoker_payload(
            provider=spec.provider,
            task_id=str(context.get("task_id") or ""),
            invoked=invocation.provider_call_confirmed,
            output_delivered=invocation.delivered,
            gate_passed=invocation.delivered,
            provider_call_count=1 if invocation.provider_call_confirmed else 0,
            response=invocation.text,
            raw_response=invocation.raw_stdout,
            usage=invocation.usage,
            error=invocation.error,
            evidence_refs=[f"online:{spec.provider}:{context.get('task_id')}:u3a"],
            transport="benchmark_direct_cli",
            selection_source="injected_transport",
            extra={"model": spec.model, "wall_sec": invocation.wall_sec},
        )

    task_id = f"u3a-{spec.model_id}-full"
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="u3a-v1",
        task_statement=BASE_TASK,
        task_type="repair",
        route={
            "recommended_flow": "direct",
            "provider": spec.provider,
            "online_policy": "auto",
            "injected_transport": True,
            "workspace_root": str(isolated_dir),
            "difficulty": "medium",
        },
        online_enabled=True,
        local_enabled=False,
        online_prompt=BASE_TASK,
        online_model_name=spec.model,
        codeintel={
            "target_symbol": "provider_call_count",
            "diagnosis": "preserve already-started call count when retry spawn raises OSError",
            "implementation_target": "normalize_status",
        },
        pillars={"evidence_required": True, "claim_fail_closed": True},
        evidence_refs=(
            "u3a:first-process-started",
            "u3a:retry-process-not-started",
            "u3a:focused-tests-only",
        ),
    )
    started = time.monotonic()
    receipt = UnifiedRuntime().run(
        request,
        online_invoker=invoker,
        verifier=_full_verifier,
        learning=_full_learning,
    )
    wall_sec = round(time.monotonic() - started, 3)
    invocation = captured.get("invocation")
    if not isinstance(invocation, Invocation):
        invocation = Invocation(
            provider=spec.provider,
            model=spec.model,
            text="",
            raw_stdout="",
            raw_stderr="",
            returncode=None,
            wall_sec=wall_sec,
            usage={},
            error="full_invocation_missing",
            provider_call_confirmed=False,
        )
    verification = (
        receipt.get("verifier", {}).get("response", {}).get("verification", {})
        if isinstance(receipt.get("verifier"), Mapping)
        else {}
    )
    return {
        "arm": "nexus_full",
        **_invocation_payload(invocation, verification),
        "wall_sec": wall_sec,
        "prompt_chars": captured.get("prompt_chars", 0),
        "online_status": receipt.get("online", {}).get("status"),
        "verifier_status": receipt.get("verifier", {}).get("status"),
        "learning_status": receipt.get("learning", {}).get("status"),
        "receipt_complete": bool(receipt.get("receipt_complete")),
        "capability_closure_complete": bool(receipt.get("capability_closure_complete")),
        "public_claim_allowed": bool(receipt.get("public_claim_allowed")),
        "selected_capabilities": list(receipt.get("selected_capabilities") or []),
        "planner_decision_id": str(receipt.get("planner_decision_id") or ""),
        "terminal_status": str(receipt.get("terminal_status") or ""),
    }


class _BenchmarkLocalService:
    def __init__(self, spec: ModelSpec, isolated_dir: Path) -> None:
        self.spec = spec
        self.isolated_dir = isolated_dir
        self.last_invocation: Invocation | None = None
        self.prompt_chars = 0

    def handle(self, request: Any) -> dict[str, Any]:
        payload = dict(request) if isinstance(request, Mapping) else vars(request)
        snapshot = payload.get("planner_snapshot") if isinstance(payload.get("planner_snapshot"), Mapping) else {}
        full_context = {
            "route_truth_source": snapshot.get("route_truth_source"),
            "execution_topology": snapshot.get("execution_topology"),
            "executor_provider": snapshot.get("executor_provider"),
            "executor_model": snapshot.get("executor_model"),
            "selected_capabilities": snapshot.get("selected_capabilities", []),
            "planner_decision_id": snapshot.get("planner_decision_id"),
            "capability_evidence_bundle": snapshot.get("capability_evidence_bundle", {}),
        }
        prompt = (
            BASE_TASK
            + "\n\n[NEXUS_FULL_CONTEXT]\n"
            + json.dumps(full_context, ensure_ascii=False, sort_keys=True, default=str)
            + "\n\n"
            + BOUNDED_CONTEXT
        )
        self.prompt_chars = len(prompt)
        invocation = invoke_model(self.spec, prompt, self.isolated_dir)
        self.last_invocation = invocation
        candidate_hash = hashlib.sha256(invocation.text.encode()).hexdigest()
        return {
            "task_id": str(payload.get("task_id") or ""),
            "invoked": invocation.provider_call_confirmed,
            "local_model_invoked": invocation.provider_call_confirmed,
            "output_delivered": invocation.delivered,
            "action": "candidate",
            "provider": self.spec.provider,
            "model_name": self.spec.model,
            "response_text": invocation.text,
            "raw_response": invocation.raw_stdout,
            "error": invocation.error,
            "evidence_refs": [f"local:{payload.get('task_id')}:u3a"],
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash": candidate_hash,
                "selected_candidate_hash_matches_applied": False,
                "model_candidate_hash": candidate_hash,
            },
            "verifier_summary": {
                "verifier_reached": False,
                "verifier_status": "not_run",
                "exit_code": None,
            },
            "local_outputs": {
                "concise_summary": "u3a composite candidate generated; external verifier required"
            },
            "outcome_contributed": False,
        }


def run_full_local(spec: ModelSpec, isolated_dir: Path) -> dict[str, Any]:
    task_id = f"u3a-{spec.model_id}-full"
    local_service = _BenchmarkLocalService(spec, isolated_dir)
    local_request = {
        "task_id": task_id,
        "action": "candidate",
        "target_file": "benchmark_fixture.py",
        "benchmark_prompt": BASE_TASK,
        "planner_snapshot": {
            "route_truth_source": "CapabilityPlanner",
            "executor_provider": "ollama",
            "executor_model": spec.model,
            "model_call_allowed": True,
            "execution_topology": "single_local_model",
            "protocol_mode": "anchored_edit",
        },
    }
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="u3a-v1",
        task_statement=BASE_TASK,
        task_type="repair",
        route={
            "recommended_flow": "local",
            "local_enabled": True,
            "workspace_root": str(isolated_dir),
            "difficulty": "medium",
        },
        online_enabled=False,
        local_enabled=True,
        local_request=local_request,
        codeintel={
            "target_symbol": "provider_call_count",
            "diagnosis": "preserve already-started call count when retry spawn raises OSError",
            "implementation_target": "normalize_status",
        },
        pillars={"evidence_required": True, "claim_fail_closed": True},
        evidence_refs=(
            "u3a:first-process-started",
            "u3a:retry-process-not-started",
            "u3a:focused-tests-only",
        ),
    )
    started = time.monotonic()
    receipt = UnifiedRuntime(local_service=local_service).run(
        request,
        verifier=_full_verifier,
        learning=_full_learning,
    )
    wall_sec = round(time.monotonic() - started, 3)
    invocation = local_service.last_invocation or Invocation(
        provider=spec.provider,
        model=spec.model,
        text="",
        raw_stdout="",
        raw_stderr="",
        returncode=None,
        wall_sec=wall_sec,
        usage={},
        error="full_invocation_missing",
        provider_call_confirmed=False,
    )
    verification = (
        receipt.get("verifier", {}).get("response", {}).get("verification", {})
        if isinstance(receipt.get("verifier"), Mapping)
        else {}
    )
    return {
        "arm": "nexus_full",
        **_invocation_payload(invocation, verification),
        "wall_sec": wall_sec,
        "prompt_chars": local_service.prompt_chars,
        "local_status": receipt.get("local", {}).get("status"),
        "verifier_status": receipt.get("verifier", {}).get("status"),
        "learning_status": receipt.get("learning", {}).get("status"),
        "receipt_complete": bool(receipt.get("receipt_complete")),
        "capability_closure_complete": bool(receipt.get("capability_closure_complete")),
        "public_claim_allowed": bool(receipt.get("public_claim_allowed")),
        "selected_capabilities": list(receipt.get("selected_capabilities") or []),
        "planner_decision_id": str(receipt.get("planner_decision_id") or ""),
        "terminal_status": str(receipt.get("terminal_status") or ""),
    }


def run_full_arm(spec: ModelSpec, isolated_dir: Path) -> dict[str, Any]:
    if spec.transport == "ollama_http":
        return run_full_local(spec, isolated_dir)
    return run_full_online(spec, isolated_dir)


def role_recommendation(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    bare = arms.get("bare", {})
    bounded = arms.get("nexus_bounded", {})
    full = arms.get("nexus_full", {})
    arm_rows = [bare, bounded, full]
    infra_valid = [
        bool(row.get("provider_call_confirmed"))
        and str(row.get("error") or "") not in {
            "provider_binary_not_found",
            "provider_auth_blocked",
            "provider_balance_blocked",
            "provider_model_unavailable",
            "provider_timeout",
            "provider_process_error",
            "provider_subprocess_failed",
            "provider_client_upgrade_required",
            "provider_client_unsupported",
        }
        for row in arm_rows
    ]
    if not any(infra_valid):
        return {
            "status": "BLOCKED_PROVIDER",
            "role": "NO_ACTIVE_ROLE",
            "autonomy": "L0",
            "confidence": "blocked",
        }
    if not all(infra_valid):
        return {
            "status": "THREE_ARM_INCOMPLETE",
            "role": "EXPERIMENT_ONLY",
            "autonomy": "L0",
            "confidence": "insufficient",
        }

    scores = [float(row.get("verification", {}).get("score") or 0.0) for row in arm_rows]
    bounded_checks = bounded.get("verification", {}).get("checks", {})
    full_checks = full.get("verification", {}).get("checks", {})
    bounded_code = bool(bounded_checks.get("implementation_cases_pass"))
    full_code = bool(full_checks.get("implementation_cases_pass"))
    bounded_claim = all(
        bool(bounded_checks.get(key))
        for key in (
            "claim_not_proven",
            "production_ready_false",
            "public_claim_false",
            "receipt_complete_false",
        )
    )
    full_claim = all(
        bool(full_checks.get(key))
        for key in (
            "claim_not_proven",
            "production_ready_false",
            "public_claim_false",
            "receipt_complete_false",
        )
    )
    bounded_diagnosis = all(
        bool(bounded_checks.get(key))
        for key in (
            "account_current_is_zero",
            "account_correct_is_one",
            "second_process_not_started",
            "defect_explanation_present",
        )
    )
    full_diagnosis = all(
        bool(full_checks.get(key))
        for key in (
            "account_current_is_zero",
            "account_correct_is_one",
            "second_process_not_started",
            "defect_explanation_present",
        )
    )

    if bounded_code and full_code and bounded_claim and full_claim and bounded_diagnosis and full_diagnosis:
        return {
            "status": "PROVISIONAL_PASS",
            "role": "BOUNDED_ENGINEERING_CANDIDATE",
            "autonomy": "L1+",
            "confidence": "provisional_one_run",
            "promotion_requires": ["second_repetition", "role_specific_suite", "physical_patch_verifier"],
        }
    if bounded_code and full_code and bounded_claim and full_claim:
        return {
            "status": "PROVISIONAL_PASS",
            "role": "PATCH_CANDIDATE_GENERATOR",
            "autonomy": "L1",
            "confidence": "provisional_one_run",
            "promotion_requires": ["second_repetition", "diagnostic_suite"],
        }
    if bounded_diagnosis and full_diagnosis and bounded_claim and full_claim:
        return {
            "status": "PROVISIONAL_PASS",
            "role": "BOUNDED_REVIEW_AND_AUDIT",
            "autonomy": "L1",
            "confidence": "provisional_one_run",
            "promotion_requires": ["second_repetition", "counterexample_suite"],
        }
    if bounded_claim and full_claim:
        return {
            "status": "CONDITIONAL",
            "role": "READ_ONLY_SCHEMA_EXECUTOR",
            "autonomy": "L0.5",
            "confidence": "provisional_one_run",
        }
    return {
        "status": "UNQUALIFIED",
        "role": "NO_DEFAULT_ASSIGNMENT",
        "autonomy": "L0",
        "confidence": "provisional_one_run",
        "scores": scores,
    }


def run_model(
    spec: ModelSpec,
    isolated_root: Path,
    *,
    selected_arms: tuple[str, ...] = ("bare", "nexus_bounded", "nexus_full"),
) -> dict[str, Any]:
    isolated_dir = isolated_root / re.sub(r"[^A-Za-z0-9_.-]+", "-", spec.model_id)
    isolated_dir.mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in isolated_dir.iterdir())
    arms: dict[str, dict[str, Any]] = {}
    for arm in selected_arms:
        if arm in {"bare", "nexus_bounded"}:
            arms[arm] = run_direct_arm(spec, arm, isolated_dir)
        elif arm == "nexus_full":
            arms[arm] = run_full_arm(spec, isolated_dir)
        else:
            raise ValueError(f"unsupported_arm:{arm}")
    after = sorted(path.name for path in isolated_dir.iterdir())
    recommendation = (
        role_recommendation(arms)
        if {"bare", "nexus_bounded", "nexus_full"} <= set(arms)
        else {
            "status": "PARTIAL_ARMS",
            "role": "UNSET_PENDING_MERGE",
            "autonomy": "L0",
            "confidence": "incomplete",
        }
    )
    workspace_mutation_observed = before != after
    if workspace_mutation_observed:
        recommendation = {
            "status": "ISOLATION_CONTRACT_VIOLATION",
            "role": "EXPERIMENT_ONLY",
            "autonomy": "L0",
            "confidence": "blocked_by_workspace_mutation",
        }
    return {
        "model_id": spec.model_id,
        "cohort": spec.cohort,
        "provider": spec.provider,
        "transport": spec.transport,
        "model": spec.model,
        "resource_tier": spec.resource_tier,
        "expected_current_blocker": spec.expected_current_blocker,
        "arms": arms,
        "three_arm_complete": {"bare", "nexus_bounded", "nexus_full"} <= set(arms)
        and all(
            bool(arms[name].get("provider_call_confirmed"))
            and bool(arms[name].get("verification"))
            for name in ("bare", "nexus_bounded", "nexus_full")
        ),
        "isolated_directory_entries_before": before,
        "isolated_directory_entries_after": after,
        "workspace_mutation_observed": workspace_mutation_observed,
        "role_recommendation": recommendation,
        "public_claim_allowed": False,
    }


def settle(results: list[dict[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    required = [row for row in results if row.get("cohort") == "required"]
    discovery = [row for row in results if row.get("cohort") == "discovery"]
    complete = [row for row in results if row.get("three_arm_complete")]
    blocked = [
        row
        for row in results
        if row.get("role_recommendation", {}).get("status") == "BLOCKED_PROVIDER"
    ]
    return {
        "schema": SCHEMA,
        "generated_at_epoch": int(time.time()),
        "config_schema": config.get("schema"),
        "task_id": config.get("composite_task", {}).get("task_id"),
        "result_count": len(results),
        "required_count": len(required),
        "discovery_count": len(discovery),
        "three_arm_complete_count": len(complete),
        "blocked_provider_count": len(blocked),
        "all_required_three_arm_complete": bool(required) and all(
            row.get("three_arm_complete") for row in required
        ),
        "role_definitions_final": False,
        "role_definition_status": "PROVISIONAL_UNTIL_PROMOTION_REPETITION_AND_ROLE_SUITE",
        "public_claim_allowed": False,
        "results": results,
    }


def select_specs(
    specs: list[ModelSpec],
    *,
    cohort: str,
    model_ids: set[str],
) -> list[ModelSpec]:
    selected = []
    for spec in specs:
        if cohort != "all" and spec.cohort != cohort:
            continue
        if model_ids and spec.model_id not in model_ids:
            continue
        selected.append(spec)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--cohort", choices=("required", "discovery", "all"), default="required")
    parser.add_argument("--model-id", action="append", default=[])
    parser.add_argument(
        "--arm",
        action="append",
        choices=("bare", "nexus_bounded", "nexus_full"),
        default=[],
        help="Run only selected arm(s); repeat the option for multiple arms.",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--isolated-root", type=Path, default=ISOLATED_ROOT)
    args = parser.parse_args(argv)

    config, specs = load_specs(args.config)
    selected = select_specs(specs, cohort=args.cohort, model_ids=set(args.model_id))
    if not selected:
        raise SystemExit("no_models_selected")
    args.isolated_root.mkdir(parents=True, exist_ok=True)

    selected_arms = tuple(args.arm) or ("bare", "nexus_bounded", "nexus_full")
    results: list[dict[str, Any]] = []
    for spec in selected:
        print(
            f"[u3a] model={spec.model_id} provider={spec.provider} "
            f"transport={spec.transport} arms={','.join(selected_arms)}",
            file=sys.stderr,
        )
        results.append(run_model(spec, args.isolated_root, selected_arms=selected_arms))
    payload = settle(results, config)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
