"""Parallel isolated worker competition with deterministic winner selection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4

from nexus.executors.worker_contract import SUPPORTED_WORKER_PROVIDERS
from nexus.orchestrator.governed_integration import ControlledIntegrationManager
from nexus.orchestrator.governed_push import GovernedPushManager


TERMINAL_TASK_STATUSES = frozenset({"CANDIDATE_COMMITTED", "FINAL_BLOCK"})
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class CompetitionCandidate:
    candidate_id: str
    task_id: str
    provider: str
    target_repo_root: str


def select_deterministic_winner(
    candidates: Sequence[Mapping[str, Any]],
    provider_order: Sequence[str],
) -> dict[str, Any]:
    """Select only fully verified candidates; ties resolve by declared provider order."""

    rank = {provider: index for index, provider in enumerate(provider_order)}
    eligible: list[tuple[tuple[int, int, int, str], Mapping[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    gate_names = (
        "scope_gate_passed",
        "deletion_gate_passed",
        "controller_gate_passed",
        "protected_contract_gate_passed",
        "verifier_gate_passed",
    )
    for candidate in candidates:
        receipt = candidate.get("verified_receipt") or {}
        packet = candidate.get("promotion_packet") or {}
        valid = (
            candidate.get("status") == "CANDIDATE_COMMITTED"
            and receipt.get("verified") is True
            and all(receipt.get(name) is True for name in gate_names)
            and candidate.get("candidate_commit_created") is True
            and bool(packet.get("candidate_commit_sha"))
            and candidate.get("merge_performed", False) is False
            and candidate.get("push_performed", False) is False
        )
        if not valid:
            rejected.append({"task_id": candidate.get("task_id"), "reason": "candidate proof incomplete"})
            continue
        provider = str(candidate.get("provider", ""))
        evidence_count = len(receipt.get("verifier_evidence") or [])
        gate_score = sum(bool(receipt.get(name)) for name in gate_names)
        provider_rank = rank.get(provider, len(rank))
        task_id = str(candidate.get("task_id", ""))
        score = (gate_score, evidence_count, -provider_rank, task_id)
        eligible.append((score, candidate))

    if not eligible:
        return {
            "status": "NO_WINNER",
            "winner_task_id": None,
            "ranked_candidates": [],
            "rejected_candidates": rejected,
            "reason": "no candidate passed the common verifier and promotion invariants",
        }
    eligible.sort(key=lambda item: item[0], reverse=True)
    winner = eligible[0][1]
    return {
        "status": "WINNER_SELECTED",
        "winner_task_id": winner.get("task_id"),
        "ranked_candidates": [item[1].get("task_id") for item in eligible],
        "rejected_candidates": rejected,
        "reason": "highest verified evidence score with deterministic provider-order tie break",
    }


class WorkerCompetitionCoordinator:
    def __init__(self, service: Any, state_dir: Optional[str | Path] = None):
        self.service = service
        configured = state_dir or getattr(service, "state_dir", Path.cwd() / ".nexus/self_hosted_tasks")
        self.state_dir = Path(configured).expanduser().resolve() / "competitions"

    def _path(self, competition_id: str) -> Path:
        return self.state_dir / f"{competition_id}.json"

    def _write(self, state: Mapping[str, Any]) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        destination = self._path(str(state["competition_id"]))
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.state_dir,
            prefix=f".{destination.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(dict(state), handle, sort_keys=True, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(destination)
        return dict(state)

    def _read(self, competition_id: str) -> Optional[dict[str, Any]]:
        path = self._path(competition_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _candidate_request(
        request: Mapping[str, Any],
        competition_id: str,
        provider: str,
    ) -> tuple[dict[str, Any], CompetitionCandidate]:
        candidate_id = f"{competition_id}-{provider}"
        task_id = _SAFE_ID.sub("-", candidate_id).strip("-")
        target_root = Path(str(request["target_repo_root"])).expanduser().resolve() / provider
        candidate_request = dict(request)
        candidate_request.update(
            {
                "task_id": task_id,
                "worker": provider,
                "fallback_worker": None,
                "target_repo_root": str(target_root),
            }
        )
        candidate_request.pop("fallback_provider", None)
        return candidate_request, CompetitionCandidate(
            candidate_id=candidate_id,
            task_id=task_id,
            provider=provider,
            target_repo_root=str(target_root),
        )

    def submit(self, request: Mapping[str, Any], providers: Sequence[str]) -> dict[str, Any]:
        normalized = tuple(str(provider).strip().lower() for provider in providers)
        if len(normalized) < 2 or len(set(normalized)) != len(normalized):
            raise ValueError("competition requires at least two distinct workers")
        unknown = set(normalized) - set(SUPPORTED_WORKER_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown competition workers: {sorted(unknown)}")
        base_id = str(request.get("competition_id") or request.get("task_id") or f"competition-{uuid4().hex[:10]}")
        competition_id = _SAFE_ID.sub("-", base_id).strip("-")
        if not competition_id:
            raise ValueError("competition_id must contain a safe identifier")
        if self._read(competition_id) is not None:
            return self.get(competition_id)

        prepared = [self._candidate_request(request, competition_id, provider) for provider in normalized]
        with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="nexus-competition") as pool:
            futures = [pool.submit(self.service.submit_task, candidate_request) for candidate_request, _ in prepared]
            submissions = [future.result() for future in futures]
        candidates = [candidate for _, candidate in prepared]
        state = {
            "schema": "nexus.worker_competition_state.v1",
            "competition_id": competition_id,
            "status": "SUBMITTED",
            "provider_order": list(normalized),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "task_id": candidate.task_id,
                    "provider": candidate.provider,
                    "target_repo_root": candidate.target_repo_root,
                    "submission": submission,
                }
                for candidate, submission in zip(candidates, submissions)
            ],
        }
        return self._write(state)

    def push_winner(
        self,
        competition_id: str,
        *,
        remote: str,
        authorized: bool,
    ) -> dict[str, Any]:
        state = self.get(competition_id)
        if state is None:
            raise KeyError(f"unknown competition_id: {competition_id}")
        if state.get("status") != "INTEGRATED":
            raise RuntimeError("only an integrated winner can be pushed")
        integration = state.get("integration") or {}
        winner_task_id = str((state.get("winner") or {}).get("winner_task_id") or "")
        winner_state = self.service.get_task(winner_task_id)
        if winner_state is None:
            raise RuntimeError("winner task state is missing")
        contract = winner_state.get("contract") or {}
        configured_remotes = frozenset(
            item.strip()
            for item in os.getenv("NEXUS_GOVERNED_PUSH_REMOTES", "").split(",")
            if item.strip()
        )
        receipt = GovernedPushManager(
            repo_root=str(contract.get("controller_repo_root", "")),
            allowed_remotes=configured_remotes,
        ).push(
            remote=remote,
            branch=str(integration.get("integration_branch", "")),
            expected_sha=str(integration.get("integration_commit_sha", "")),
            authorized=authorized,
            integration_receipt=integration,
        )
        state["status"] = "PUSHED"
        state["push"] = {
            "schema": receipt.schema,
            "remote": receipt.remote,
            "branch": receipt.branch,
            "pushed_commit_sha": receipt.pushed_commit_sha,
            "remote_commit_sha": receipt.remote_commit_sha,
            "push_performed": receipt.push_performed,
            "force_push": receipt.force_push,
            "authorized": receipt.authorized,
        }
        return self._write(state)

    def get(self, competition_id: str) -> Optional[dict[str, Any]]:
        state = self._read(competition_id)
        if state is None:
            return None
        candidates: list[dict[str, Any]] = []
        all_terminal = True
        for candidate in state.get("candidates", []):
            task_state = self.service.get_task(str(candidate["task_id"])) or {
                "task_id": candidate["task_id"],
                "status": "MISSING",
            }
            task_state = dict(task_state)
            task_state.update(
                {
                    "candidate_id": candidate["candidate_id"],
                    "provider": candidate["provider"],
                }
            )
            candidates.append(task_state)
            if task_state.get("status") not in TERMINAL_TASK_STATUSES:
                all_terminal = False
        state["candidate_states"] = candidates
        if all_terminal:
            decision = select_deterministic_winner(candidates, state.get("provider_order", []))
            state["status"] = decision["status"]
            state["winner"] = decision
        else:
            state["status"] = "RUNNING"
        return self._write(state)

    def integrate_winner(
        self,
        competition_id: str,
        *,
        integration_branch: str = "nexus/integration",
    ) -> dict[str, Any]:
        state = self.get(competition_id)
        if state is None:
            raise KeyError(f"unknown competition_id: {competition_id}")
        if state.get("status") != "WINNER_SELECTED":
            raise RuntimeError("competition has no deterministic verified winner")
        winner_task_id = str((state.get("winner") or {}).get("winner_task_id") or "")
        winner_state = self.service.get_task(winner_task_id)
        if winner_state is None:
            raise RuntimeError("winner task state is missing")
        contract = winner_state.get("contract") or {}
        integration_root = Path(str(contract.get("target_worktree_root", self.state_dir))) / "integrations"
        receipt = ControlledIntegrationManager(integration_root=integration_root).integrate_task_state(
            winner_state,
            integration_branch=integration_branch,
        )
        state["status"] = "INTEGRATED"
        state["integration"] = {
            "schema": receipt.schema,
            "task_id": receipt.task_id,
            "integration_branch": receipt.integration_branch,
            "source_branch": receipt.source_branch,
            "candidate_commit_sha": receipt.candidate_commit_sha,
            "integration_commit_sha": receipt.integration_commit_sha,
            "verifier_passed": receipt.verifier_passed,
            "merge_performed": receipt.merge_performed,
            "push_performed": receipt.push_performed,
            "worktree_removed": receipt.worktree_removed,
            "failure_reason": receipt.failure_reason,
        }
        return self._write(state)
