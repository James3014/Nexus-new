"""Nightly quarantine entry: tests/contract/test_boundary_compliance.py (#1927). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/contract/test_boundary_compliance.py",
    "disposition": "quarantine",
    "issue": "#1927",
    "cause": "needs the Rust nexus_core extension (target/release), which the nightly runner does not build; decide build-in-CI or delete",
    "tests": (
        "TestBoundaryCompliance::test_error_transparency_from_rust_to_python",
        "TestBoundaryCompliance::test_minimal_interface_leaks",
        "TestBoundaryCompliance::test_transition_matrix_closed_loop",
    ),
}
