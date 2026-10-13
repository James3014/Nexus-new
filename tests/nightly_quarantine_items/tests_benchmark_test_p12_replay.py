"""Nightly quarantine entry: tests/benchmark/test_p12_replay.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/benchmark/test_p12_replay.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: test_p12_manifest_parser and test_bundle_summary_keys audit the generated, gitignored artifacts/runtime/local_model_armor_p12_real_june_b_replay_v0 bundle; test_missing_controls_taxonomy is not host state, it is stale (the legacy adapter path never supplies route_context.signal_snapshot, so it returns missing_signal_snapshot instead of missing_required_control) and needs an owner fix-or-delete decision",
    "tests": (
        "test_bundle_summary_keys",
        "test_missing_controls_taxonomy",
        "test_p12_manifest_parser",
    ),
}
