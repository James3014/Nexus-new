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
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

ROUTE_MODE_AT_START = os.environ.get("NEXUS_CAIRNWORK_ROUTE", "off").strip().lower()
ROUTE_BIN_AT_START = os.environ.get("NEXUS_CAIRNWORK_ROUTE_BIN", "").strip()
ROUTE_STATE_AT_START = os.environ.get("NEXUS_CAIRNWORK_STATE", "").strip()
CAIRNWORK_WORKER = "cairnwork"
TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED"})
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
# The only fields a pilot small fix may carry (booleans only when false).
_SMALL_FIX_FIELDS = frozenset({
    "task_id",
    "what",
    "why",
    "worker",
    "allowed_files",
    "verifier_commands",
    "owner_confirmation",
    "task_card_path",
    "task_card_hash",
})
_FALSE_ALLOWED = frozenset({"authority_change_candidate_confirmation", "fail_to_pass_required"})
_PYTEST_FLAGS = frozenset({"-q", "-x", "-v"})
_TEST_PATH = re.compile(r"tests/(?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+\.py(?:::[A-Za-z0-9_\[\]\-]+)*")
_CALL_TIMEOUT_SECONDS = 60
_SHADOW_TIMEOUT_SECONDS = 10


def _gateway() -> Any:
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


def route_mode() -> str:
    return ROUTE_MODE_AT_START if ROUTE_MODE_AT_START in ("shadow", "route") else "off"


def small_fix_shape(arguments: Mapping[str, Any], verifiers: list[str]) -> bool:
    """Only the listed fields, and every verifier ``python3 -m pytest [-q|-x|-v] tests/...``
    (Cairnwork checks the same again; this decides only what is offered to it)."""
    for key, value in arguments.items():
        if key in _FALSE_ALLOWED and value is False:
            continue
        if key not in _SMALL_FIX_FIELDS:
            return False
    if not verifiers:
        return False
    for command in verifiers:
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        rest = argv[3:]
        if argv[:3] != ["python3", "-m", "pytest"] or not rest:
            return False
        if not all(a in _PYTEST_FLAGS or _TEST_PATH.fullmatch(a) for a in rest):
            return False
        if not any(_TEST_PATH.fullmatch(a) for a in rest):
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
    *args: str,
    payload: Optional[dict[str, Any]] = None,
    timeout: float = _CALL_TIMEOUT_SECONDS,
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
            timeout=max(1.0, timeout),
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

    def _cairnwork_root(self) -> Optional[Path]:
        """The SelfHosted state directory; never a shared /tmp fallback."""
        configured = getattr(self.service, "state_dir", None)
        return Path(configured).expanduser().resolve() if configured else None

    def _cairnwork_job_path(self, task_id: str) -> Optional[Path]:
        root = self._cairnwork_root()
        if root is None or not _SLUG.fullmatch(str(task_id)):
            return None
        return root / "cairnwork_jobs" / f"{task_id}.json"

    def _cairnwork_owns(self, task_id: str) -> bool:
        path = self._cairnwork_job_path(task_id)
        return path is not None and path.is_file() and not path.is_symlink()

    def _cairnwork_shadow(self, arguments: Mapping[str, Any], payload: dict[str, Any]) -> None:
        """Log what route mode would do, in the background: never raises, never
        delays or changes the response."""
        root = self._cairnwork_root()
        if root is None:
            return
        worker = str(arguments.get("worker") or "")
        try:
            threading.Thread(
                target=_shadow_check, args=(root, worker, payload), daemon=True
            ).start()
        except RuntimeError:  # no thread available: skip the shadow line, never the response
            return

    def _cairnwork_submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload["idempotency_key"]
        path = self._cairnwork_job_path(task_id)
        if path is None:
            raise _gateway().GatewayInputError("CAIRNWORK_NO_STATE_DIR")
        if not ROUTE_BIN_AT_START or not ROUTE_STATE_AT_START:
            raise _gateway().GatewayInputError("CAIRNWORK_UNCONFIGURED")  # before any record
        if not path.exists() and self.service.get_task_snapshot(task_id) is not None:
            raise _gateway().GatewayInputError("CAIRNWORK_TASK_ID_OWNED_BY_NEXUS")
        created = _create_record(path, task_id, payload["card_hash"])
        if created and self.service.get_task_snapshot(task_id) is not None:
            path.unlink(missing_ok=True)  # SelfHosted took the id meanwhile: nothing was sent
            raise _gateway().GatewayInputError("CAIRNWORK_TASK_ID_OWNED_BY_NEXUS")
        code, body = call_cairnwork("submit", payload=payload)
        if code == 2 and body.get("error") == "NOT_ACCEPTING":
            if created:  # only the call that made the record may take it back
                path.unlink(missing_ok=True)
            raise _gateway().GatewayInputError("CAIRNWORK_NOT_ACCEPTING")
        if code != 0:
            error = str(body.get("error") or "ERROR")
            raise _gateway().GatewayInputError(
                error if error.startswith("CAIRNWORK_") else f"CAIRNWORK_{error}"
            )
        return {
            "schema": "nexus.worker_candidate.v1",
            "task_id": task_id,
            "owner": "cairnwork",
            "status": body.get("status"),
            "cairnwork_task_id": body.get("task_id"),
            "duplicate": body.get("duplicate"),
            "candidate_only": True,
        }

    def _cairnwork_status(
        self, task_id: str, *, timeout: float = _CALL_TIMEOUT_SECONDS
    ) -> dict[str, Any]:
        code, body = call_cairnwork("status", "--key", task_id, timeout=timeout)
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
        """Bounded by timeout_seconds; an unreadable status returns at once."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self._cairnwork_status(task_id, timeout=deadline - time.monotonic())
            if status["terminal"] or "error" in status or time.monotonic() >= deadline:
                return status
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def _cairnwork_cancel(self, task_id: str) -> dict[str, Any]:
        status = self._cairnwork_status(task_id)
        if not status.get("cairnwork_task_id"):
            return {**status, "cancelled": False}
        code, body = call_cairnwork("cancel", f"--task-id={status['cairnwork_task_id']}")
        if code != 0:
            return {
                **status,
                "cancelled": False,
                "error": body.get("error"),
                "detail": body.get("detail"),
            }
        return {**status, "status": body.get("status"), "terminal": True, "cancelled": True}


def _create_record(path: Path, task_id: str, card_hash: str) -> bool:
    """Create the ownership record atomically; False if it already existed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "nexus.cairnwork_job.v1",
        "task_id": task_id,
        "owner": "cairnwork",
        "task_card_hash": card_hash,
        "created_at": time.time(),
    }
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
    return True


def _shadow_check(root: Path, worker: str, payload: dict[str, Any]) -> None:
    try:
        code, body = call_cairnwork("check", payload=payload, timeout=_SHADOW_TIMEOUT_SECONDS)
        line = {
            "at": time.time(),
            "task_id": payload["idempotency_key"],
            "worker": worker,
            "exit": code,
            "answer": body,
        }
        data = (json.dumps(line, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(
            root / "cairnwork_shadow.jsonl",
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.write(fd, data)  # one append per line: lines from parallel checks never mix
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 - shadow mode must never affect the live path
        return
