"""Nightly quarantine entry: tests/benchmark/test_p12_replay.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the manifest/bundle tests read the real P12 replay evidence committed under tests/fixtures/host_evidence_1926/; test_missing_controls_taxonomy now asserts the current missing_signal_snapshot contract (also covered by test_capability_ab_runner::test_local_model_adapter_missing_controls).
ENTRY = None
