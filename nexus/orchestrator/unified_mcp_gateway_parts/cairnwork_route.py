"""Forward one task type from ``nexus_worker_candidate`` to Cairnwork (council F).

The Gateway keeps its entry, authentication and Task Card checks; Cairnwork only
gets requests that passed them. Contract: James3014/cairnwork docs/GATEWAY_ROUTE.md.

``NEXUS_CAIRNWORK_ROUTE`` is read once, at start (setting it later changes nothing):

* ``off`` (default, and any unknown value): nothing here runs for new requests.
* ``shadow``: for each request shaped like a small bug fix, ask ``cairnwork-route
  check`` and append the answer to ``<state>/cairnwork_shadow.jsonl``. The response
  and every other state are exactly what they are without it; a failing check is
  only logged.
* ``route``: a request with ``worker: "cairnwork"`` and that shape is submitted to
  Cairnwork instead of the SelfHosted service.

``NEXUS_CAIRNWORK_ROUTE_BIN`` and ``NEXUS_CAIRNWORK_STATE`` name the command and
Cairnwork's state directory.

Ownership: before submitting, ``<state>/cairnwork_jobs/<task_id>.json`` records that
Cairnwork owns the task id. ``nexus_task_status``/``wait``/``cancel`` for a recorded
id go to Cairnwork in every mode, so tasks forwarded before a rollback stay
visible. Only ``NOT_ACCEPTING`` (Cairnwork bound nothing) removes the record. After
any other answer the task is never given to the SelfHosted service, and an
answer that cannot be read is reported as ``UNKNOWN_REQUIRES_RECONCILE``.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

ROUTE_MODE_AT_START = os.environ.get("NEXUS_CAIRNWORK_ROUTE", "off").strip().lower()
ROUTE_BIN_AT_START = os.environ.get("NEXUS_CAIRNWORK_ROUTE_BIN", "").strip()
ROUTE_STATE_AT_START = os.environ.get("NEXUS_CAIRNWORK_STATE", "").strip()
CAIRNWORK_WORKER = "cairnwork"
TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
# Requests that carry any of these are not "a small bug fix" for the pilot.
_NOT_SMALL_FIX = (
    "authority_change_candidate_confirmation",
    "fail_to_pass_required",
    "rie_knowledge_identity",
    "codeintel_lookup",
    "planner_output",
    "workforce_demands",
    "workforce_admission",
    "external_target",
    "provider",
    "model",
)
_CALL_TIMEOUT_SECONDS = 60


def _gateway() -> Any:
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


def route_mode() -> str:
    return ROUTE_MODE_AT_START if ROUTE_MODE_AT_START in ("shadow", "route") else "off"


def small_fix_shape(arguments: Mapping[str, Any], verifiers: list[str]) -> bool:
    """No extra powers or inputs, and every verifier is ``python3 -m pytest tests/...``."""
    for key in _NOT_SMALL_FIX:
        value = arguments.get(key)
        if value not in (None, False, ""):
            return False
    for command in verifiers:
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if argv[:3] != ["python3", "-m", "pytest"] or not any(a.startswith("tests/") for a in argv):
            return False
    return True


def cairnwork_payload(
    *,
    task_id: str,
    task_card_hash: str,
    what: str,
    why: str,
    repo: Path,
    base: str,
    allowed: list[str],
    verifiers: list[str],
) -> dict[str, Any]:
    return {
        "idempotency_key": task_id,
        "card_hash": task_card_hash,
        "title": what.splitlines()[0][:200] if what.strip() else task_id,
        "instructions": f"{what}\n\nWhy: {why}",
        "repo": str(repo),
        "base_commit": base,
        "allowed_files": list(allowed),
        "verifiers": [[f"pytest-{i}", shlex.split(c)] for i, c in enumerate(verifiers)],
    }


def call_cairnwork(
    *args: str, payload: Optional[dict[str, Any]] = None
) -> tuple[int, dict[str, Any]]:
    """Run cairnwork-route; (exit code, JSON). A timeout kills the command and waits for it."""
    if not ROUTE_BIN_AT_START or not ROUTE_STATE_AT_START:
        return 1, {"error": "CAIRNWORK_UNCONFIGURED", "detail": "route bin or state not set"}
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv from the start-time configuration
            [ROUTE_BIN_AT_START, "--state", ROUTE_STATE_AT_START, *args],
            input=json.dumps(payload) if payload is not None else "",
            capture_output=True,
            text=True,
            timeout=_CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, {"error": "CAIRNWORK_CALL_FAILED", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        body = json.loads(done.stdout)
    except ValueError:
        return 1, {"error": "CAIRNWORK_OUTPUT_UNREADABLE", "detail": done.stdout[-500:]}
    if not isinstance(body, dict):
        return 1, {"error": "CAIRNWORK_OUTPUT_UNREADABLE", "detail": "not an object"}
    return done.returncode, body


class _CairnworkRouteMixin:
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:
        service: SelfHostedTaskService

    def _cairnwork_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        base = (
            Path(configured).expanduser().resolve()
            if configured
            else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        )
        return base

    def _cairnwork_job_path(self, task_id: str) -> Optional[Path]:
        if not _SLUG.fullmatch(str(task_id)):
            return None
        return self._cairnwork_root() / "cairnwork_jobs" / f"{task_id}.json"

    def _cairnwork_owns(self, task_id: str) -> bool:
        path = self._cairnwork_job_path(task_id)
        return path is not None and path.is_file()

    def _cairnwork_shadow(self, arguments: Mapping[str, Any], payload: dict[str, Any]) -> None:
        """Log what route mode would do. Never raises, never changes the response."""
        try:
            code, body = call_cairnwork("check", payload=payload)
            line = {
                "at": time.time(),
                "task_id": payload["idempotency_key"],
                "worker": str(arguments.get("worker") or ""),
                "exit": code,
                "answer": body,
            }
            root = self._cairnwork_root()
            root.mkdir(parents=True, exist_ok=True)
            with open(root / "cairnwork_shadow.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
        except Exception:  # noqa: BLE001 - shadow mode must never affect the live path
            return

    def _cairnwork_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload["idempotency_key"]
        path = self._cairnwork_job_path(task_id)
        if path is None:
            raise _gateway().GatewayInputError("task_id must be a stable bounded slug")
        if not path.exists() and self.service.get_task_snapshot(task_id) is not None:
            raise _gateway().GatewayInputError("CAIRNWORK_TASK_ID_OWNED_BY_NEXUS")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            record = {
                "schema": "nexus.cairnwork_job.v1",
                "task_id": task_id,
                "owner": "cairnwork",
                "task_card_hash": payload["card_hash"],
                "created_at": time.time(),
            }
            path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        code, body = call_cairnwork("submit", payload=payload)
        if code == 2 and body.get("error") == "NOT_ACCEPTING":
            path.unlink(missing_ok=True)  # nothing was bound: the task is not Cairnwork's
            raise _gateway().GatewayInputError("CAIRNWORK_NOT_ACCEPTING")
        if code != 0:
            raise _gateway().GatewayInputError(f"CAIRNWORK_{body.get('error') or 'ERROR'}")
        return {
            "schema": "nexus.worker_candidate.v1",
            "task_id": task_id,
            "owner": "cairnwork",
            "status": body.get("status"),
            "cairnwork_task_id": body.get("task_id"),
            "duplicate": body.get("duplicate"),
            "candidate_only": True,
        }

    def _cairnwork_status(self, task_id: str) -> dict[str, Any]:
        code, body = call_cairnwork("status", "--key", task_id)
        base = {"schema": "nexus.cairnwork_task.v1", "task_id": task_id, "owner": "cairnwork"}
        if code != 0:
            return {
                **base,
                "status": "UNKNOWN_REQUIRES_RECONCILE",
                "terminal": False,
                "error": body.get("error"),
                "detail": body.get("detail"),
            }
        status = str(body.get("status"))
        return {
            **base,
            "status": status,
            "terminal": status in TERMINAL,
            "core_verified": body.get("core_verified"),
            "candidate_commit": body.get("candidate_commit"),
            "cairnwork_task_id": body.get("task_id"),
            "phase": body.get("phase"),
        }

    def _cairnwork_wait(
        self, task_id: str, *, timeout_seconds: float, poll_interval_seconds: float
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self._cairnwork_status(task_id)
            if status["terminal"] or time.monotonic() >= deadline:
                return status
            time.sleep(poll_interval_seconds)

    def _cairnwork_cancel(self, task_id: str) -> dict[str, Any]:
        status = self._cairnwork_status(task_id)
        if not status.get("cairnwork_task_id"):
            return {**status, "cancelled": False}
        code, body = call_cairnwork("cancel", "--task-id", str(status["cairnwork_task_id"]))
        if code != 0:
            return {
                **status,
                "cancelled": False,
                "error": body.get("error"),
                "detail": body.get("detail"),
            }
        return {**status, "status": body.get("status"), "terminal": True, "cancelled": True}
