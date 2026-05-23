from __future__ import annotations

from pathlib import Path

from nexus.core.context_text_store import (
    DEFAULT_PROGRAM_RULES,
    ContextTextStore,
)


def test_context_text_store_loads_program_rules_with_default_fallback(tmp_path: Path) -> None:
    store = ContextTextStore(tmp_path)
    rules_path = tmp_path / "program.md"

    assert store.load_program_rules(str(rules_path)) == DEFAULT_PROGRAM_RULES

    rules_path.write_text("keep rules local", encoding="utf-8")

    assert store.load_program_rules(str(rules_path)) == "keep rules local"


def test_context_text_store_loads_last_handoff_and_degrades_on_invalid_json(tmp_path: Path) -> None:
    store = ContextTextStore(tmp_path)
    handoff_path = tmp_path / ".nexus" / "state" / "last_handoff.json"
    handoff_path.parent.mkdir(parents=True)

    assert store.load_last_handoff() == {}

    handoff_path.write_text(
        '{"task_id": "ctx-store", "phase": "X", "state_token": "TOKEN"}',
        encoding="utf-8",
    )

    assert store.load_last_handoff() == {
        "task_id": "ctx-store",
        "phase": "X",
        "state_token": "TOKEN",
    }

    handoff_path.write_text("{not-json", encoding="utf-8")

    assert store.load_last_handoff() == {}
