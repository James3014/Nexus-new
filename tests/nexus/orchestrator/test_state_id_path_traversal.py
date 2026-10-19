"""SEC-015 / SEC-016: campaign_id and competition_id must not escape the state dir."""

import json
from pathlib import Path

import pytest

from nexus.orchestrator.refactor_campaign import RefactorCampaignCoordinator, RefactorWave
from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer
from nexus.orchestrator.worker_competition import (
    WorkerCompetitionCoordinator,
    contained_state_path,
    validate_state_id,
)

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


class _Service:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir

    def get_task(self, task_id):
        return {"task_id": task_id, "status": "SUBMITTED"}


def _competition(tmp_path: Path) -> WorkerCompetitionCoordinator:
    return WorkerCompetitionCoordinator(_Service(tmp_path / "service-state"))


def _plant_outside(tmp_path: Path, key: str) -> Path:
    """Plant a forged state file where ``../x/evil`` would point from the state dir."""
    outside = tmp_path / "service-state" / "x"
    outside.mkdir(parents=True, exist_ok=True)
    forged = outside / "evil.json"
    forged.write_text(json.dumps({key: "../x/evil", "status": "READY"}), encoding="utf-8")
    return forged


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_validate_state_id_rejects_unsafe_ids(bad_id):
    with pytest.raises(ValueError, match="^SOME_CODE$"):
        validate_state_id(bad_id, code="SOME_CODE")


@pytest.mark.parametrize(
    "good_id", ["a", "repo-refactor", "competition-0a1b2c3d4e", "x.y_z-1", "A" * 128]
)
def test_validate_state_id_accepts_ids_create_produces(good_id):
    assert validate_state_id(good_id, code="SOME_CODE") == good_id


def test_contained_state_path_rejects_symlinked_state_file(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (tmp_path / "elsewhere.json").write_text("{}", encoding="utf-8")
    (state_dir / "link.json").symlink_to(tmp_path / "elsewhere.json")
    with pytest.raises(ValueError, match="^CODE$"):
        contained_state_path(state_dir, "link", code="CODE")
    assert contained_state_path(state_dir, "plain", code="CODE") == state_dir / "plain.json"


def test_competition_traversal_id_rejected_for_get_integrate_push(tmp_path):
    coordinator = _competition(tmp_path)
    forged = _plant_outside(tmp_path, "competition_id")
    before = forged.read_text(encoding="utf-8")
    for bad_id in ("../x/evil", "../../x/evil", "..", "../x"):
        with pytest.raises(ValueError, match="^COMPETITION_ID_INVALID$"):
            coordinator.get(bad_id)
        with pytest.raises(ValueError, match="^COMPETITION_ID_INVALID$"):
            coordinator.integrate_winner(bad_id)
        with pytest.raises(ValueError, match="^COMPETITION_ID_INVALID$"):
            coordinator.push_winner(
                bad_id,
                remote="origin",
                authority_goal_id="goal",
                authority_coordination_scope_id="scope",
            )
    assert forged.read_text(encoding="utf-8") == before


def test_competition_write_rejects_traversal_id_in_state(tmp_path):
    coordinator = _competition(tmp_path)
    with pytest.raises(ValueError, match="^COMPETITION_ID_INVALID$"):
        coordinator._write({"competition_id": "../escaped", "status": "SUBMITTED"})
    assert not (coordinator.state_dir.parent / "escaped.json").exists()


def test_competition_forged_state_with_mismatching_id_is_rejected_and_not_written(tmp_path):
    coordinator = _competition(tmp_path)
    coordinator.state_dir.mkdir(parents=True)
    (coordinator.state_dir / "legit.json").write_text(
        json.dumps({"competition_id": "../forged", "status": "SUBMITTED", "candidates": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="^COMPETITION_STATE_ID_MISMATCH$"):
        coordinator.get("legit")
    assert not (coordinator.state_dir.parent / "forged.json").exists()


def test_competition_valid_id_round_trips(tmp_path):
    coordinator = _competition(tmp_path)
    coordinator._write({
        "competition_id": "refactor-competition.v1_a",
        "status": "SUBMITTED",
        "candidates": [],
    })
    state = coordinator.get("refactor-competition.v1_a")
    assert state is not None
    assert state["competition_id"] == "refactor-competition.v1_a"
    assert coordinator.get("never-created") is None


def _campaign(tmp_path: Path) -> RefactorCampaignCoordinator:
    return RefactorCampaignCoordinator(
        _competition(tmp_path), state_dir=tmp_path / "service-state" / "campaigns"
    )


def test_campaign_traversal_id_rejected_for_get_advance_rollback(tmp_path):
    coordinator = _campaign(tmp_path)
    forged = _plant_outside(tmp_path, "campaign_id")
    before = forged.read_text(encoding="utf-8")
    for bad_id in ("../x/evil", "../../x/evil", "..", "../x"):
        with pytest.raises(ValueError, match="^CAMPAIGN_ID_INVALID$"):
            coordinator.get(bad_id)
        with pytest.raises(ValueError, match="^CAMPAIGN_ID_INVALID$"):
            coordinator.advance(bad_id)
        with pytest.raises(ValueError, match="^CAMPAIGN_ID_INVALID$"):
            coordinator.rollback(bad_id, wave_id="wave-1")
    assert forged.read_text(encoding="utf-8") == before


def test_campaign_forged_state_with_mismatching_id_is_rejected(tmp_path):
    coordinator = _campaign(tmp_path)
    coordinator.state_dir.mkdir(parents=True)
    (coordinator.state_dir / "legit.json").write_text(
        json.dumps({"campaign_id": "../forged", "status": "COMPLETED"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="^CAMPAIGN_STATE_ID_MISMATCH$"):
        coordinator.get("legit")
    with pytest.raises(ValueError, match="^CAMPAIGN_STATE_ID_MISMATCH$"):
        coordinator.advance("legit")


def test_campaign_valid_id_round_trips(tmp_path):
    coordinator = _campaign(tmp_path)
    created = coordinator.create(
        "repo-refactor.v2_a",
        {
            "controller_repo_root": str(tmp_path / "repo"),
            "target_worktree_root": str(tmp_path / "t"),
        },
        [RefactorWave("wave-1", "refactor one", ("nexus/a.py",))],
        ["codex", "opencode"],
    )
    assert created["campaign_id"] == "repo-refactor.v2_a"
    state = coordinator.get("repo-refactor.v2_a")
    assert state is not None
    assert state["status"] == "READY"


def test_gateway_tools_return_invalid_code_for_traversal_ids(tmp_path):
    server = NexusSelfHostedMCPServer(service=_Service(tmp_path / "service-state"))  # type: ignore[arg-type]
    calls = [
        ("nexus_self_hosted_get_competition", {"competition_id": "../x"}, "COMPETITION_ID_INVALID"),
        ("nexus_self_hosted_get_refactor_campaign", {"campaign_id": "../x"}, "CAMPAIGN_ID_INVALID"),
        (
            "nexus_self_hosted_advance_refactor_campaign",
            {"campaign_id": "../x"},
            "CAMPAIGN_ID_INVALID",
        ),
    ]
    for name, arguments, code in calls:
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        assert response is not None
        assert response["result"]["isError"] is True
        assert response["result"]["structuredContent"] == {"error": code}


# --- Round-1 review follow-ups (#2663) ---------------------------------------------


class _SubmittingService(_Service):
    def submit_task(self, request):
        return {"task_id": request["task_id"], "status": "SUBMITTED"}


_WAVE = RefactorWave("wave-1", "refactor one", ("nexus/a.py",))


def _base_request(tmp_path: Path) -> dict:
    return {
        "controller_repo_root": str(tmp_path / "repo"),
        "target_worktree_root": str(tmp_path / "targets"),
    }


@pytest.mark.parametrize(
    ("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b"), ("..a...b..", "a-b")]
)
def test_sanitize_state_id_produces_valid_ids(raw, expected):
    from nexus.orchestrator.worker_competition import sanitize_state_id

    assert sanitize_state_id(raw, code="CODE") == expected
    assert validate_state_id(sanitize_state_id(raw, code="CODE"), code="CODE")


@pytest.mark.parametrize("raw", ["", "...", "__", "-.-", "a" * 129])
def test_sanitize_state_id_fails_clearly(raw):
    from nexus.orchestrator.worker_competition import sanitize_state_id

    with pytest.raises(ValueError, match="^CODE$"):
        sanitize_state_id(raw, code="CODE")


@pytest.mark.parametrize(("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b")])
def test_campaign_create_sanitizes_edge_ids_and_round_trips(tmp_path, raw, expected):
    coordinator = _campaign(tmp_path)
    created = coordinator.create(raw, _base_request(tmp_path), [_WAVE], ["codex", "opencode"])
    assert created["campaign_id"] == expected
    state = coordinator.get(expected)
    assert state is not None
    assert state["campaign_id"] == expected


@pytest.mark.parametrize(("raw", "expected"), [("_foo", "foo"), (".foo", "foo"), ("a..b", "a-b")])
def test_competition_submit_sanitizes_edge_ids_and_round_trips(tmp_path, raw, expected):
    coordinator = WorkerCompetitionCoordinator(_SubmittingService(tmp_path / "service-state"))
    submitted = coordinator.submit(
        {
            "competition_id": raw,
            "authority_goal_id": "goal",
            "authority_coordination_scope_id": "scope",
            "target_repo_root": str(tmp_path / "targets"),
        },
        ["codex", "opencode"],
    )
    assert submitted["competition_id"] == expected
    state = coordinator.get(expected)
    assert state is not None
    assert state["competition_id"] == expected


def test_campaign_create_rejects_id_too_long_for_wave_task_ids(tmp_path):
    coordinator = _campaign(tmp_path)
    wave = RefactorWave("wave-1", "refactor one", ("nexus/a.py",))
    with pytest.raises(ValueError, match="^CAMPAIGN_ID_TOO_LONG$"):
        coordinator.create("c" * 122, _base_request(tmp_path), [wave], ["codex", "opencode"])
    assert not coordinator.state_dir.exists() or not any(coordinator.state_dir.iterdir())
    # Exactly at the limit (len + 1 + len("wave-1") == 128) is accepted.
    created = coordinator.create("c" * 121, _base_request(tmp_path), [wave], ["codex", "opencode"])
    assert len(f"{created['campaign_id']}-wave-1") == 128


def test_campaign_create_rejects_traversal_wave_id(tmp_path):
    coordinator = _campaign(tmp_path)
    with pytest.raises(ValueError, match="^WAVE_ID_INVALID$"):
        coordinator.create(
            "camp",
            _base_request(tmp_path),
            [RefactorWave("../x", "refactor one", ("nexus/a.py",))],
            ["codex", "opencode"],
        )


def test_campaign_rollback_rejects_traversal_wave_id(tmp_path):
    coordinator = _campaign(tmp_path)
    coordinator.create("camp", _base_request(tmp_path), [_WAVE], ["codex", "opencode"])
    state = coordinator.get("camp")
    assert state is not None
    state["checkpoints"] = {"../x": "a" * 40, "../../escape": "a" * 40}
    coordinator._write(state)
    targets = tmp_path / "targets"
    for bad_wave in ("../x", "../../escape"):
        with pytest.raises(ValueError, match="^WAVE_ID_INVALID$"):
            coordinator.rollback("camp", wave_id=bad_wave)
    assert not targets.exists() or sorted(p.name for p in targets.rglob("*")) == [
        "campaign-rollbacks"
    ]
    assert not (targets / "x").exists()


def test_gateway_rollback_integrate_push_tools_reject_traversal_ids(tmp_path):
    server = NexusSelfHostedMCPServer(service=_Service(tmp_path / "service-state"))  # type: ignore[arg-type]
    calls = [
        (
            "nexus_self_hosted_rollback_refactor_campaign",
            {"campaign_id": "../x", "wave_id": "wave-1"},
            "CAMPAIGN_ID_INVALID",
        ),
        (
            "nexus_self_hosted_integrate_competition",
            {"competition_id": "../x"},
            "COMPETITION_ID_INVALID",
        ),
        (
            "nexus_self_hosted_push_competition",
            {
                "competition_id": "../x",
                "remote": "origin",
                "authority_goal_id": "goal",
                "authority_coordination_scope_id": "scope",
            },
            "COMPETITION_ID_INVALID",
        ),
    ]
    for name, arguments, code in calls:
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        assert response is not None
        assert response["result"]["isError"] is True
        assert response["result"]["structuredContent"] == {"error": code}
