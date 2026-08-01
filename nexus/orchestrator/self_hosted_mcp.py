"""Minimal stdio MCP protocol adapter for governed self-hosted development."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Optional

from nexus.executors.worker_contract import SUPPORTED_WORKER_PROVIDERS
from nexus.orchestrator.refactor_campaign import RefactorCampaignCoordinator, RefactorWave
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worker_competition import WorkerCompetitionCoordinator

WORKER_ENUM = list(SUPPORTED_WORKER_PROVIDERS)


class NexusSelfHostedMCPServer:
    def __init__(self, service: Optional[SelfHostedTaskService] = None):
        state_dir = os.getenv("NEXUS_SELF_HOSTED_STATE_DIR")
        self.service = service or SelfHostedTaskService(state_dir=state_dir or None)
        self.competition = WorkerCompetitionCoordinator(self.service)
        self.campaigns = RefactorCampaignCoordinator(self.competition)

    @staticmethod
    def _tool_specs() -> list[dict[str, Any]]:
        task_properties = {
            "task_id": {"type": "string"},
            "what": {"type": "string"},
            "why": {"type": "string"},
            "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "target_base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "controller_repo_root": {"type": "string"},
            "target_repo_root": {"type": "string"},
            "target_worktree_root": {"type": "string"},
            "allowed_files": {"type": "array", "items": {"type": "string"}},
            "forbidden_files": {"type": "array", "items": {"type": "string"}},
            "authorized_deletions": {"type": "array", "items": {"type": "string"}},
            "verifier_commands": {"type": "array", "items": {"type": "string"}},
            "protected_contracts": {"type": "array", "items": {"type": "string"}},
            "worker": {"type": "string", "enum": ["auto", *WORKER_ENUM]},
            "worker_order": {"type": "array", "items": {"type": "string", "enum": WORKER_ENUM}, "uniqueItems": True},
            "fallback_worker": {"type": "string", "enum": WORKER_ENUM},
        }
        return [
            {
                "name": "nexus_self_hosted_submit_task",
                "description": "Map WHAT/WHY to an Architect Contract and run one governed Codex Target task.",
                "inputSchema": {
                    "type": "object",
                    "properties": task_properties,
                    "required": [
                        "what",
                        "why",
                        "controller_revision",
                        "target_base_revision",
                        "controller_repo_root",
                        "target_repo_root",
                        "target_worktree_root",
                        "allowed_files",
                    ],
                    "additionalProperties": True,
                },
            },
            {
                "name": "nexus_self_hosted_get_task",
                "description": "Read durable task lifecycle state.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_wait_task",
                "description": "Bounded poll until the task reaches ACTION_REQUIRED, FINAL_BLOCK, or TERMINAL.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 60, "default": 10},
                        "poll_interval_seconds": {"type": "number", "exclusiveMinimum": 0, "default": 0.25},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_list_actionable_tasks",
                "description": "List tasks whose deterministic task-action envelope requires caller attention.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_self_hosted_compete_task",
                "description": "Submit isolated worker candidates in parallel and apply the common verifier.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **task_properties,
                        "competition_id": {"type": "string"},
                        "workers": {
                            "type": "array",
                            "items": {"type": "string", "enum": WORKER_ENUM},
                            "minItems": 2,
                            "uniqueItems": True,
                        },
                    },
                    "required": ["what", "why", "workers", "controller_revision", "target_base_revision", "controller_repo_root", "target_repo_root", "target_worktree_root", "allowed_files"],
                    "additionalProperties": True,
                },
            },
            {
                "name": "nexus_self_hosted_get_competition",
                "description": "Read parallel candidate states and deterministic winner decision.",
                "inputSchema": {
                    "type": "object",
                    "required": ["competition_id"],
                    "properties": {"competition_id": {"type": "string"}},
                },
            },
            {
                "name": "nexus_self_hosted_integrate_competition",
                "description": "Merge the deterministic verified winner into nexus/integration only; never push or merge protected main.",
                "inputSchema": {
                    "type": "object",
                    "required": ["competition_id"],
                    "properties": {
                        "competition_id": {"type": "string"},
                        "integration_branch": {"type": "string", "default": "nexus/integration"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_create_refactor_campaign",
                "description": "Create a bounded multi-wave refactor campaign with checkpoints and rollback.",
                "inputSchema": {
                    "type": "object",
                    "required": ["campaign_id", "base_request", "waves", "workers"],
                    "properties": {
                        "campaign_id": {"type": "string"},
                        "base_request": {"type": "object"},
                        "workers": {"type": "array", "items": {"type": "string", "enum": WORKER_ENUM}, "minItems": 2, "uniqueItems": True},
                        "waves": {"type": "array", "items": {"type": "object"}, "minItems": 1},
                        "max_scope_entries": {"type": "integer", "minimum": 1, "default": 100},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_advance_refactor_campaign",
                "description": "Advance one campaign wave; each wave requires competition, common verification, and integration evidence.",
                "inputSchema": {"type": "object", "required": ["campaign_id"], "properties": {"campaign_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_get_refactor_campaign",
                "description": "Read durable campaign wave, checkpoint, and rollback state.",
                "inputSchema": {"type": "object", "required": ["campaign_id"], "properties": {"campaign_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_rollback_refactor_campaign",
                "description": "Rollback an integration branch to a durable wave checkpoint.",
                "inputSchema": {"type": "object", "required": ["campaign_id", "wave_id"], "properties": {"campaign_id": {"type": "string"}, "wave_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_push_competition",
                "description": "Explicitly push an integrated winner only to an allowlisted remote and nexus/integration branch.",
                "inputSchema": {
                    "type": "object",
                    "required": ["competition_id", "remote", "authorized"],
                    "properties": {
                        "competition_id": {"type": "string"},
                        "remote": {"type": "string"},
                        "authorized": {"type": "boolean"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_get_receipt",
                "description": "Read execution evidence and Verified Candidate Receipt.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_get_promotion_packet",
                "description": "Read the hash-bound candidate promotion packet.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_reconcile_tasks",
                "description": "Reconcile non-terminal task owners after an MCP restart.",
                "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_resume_task",
                "description": "Resume a task only from durable, non-provider execution evidence.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_approve_promotion",
                "description": "Approve an exact candidate binding without merging or pushing.",
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "task_id",
                        "candidate_commit_sha",
                        "candidate_tree_sha",
                        "candidate_state_hash",
                        "verified_receipt_hash",
                    ],
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_status",
                "description": "Report canonical lifecycle state and active Target budget.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_self_hosted_cleanup",
                "description": "Dry-run or apply governed terminal Target cleanup decisions.",
                "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "apply": {"type": "boolean", "default": False}}},
            },
            {
                "name": "nexus_self_hosted_archive_state",
                "description": "Dry-run or apply terminal state archive with a reproducible manifest hash.",
                "inputSchema": {"type": "object", "properties": {"apply": {"type": "boolean", "default": False}}},
            },
            {
                "name": "nexus_self_hosted_integrate_approved",
                "description": "Integrate an exact approved candidate to nexus/integration without push.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}, "integration_branch": {"type": "string", "default": "nexus/integration"}}},
            },
            {
                "name": "nexus_self_hosted_owner_finish",
                "description": "Owner-only atomic approval and integration of an exact candidate binding; never pushes.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "integration_branch": {"type": "string", "default": "nexus/integration/main"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_dispose_candidate",
                "description": "Record REJECTED or SUPERSEDED candidate disposition while retaining its ref and receipt.",
                "inputSchema": {"type": "object", "required": ["task_id", "disposition"], "properties": {"task_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["REJECTED", "SUPERSEDED"]}, "superseded_by": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_close_retained_without_candidate",
                "description": "Fail-closed operation to close a RETAINED_FOR_REVIEW task that never produced a candidate.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "superseded_by"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "superseded_by": {"type": "string"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_close_without_candidate",
                "description": "Fail-closed operation to close a RETAINED_FOR_REVIEW or FINAL_BLOCK task that never produced a candidate.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "superseded_by"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "superseded_by": {"type": "string"},
                    },
                },
            },
            {
                "name": "nexus_self_hosted_cancel_task",
                "description": "Cancel a non-running task and apply its governed terminal Target cleanup.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_self_hosted_recover_verified_uncommitted_candidate",
                "description": "Recover a verified-uncommitted candidate task without re-running model providers.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"}
                    }
                },
            },
        ]

    @staticmethod
    def _success(request_id: Any, payload: Any) -> dict[str, Any]:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "structuredContent": payload,
                "isError": False,
            },
        }

    @staticmethod
    def _tool_error(request_id: Any, error: Exception | str) -> dict[str, Any]:
        payload = {"error": str(error)}
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "structuredContent": payload,
                "isError": True,
            },
        }

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if name == "nexus_self_hosted_submit_task":
            return self.service.submit_task(arguments)
        if name == "nexus_self_hosted_compete_task":
            workers = arguments.get("workers") or []
            request = dict(arguments)
            request.pop("workers", None)
            return self.competition.submit(request, workers)
        if name == "nexus_self_hosted_get_competition":
            return self.competition.get(str(arguments.get("competition_id", "")))
        if name == "nexus_self_hosted_integrate_competition":
            return self.competition.integrate_winner(
                str(arguments.get("competition_id", "")),
                integration_branch=str(arguments.get("integration_branch", "nexus/integration")),
            )
        if name == "nexus_self_hosted_create_refactor_campaign":
            waves = [
                RefactorWave(
                    wave_id=str(item["wave_id"]),
                    objective=str(item["objective"]),
                    allowed_files=tuple(str(path) for path in item.get("allowed_files", [])),
                    verifier_commands=tuple(str(command) for command in item.get("verifier_commands", [])),
                )
                for item in arguments.get("waves", [])
            ]
            return self.campaigns.create(
                str(arguments["campaign_id"]),
                dict(arguments["base_request"]),
                waves,
                [str(provider) for provider in arguments.get("workers", [])],
                max_scope_entries=int(arguments.get("max_scope_entries", 100)),
            )
        if name == "nexus_self_hosted_advance_refactor_campaign":
            return self.campaigns.advance(str(arguments["campaign_id"]))
        if name == "nexus_self_hosted_get_refactor_campaign":
            return self.campaigns.get(str(arguments["campaign_id"]))
        if name == "nexus_self_hosted_rollback_refactor_campaign":
            return self.campaigns.rollback(
                str(arguments["campaign_id"]),
                wave_id=str(arguments["wave_id"]),
            )
        if name == "nexus_self_hosted_push_competition":
            return self.competition.push_winner(
                str(arguments["competition_id"]),
                remote=str(arguments["remote"]),
                authorized=bool(arguments["authorized"]),
            )
        task_id = str(arguments.get("task_id", ""))
        if name == "nexus_self_hosted_get_task":
            return self.service.get_task(task_id)
        if name == "nexus_self_hosted_wait_task":
            return self.service.wait_task(
                task_id,
                timeout_seconds=float(arguments.get("timeout_seconds", 10.0)),
                poll_interval_seconds=float(arguments.get("poll_interval_seconds", 0.25)),
            )
        if name == "nexus_self_hosted_list_actionable_tasks":
            return self.service.list_actionable_tasks()
        if name == "nexus_self_hosted_get_receipt":
            return self.service.get_receipt(task_id)
        if name == "nexus_self_hosted_get_promotion_packet":
            return self.service.get_promotion_packet(task_id)
        if name == "nexus_self_hosted_reconcile_tasks":
            if task_id:
                return self.service.reconcile_task(task_id)
            return {"tasks": self.service.reconcile_tasks()}
        if name == "nexus_self_hosted_resume_task":
            return self.service.resume_task(task_id)
        if name == "nexus_self_hosted_approve_promotion":
            return self.service.approve_promotion(
                task_id,
                candidate_commit_sha=str(arguments["candidate_commit_sha"]),
                candidate_tree_sha=str(arguments["candidate_tree_sha"]),
                candidate_state_hash=str(arguments["candidate_state_hash"]),
                verified_receipt_hash=str(arguments["verified_receipt_hash"]),
            )
        if name == "nexus_self_hosted_status":
            return self.service.lifecycle_status()
        if name == "nexus_self_hosted_cleanup":
            return self.service.cleanup_tasks(
                task_id=task_id or None,
                dry_run=not bool(arguments.get("apply", False)),
            )
        if name == "nexus_self_hosted_archive_state":
            return self.service.archive_states(dry_run=not bool(arguments.get("apply", False)))
        if name == "nexus_self_hosted_integrate_approved":
            return self.service.integrate_approved(
                task_id,
                integration_branch=str(arguments.get("integration_branch", "nexus/integration")),
            )
        if name == "nexus_self_hosted_owner_finish":
            return self.service.owner_finish(
                task_id,
                candidate_commit_sha=str(arguments["candidate_commit_sha"]),
                candidate_tree_sha=str(arguments["candidate_tree_sha"]),
                candidate_state_hash=str(arguments["candidate_state_hash"]),
                verified_receipt_hash=str(arguments["verified_receipt_hash"]),
                integration_branch=str(arguments.get("integration_branch", "nexus/integration/main")),
            )
        if name == "nexus_self_hosted_dispose_candidate":
            return self.service.dispose_candidate(
                task_id,
                disposition=str(arguments["disposition"]),
                superseded_by=arguments.get("superseded_by"),
            )
        if name == "nexus_self_hosted_close_retained_without_candidate":
            return self.service.close_retained_without_candidate(
                task_id,
                superseded_by=str(arguments.get("superseded_by", "")),
            )
        if name == "nexus_self_hosted_close_without_candidate":
            return self.service.close_task_without_candidate(
                task_id,
                superseded_by=str(arguments.get("superseded_by", "")),
            )
        if name == "nexus_self_hosted_cancel_task":
            return self.service.cancel_task(task_id)
        if name == "nexus_self_hosted_recover_verified_uncommitted_candidate":
            return self.service.recover_verified_uncommitted_candidate(task_id)
        raise ValueError(f"unknown tool: {name}")

    def handle(self, request: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized" or request_id is None:
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "nexus-self-hosted-development", "version": "1.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self._tool_specs()}}
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                return self._success(request_id, self._call_tool(str(params["name"]), params.get("arguments") or {}))
            except Exception as exc:
                return self._tool_error(request_id, exc)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }

    def serve(self, input_stream, output_stream) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                output_stream.write(json.dumps(response, sort_keys=True) + "\n")
                output_stream.flush()
