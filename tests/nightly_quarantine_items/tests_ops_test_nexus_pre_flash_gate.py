"""Nightly quarantine entry: tests/ops/test_nexus_pre_flash_gate.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_nexus_pre_flash_gate.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": (
        "test_benchmark_autodata_manifest_gate_accepts_real_flash_and_pro_manifests",
        "test_quick_payload_includes_brain_hub_coverage_gate",
        "test_quick_payload_skips_flash_style_repair_subset",
    ),
}
