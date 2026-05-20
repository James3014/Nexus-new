from __future__ import annotations

from typing import Any, Callable

from nexus.engine.capability_contracts import CapabilityNode


def apply_learning_policy(
    *,
    nodes: dict[str, CapabilityNode],
    states: dict[str, str],
    reasons: dict[str, list[str]],
    learning_policy: dict[str, Any],
    enable: Callable[[str, str], None],
) -> None:
    for name in learning_policy.get("promoted_capabilities", ()) or ():
        cap = str(name)
        if cap in nodes:
            enable(cap, "learning_policy_promoted")
    for name in learning_policy.get("penalized_capabilities", ()) or ():
        cap = str(name)
        if cap not in nodes:
            continue
        reasons[cap].append("learning_policy_penalized")
        if learning_policy.get("enforce_penalties") is True and states.get(cap) == "conditional":
            states[cap] = "optional"
