"""SEC-015 / SEC-016: campaign_id and competition_id must not escape the state dir.

Retired 2026-10-21 (#2584 Phase-2 batch B): ``nexus.orchestrator.worker_competition``
and ``nexus.orchestrator.refactor_campaign`` were deleted together with the
self-hosted MCP competition/campaign tools (see
``ARCHIVED_2026-10-21_phase2_batch_B.md``). The traversal surface no longer exists:
each case below keeps its test id and now asserts that the module is gone, or
that the retired MCP tool is rejected as unknown before any state is touched.
"""

import importlib.util
from pathlib import Path

import pytest

from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer

WORKER_COMPETITION = "nexus.orchestrator.worker_competition"
REFACTOR_CAMPAIGN = "nexus.orchestrator.refactor_campaign"

TRAVERSAL_IDS = [
    "../x",
    "../../x/evil",
    "..",
    ".",
    "a/../b",
    "a/b",
    "a..b",
    "",
    "x\n",
    "/abs",
    "-x",
    "a" * 129,
]


def _retired(module: str) -> None:
    assert importlib.util.find_spec(module) is None


class _Service:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "SUBMITTED"}


def _assert_retired_tools_rejected(tmp_path: Path, calls) -> None:
    state_dir = tmp_path / "service-state"
    server = NexusSelfHostedMCPServer(service=_Service(state_dir))  # type: ignore[arg-type]
    for name, arguments in calls:
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        assert response is not None
        assert response["result"]["isError"] is True
        assert response["result"]["structuredContent"] == {"error": f"unknown tool: {name}"}
    assert not state_dir.exists()


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_validate_state_id_rejects_unsafe_ids(bad_id):
    _retired(WORKER_COMPETITION)


@pytest.mark.parametrize(
    "good_id", ["a", "repo-refactor", "competition-0a1b2c3d4e", "x.y_z-1", "A" * 128]
)
def test_validate_state_id_accepts_ids_create_produces(good_id):
    _retired(WORKER_COMPETITION)


def test_contained_state_path_rejects_symlinked_state_file(tmp_path):
    _retired(WORKER_COMPETITION)


def test_competition_traversal_id_rejected_for_get_integrate_push(tmp_path):
    _retired(WORKER_COMPETITION)


def test_competition_write_rejects_traversal_id_in_state(tmp_path):
    _retired(WORKER_COMPETITION)


def test_competition_forged_state_with_mismatching_id_is_rejected_and_not_written(tmp_path):
    _retired(WORKER_COMPETITION)


def test_competition_valid_id_round_trips(tmp_path):
    _retired(WORKER_COMPETITION)


def test_campaign_traversal_id_rejected_for_get_advance_rollback(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_campaign_forged_state_with_mismatching_id_is_rejected(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_campaign_valid_id_round_trips(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_gateway_tools_return_invalid_code_for_traversal_ids(tmp_path):
    _assert_retired_tools_rejected(
        tmp_path,
        [
            ("nexus_self_hosted_get_competition", {"competition_id": "../x"}),
            ("nexus_self_hosted_get_refactor_campaign", {"campaign_id": "../x"}),
            ("nexus_self_hosted_advance_refactor_campaign", {"campaign_id": "../x"}),
        ],
    )


# --- Round-1 review follow-ups (#2663) ---------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b"), ("..a...b..", "a-b")]
)
def test_sanitize_state_id_produces_valid_ids(raw, expected):
    _retired(WORKER_COMPETITION)


@pytest.mark.parametrize("raw", ["", "...", "__", "-.-", "a" * 129])
def test_sanitize_state_id_fails_clearly(raw):
    _retired(WORKER_COMPETITION)


@pytest.mark.parametrize(("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b")])
def test_campaign_create_sanitizes_edge_ids_and_round_trips(tmp_path, raw, expected):
    _retired(REFACTOR_CAMPAIGN)


@pytest.mark.parametrize(("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b")])
def test_competition_submit_sanitizes_edge_ids_and_round_trips(tmp_path, raw, expected):
    _retired(WORKER_COMPETITION)


def test_campaign_create_rejects_id_too_long_for_wave_task_ids(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_campaign_create_rejects_traversal_wave_id(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_campaign_rollback_rejects_traversal_wave_id(tmp_path):
    _retired(REFACTOR_CAMPAIGN)


def test_gateway_rollback_integrate_push_tools_reject_traversal_ids(tmp_path):
    _assert_retired_tools_rejected(
        tmp_path,
        [
            (
                "nexus_self_hosted_rollback_refactor_campaign",
                {"campaign_id": "../x", "wave_id": "wave-1"},
            ),
            ("nexus_self_hosted_integrate_competition", {"competition_id": "../x"}),
            (
                "nexus_self_hosted_push_competition",
                {
                    "competition_id": "../x",
                    "remote": "origin",
                    "authority_goal_id": "goal",
                    "authority_coordination_scope_id": "scope",
                },
            ),
        ],
    )
