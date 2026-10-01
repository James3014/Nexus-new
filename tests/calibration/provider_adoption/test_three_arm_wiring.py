"""Tests for Canonical Benchmark Wiring and Pre-Three-Arm Qualification Isolation.

Invariants:
1. PROVIDER_ADOPTION_EXPERIMENT_V1 is a pre-three-arm qualification gate.
2. Unqualified or blocked candidates (like Apple FM whose license is not agreed) MUST NOT
   be prematurely registered in nexus/config/model_three_arm_matrix.yaml.
3. Every transport registered in the canonical three-arm matrix MUST have a real, verified
   dispatcher in scripts/bench/experimental/model_workforce_three_arm.py.
4. apple_fm_cli cannot be registered into canonical matrix while canonical harness cannot dispatch it.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "nexus/config/model_three_arm_matrix.yaml"
THREE_ARM_HARNESS_PATH = REPO_ROOT / "scripts/bench/experimental/model_workforce_three_arm.py"

CANONICAL_HARNESS_SUPPORTED_TRANSPORTS = {
    "codex_cli",
    "agy_cli",
    "grok_cli",
    "gemini_cli",
    "opencode_cli",
    "mimo_cli",
    "ollama_http",
}


def _load_canonical_matrix() -> dict:
    assert MATRIX_PATH.is_file(), f"Canonical matrix not found: {MATRIX_PATH}"
    payload = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_canonical_matrix_does_not_contain_unqualified_apple_fm():
    """Verify Apple FM is not prematurely enrolled in canonical three-arm matrix."""
    data = _load_canonical_matrix()
    models = data.get("models", {})
    assert "apple_fm_local" not in models, (
        "apple_fm_local must NOT be enrolled in canonical model_three_arm_matrix.yaml "
        "before passing the provider adoption qualification gate."
    )
    for model_id, spec in models.items():
        assert spec.get("transport") != "apple_fm_cli", (
            f"Model '{model_id}' registered with un-dispatchable transport 'apple_fm_cli' in canonical matrix."
        )


def test_negative_control_apple_fm_cli_rejected_by_canonical_harness_dispatch():
    """Negative control: apple_fm_cli cannot be registered into canonical matrix while harness cannot dispatch it."""
    import importlib.util
    import sys

    module_name = "model_workforce_three_arm_test"
    spec = importlib.util.spec_from_file_location(module_name, THREE_ARM_HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    harness_mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = harness_mod
    try:
        spec.loader.exec_module(harness_mod)

        # Construct an Apple FM model spec
        apple_fm_spec = harness_mod.ModelSpec(
            model_id="apple_fm_local",
            cohort="discovery",
            provider="apple_fm",
            transport="apple_fm_cli",
            model="default",
            timeout_sec=120.0,
            resource_tier="local_light",
        )

        # In canonical harness, _binary_for returns empty string for apple_fm_cli
        binary = harness_mod._binary_for(apple_fm_spec)
        assert binary == "", (
            "Harness unexpectedly resolved a binary for unsupported apple_fm_cli transport."
        )

        # And _subprocess_command returns []
        cmd = harness_mod._subprocess_command(apple_fm_spec, "test prompt", Path("/tmp"))
        assert cmd == [], "Harness returned a command for unsupported apple_fm_cli transport."

        # Verify that canonical matrix does NOT contain apple_fm_cli
        matrix_data = _load_canonical_matrix()
        registered_transports = {m.get("transport") for m in matrix_data.get("models", {}).values()}
        assert "apple_fm_cli" not in registered_transports, (
            "apple_fm_cli cannot be registered into canonical matrix while canonical harness cannot dispatch it"
        )
    finally:
        sys.modules.pop(module_name, None)
