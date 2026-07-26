"""Durable, restartable service facade for the self-hosted MCP surface."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterator, Mapping, Optional
from uuid import uuid4

from nexus.executors.codex_executor import CodexCliExecutor
from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectureDecision,
    ArchitectTaskContract,
    DevelopmentGoal,
    HumanApprovalPolicy,
    MutationMode,
)
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager


Runner = Callable[[ArchitectTaskContract, Mapping[str, Any], Callable[[str, dict[str, Any]], None]], dict[str, Any]]
TERMINAL_STATUSES = frozenset({"CANDIDATE_COMMITTED", "FINAL_BLOCK"})
RESUMABLE_STATUSES = frozenset({"WORKER_COMPLETED", "CANDIDATE_CAPTURED", "VERIFIED"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class SelfHostedTaskService:
    def __init__(
        self,
        state_dir: str | Path = ".nexus/self_hosted_tasks",
        runner: Optional[Runner] = None,
        *,
        stale_after_seconds: float = 30.0,
        auto_reconcile: bool = True,
    ):
        self.state_dir = Path(state_dir).expanduser().resolve()
        self._custom_runner = runner
        self.runner = runner or self._run_default
        self.stale_after_seconds = stale_after_seconds
        self._threads: dict[str, threading.Thread] = {}
        if auto_reconcile:
            self.reconcile_tasks()

    def _state_path(self, task_id: str) -> Path:
        return self.state_dir / f"{task_id}.json"

    def _lock_path(self) -> Path:
        return self.state_dir / ".state.lock"

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock_path().open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        normalized = _jsonable(state)
        destination = self._state_path(task_id)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.state_dir,
            prefix=f".{task_id}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(normalized, handle, sort_keys=True, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(destination)
        return normalized

    def _write_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            return self._write_state_locked(task_id, state)

    def _create_state(self, task_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._state_lock():
            destination = self._state_path(task_id)
            if destination.exists():
                return json.loads(destination.read_text(encoding="utf-8")), False
            return self._write_state_locked(task_id, state), True

    def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._state_path(task_id)
        if not path.exists():
            return None
        with self._state_lock():
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def _mutate_state(self, task_id: str, mutator: Callable[[dict[str, Any]], None]) -> Optional[dict[str, Any]]:
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                return None
            state = json.loads(path.read_text(encoding="utf-8"))
            mutator(state)
            return self._write_state_locked(task_id, state)

    def _checkpoint(
        self,
        task_id: str,
        status: str,
        values: Optional[Mapping[str, Any]] = None,
        *,
        attempt_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        now = _utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if attempt_id is not None and state.get("attempt_id") != attempt_id:
                raise RuntimeError("task attempt ownership changed")
            previous = state.get("status")
            state["status"] = status
            if values:
                state.update(_jsonable(dict(values)))
            state["updated_at"] = now
            state["heartbeat_at"] = now
            history = list(state.get("status_history", []))
            if previous != status:
                history.append({"status": status, "at": now})
            state["status_history"] = history
            if status in TERMINAL_STATUSES:
                state["worker_finished_at"] = now
                state["worker_child_pgid"] = None

        return self._mutate_state(task_id, mutate)

    def _heartbeat(self, task_id: str, attempt_id: str, stop: threading.Event) -> None:
        while not stop.wait(1.0):
            try:
                self._mutate_state(
                    task_id,
                    lambda state: self._touch_owned_state(state, attempt_id),
                )
            except (RuntimeError, OSError, json.JSONDecodeError):
                return

    @staticmethod
    def _touch_owned_state(state: dict[str, Any], attempt_id: str) -> None:
        if state.get("attempt_id") != attempt_id or state.get("status") in TERMINAL_STATUSES:
            raise RuntimeError("task is no longer owned by this attempt")
        now = _utc_now()
        state["heartbeat_at"] = now
        state["updated_at"] = now

    def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract:
        if "prompt" in request:
            raise ValueError("prompt is not accepted; submit WHAT and WHY")
        worker = str(request.get("worker", "codex")).strip().lower()
        if worker != "codex":
            raise ValueError("MCP v1 only supports the codex worker")
        what = str(request.get("what", "")).strip()
        why = str(request.get("why", "")).strip()
        if not what or not why:
            raise ValueError("what and why are required")
        task_id = str(request.get("task_id") or f"mcp-{uuid4().hex[:12]}")
        decisions = request.get("architecture_decisions") or [
            {
                "decision_id": "target-boundary",
                "selected_option": "Target-only mutation",
                "rationale": "Preserve Controller immutability during worker execution",
                "rejected_alternatives": ["Controller mutation"],
            }
        ]
        decision_models = [
            item if isinstance(item, ArchitectureDecision) else ArchitectureDecision(**item)
            for item in decisions
        ]
        verifier_commands = [str(item) for item in request.get("verifier_commands", [])]
        protected_contracts = [str(item) for item in request.get("protected_contracts", [])]
        return ArchitectTaskContract(
            task_id=task_id,
            objective=what,
            goal=DevelopmentGoal(what=what, why=why),
            architecture_decisions=decision_models,
            acceptance_profile=AcceptanceProfile(
                verifier_commands=verifier_commands,
                protected_contracts=protected_contracts,
                required_evidence=["candidate_state_hash", "controller_unchanged", "verified_candidate_receipt"],
            ),
            human_approval_policy=HumanApprovalPolicy(
                approver_roles=list(request.get("approver_roles", ["James"])),
            ),
            controller_revision=str(request["controller_revision"]),
            target_base_revision=str(request["target_base_revision"]),
            controller_repo_root=str(request["controller_repo_root"]),
            target_repo_root=str(request["target_repo_root"]),
            target_worktree_root=str(request["target_worktree_root"]),
            allowed_files=list(request["allowed_files"]),
            forbidden_files=list(request.get("forbidden_files", [])),
            verifier_commands=verifier_commands,
            protected_contracts=protected_contracts,
            preferred_provider="codex",
            fallback_provider=None,
            maximum_provider_calls=1,
            maximum_replans=0,
            mutation_mode=MutationMode.WORKING_TREE_ONLY,
            human_approval_required=True,
        )

    @staticmethod
    def _prompt(contract: ArchitectTaskContract) -> str:
        allowed = ", ".join(contract.allowed_files)
        return (
            f"WHAT: {contract.goal.what}\n"
            f"WHY: {contract.goal.why}\n"
            f"Allowed files: {allowed}\n"
            "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
            "outside the allowed scope. Return a concise summary after making the change."
        )

    def _set_child_pgid(self, task_id: str, attempt_id: str, pgid: Optional[int]) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("attempt_id") == attempt_id and state.get("status") not in TERMINAL_STATUSES:
                state["worker_child_pgid"] = pgid
                state["updated_at"] = _utc_now()

        self._mutate_state(task_id, mutate)

    def _lease_from_state(self, state: Mapping[str, Any]) -> TargetWorktreeLease:
        raw = state.get("lease")
        if not isinstance(raw, Mapping):
            raise RuntimeError("durable lease evidence is missing")
        return TargetWorktreeLease(**dict(raw))

    def _capture_resumed_candidate(
        self,
        contract: ArchitectTaskContract,
        controller: SelfHostedDevelopmentController,
        lease: TargetWorktreeLease,
        state: Mapping[str, Any],
    ):
        candidate = controller.collect_candidate(contract, lease)
        stored = state.get("candidate") or {}
        if stored.get("candidate_state_hash") and stored["candidate_state_hash"] != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed during recovery")
        return candidate

    def _run_default_resumable(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        update: Callable[[str, dict[str, Any]], None],
        *,
        task_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller = SelfHostedDevelopmentController(worktree_manager=manager)
        state = self._read_state(task_id) or {}
        status = str(state.get("status"))
        if status == "SUBMITTED":
            lease = controller.prepare_task(contract)
            update("TARGET_LEASED", {"lease": lease})
            update("WORKER_RUNNING", {})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status in {"TARGET_LEASED", "WORKER_RUNNING"}:
            raise RuntimeError("worker lost before execution receipt; recovery is fail-closed")
        else:
            lease = self._lease_from_state(state)

        execution = state.get("execution")
        if status == "WORKER_RUNNING":
            def on_process_group(pgid: Optional[int]) -> None:
                self._set_child_pgid(task_id, attempt_id, pgid)

            execution_receipt = CodexCliExecutor(
                timeout_seconds=float(request.get("timeout_seconds", 900.0)),
                on_process_group=on_process_group,
            ).invoke(
                contract,
                lease,
                prompt=self._prompt(contract),
            )
            execution = execution_receipt
            update("WORKER_COMPLETED", {"execution": execution_receipt})
            state = self._read_state(task_id) or {}
            status = "WORKER_COMPLETED"

        if status == "WORKER_COMPLETED":
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)
            update("CANDIDATE_CAPTURED", {"candidate": candidate})
            state = self._read_state(task_id) or {}
            status = "CANDIDATE_CAPTURED"
        else:
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)

        verified = CandidateVerifier(manager).verify(
            contract,
            lease,
            candidate,
            protected_paths=request.get("protected_paths") or {},
        )
        if not verified.verified:
            raise RuntimeError("candidate verification failed: " + ",".join(verified.failure_reasons))
        update("VERIFIED", {"verified_receipt": verified})
        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        result = {
            "execution": execution,
            "candidate": candidate,
            "verified_receipt": verified,
            "promotion_packet": packet,
            "promotion_status": packet.promotion_status,
            "candidate_commit_created": packet.candidate_commit_created,
            "public_claim_allowed": packet.public_claim_allowed,
            "production_ready": packet.production_ready,
            "merge_performed": packet.merge_performed,
            "push_performed": packet.push_performed,
        }
        return result

    def _run_default(self, contract, request, update):
        return self._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=str((self._read_state(contract.task_id) or {}).get("attempt_id", "")),
        )

    def _run_owned_task(self, task_id: str, attempt_id: str) -> None:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return
        owner_pid = os.getpid()
        if state.get("worker_pid") not in (None, owner_pid):
            return
        stop = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(task_id, attempt_id, stop), daemon=True)
        heartbeat.start()

        def update(status: str, values: dict[str, Any]) -> None:
            self._checkpoint(task_id, status, values, attempt_id=attempt_id)

        try:
            contract = self.build_contract(state["request"])
            if self._custom_runner is None:
                result = self._run_default_resumable(
                    contract,
                    state["request"],
                    update,
                    task_id=task_id,
                    attempt_id=attempt_id,
                )
            else:
                result = self.runner(contract, state["request"], update)
            self._checkpoint(task_id, "CANDIDATE_COMMITTED", result, attempt_id=attempt_id)
        except Exception as exc:
            self._terminate_owned_processes(task_id, exclude_pid=owner_pid)
            self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {"error": str(exc), "promotion_status": "NOT_CREATED"},
                attempt_id=attempt_id,
            )
        finally:
            stop.set()
            heartbeat.join(timeout=2.0)

    def _wait_for_owner(self, task_id: str, attempt_id: str, pid: int) -> bool:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            state = self._read_state(task_id)
            if state is None or state.get("attempt_id") != attempt_id:
                return False
            if state.get("worker_pid") == pid:
                return True
            time.sleep(0.05)
        return False

    def _launch_worker(self, task_id: str, attempt_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return state
        if state.get("worker_pid") and self._pid_alive(int(state["worker_pid"])):
            return state
        if self._custom_runner is not None:
            thread = threading.Thread(target=self._run_owned_task, args=(task_id, attempt_id), daemon=True)
            self._threads[task_id] = thread
            self._mutate_state(
                task_id,
                lambda current: current.update({
                    "worker_pid": os.getpid(),
                    "worker_pgid": os.getpgrp(),
                    "worker_mode": "thread",
                    "worker_started_at": _utc_now(),
                    "heartbeat_at": _utc_now(),
                }),
            )
            thread.start()
            return self._read_state(task_id)
        command = [
            sys.executable,
            "-m",
            "nexus.orchestrator.self_hosted_task_worker",
            "--state-dir",
            str(self.state_dir),
            "--task-id",
            task_id,
            "--attempt-id",
            attempt_id,
        ]
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
        process = subprocess.Popen(
            command,
            cwd=source_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        return self._mutate_state(
            task_id,
            lambda current: current.update({
                "worker_pid": process.pid,
                "worker_pgid": pgid,
                "worker_mode": "process",
                "worker_started_at": _utc_now(),
                "heartbeat_at": _utc_now(),
            }),
        )

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return True

    def _terminate_owned_processes(self, task_id: str, *, exclude_pid: Optional[int] = None) -> None:
        state = self._read_state(task_id) or {}
        current_pgid = os.getpgrp()
        for raw_pgid in (state.get("worker_child_pgid"), state.get("worker_pgid")):
            if not raw_pgid:
                continue
            pgid = int(raw_pgid)
            if pgid in {current_pgid, exclude_pid}:
                continue
            try:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                continue

    def reconcile_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None or state.get("status") in TERMINAL_STATUSES:
            return state
        pid = state.get("worker_pid")
        heartbeat_at = _parse_time(state.get("heartbeat_at"))
        stale = heartbeat_at is not None and time.time() - heartbeat_at > self.stale_after_seconds
        if pid and self._pid_alive(int(pid)) and not stale:
            return state
        if pid and self._pid_alive(int(pid)) and stale:
            self._terminate_owned_processes(task_id)
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {"error": "stale task heartbeat; owned process group terminated", "promotion_status": "NOT_CREATED"},
                attempt_id=state.get("attempt_id"),
            )
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            return self._launch_worker(task_id, str(state.get("attempt_id")))
        self._terminate_owned_processes(task_id)
        return self._checkpoint(
            task_id,
            "FINAL_BLOCK",
            {"error": "worker lost before recoverable execution evidence", "promotion_status": "NOT_CREATED"},
            attempt_id=state.get("attempt_id"),
        )

    def reconcile_tasks(self) -> list[dict[str, Any]]:
        if not self.state_dir.exists():
            return []
        states = []
        for path in sorted(self.state_dir.glob("*.json")):
            state = self.reconcile_task(path.stem)
            if state is not None:
                states.append(state)
        return states

    def resume_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self.reconcile_task(task_id)

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        contract = self.build_contract(request)
        attempt_id = uuid4().hex
        now = _utc_now()
        state: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "status_history": [{"status": "SUBMITTED", "at": now}],
            "request": _jsonable(dict(request)),
            "contract": contract.model_dump(mode="json"),
            "contract_hash": contract.contract_hash,
            "attempt_id": attempt_id,
            "worker_pid": None,
            "worker_pgid": None,
            "worker_child_pgid": None,
            "worker_started_at": None,
            "worker_finished_at": None,
            "heartbeat_at": now,
            "updated_at": now,
            "promotion_status": "NOT_CREATED",
            "merge_performed": False,
            "push_performed": False,
        }
        existing, created = self._create_state(contract.task_id, state)
        if not created:
            if existing.get("contract_hash") != contract.contract_hash:
                raise ValueError("task_id already exists with a different contract")
            return self.reconcile_task(contract.task_id) or existing
        return self._launch_worker(contract.task_id, attempt_id) or state

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self.reconcile_task(task_id)

    def get_receipt(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self.get_task(task_id)
        if state is None:
            return None
        return {
            "task_id": task_id,
            "status": state.get("status"),
            "contract_hash": state.get("contract_hash"),
            "execution": state.get("execution"),
            "candidate": state.get("candidate"),
            "verified_receipt": state.get("verified_receipt"),
            "error": state.get("error"),
        }

    def get_promotion_packet(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self.get_task(task_id)
        if state is None:
            return None
        return {
            "task_id": task_id,
            "promotion_status": state.get("promotion_status"),
            "promotion_packet": state.get("promotion_packet"),
            "candidate_commit_created": state.get("candidate_commit_created", False),
            "public_claim_allowed": state.get("public_claim_allowed", False),
            "production_ready": state.get("production_ready", False),
            "merge_performed": state.get("merge_performed", False),
            "push_performed": state.get("push_performed", False),
        }

    def approve_promotion(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        packet = state.get("promotion_packet") or {}
        expected = {
            "candidate_commit_sha": candidate_commit_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "candidate_state_hash": candidate_state_hash,
            "verified_receipt_hash": verified_receipt_hash,
        }

        def mutate(current: dict[str, Any]) -> None:
            current["promotion_status"] = "APPROVED" if not any(packet.get(k) != v for k, v in expected.items()) else "INVALIDATED"
            if current["promotion_status"] == "APPROVED":
                current["approved_binding"] = expected
            else:
                current["approval_error"] = "promotion binding does not match candidate packet"
            current["merge_performed"] = False
            current["push_performed"] = False

        return self._mutate_state(task_id, mutate) or state
