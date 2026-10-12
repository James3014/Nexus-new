from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_l0_keeps_authority_and_uses_conditional_load_map():
    agents = _read("AGENTS.md")
    for token in (
        "active Git-tracked Task Card",
        "docs/agents/TASK_EXECUTION_CONTRACT.md",
        "compact machine Workforce\n  Admission",
        "docs/agents/WORKFORCE_EXECUTION_OVERLAY.md",
        "docs/agents/CLAIM_AND_RECEIPT_OVERLAY.md",
        "docs/agents/LEARNING_WRITEBACK_OVERLAY.md",
        "CapabilityPlanner",
        "HARD_BLOCK",
        "DIRECT_DELEGATED",
    ):
        assert token in agents
    for legacy_scope in ("max_files_touched", "allowed_paths", "forbidden_paths", "Tool Execution Rules"):
        assert legacy_scope not in agents


def test_overlays_have_current_metadata_and_no_second_router():
    names = (
        "TASK_EXECUTION_CONTRACT.md",
        "WORKFORCE_EXECUTION_OVERLAY.md",
        "CLAIM_AND_RECEIPT_OVERLAY.md",
        "LEARNING_WRITEBACK_OVERLAY.md",
    )
    for name in names:
        text = _read(f"docs/agents/{name}")
        assert "artifact_authority: current" in text
        assert "owner: James Chen" in text
        assert "status: active" in text
    workforce = _read("docs/agents/WORKFORCE_EXECUTION_OVERLAY.md")
    assert "create a router" in workforce
    assert "second router" not in workforce.lower()


def test_full_policy_loading_is_conditional():
    agents = _read("AGENTS.md")
    workforce = _read("docs/agents/WORKFORCE_EXECUTION_OVERLAY.md")
    assert "full policy/YAML only" in agents
    assert "only when changing provider/model" in workforce
    assert "for normal model work" in workforce.lower()
    assert "must read" not in agents.lower()


def test_muse_remains_response_overlay_only():
    muse = _read("MUSE_PROTO.md").lower()
    assert "response-compression" in muse
    assert "does not authorize repository mutation" in muse
    assert "workforce roster" not in muse
    assert "route decisions" not in muse


def test_context_budget_is_bounded_by_bytes_and_semantics():
    # AGENTS.md is loaded at every agent start; 12 KB keeps it well inside the
    # 24 KB rule-file loader limit (#1341).
    assert (ROOT / "AGENTS.md").stat().st_size <= 12_000
    # Overlays are read on demand per the load map, not loaded at start, so the
    # loader limit does not apply. These caps only stop unbounded growth:
    # current size plus about 10% headroom, set by Owner decision in #1858.
    overlay_caps = {
        "TASK_EXECUTION_CONTRACT.md": 36_000,
        "WORKFORCE_EXECUTION_OVERLAY.md": 4_000,
        "CLAIM_AND_RECEIPT_OVERLAY.md": 4_000,
        "LEARNING_WRITEBACK_OVERLAY.md": 4_000,
    }
    sizes = {name: (ROOT / "docs/agents" / name).stat().st_size for name in overlay_caps}
    for name, cap in overlay_caps.items():
        assert sizes[name] <= cap, (name, sizes[name], cap)
    assert sum(sizes.values()) <= 42_000
    assert "active Git-tracked Task Card" in _read("AGENTS.md")
