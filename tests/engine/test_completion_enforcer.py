from nexus.engine.completion_enforcer import CompletionDecision
from nexus.engine.completion_enforcer import CompletionEnforcementError
from nexus.engine.completion_enforcer import decide_completion
from nexus.engine.completion_enforcer import enforce_completion
from nexus.engine.completion_enforcer import write_completion_handoff
import json


def test_decide_completion_reads_retryable_semantic_state():
    decision = decide_completion(
        {
            "semantic_status": "UNVERIFIED",
            "retryable": True,
            "blocker_type": "semantic_incomplete",
            "next_action": "retry_repair",
        }
    )

    assert decision == CompletionDecision(
        semantic_status="UNVERIFIED",
        retryable=True,
        blocker_type="semantic_incomplete",
        next_action="retry_repair",
    )


def test_enforce_completion_returns_decision_when_verified():
    decision = enforce_completion(
        {
            "semantic_status": "VERIFIED",
            "retryable": False,
            "blocker_type": "none",
            "next_action": "none",
        },
        context="run",
    )

    assert decision.semantic_status == "VERIFIED"


def test_enforce_completion_raises_with_blocked_context():
    try:
        enforce_completion(
            {
                "semantic_status": "BLOCKED",
                "retryable": False,
                "blocker_type": "governance",
                "next_action": "stop",
                "semantic_failures": ["low_disk_space"],
            },
            context="research:run",
        )
    except CompletionEnforcementError as exc:
        assert exc.decision.semantic_status == "BLOCKED"
        assert exc.decision.blocker_type == "governance"
        assert "low_disk_space" in str(exc)
    else:
        raise AssertionError("expected CompletionEnforcementError")


def test_write_completion_handoff_updates_state_checkpoint(tmp_path):
    payload = {
        "command_name": "research:run",
        "task_name": "fix queue race",
        "semantic_status": "UNVERIFIED",
        "retryable": True,
        "blocker_type": "semantic_incomplete",
        "next_action": "retry_repair",
        "semantic_failures": ["below_threshold"],
        "execution_path": "cli->research_control_plane",
    }

    out = write_completion_handoff(project_root=tmp_path, payload=payload, context="research:run")

    sidecar = json.loads(out.read_text(encoding="utf-8"))
    state_handoff = json.loads((tmp_path / ".nexus" / "state" / "last_handoff.json").read_text(encoding="utf-8"))
    assert sidecar["task_id"] == "fix queue race"
    assert sidecar["phase"] == "R"
    assert sidecar["state_token"] == "UNVERIFIED"
    assert state_handoff["next_action"] == "retry_repair"
    assert state_handoff["task_id"] == "fix queue race"
