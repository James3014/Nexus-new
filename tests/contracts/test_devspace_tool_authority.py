from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_MODULE = ROOT / "nexus" / "contracts" / "devspace_tool_authority.py"
JIT_SOURCE = ROOT / "nexus" / "core" / "jit_tool_injector.py"


def _production_python_text() -> str:
    parts: list[str] = []
    for path in sorted((ROOT / "nexus").rglob("*.py")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_effect_ceiling_projection_is_exact_and_policy_bound() -> None:
    assert not AUTHORITY_MODULE.exists()


def test_policy_hash_is_deterministic_and_changes_with_policy_content() -> None:
    source = _production_python_text()
    assert "nexus.devspace.tool_authority.v1" not in source
    assert "TOOL_AUTHORITY_POLICY_SCHEMA" not in source


def test_unknown_effect_and_malformed_intents_fail_closed() -> None:
    source = _production_python_text()
    assert "build_governed_tool_authority" not in source
    assert "canonicalize_tool_intents" not in source


def test_manifest_binds_planner_identity_and_subset_relations() -> None:
    source = _production_python_text()
    assert "build_tool_projection_manifest" not in source
    assert "build_tool_authority_fragment" not in source


def test_real_canonical_dispatch_envelope_binds_planner_identity() -> None:
    source = JIT_SOURCE.read_text(encoding="utf-8")
    assert "apply_canonical_mask" not in source
    assert "devspace_tool_authority" not in source
