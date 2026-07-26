"""Durable service facade for the Nexus self-hosted development MCP surface."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Optional
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
from nexus.orchestrator.worktree_manager import WorktreeManager


Runner = Callable[[ArchitectTaskContract, Mapping[str, Any], Callable[[str, dict[str, Any]], None]], dict[str, Any]]


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


class SelfHostedTaskService:
    def __init__(self, state_dir: str | Path = ".nexus/self_hosted_tasks", runner: Optional[Runner] = None):
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.runner = runner or self._run_default

    def _state_path(self, task_id: str) -> Path:
        return self.state_dir / f"{task_id}.json"

    def _write_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
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

    def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._state_path(task_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

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
                required_evidence=[
                    "candidate_state_hash",
                    "controller_unchanged",
                    "verified_candidate_receipt",
                ],
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

    def _run_default(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        update: Callable[[str, dict[str, Any]], None],
    ) -> dict[str, Any]:
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller = SelfHostedDevelopmentController(worktree_manager=manager)
        update("TARGET_LEASED", {})
        lease, execution, candidate = controller.execute_codex_candidate(
            contract,
            prompt=self._prompt(contract),
            executor=CodexCliExecutor(timeout_seconds=float(request.get("timeout_seconds", 900.0))),
        )
        update("CANDIDATE_CAPTURED", {"execution": execution, "candidate": candidate})
        verified = CandidateVerifier(manager).verify(
            contract,
            lease,
            candidate,
            protected_paths=request.get("protected_paths") or {},
        )
        update("VERIFYING", {"verified_receipt": verified})
        if not verified.verified:
            raise RuntimeError("candidate verification failed: " + ",".join(verified.failure_reasons))
        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        return {
            "execution": execution,
            "candidate": candidate,
            "verified_receipt": verified,
            "promotion_packet": packet,
            "promotion_status": packet.promotion_status,
            "candidate_commit_created": packet.candidate_commit_created,
            "merge_performed": packet.merge_performed,
            "push_performed": packet.push_performed,
        }

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        contract = self.build_contract(request)
        existing = self._read_state(contract.task_id)
        if existing is not None:
            return existing
        state: dict[str, Any] = {
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "contract": contract.model_dump(mode="json"),
            "contract_hash": contract.contract_hash,
            "promotion_status": "NOT_CREATED",
            "merge_performed": False,
            "push_performed": False,
        }
        self._write_state(contract.task_id, state)

        def update(status: str, values: dict[str, Any]) -> None:
            state["status"] = status
            state.update(_jsonable(values))
            self._write_state(contract.task_id, state)

        try:
            result = self.runner(contract, request, update)
            state.update(_jsonable(result))
            state["status"] = "CANDIDATE_COMMITTED"
            return self._write_state(contract.task_id, state)
        except Exception as exc:
            state["status"] = "FINAL_BLOCK"
            state["error"] = str(exc)
            state["promotion_status"] = "NOT_CREATED"
            return self._write_state(contract.task_id, state)

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self._read_state(task_id)

    def get_receipt(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
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
        state = self._read_state(task_id)
        if state is None:
            return None
        return {
            "task_id": task_id,
            "promotion_status": state.get("promotion_status"),
            "promotion_packet": state.get("promotion_packet"),
            "candidate_commit_created": state.get("candidate_commit_created", False),
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
        if any(packet.get(key) != value for key, value in expected.items()):
            state["promotion_status"] = "INVALIDATED"
            state["approval_error"] = "promotion binding does not match candidate packet"
            return self._write_state(task_id, state)
        state["promotion_status"] = "APPROVED"
        state["approved_binding"] = expected
        state["merge_performed"] = False
        state["push_performed"] = False
        return self._write_state(task_id, state)
