from types import MappingProxyType

import pytest

from nexus.core.blackboard import Blackboard


def test_blackboard_appends_immutable_phase_events():
    board = Blackboard()
    source = {"risk": ["high"]}

    event = board.append("P", "impact_map", source)
    source["risk"].append("mutated")

    assert event["event_id"] == 1
    assert event["phase"] == "P"
    assert event["key"] == "impact_map"
    assert event["value"]["risk"] == ("high",)
    assert isinstance(event, MappingProxyType)


def test_blackboard_view_is_read_only_and_filterable():
    board = Blackboard()
    board.append("P", "impact_map", {"target.py": {"risk": "HIGH"}})
    board.append("X", "research_pack", {"citations": ["docs"]})

    p_view = board.view("P")

    assert len(p_view["events"]) == 1
    assert p_view["latest"]["impact_map"]["target.py"]["risk"] == "HIGH"
    assert board.has("impact_map", "P") is True
    assert board.has("research_pack", "P") is False
    with pytest.raises(TypeError):
        p_view["latest"]["impact_map"] = {}


def test_blackboard_preserves_history_when_same_key_is_appended_again():
    board = Blackboard()

    board.append("P", "impact_map", {"version": 1})
    board.append("D", "impact_map", {"version": 2})

    view = board.view()
    assert len(view["events"]) == 2
    assert view["latest"]["impact_map"]["version"] == 2
    assert board.view("P")["latest"]["impact_map"]["version"] == 1


def test_blackboard_rejects_empty_phase_or_key():
    board = Blackboard()

    with pytest.raises(ValueError, match="blackboard_phase_required"):
        board.append("", "x", 1)
    with pytest.raises(ValueError, match="blackboard_key_required"):
        board.append("P", "", 1)
