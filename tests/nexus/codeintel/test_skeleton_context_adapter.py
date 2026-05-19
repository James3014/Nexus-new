from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.skeleton_context_adapter import build_code_skeleton_context


def test_skeleton_context_adapter_builds_bounded_context_with_rationale(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "# WHY: preserve the hard gate before dispatch\n"
        "def route(value):\n"
        "    \"\"\"Route a value.\"\"\"\n"
        "    return value\n",
        encoding="utf-8",
    )

    payload = build_code_skeleton_context(tmp_path, ["route"])

    assert payload["status"] == "PASS"
    assert payload["ast_graph_freshness_status"] == "FRESH"
    assert payload["kept_symbol_count"] == 1
    assert payload["kept_symbols"][0]["symbol"] == "mod.route"
    assert "WHY: preserve the hard gate before dispatch" in payload["kept_symbols"][0]["rationale_context"]
    assert payload["estimated_tokens"] > 0


def test_skeleton_context_adapter_returns_when_lookups_find_no_symbols(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")

    payload = build_code_skeleton_context(tmp_path, ["missing"])

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == ["no_symbols_found"]
