#!/usr/bin/env python3
"""Issue #29 governed-path canary: same-task Online consumption of Local/World C evidence.

This harness drives exactly one task through the canonical product path and
then independently re-verifies the evidence chain the runtime wrote.  It owns
no route, admission, provider, verifier, or contribution authority:

1. Task Card authority: the tracked card is read back from Git (``HEAD`` blob
   bytes must equal the working bytes, ``task_id`` must match, ``AUTO_CHAIN``
   must be false) and becomes a ``VerifiedTaskCardIdentity``.  That identity is
   the only way the ``task_card`` Workforce control is supplied.
2. ``execute_canonical_product_task`` is the single execution entry:
   CapabilityPlanner (sole route authority) -> Workforce Admission for the
   Local and Online demands -> ``BattlesuitGateway.ask_unified`` ->
   ``run_mainchain`` -> ``UnifiedRuntime`` (Local World C, VAP, admitted Agy
   Online call with the VAP inline, World C verifier, learning) -> RootReceipt.
3. ``evaluate_runtime_evidence`` re-derives every claim from the durable
   runtime receipt.  It never writes a verifier verdict or a contribution
   value; it only reports whether the runtime-recorded values are consistent
   and physically bound.

Modes:

* default (dry): Task Card readback, Workforce policy route check, optional
  read-only host preflight (``--host-preflight``).  No model is called.
* ``--physical``: mandatory host preflight (Owner decision 5, 2026-10-13),
  abort on any failure, then one real run.  Requires ``--confirm-task-id``
  equal to the card's task_id so a physical call can never be implicit.

The replaced PR #1408 script (``canary_issue29_physical_local_online.py``) is
not closure evidence (Owner decision 4): it bypassed Planner/Workforce/runtime.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA = "nexus.issue29.governed_canary_receipt.v1"
ISSUE_NUMBER = 29
DURABLE_MARKER = "ONLINE_LOCAL_SAME_TASK_CAUSAL_CONSUMPTION_VERIFIED"
TASK_ID = "github-issue-29-governed-canary-20261013-r1"
TASK_CARD_PATH = "tasks/github-issue-29-governed-canary-20261013/00-governed-local-online-canary.md"

EXPECTED_LOCAL = {
    "worker_id": "local_coder_7b",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b-instruct",
}
EXPECTED_ONLINE = {
    "worker_id": "agy_flash_38",
    "provider": "agy",
    "model": "gemini-3.8-flash-medium",
}
EXPECTED_AGY_PERMISSION_MODE = "plan_no_autoapprove"
WORLD_C_VERIFIER_SOURCE = "HealOrchestrator.VerificationPhase"

MIN_UNUSED_MEMORY_BYTES = 6 * 1024**3
# kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical.
MEMORY_PRESSURE_NORMAL = 1
OLLAMA_SERVICE_LABEL = "com.james.local-models-ollama"
OLLAMA_SERVICE_PS_URL = "http://127.0.0.1:11435/api/ps"
OLLAMA_GATEWAY_TAGS_URL = "http://127.0.0.1:11434/api/tags"
SPLASH_MODELS_URL = "http://127.0.0.1:8000/v1/models"
DEFAULT_STATE_ROOT = Path.home() / ".local" / "state" / "nexus-issue29-governed-canary"

TASK_STATEMENT = (
    "Repair add_one in calc.py so that add_one(x) returns x + 1. "
    "Answer only from the inline evidence in this prompt; do not use tools "
    "and do not read or write files."
)
FIXTURE_FILES = {
    "calc.py": "def add_one(x):\n    return x\n",
}
TARGET_FILE = "calc.py"
VERIFIER_COMMAND = (
    "python3",
    "-c",
    "import py_compile; py_compile.compile('calc.py', doraise=True); "
    "import calc; assert calc.add_one(1) == 2; assert calc.add_one(-1) == 0",
)

TRANSPORT_OVERRIDE_ENV = (
    "NEXUS_OLLAMA_URL",
    "NEXUS_AGY_BIN",
    "NEXUS_AGY_EXECUTABLE",
    "NEXUS_AGY_COMMAND",
)

STATUS_PASS = "PASS"
STATUS_FAILED = "FAILED"
STATUS_BLOCKED = "BLOCKED"
STATUS_ABORTED = "ABORTED_PREFLIGHT"
STATUS_DRY = "DRY_PREFLIGHT_ONLY"


class CanaryBlocked(RuntimeError):
    """A pre-execution gate refused the run; no model was called."""


@dataclass
class Check:
    name: str
    ok: bool
    detail: Any = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": bool(self.ok), "detail": self.detail}


@dataclass
class HostProbes:
    """Read-only host observations; injected in tests, real only in physical runs."""

    http_get: Callable[[str], tuple[int, str]]
    unused_memory_bytes: Callable[[], int]
    agy_path: Callable[[], str]
    # Defaults to "unknown" so a caller that omits the probe fails closed.
    memory_pressure_level: Callable[[], int] = lambda: 0


@dataclass
class Evaluation:
    checks: list[Check] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: Any = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [check.name for check in self.checks if not check.ok]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _git(repo_root: Path, *args: str, binary: bool = False) -> Any:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=not binary,
        check=False,
    )
    if result.returncode != 0:
        raise CanaryBlocked(f"git_failed:{' '.join(args)}")
    return result.stdout if binary else result.stdout.strip()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Task Card authority
# --------------------------------------------------------------------------


def verify_task_card(
    repo_root: Path = REPO_ROOT,
    card_path: str = TASK_CARD_PATH,
    task_id: str = TASK_ID,
) -> tuple[Any, dict[str, Any]]:
    """Read the tracked card back from Git and mint a VerifiedTaskCardIdentity."""
    from nexus.engine.canonical_task_seam import VerifiedTaskCardIdentity

    repo_root = Path(repo_root).resolve()
    absolute = (repo_root / card_path).resolve()
    try:
        absolute.relative_to(repo_root)
    except ValueError as exc:
        raise CanaryBlocked("task_card_path_outside_repository") from exc
    if not absolute.is_file() or absolute.is_symlink():
        raise CanaryBlocked("task_card_missing")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", card_path],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise CanaryBlocked("task_card_not_git_tracked")
    head_bytes = _git(repo_root, "show", f"HEAD:{card_path}", binary=True)
    working_bytes = absolute.read_bytes()
    if head_bytes != working_bytes:
        raise CanaryBlocked("task_card_working_copy_differs_from_head")
    text = working_bytes.decode("utf-8")
    if f"task_id: `{task_id}`" not in text:
        raise CanaryBlocked("task_card_task_id_mismatch")
    if "AUTO_CHAIN: true" in text or "AUTO_CHAIN=true" in text:
        raise CanaryBlocked("task_card_auto_chain_not_false")
    digest = _sha256_bytes(working_bytes)
    identity = VerifiedTaskCardIdentity(
        task_id=task_id,
        task_card_path=card_path,
        canonical_task_card_path=str(absolute),
        task_card_hash=digest,
    )
    return identity, {
        "path": card_path,
        "sha256": digest,
        "git_blob": _git(repo_root, "rev-parse", f"HEAD:{card_path}"),
        "head": _git(repo_root, "rev-parse", "HEAD"),
    }


def source_identity(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    status = _git(repo_root, "status", "--porcelain=v1")
    pin = ""
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if "nexus-runtime @" in line:
                pin = line.strip().strip(",").strip('"')
                break
    return {
        "head": _git(repo_root, "rev-parse", "HEAD"),
        "tree": _git(repo_root, "rev-parse", "HEAD^{tree}"),
        "dirty": bool(status),
        "nexus_runtime_pin": pin,
        "python": sys.executable,
    }


def workforce_route_preflight() -> dict[str, Any]:
    """Read the tracked Workforce policy; no admission decision is made here."""
    from nexus.services.model_workforce_policy import (
        WorkforcePolicyLoader,  # pyright: ignore[reportAttributeAccessIssue]
    )

    snapshot = WorkforcePolicyLoader().load()
    online_route = snapshot.routing.get("online") or {}
    local_route = snapshot.routing.get("local_first") or {}
    online_worker = snapshot.workers.get(str(online_route.get("fast_bounded_implementation")))
    local_worker = snapshot.workers.get(str(local_route.get("bounded_code_candidate")))

    def describe(worker: Any) -> dict[str, Any]:
        if worker is None:
            return {}
        return {
            "worker_id": worker.worker_id,
            "provider": worker.provider,
            "model": worker.model,
            "availability": getattr(worker, "availability", ""),
            "requires": list(getattr(worker, "requires", ()) or ()),
        }

    return {
        "online_fast_bounded_implementation": describe(online_worker),
        "online_fallback": online_route.get("fast_bounded_implementation_fallback"),
        "local_bounded_code_candidate": describe(local_worker),
    }


# --------------------------------------------------------------------------
# Host preflight (Owner decision 5)
# --------------------------------------------------------------------------


def _real_http_get(url: str) -> tuple[int, str]:
    try:
        if not url.startswith("http://127.0.0.1:"):
            return 0, "refused_non_loopback_url"
        with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
            return int(response.status), response.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), ""
    except (urllib.error.URLError, OSError) as exc:
        return 0, f"unreachable:{exc}"


def _real_unused_memory_bytes() -> int:
    """Free + speculative + inactive + purgeable pages from vm_stat.

    Splash keeps ~41 GiB wired on M5, so free + speculative alone stays near
    zero even when the kernel can hand out inactive/purgeable pages without
    swapping. Compressed pages are not counted. The separate pressure check
    keeps this from admitting a run while the host is already under strain.
    """
    result = subprocess.run(["vm_stat"], capture_output=True, text=True, check=False)
    page_size = 16384
    free_pages = 0
    for line in result.stdout.splitlines():
        if "page size of" in line:
            page_size = int(line.split("page size of", 1)[1].split()[0])
        elif line.startswith((
            "Pages free:",
            "Pages speculative:",
            "Pages inactive:",
            "Pages purgeable:",
        )):
            free_pages += int(line.split(":", 1)[1].strip().rstrip("."))
    return free_pages * page_size


def _real_memory_pressure_level() -> int:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True,
            text=True,
            check=False,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError):
        return 0


def real_host_probes() -> HostProbes:
    return HostProbes(
        http_get=_real_http_get,
        unused_memory_bytes=_real_unused_memory_bytes,
        memory_pressure_level=_real_memory_pressure_level,
        agy_path=lambda: shutil.which(os.environ.get("NEXUS_AGY_BIN") or "agy") or "",
    )


def host_preflight(
    probes: HostProbes,
    *,
    min_unused_bytes: int = MIN_UNUSED_MEMORY_BYTES,
    target_local_model: str = EXPECTED_LOCAL["model"],
) -> dict[str, Any]:
    """Read-only checks; ``ok`` is False when the run must abort."""
    evaluation = Evaluation()
    # Service state is observed through its own loopback port only; this
    # harness never calls the service manager (no launchctl, no changes).
    status, body = probes.http_get(OLLAMA_SERVICE_PS_URL)
    evaluation.add(
        "ollama_service_answers",
        status == 200,
        {"label": OLLAMA_SERVICE_LABEL, "url": OLLAMA_SERVICE_PS_URL, "status": status},
    )
    loaded: list[str] = []
    ps_ok = False
    if status == 200:
        try:
            payload = json.loads(body or "{}")
            loaded = [
                str(item.get("name") or item.get("model") or "")
                for item in payload.get("models") or []
            ]
            ps_ok = all(name == target_local_model for name in loaded)
        except (ValueError, AttributeError):
            ps_ok = False
    evaluation.add(
        "ollama_ps_empty_or_only_target",
        ps_ok,
        {"status": status, "loaded_models": loaded},
    )

    gateway_status, _ = probes.http_get(OLLAMA_GATEWAY_TAGS_URL)
    evaluation.add("ollama_gateway_answers", gateway_status == 200, gateway_status)

    splash_status, _ = probes.http_get(SPLASH_MODELS_URL)
    evaluation.add("splash_8000_answers", 200 <= splash_status < 500, splash_status)

    unused = int(probes.unused_memory_bytes())
    evaluation.add(
        "unused_memory_at_least_threshold",
        unused >= min_unused_bytes,
        {
            "reclaimable_bytes": unused,
            "threshold_bytes": min_unused_bytes,
            "counted_pages": "free+speculative+inactive+purgeable",
        },
    )
    pressure = int(probes.memory_pressure_level())
    evaluation.add(
        "memory_pressure_normal",
        pressure == MEMORY_PRESSURE_NORMAL,
        {"kern.memorystatus_vm_pressure_level": pressure},
    )

    agy_path = probes.agy_path()
    evaluation.add("agy_binary_resolvable", bool(agy_path), agy_path)
    return {
        "ok": not evaluation.failed,
        "failed": evaluation.failed,
        "checks": [check.to_dict() for check in evaluation.checks],
        "service_changes": "none",
    }


# --------------------------------------------------------------------------
# Fixture workspace (keeps the canonical Nexus-new checkout pristine)
# --------------------------------------------------------------------------


def materialize_fixture(workspace: Path) -> dict[str, Any]:
    if workspace.exists():
        raise CanaryBlocked("fixture_workspace_already_exists")
    workspace.mkdir(parents=True)
    for relative, content in FIXTURE_FILES.items():
        (workspace / relative).write_text(content, encoding="utf-8")
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "nexus-issue29-canary",
        "GIT_AUTHOR_EMAIL": "canary@nexus.invalid",
        "GIT_COMMITTER_NAME": "nexus-issue29-canary",
        "GIT_COMMITTER_EMAIL": "canary@nexus.invalid",
    }
    for args in (
        ("init", "-q"),
        ("add", "--", *FIXTURE_FILES),
        ("commit", "-q", "-m", "issue29 fixture"),
    ):
        subprocess.run(
            ["git", *args], cwd=str(workspace), env=git_env, check=True, capture_output=True
        )
    revision = _git(workspace, "rev-parse", "HEAD")
    return {
        "workspace": str(workspace),
        "revision": revision,
        "files": {name: _sha256_text(body) for name, body in FIXTURE_FILES.items()},
    }


@contextlib.contextmanager
def _scoped_environ(updates: Mapping[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_execution_context(task_id: str, workspace_revision: str) -> dict[str, Any]:
    """Only task facts; route/provider/model/worker keys are rejected downstream."""
    return {
        "task_id": task_id,
        "workspace_revision": workspace_revision,
        "local_assist_mode": "advisor",
        "online_policy": "auto",
        "execution_world": "local_armor",
        "target_files": [TARGET_FILE],
        "target_file": TARGET_FILE,
        "verifier_command": list(VERIFIER_COMMAND),
    }


# --------------------------------------------------------------------------
# Independent evidence evaluation
# --------------------------------------------------------------------------


def _admission_record(receipt: Mapping[str, Any], channel: str) -> dict[str, Any]:
    for record in _mapping(receipt.get("workforce_admission")).get("records") or []:
        if _mapping(_mapping(record).get("demand")).get("execution_channel") == channel:
            return _mapping(record)
    return {}


def _world_c_receipt(local_stage: Mapping[str, Any]) -> dict[str, Any]:
    response = _mapping(local_stage.get("response"))
    outputs = _mapping(response.get("local_outputs"))
    return _mapping(outputs.get("world_c_receipt") or response.get("world_c_receipt"))


def evaluate_runtime_evidence(
    receipt: Mapping[str, Any],
    *,
    task_id: str,
    root_receipt_valid: bool,
    root_receipt_blockers: tuple[str, ...] | list[str] = (),
    expected_local: Mapping[str, str] = EXPECTED_LOCAL,
    expected_online: Mapping[str, str] = EXPECTED_ONLINE,
    agy_executable: str = "",
) -> Evaluation:
    """Re-derive the same-task Local -> Online consumption chain from the receipt."""
    from nexus.services.local_heal.world_c_receipt import validate_world_c_receipt
    from nexus.services.verified_assist_contract import (
        validate_vap_runtime_binding,
        validate_verified_assist_packet_integrity,
        verify_consumption_proof,
    )

    ev = Evaluation()
    canonical = _mapping(receipt.get("canonical_execution"))
    attempt = _mapping(receipt.get("execution_attempt"))
    bundle = _mapping(receipt.get("capability_evidence_bundle"))
    source_hash = str(bundle.get("source_hash") or "")

    # 1. Planner authority and task identity.
    ev.add(
        "planner_sole_authority",
        canonical.get("execution_decision_authority") == "CapabilityPlanner"
        and receipt.get("selection_authority") == "CapabilityPlanner",
        canonical.get("execution_decision_authority"),
    )
    ev.add(
        "task_identity",
        receipt.get("task_id") == task_id and canonical.get("task_id") == task_id,
        {"receipt": receipt.get("task_id"), "canonical": canonical.get("task_id")},
    )
    ev.add("execution_attempt_bound", bool(attempt.get("attempt_id")), attempt.get("attempt_id"))

    # 2. Workforce Admission for both channels with exact identities.
    admission = _mapping(receipt.get("workforce_admission"))
    for channel, expected in (("local", expected_local), ("online", expected_online)):
        decision = _mapping(_admission_record(receipt, channel).get("decision"))
        observed = {
            "decision": decision.get("decision"),
            "worker_id": decision.get("resolved_worker_id"),
            "provider": decision.get("resolved_provider"),
            "model": decision.get("resolved_model"),
            "reasons": decision.get("decision_reasons"),
            "missing_controls": decision.get("missing_controls"),
        }
        ev.evidence[f"{channel}_admission"] = observed
        ev.add(
            f"{channel}_admitted_exact_identity",
            decision.get("decision") == "ALLOW"
            and decision.get("resolved_worker_id") == expected["worker_id"]
            and decision.get("resolved_provider") == expected["provider"]
            and decision.get("resolved_model") == expected["model"],
            observed,
        )
    ev.add(
        "workforce_overall_allow",
        admission.get("overall_decision") == "ALLOW",
        admission.get("overall_decision"),
    )

    # 3. Local / World C physical result.
    local = _mapping(receipt.get("local"))
    local_response = _mapping(local.get("response"))
    candidate = _mapping(local_response.get("candidate_summary"))
    world_c = _world_c_receipt(local)
    world_c_ok, world_c_reasons = (
        validate_world_c_receipt(world_c) if world_c else (False, ["world_c_receipt_missing"])
    )
    selected_hash = str(candidate.get("selected_candidate_hash") or "")
    ev.evidence["local"] = {
        "status": local.get("status"),
        "provider": local_response.get("provider"),
        "resolved_models": local_response.get("resolved_models"),
        "provider_call_count": local.get("provider_call_count"),
        "model_call_count": local.get("model_call_count"),
        "selected_candidate_hash": selected_hash,
        "applied_patch_hash": candidate.get("applied_patch_hash"),
        "world_c_receipt_hash": world_c.get("receipt_hash"),
        "world_c_valid": world_c_ok,
        "world_c_reasons": list(world_c_reasons),
    }
    ev.add(
        "local_physical_call",
        local.get("status") == "SUCCEEDED"
        and int(local.get("model_call_count") or 0) >= 1
        and local_response.get("provider") == expected_local["provider"]
        and expected_local["model"] in list(local_response.get("resolved_models") or []),
        ev.evidence["local"],
    )
    ev.add(
        "local_response_same_task",
        local_response.get("task_id") == task_id,
        local_response.get("task_id"),
    )
    ev.add(
        "local_candidate_isolated_hash_matched",
        bool(selected_hash)
        and candidate.get("isolation_status") == "isolated"
        and candidate.get("selected_candidate_hash_matches_applied") is True
        and candidate.get("applied_patch_hash") == selected_hash,
        candidate.get("isolation_status"),
    )
    ev.add("world_c_receipt_valid", world_c_ok, list(world_c_reasons))
    ev.add(
        "world_c_same_task_and_source",
        world_c.get("task_id") == task_id
        and world_c.get("source_hash") == source_hash
        and bool(source_hash),
        {
            "world_c_task": world_c.get("task_id"),
            "world_c_source": world_c.get("source_hash"),
            "runtime_source": source_hash,
        },
    )

    # 4. VAP: frozen Local evidence identity, bound to this runtime attempt.
    verified = _mapping(receipt.get("verified_assist"))
    packet = _mapping(verified.get("packet"))
    integrity = (
        validate_verified_assist_packet_integrity(packet)
        if packet
        else {"ok": False, "reason": "packet_missing"}
    )
    binding = (
        validate_vap_runtime_binding(
            packet,
            task_id=task_id,
            canonical_execution=canonical,
            execution_attempt=attempt,
            source_hash=source_hash,
            execution_world=str(canonical.get("execution_world") or ""),
        )
        if packet
        else {"ok": False, "reason": "packet_missing"}
    )
    packet_hash = str(packet.get("packet_hash") or "")
    canonical_fragment = ""
    if integrity.get("ok"):
        canonical_fragment = integrity["canonical_packet"].compact_injection()
    ev.evidence["vap"] = {
        "packet_hash": packet_hash,
        "packet_id": packet.get("packet_id"),
        "integrity": integrity.get("reason"),
        "runtime_binding": binding.get("reason"),
        "local_stage_packet_hash": local.get("verified_assist_packet_hash"),
        "local_stage_expected_hash": local.get("verified_assist_packet_expected_hash"),
        "injection_fragment_sha256": _sha256_text(canonical_fragment) if canonical_fragment else "",
    }
    ev.add("vap_integrity", bool(integrity.get("ok")), integrity.get("reason"))
    ev.add("vap_runtime_binding", bool(binding.get("ok")), binding.get("reason"))
    ev.add(
        "vap_matches_local_stage",
        bool(packet_hash)
        and local.get("verified_assist_packet_hash") == packet_hash
        and local.get("verified_assist_packet_expected_hash") == packet_hash,
        ev.evidence["vap"],
    )
    ev.add(
        "vap_derived_from_selected_local_candidate",
        bool(selected_hash)
        and f"candidate_hash={selected_hash}" in str(packet.get("reproduction_evidence") or ""),
        packet.get("reproduction_evidence"),
    )
    ev.add(
        "vap_fragment_recorded_exactly",
        bool(canonical_fragment) and verified.get("injection_fragment") == canonical_fragment,
        "",
    )

    # 5. Online: admitted Agy, plan+sandbox, VAP bytes inline in the physical input.
    online = _mapping(receipt.get("online"))
    online_response = _mapping(online.get("response"))
    process = _mapping(online_response.get("process_evidence"))
    authority = _mapping(_mapping(online.get("context_trace")).get("gateway_invocation_authority"))
    assembled = str(online_response.get("assembled_online_prompt") or "")
    provider_input_sha = str(process.get("provider_input_sha256") or "")
    ev.evidence["online"] = {
        "status": online.get("status"),
        "provider": online_response.get("provider"),
        "provider_call_count": online_response.get("provider_call_count"),
        "admitted_model": authority.get("resolved_model"),
        "online_model_name": authority.get("online_model_name"),
        "permission_mode": process.get("provider_permission_mode"),
        "working_directory_isolation": process.get("working_directory_isolation"),
        "provider_input_sha256": provider_input_sha,
        "assembled_prompt_sha256": _sha256_text(assembled) if assembled else "",
        "attempt_id": process.get("attempt_id"),
    }
    ev.add(
        "online_physical_call",
        online.get("status") == "SUCCEEDED"
        and online_response.get("provider") == expected_online["provider"]
        and int(online_response.get("provider_call_count") or 0) >= 1
        and process.get("process_started") is True
        and process.get("returncode") == 0,
        ev.evidence["online"],
    )
    ev.add(
        "online_model_bound_to_admission",
        authority.get("gate_passed") is True
        and authority.get("resolved_model") == expected_online["model"]
        and authority.get("online_model_name") == expected_online["model"],
        authority.get("resolved_model"),
    )
    # The runtime receipt stores only hashes of the executed command.  Recompute
    # the fingerprint from the argv the runtime transport builds for Agy
    # (``[bin, --mode, plan, --sandbox, --model, <model>, -p, <assembled prompt>]``)
    # so the Online model is proven from the argv that actually ran.  Fail closed
    # when the executable is unknown or the fingerprint differs.
    expected_argv = [
        agy_executable,
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        expected_online["model"],
        "-p",
        assembled,
    ]
    expected_fingerprint = (
        hashlib.sha256(json.dumps(expected_argv, ensure_ascii=False).encode("utf-8")).hexdigest()
        if agy_executable and assembled
        else ""
    )
    ev.evidence["online"]["expected_command_fingerprint"] = expected_fingerprint
    ev.evidence["online"]["observed_command_fingerprint"] = process.get("command_fingerprint")
    ev.add(
        "online_command_fingerprint_matches_admitted_argv",
        bool(expected_fingerprint) and process.get("command_fingerprint") == expected_fingerprint,
        {
            "expected": expected_fingerprint,
            "observed": process.get("command_fingerprint"),
            "agy_executable_known": bool(agy_executable),
        },
    )
    ev.add(
        "online_agy_plan_sandbox_no_grants",
        process.get("provider_permission_mode") == EXPECTED_AGY_PERMISSION_MODE
        and process.get("working_directory_isolation") == "runtime_ephemeral",
        process.get("provider_permission_mode"),
    )
    ev.add(
        "online_same_attempt",
        process.get("attempt_id") == attempt.get("attempt_id") and online.get("task_id") == task_id,
        process.get("attempt_id"),
    )
    ev.add(
        "online_input_is_assembled_prompt",
        bool(assembled)
        and bool(provider_input_sha)
        and _sha256_text(assembled) == provider_input_sha,
        "",
    )
    ev.add(
        "vap_inline_in_online_input",
        bool(canonical_fragment) and canonical_fragment in assembled,
        "",
    )

    # 6. Consumption proof bound to the physical provider input.
    consumption = _mapping(verified.get("consumption"))
    credit = _mapping(verified.get("credit"))
    proof = (
        verify_consumption_proof(consumption)
        if consumption
        else {"ok": False, "reason": "no_consumption_record"}
    )
    ev.evidence["consumption"] = {
        "status": consumption.get("consumption_status"),
        "proof": consumption.get("consumption_proof"),
        "proof_verification": proof.get("reason"),
        "final_prompt_hash": consumption.get("final_prompt_hash"),
        "assembled_fragment_hash": consumption.get("assembled_fragment_hash"),
        "assist_credited": credit.get("assist_credited"),
        "credit_reason": credit.get("reason"),
    }
    ev.add(
        "consumption_proof_verified",
        consumption.get("consumption_status") == "consumed"
        and bool(proof.get("ok"))
        and consumption.get("packet_hash") == packet_hash,
        proof.get("reason"),
    )
    ev.add(
        "consumption_bound_to_provider_input",
        bool(provider_input_sha) and consumption.get("final_prompt_hash") == provider_input_sha,
        "",
    )
    ev.add(
        "consumption_fragment_is_vap",
        bool(canonical_fragment)
        and consumption.get("assembled_fragment_hash") == _sha256_text(canonical_fragment),
        "",
    )
    ev.add(
        "assist_credit_runtime_minted",
        credit.get("assist_credited") is True
        and credit.get("packet_hash") == packet_hash
        and _mapping(credit.get("proof_verification")).get("ok") is True,
        credit.get("reason"),
    )

    # 7. Verifier authority (World C), bound to this task/attempt/source.
    verifier = _mapping(receipt.get("verifier"))
    verifier_response = _mapping(verifier.get("response"))
    ev.evidence["verifier"] = {
        "status": verifier.get("status"),
        "source": verifier_response.get("source"),
        "verifier_status": verifier_response.get("verifier_status"),
        "world_c_receipt_hash": verifier_response.get("world_c_receipt_hash"),
        "attempt_id": verifier_response.get("attempt_id"),
    }
    ev.add(
        "verifier_world_c_authoritative_pass",
        verifier.get("status") == "SUCCEEDED"
        and verifier_response.get("verifier_status") == "pass"
        and verifier_response.get("source") == WORLD_C_VERIFIER_SOURCE
        and verifier_response.get("world_c_receipt_hash") == world_c.get("receipt_hash"),
        ev.evidence["verifier"],
    )
    ev.add(
        "verifier_bound_to_attempt_and_source",
        verifier_response.get("task_id") == task_id
        and verifier_response.get("attempt_id") == attempt.get("attempt_id")
        and verifier_response.get("source_hash") == source_hash,
        "",
    )

    # 8. Runtime-recorded consumption / contribution (read, never written).
    trace = _mapping(local.get("substitution_trace"))
    claim = _mapping(receipt.get("claim_boundary"))
    online_consumed = trace.get("online_consumed") is True
    contributed = (
        trace.get("final_outcome_contributed") is True and claim.get("outcome_contributed") is True
    )
    ev.evidence["contribution"] = {
        "online_consumed": trace.get("online_consumed"),
        "final_outcome_contributed": trace.get("final_outcome_contributed"),
        "claim_boundary_outcome_contributed": claim.get("outcome_contributed"),
        "public_claim_allowed": claim.get("public_claim_allowed"),
        "causal_basis": (
            "runtime: outcome_contributed = live-minted VAP credit AND World C verifier "
            "bound to task/attempt/source"
        ),
    }
    ev.add("online_consumed_recorded", online_consumed, trace.get("online_consumed"))
    ev.add("final_outcome_contributed_recorded", contributed, ev.evidence["contribution"])
    ev.add(
        "public_claim_not_granted",
        claim.get("public_claim_allowed") is False,
        claim.get("public_claim_allowed"),
    )

    # 9. Learning stage + RootReceipt.
    learning = _mapping(receipt.get("learning"))
    root = _mapping(receipt.get("root_receipt"))
    ev.evidence["root_receipt"] = {
        "valid": bool(root_receipt_valid),
        "blockers": list(root_receipt_blockers),
        "root_receipt_hash": root.get("root_receipt_hash"),
        "world_c_receipt_hash": root.get("world_c_receipt_hash"),
        "verifier_bound_to_world_c": root.get("verifier_bound_to_world_c"),
        "learning_status": learning.get("status"),
        "terminal_status": receipt.get("terminal_status"),
    }
    ev.add(
        "learning_stage_complete",
        learning.get("status") == "SUCCEEDED" and learning.get("gate_passed") is True,
        learning.get("status"),
    )
    ev.add(
        "root_receipt_valid",
        bool(root_receipt_valid)
        and not list(root_receipt_blockers)
        and root.get("world_c_receipt_hash") == world_c.get("receipt_hash"),
        list(root_receipt_blockers),
    )
    ev.add(
        "terminal_succeeded",
        receipt.get("terminal_status") == "SUCCEEDED",
        receipt.get("terminal_status"),
    )
    return ev


def _online_blocked_reason(evaluation: Evaluation) -> str:
    observed = _mapping(evaluation.evidence.get("online_admission"))
    if observed.get("decision") == "ALLOW" and observed.get("model") == EXPECTED_ONLINE["model"]:
        return ""
    return (
        "online_model_not_lawfully_admitted:"
        f"{observed.get('worker_id')}:{observed.get('model')}:{observed.get('decision')}:"
        f"{';'.join(str(r) for r in observed.get('reasons') or [])}"
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def run_canary(
    *,
    physical: bool,
    state_root: Path = DEFAULT_STATE_ROOT,
    run_id: str | None = None,
    repo_root: Path = REPO_ROOT,
    card_path: str = TASK_CARD_PATH,
    task_id: str = TASK_ID,
    confirm_task_id: str = "",
    host_probes: HostProbes | None = None,
    run_host_preflight: bool = False,
    min_unused_bytes: int = MIN_UNUSED_MEMORY_BYTES,
    executor: Callable[..., Any] | None = None,
    extra_context: Mapping[str, Any] | None = None,
    runtime_env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run one governed canary attempt and write its receipt; returns the receipt."""
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(state_root).expanduser() / task_id / run_id
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "issue": ISSUE_NUMBER,
        "task_id": task_id,
        "run_id": run_id,
        "mode": "physical" if physical else "dry",
        "started_at": _now(),
        "expected_local": dict(EXPECTED_LOCAL),
        "expected_online": dict(EXPECTED_ONLINE),
        "fallback_policy": "none_fail_closed",
        "claim_ceiling": (
            "One governed same-task canary receipt. No Candidate approval, merge, "
            "release, model promotion, production or public claim; durable marker "
            "requires independent review of this receipt."
        ),
        "limitations": [
            "Online model identity is bound to the admitted argv (--model) and the "
            "runtime command fingerprint only; the provider-side served model is "
            "not observed (the runtime Agy adapter has no log-level model "
            "attestation).",
            "The runtime receipt does not bind the Task Card hash; only this harness receipt does.",
        ],
        "durable_marker": DURABLE_MARKER,
        "durable_marker_eligible": False,
        "online_consumed": False,
        "final_outcome_contributed": False,
        "independent_review_required": True,
        "checks": [],
        "reasons": [],
    }

    def finish(status: str, reasons: list[str]) -> dict[str, Any]:
        receipt["status"] = status
        receipt["reasons"] = reasons
        receipt["finished_at"] = _now()
        receipt["durable_marker_eligible"] = bool(
            physical and status == STATUS_PASS and not receipt.get("transport_overrides")
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "issue29_governed_canary_receipt.json"
        path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        receipt["receipt_path"] = str(path)
        return receipt

    try:
        receipt["source"] = source_identity(repo_root)
        identity, card = verify_task_card(repo_root, card_path, task_id)
        receipt["task_card"] = card
        route = workforce_route_preflight()
        receipt["workforce_route_preflight"] = route
        online_route = _mapping(route.get("online_fast_bounded_implementation"))
        if (
            online_route.get("worker_id") != EXPECTED_ONLINE["worker_id"]
            or online_route.get("model") != EXPECTED_ONLINE["model"]
            or online_route.get("availability") != "AVAILABLE"
        ):
            raise CanaryBlocked(
                "online_route_not_agy_flash_38:"
                f"{online_route.get('worker_id')}:{online_route.get('model')}:{online_route.get('availability')}"
            )
        if route.get("online_fallback") is not None:
            raise CanaryBlocked("online_fallback_configured")
        if physical and confirm_task_id != task_id:
            raise CanaryBlocked("physical_run_requires_confirm_task_id")
        if receipt["source"]["dirty"] and physical:
            raise CanaryBlocked("source_worktree_dirty")
    except CanaryBlocked as exc:
        return finish(STATUS_BLOCKED, [str(exc)])

    if physical or run_host_preflight:
        probes = host_probes or real_host_probes()
        preflight = host_preflight(probes, min_unused_bytes=min_unused_bytes)
        receipt["host_preflight"] = preflight
        if physical and not preflight["ok"]:
            return finish(
                STATUS_ABORTED, [f"host_preflight_failed:{name}" for name in preflight["failed"]]
            )

    if not physical:
        return finish(STATUS_DRY, ["dry_run_no_model_called"])

    try:
        fixture = materialize_fixture(run_dir / "workspace")
    except (CanaryBlocked, OSError, subprocess.CalledProcessError) as exc:
        return finish(STATUS_BLOCKED, [f"fixture_materialization_failed:{exc}"])
    receipt["fixture"] = fixture

    context = build_execution_context(task_id, fixture["revision"])
    context.update(dict(extra_context or {}))
    env = {"NEXUS_ARMOR_ARTIFACT_ROOT": str(run_dir / "armor"), **dict(runtime_env or {})}
    receipt["runtime_env"] = {key: env[key] for key in sorted(env)}
    # Any provider-endpoint override (fake transports in tests, or an operator
    # shell variable) makes the receipt ineligible for the durable marker.
    receipt["transport_overrides"] = {
        key: (env.get(key) or os.environ.get(key))
        for key in TRANSPORT_OVERRIDE_ENV
        if env.get(key) or os.environ.get(key)
    }
    if executor is None:
        from nexus.engine.canonical_task_seam import execute_canonical_product_task

        executor = execute_canonical_product_task
    tracked_before = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=no")
    try:
        with _scoped_environ(env):
            result = executor(
                TASK_STATEMENT,
                Path(fixture["workspace"]),
                execution_context=context,
                task_card_identity=identity,
            )
    except ValueError as exc:
        # The canonical seam rejects caller overrides and identity drift before
        # any provider call; these are governance refusals, not run failures.
        return finish(STATUS_BLOCKED, [f"canonical_seam_rejected:{exc}"])
    except Exception as exc:  # noqa: BLE001 - record any runtime crash fail-closed
        return finish(STATUS_FAILED, [f"canonical_runtime_exception:{type(exc).__name__}:{exc}"])

    runtime_receipt = _mapping(result.receipt)
    receipt_path = Path(str(result.receipt_path))
    receipt["runtime_receipt"] = {
        "path": str(receipt_path),
        "sha256": _sha256_bytes(receipt_path.read_bytes()) if receipt_path.is_file() else "",
        "receipt_hash": runtime_receipt.get("receipt_hash"),
    }
    try:
        from nexus_runtime.kernel.transport import resolve_registered_provider_executable

        agy_executable = resolve_registered_provider_executable(
            "agy", environ={**os.environ, **env}
        )
    except Exception:  # noqa: BLE001 - unknown executable fails the fingerprint check closed
        agy_executable = ""
    receipt["agy_executable"] = agy_executable
    evaluation = evaluate_runtime_evidence(
        runtime_receipt,
        task_id=task_id,
        agy_executable=agy_executable,
        root_receipt_valid=bool(result.root_receipt_valid),
        root_receipt_blockers=tuple(result.root_receipt_blockers),
    )
    # The canonical checkout and the fixture source must be untouched: World C
    # mutates only its isolated copy and Agy runs in plan mode without grants.
    tracked_after = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=no")
    evaluation.add(
        "canonical_worktree_tracked_files_unchanged", tracked_before == tracked_after, tracked_after
    )
    fixture_now = {
        name: _sha256_bytes((Path(fixture["workspace"]) / name).read_bytes())
        for name in FIXTURE_FILES
    }
    evaluation.add("fixture_source_unchanged", fixture_now == fixture["files"], fixture_now)
    receipt["checks"] = [check.to_dict() for check in evaluation.checks]
    receipt["evidence"] = evaluation.evidence
    receipt["online_consumed"] = (
        _mapping(evaluation.evidence.get("contribution")).get("online_consumed") is True
    )
    receipt["final_outcome_contributed"] = (
        _mapping(evaluation.evidence.get("contribution")).get("final_outcome_contributed") is True
    )
    blocked = _online_blocked_reason(evaluation)
    if blocked:
        receipt["online_consumed"] = False
        receipt["final_outcome_contributed"] = False
        return finish(STATUS_BLOCKED, [blocked, "return_to_owner_no_fallback"])
    if evaluation.failed:
        receipt["online_consumed"] = (
            receipt["online_consumed"] and "consumption_proof_verified" not in evaluation.failed
        )
        receipt["final_outcome_contributed"] = False
        return finish(STATUS_FAILED, [f"check_failed:{name}" for name in evaluation.failed])
    return finish(STATUS_PASS, [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument(
        "--physical", action="store_true", help="Run one real Local + Online canary."
    )
    parser.add_argument(
        "--confirm-task-id", default="", help="Must equal the Task Card task_id for --physical."
    )
    parser.add_argument(
        "--host-preflight", action="store_true", help="Run read-only host checks in dry mode."
    )
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    receipt = run_canary(
        physical=args.physical,
        state_root=Path(args.state_root),
        run_id=args.run_id,
        confirm_task_id=args.confirm_task_id,
        run_host_preflight=args.host_preflight,
    )
    summary = {
        key: receipt.get(key)
        for key in (
            "status",
            "reasons",
            "mode",
            "task_id",
            "run_id",
            "online_consumed",
            "final_outcome_contributed",
            "durable_marker_eligible",
            "receipt_path",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if receipt["status"] in {STATUS_PASS, STATUS_DRY} else 1


if __name__ == "__main__":
    raise SystemExit(main())
