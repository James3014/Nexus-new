from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReplanTrigger(str, Enum):
    ACCEPTANCE_REJECT = "acceptance_reject"
    TIMEOUT = "timeout"
    LOW_BELIEF = "low_belief"
    TRUST_MISMATCH = "trust_mismatch"
    NONE = "none"


def should_replan(state: dict[str, Any], reason: str = "") -> tuple[bool, ReplanTrigger]:
    if reason:
        try:
            trigger = ReplanTrigger(reason.lower())
        except ValueError:
            trigger = ReplanTrigger.NONE
    else:
        trigger = ReplanTrigger.NONE

    if trigger == ReplanTrigger.ACCEPTANCE_REJECT:
        return True, trigger
    if trigger == ReplanTrigger.TIMEOUT:
        return True, trigger
    if trigger == ReplanTrigger.LOW_BELIEF:
        return True, trigger
    if trigger == ReplanTrigger.TRUST_MISMATCH:
        return True, trigger

    belief = float(state.get("belief_confidence", 1.0) or 1.0)
    if belief < 0.3:
        return True, ReplanTrigger.LOW_BELIEF
    return False, ReplanTrigger.NONE
