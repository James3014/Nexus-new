from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from nexus.core.capability_constraints import CapabilityConstraints
from nexus.services.prompt_builder import PromptBuilder


def _signal() -> SimpleNamespace:
    return SimpleNamespace(task_desc="regular coding task")


def _palace(constraints: dict) -> MagicMock:
    palace = MagicMock()
    palace.verify_context.return_value = {"status": "ALLOWED"}
    palace.get_skill_constraints.return_value = constraints
    return palace


def _builder(constraints: dict) -> PromptBuilder:
    builder = PromptBuilder.__new__(PromptBuilder)
    builder.mem_palace = _palace(constraints)
    return builder


def test_unavailable_source_is_carried_in_constraint_result(tmp_path):
    palace = _palace({
        "forbid": ["no shell"],
        "require": [],
        "prefer": [],
        "constraints_source": "unavailable",
        "constraints_unavailable_reason": "table_read_failed",
    })
    verdict = CapabilityConstraints(str(tmp_path), mem_palace=palace).evaluate_constraints(
        _signal()
    )

    assert verdict["status"] == "ALLOWED"
    assert verdict["constraints_source"] == "unavailable"
    assert verdict["constraints_unavailable_reason"] == "table_read_failed"
    assert verdict["forbidden_skills_rules"] == ["no shell"]


def test_ok_and_legacy_source_default_to_ok(tmp_path):
    palace = _palace({"forbid": [], "require": [], "prefer": []})
    verdict = CapabilityConstraints(str(tmp_path), mem_palace=palace).evaluate_constraints(
        _signal()
    )
    assert verdict["constraints_source"] == "ok"
    assert verdict["constraints_unavailable_reason"] == ""
    assert verdict["status"] == "ALLOWED"


def test_prompt_context_flags_unavailable_but_not_ok():
    unavailable = _builder({
        "forbid": [],
        "require": [],
        "prefer": [],
        "constraints_source": "unavailable",
        "constraints_unavailable_reason": "table_read_failed",
    })._get_ethical_constraints()
    assert "Belief constraints unavailable: table_read_failed" in unavailable
    assert "Constitutional Firewall Clean" not in unavailable

    ok = _builder({
        "forbid": [],
        "require": [],
        "prefer": [],
        "constraints_source": "ok",
    })._get_ethical_constraints()
    assert ok == "None (Constitutional Firewall Clean)"

    with_rules = _builder({
        "forbid": ["x"],
        "require": [],
        "prefer": [],
        "constraints_source": "ok",
    })._get_ethical_constraints()
    assert "unavailable" not in with_rules
    assert "- x" in with_rules
