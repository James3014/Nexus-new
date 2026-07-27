import json

import pytest

from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer


class FakeService:
    def submit_task(self, arguments):
        return {"task_id": arguments["task_id"], "status": "CANDIDATE_COMMITTED"}

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "CANDIDATE_COMMITTED"}

    def get_receipt(self, task_id):
        return {"task_id": task_id, "verified": True}

    def get_promotion_packet(self, task_id):
        return {"task_id": task_id, "promotion_status": "PENDING_HUMAN_APPROVAL"}

    def approve_promotion(self, task_id, **kwargs):
        return {"task_id": task_id, "promotion_status": "APPROVED", "merge_performed": False}

    def lifecycle_status(self):
        return {"active_targets": 0}

    def cleanup_tasks(self, **kwargs):
        return {"dry_run": kwargs.get("dry_run", True)}

    def archive_states(self, **kwargs):
        return {"dry_run": kwargs.get("dry_run", True)}

    def integrate_approved(self, task_id, **kwargs):
        return {"task_id": task_id, "status": "INTEGRATED", "push_performed": False}

    def dispose_candidate(self, task_id, **kwargs):
        return {"task_id": task_id, "status": kwargs["disposition"]}


def test_tools_list_exposes_governed_self_hosted_surface():
    server = NexusSelfHostedMCPServer(service=FakeService())

    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    names = {item["name"] for item in response["result"]["tools"]}
    assert {
        "nexus_self_hosted_submit_task",
        "nexus_self_hosted_compete_task",
        "nexus_self_hosted_get_competition",
        "nexus_self_hosted_integrate_competition",
        "nexus_self_hosted_create_refactor_campaign",
        "nexus_self_hosted_advance_refactor_campaign",
        "nexus_self_hosted_get_refactor_campaign",
        "nexus_self_hosted_rollback_refactor_campaign",
        "nexus_self_hosted_push_competition",
        "nexus_self_hosted_get_task",
        "nexus_self_hosted_get_receipt",
        "nexus_self_hosted_get_promotion_packet",
        "nexus_self_hosted_reconcile_tasks",
        "nexus_self_hosted_resume_task",
        "nexus_self_hosted_approve_promotion",
        "nexus_self_hosted_status",
        "nexus_self_hosted_cleanup",
        "nexus_self_hosted_archive_state",
        "nexus_self_hosted_integrate_approved",
        "nexus_self_hosted_dispose_candidate",
    } <= names
    specs = {item["name"]: item for item in response["result"]["tools"]}
    submit_properties = specs["nexus_self_hosted_submit_task"]["inputSchema"]["properties"]
    compete_properties = specs["nexus_self_hosted_compete_task"]["inputSchema"]["properties"]
    campaign_properties = specs["nexus_self_hosted_create_refactor_campaign"]["inputSchema"]["properties"]
    assert "agy" in submit_properties["worker"]["enum"]
    assert "agy" in submit_properties["worker_order"]["items"]["enum"]
    assert "agy" in submit_properties["fallback_worker"]["enum"]
    assert "agy" in compete_properties["workers"]["items"]["enum"]
    assert "agy" in campaign_properties["workers"]["items"]["enum"]


def test_tools_call_returns_structured_json_result():
    server = NexusSelfHostedMCPServer(service=FakeService())

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "nexus_self_hosted_submit_task",
                "arguments": {"task_id": "mcp-task-001"},
            },
        }
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "CANDIDATE_COMMITTED"
    assert response["result"]["structuredContent"] == payload


def test_unknown_tool_is_jsonrpc_error():
    server = NexusSelfHostedMCPServer(service=FakeService())

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "nexus_self_hosted_unknown", "arguments": {}},
        }
    )

    assert response["result"]["isError"] is True
    assert "unknown tool" in response["result"]["content"][0]["text"]
