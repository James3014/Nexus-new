"""Nightly quarantine entry: tests/ops/test_nexus_pre_flash_gate.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_nexus_pre_flash_gate.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "reads gitignored .nexus/reports/autodata flash/pro manifests that exist in no clean checkout (CI included); needs committed fixtures or an Owner decision on the real-manifest gate",
    "tests": ("test_benchmark_autodata_manifest_gate_accepts_real_flash_and_pro_manifests",),
}
