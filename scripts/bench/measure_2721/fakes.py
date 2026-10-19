"""Zero-model fakes: an in-memory Gateway transport for dry runs and tests."""

from __future__ import annotations

import hashlib
from typing import Any, Optional

FAKE_HEAD = "f" * 40


class FakeGateway:
    """Answers the P1 tool sequence without any model, worker or git effect.

    ``external_target`` toggles whether ``nexus_worker_candidate`` advertises
    the proposed external-target field.  Every call is recorded.
    """

    def __init__(self, *, external_target: bool = True, worker_error: Optional[dict[str, Any]] = None):
        self.external_target = external_target
        self.worker_error = worker_error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, path: str, body: Optional[dict[str, Any]]) -> dict[str, Any]:
        if method == "GET" and path == "/health":
            return {"git_head": FAKE_HEAD, "repo_head_current": FAKE_HEAD, "server_instance_id": "fake",
                    "controller_binding": {"status": "SEPARATE"}}
        assert body is not None
        rpc = body["method"]
        if rpc == "tools/list":
            props = {key: {} for key in ("task_id", "what", "why", "allowed_files", "verifier_commands",
                                         "task_card_path", "task_card_hash", "owner_confirmation")}
            if self.external_target:
                props["external_target"] = {}
            return {"result": {"tools": [{"name": "nexus_worker_candidate", "inputSchema": {"properties": props}}]}}
        name, args = body["params"]["name"], body["params"]["arguments"]
        self.calls.append({"tool": name, "arguments": args})
        return {"result": {"structuredContent": self._answer(name, args), "isError": self._is_error(name)}}

    def _is_error(self, name: str) -> bool:
        return name == "nexus_worker_candidate" and self.worker_error is not None

    def _answer(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        task = args.get("task_id", "")
        if name == "nexus_task_card_create":
            card = hashlib.sha256(task.encode()).hexdigest()
            return {"status": "CREATED_PENDING_COMMIT", "card_path": f"tasks/{args['campaign_id']}/00-{task}.md",
                    "card_hash": card, "index_hash": card[::-1]}
        if name == "nexus_task_card_commit":
            return {"status": "COMMITTED", "commit_sha": "e" * 40}
        if name == "nexus_worker_candidate":
            if self.worker_error is not None:
                return self.worker_error
            return {"status": "SUBMITTED", "task_id": task}
        if name in ("nexus_task_wait", "nexus_task_status"):
            return {"task_id": task, "status": "FINAL_BLOCK", "blocker": "fake_no_worker",
                    "wait": {"timed_out": False}}
        if name == "nexus_task_cancel":
            return {"task_id": task, "status": "CANCELLED"}
        return {}
