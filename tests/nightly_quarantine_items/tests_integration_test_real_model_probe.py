"""Nightly quarantine entry: tests/integration/test_real_model_probe.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_real_model_probe.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "host-only probe: real_model mode needs a local Qwen backend and a prepared astropy workspace (run_pack workspace_root / NEXUS_JUNE_REGRESSION_WORKSPACE_ROOT); a skip gate was dropped from #2031 because the exact-base impact gate rejects a new head-only SKIP, so gating it is an owner decision",
    "tests": ("test_real_model_wiring_probe_contract",),
}
