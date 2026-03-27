from pathlib import Path


def test_gate_ladder_includes_migration_safety_validator():
    script = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "gate_ladder.sh"
    text = script.read_text(encoding="utf-8")
    assert "L0.5: migration safety validator" in text
    assert "scripts/core/migration_safety_validator.py" in text
    assert "NEXUS_MIGRATION_CHECK_SCOPE" in text
