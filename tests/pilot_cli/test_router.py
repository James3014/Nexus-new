from nexus.pilot_cli.router import route_input
from nexus.pilot_cli.gateway import build_governance_payload, create_local_task_stub
from nexus.pilot_cli.session import PilotSession


def test_router_keeps_general_question_in_fast_lane():
    route = route_input("這個 stack trace 是什麼意思")
    assert route.lane == "FAST"


def test_router_marks_fix_request_for_battle_lane():
    route = route_input("幫我修這個 bug")
    assert route.lane == "BATTLE_CONFIRM"


def test_router_marks_self_check_request_for_prompt():
    route = route_input("幫我自檢一下")
    assert route.lane == "SELF_CHECK_PROMPT"


def test_router_marks_self_heal_request_for_prompt():
    route = route_input("幫我自修")
    assert route.lane == "SELF_HEAL_PROMPT"


def test_gateway_builds_battle_payload():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/repo",
    )
    payload = build_governance_payload(session, "幫我修這個 bug")
    assert payload["tenant_id"] == "pilot_a"
    assert payload["provider"] == "OpenAI"
    assert payload["lane"] == "BATTLE"
    assert payload["request"] == "幫我修這個 bug"


def test_gateway_creates_local_task_stub():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/repo",
    )
    result = create_local_task_stub(session, "幫我修這個 bug")
    assert result["status"] == "QUEUED"
    assert result["task_id"].startswith("pilot-task-")
    assert "Sensing" in result["summary"]
