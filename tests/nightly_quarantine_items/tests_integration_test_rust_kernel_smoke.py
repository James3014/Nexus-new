"""Nightly quarantine entry: tests/integration/test_rust_kernel_smoke.py (#1927). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_rust_kernel_smoke.py",
    "disposition": "quarantine",
    "issue": "#1927",
    "cause": "needs the Rust nexus_core extension (target/release), which the nightly runner does not build; decide build-in-CI or delete",
    "tests": (
        "test_rust_kernel_contamination_check",
        "test_rust_kernel_replay_verification",
        "test_rust_kernel_slice_validation",
    ),
}
