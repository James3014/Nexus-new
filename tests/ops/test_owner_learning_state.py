from pathlib import Path

import pytest

from scripts.ops.owner_learning_state import (
    LedgerContractError,
    build_projection,
    projection_json,
)


def _ledger(*, priorities: int = 3, level: str = "UNASSESSED", events: str = "") -> str:
    priority_lines = "\n".join(f"{idx}. **P{idx}** — detail" for idx in range(1, priorities + 1))
    return f"""# Ledger

## Current Learning State — bounded bootstrap projection

### Current priority frontiers — maximum three

{priority_lines}

### Domain-level mastery view

| Architecture domain | Current level | Evidence boundary | Next useful real case |
|---|---|---|---|
| Domain A | {level} | Evidence A | Next A |
| Domain B | L1 | Evidence B | Next B |

### Existing subtopic evidence that remains valid as historical baseline

Historical detail.

## Mastery scale

{events}
"""


def test_projection_is_deterministic_and_uses_only_explicit_state() -> None:
    text = _ledger()

    first = projection_json(text, source="ledger.md")
    second = projection_json(text, source="ledger.md")

    assert first == second
    projection = build_projection(text, source="ledger.md")
    assert projection["priorities"] == ["P1", "P2", "P3"]
    assert [row["level"] for row in projection["domains"]] == [
        "UNASSESSED",
        "L1",
    ]


def test_projection_rejects_more_than_three_priorities() -> None:
    with pytest.raises(LedgerContractError, match="maximum is 3"):
        build_projection(_ledger(priorities=4), source="ledger.md")


def test_projection_rejects_unknown_mastery_level() -> None:
    with pytest.raises(LedgerContractError, match="unsupported mastery level"):
        build_projection(_ledger(level="L5"), source="ledger.md")


def test_projection_rejects_duplicate_event_ids() -> None:
    events = """### LA-20260915-001 — first

### LA-20260915-001 — duplicate
"""
    with pytest.raises(LedgerContractError, match="duplicate learning-event IDs"):
        build_projection(_ledger(events=events), source="ledger.md")


def test_projection_rejects_missing_current_state() -> None:
    with pytest.raises(LedgerContractError, match="expected exactly one"):
        build_projection("# Ledger\n\n## Mastery scale\n", source="ledger.md")


def test_repository_ledger_satisfies_projection_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    ledger = root / "docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md"

    projection = build_projection(ledger.read_text(encoding="utf-8"), source=ledger.as_posix())

    assert projection["schema"] == "owner_learning.current_state.v1"
    assert len(projection["priorities"]) <= 3
    assert len(projection["domains"]) == 6
    assert all(
        row["level"] in {"UNASSESSED", "L0", "L1", "L2", "L3", "L4"}
        for row in projection["domains"]
    )
