"""Online A/B 20261013b finding 1: the with_nexus prompt must tell the model not to use tools.

Headless agy auto-denies tool calls; without the instruction Gemini tried RunCommand and
returned empty stdout on every with_nexus call while the bare arm (which always had the
instruction) answered.
"""

from __future__ import annotations

from typing import Any, Mapping

from nexus.services.online_nexus_context import (
    build_online_nexus_context,
    make_with_nexus_online_invoker,
)

NO_TOOLS_TEXT = "Do not use any tools (no commands, no file reads, no file writes). Answer directly in this reply."


def test_with_nexus_prompt_carries_no_tools_instruction_before_task() -> None:
    ctx = build_online_nexus_context(
        task_statement="fix duplicate events in apply_events",
        task_id="ab-notools-001",
        base_prompt="Return JSON.",
    )

    assert NO_TOOLS_TEXT in ctx.prompt
    assert ctx.prompt.index(NO_TOOLS_TEXT) < ctx.prompt.index("[TASK]")
    assert ctx.lineage["no_tools_instruction"] == "online_no_tools_v1"


def test_armored_invoker_sends_no_tools_instruction_to_transport() -> None:
    seen: dict[str, Any] = {}

    def transport(context: Mapping[str, Any]) -> dict[str, Any]:
        seen["online_prompt"] = context["online_prompt"]
        return {"response": "{}", "raw_response": "{}"}

    invoker = make_with_nexus_online_invoker(transport, provider="agy")
    invoker({
        "task_id": "ab-notools-002",
        "task_statement": "fix duplicate events",
        "task_type": "repair",
        "online_prompt": "Return JSON.",
        "route": {"recommended_flow": "direct"},
        "planner": {"selected_capabilities": ["claim_gate"], "plan_hash": "plan-notools"},
        "local": {"invoked": False},
        "capability_results": {},
    })

    assert NO_TOOLS_TEXT in seen["online_prompt"]
