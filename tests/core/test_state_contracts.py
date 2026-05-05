from __future__ import annotations

from nexus.core.state_contracts import NexusState


def test_nexus_state_metadata_is_pipeline_metadata_with_stage_flow():
    state = NexusState(task_id="state-contract")

    assert isinstance(state.metadata, dict)
    state.metadata["stage_flow"] = ["S", "P", "D", "X", "R", "A", "C"]

    assert state.metadata["stage_flow"] == ["S", "P", "D", "X", "R", "A", "C"]


def test_nexus_state_conversation_metadata_is_per_instance():
    first = NexusState(task_id="first")
    second = NexusState(task_id="second")

    first.init_conversation("conv-1", "keep state isolated")
    first.update_conversation_metadata({"needs_research": True})

    assert first.get_conversation_metadata()["needs_research"] is True
    assert second.get_conversation_metadata() == {}


def test_nexus_state_legacy_metadata_migrates_without_losing_contract():
    state = NexusState.model_validate(
        {
            "task_id": "legacy",
            "metadata": {
                "conversation": {
                    "conversation_id": "legacy-conv",
                    "user_goal": "migrate safely",
                    "needs_research": False,
                }
            },
        }
    )

    assert isinstance(state.metadata, dict)
    assert state.get_conversation_metadata()["conversation_id"] == "legacy-conv"
