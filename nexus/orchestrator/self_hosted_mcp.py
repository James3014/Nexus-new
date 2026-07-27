"""Minimal stdio MCP protocol adapter for governed self-hosted development."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worker_competition import WorkerCompetitionCoordinator
from nexus.orchestrator.refactor_campaign import RefactorCampaignCoordinator, RefactorWave


class NexusSelfHostedMCPServer:
    def __init__(self, service: Optional[SelfHostedTaskService] = None):
        state_dir = os.getenv("NEXUS_SELF_HOSTED_STATE_DIR", str(Path.cwd() / ".nexus/self_hosted_tasks"))
        self.service = service or SelfHostedTaskService(state_dir=state_dir)
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
            "verifier_commands": {"type": "array", "items": {"type": "string"}},
            "protected_contracts": {"type": "array", "items": {"type": "string"}},
            "worker": {"type": "string", "enum": ["auto", "codex", "gemini", "opencode", "mimo", "ollama"]},
            "worker_order": {"type": "array", "items": {"type": "string", "enum": ["codex", "gemini", "opencode", "mimo", "ollama"]}, "uniqueItems": True},
            "fallback_worker": {"type": "string", "enum": ["codex", "gemini", "opencode", "mimo", "ollama"]},
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
                "name": "nexus_self_hosted_compete_task",
                "description": "Submit isolated worker candidates in parallel and apply the common verifier.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **task_properties,
                        "competition_id": {"type": "string"},
                        "workers": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["codex", "gemini", "opencode", "mimo", "ollama"]},
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
                        "workers": {"type": "array", "items": {"type": "string", "enum": ["codex", "gemini", "opencode", "mimo", "ollama"]}, "minItems": 2, "uniqueItems": True},
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
