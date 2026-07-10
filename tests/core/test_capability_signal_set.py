from __future__ import annotations

from nexus.core.capability_signal_set import SkillSignalSet as CoreSkillSignalSet
from nexus.engine.capability_contracts import SkillSignalSet as EngineSkillSignalSet


def test_core_skill_signal_set_importable():
    cs = CoreSkillSignalSet()
    assert cs.top_skill_ids == ()


def test_core_skill_signal_set_frozen():
    cs = CoreSkillSignalSet(top_skill_ids=("s1",), skill_confidence=0.9)
    import dataclasses
    assert dataclasses.fields(cs)
    try:
        cs.top_skill_ids = ("s2",)
        assert False, "should be frozen"
    except AttributeError:
        pass


def test_engine_skill_signal_set_still_works():
    es = EngineSkillSignalSet()
    assert es.top_skill_ids == ()


def test_core_skill_signal_set_equal_to_engine():
    cs = CoreSkillSignalSet(top_skill_ids=("a", "b"), skill_confidence=0.8, trust_level="high", source="test")
    es = EngineSkillSignalSet(top_skill_ids=("a", "b"), skill_confidence=0.8, trust_level="high", source="test")
    assert cs.to_dict() == es.to_dict()
