# ARCHIVED 2026-10-16 (nexus-core-rs crate and policies P-GATE-03 / P-FLOW-01)

- Tracking issue: #2359.
- Decision: Owner (James), option A, in chat on 2026-10-16. First retire hard-lane policies P-GATE-03 and P-FLOW-01, then physically delete the Rust crate. This follows #2337 (Go swarm, Issue #2334) and the #2197 route: physical deletion with the `owner-approved-deletion` label.
- The originals are on branch `archive/2026-10-16-rust-crate-retired`, which was cut from `origin/main` 958b991b4 before this change.

## Physically deleted

| Path | Files | Lines | Evidence it was not live |
| --- | ---: | ---: | --- |
| `nexus-core-rs/` | 10 | 1,310 | <ul><li>No workflow, Taskfile target or deploy builds it. The Taskfile cargo targets build `packages/core`.</li><li>The Mac mini deploy tree has no `nexus-core-rs/target`.</li><li>The only live caller was the `nexus/engine/governance_bridge.py` binary lookup. That lookup never found a binary, so `GovernanceBridge` always took its Python contract path.</li></ul> |
| `nexus/bridge/rust_kernel.py` | 1 | 42 | Imported only by `cutover_manager.py` and `tests/integration/test_rust_wave3_cutover.py`. |
| `nexus/bridge/cutover_manager.py` | 1 | 79 | Imported only by `tests/integration/test_capability_existence_155.py`, an existence list. Its `USE_RUST_*` flags defaulted to `"0"`. |
| `generate_full_matrix_report.py` | 1 | 140 | A June Python-vs-Rust parity report script with no caller. Without the binary it can only print "Rust unavailable". |
| `generate_rollback_drill_report.py` | 1 | 177 | Same as above, for the Rust rollback drill report. |
| `scripts/generate-prod-package.sh` | 1 | 39 | Already dead: it copied from a nonexistent `nexus-swarm/`. Flagged LOW in the #2337 review. |
| **Total** | **15** | **1,787** | |

## Retired policies (removed from the manifests)

- The manifests have no `retired`/`status` field. The entries are therefore removed, and the full JSON is recorded below.
- Summary counts in `docs/reports/policy-manifest.v2.json`:
  - `total_policies` 28 → 26, `hard_lane` 11 → 9.
  - `code_backed` 27 → 25, `rollback_drills_total` 27 → 25.
  - `rollback_drills_passing` 4 → 2. This is a static number that no code computes; the two retired policies had real drills on 2026-06-15.
  - `lane_distribution` and `enforcement_mode_distribution` were recomputed; `commit_ref_policy` now says "25 baseline-freeze entries".
- `docs/reports/policy-baseline-manifest.v1.json` (the 2026-06-15 freeze): the same two entries are removed. Its summary goes from 27 to 25, and the `verification_note` records the retirement. P-CONTAM-01's historical v1 text is unchanged.
- `scripts/ops/policy_lane_precommit.py` no longer maps `nexus-core-rs/src/*.rs`, and `scripts/ops/manifest_coverage_check.py` no longer lists `nexus-core-rs/src/`.

v2 entries as of 958b991b4:

```json
[
  {
    "policy_id": "P-GATE-03",
    "phase": "Rust-Kernel",
    "owner_module": "receipt_verifier",
    "source_file": "nexus-core-rs/src/receipt_verifier.rs",
    "schema_version": "v1.0",
    "commit_sha": "1c9dce65",
    "verified_in_pr": null,
    "status_tag": "code-backed",
    "enforcement_mode": "block",
    "test_entrypoints": [
      "nexus-core-rs/src/receipt_verifier.rs::tests (11 tests)"
    ],
    "receipt_type": "ReceiptVerificationResult",
    "rollback_drill_status": "drilled-2026-06-15",
    "promotion_allowed": false,
    "lane": "hard",
    "risk_tier": "critical",
    "authority_impact": "evidence",
    "claim_impact": "claim-gated",
    "cutover_impact": "cutover-gated",
    "override_mode": "blocked",
    "expiry": null,
    "version_history": [
      {
        "version": "P-GATE-03.1.0.0",
        "timestamp": "2026-06-15T00:00:00Z",
        "diff_summary": "Baseline freeze — hardened with SHA-256 + canonical JSON",
        "lane": "hard"
      }
    ]
  },
  {
    "policy_id": "P-FLOW-01",
    "phase": "Rust-Kernel",
    "owner_module": "flow_machine",
    "source_file": "nexus-core-rs/src/flow_machine.rs",
    "schema_version": "v1.0",
    "commit_sha": "1c9dce65",
    "verified_in_pr": null,
    "status_tag": "code-backed",
    "enforcement_mode": "block",
    "test_entrypoints": [
      "nexus-core-rs/src/flow_machine.rs::tests (27 tests)",
      "tests/integration/test_rust_wave3_cutover.py"
    ],
    "receipt_type": "TransitionValidation",
    "rollback_drill_status": "drilled-2026-06-15",
    "promotion_allowed": false,
    "lane": "hard",
    "risk_tier": "critical",
    "authority_impact": "transition",
    "claim_impact": "none",
    "cutover_impact": "cutover-gated",
    "override_mode": "blocked",
    "expiry": null,
    "version_history": [
      {
        "version": "P-FLOW-01.1.0.0",
        "timestamp": "2026-06-15T00:00:00Z",
        "diff_summary": "Baseline freeze — full 14-state matrix, fail-closed",
        "lane": "hard"
      }
    ]
  }
]```

## Kept test ids (assert the retired state)

- `tests/integration/test_rust_wave3_cutover.py`: the same four test ids. They now check that the crate and the bridge are gone, that P-FLOW-01 is not a policy, and that `GovernanceBridge` falls back to Python.
- `tests/integration/test_capability_existence_155.py`: the `cutover_manager` and `rust_kernel` cases stay and assert `ModuleNotFoundError`.
- `tests/delivery/test_suggestions.py` and `tests/test_cli_thinning.py`: the same ids, with no `nexus-core-rs` sub-crate cargo hint.
- `tests/ops/test_policy_lane_gate.py`, `tests/ops/test_policy_manifest_schema.py` and `tests/integration/test_policy_lane_integration.py`: same ids.
  - P-CLAIM-02 (hard, drilled, block) is now the generic hard-lane example. P-DELIVERY-01 is the cutover example.
  - `test_evidence_family_passes_with_drill` and `test_flow_family_passes_with_drill` now assert `POLICY_NOT_FOUND`.
- `tests/nightly_quarantine_items/tests_integration_test_rust_kernel_smoke.py` stays. It is already a tombstone (`ENTRY = None`), and the package convention forbids deleting entry files.
- Guard test: `tests/ops/test_retired_rust_crate_removed.py`.

## Follow-up (not in this PR)

`.github/workflows/policy-lane-gate.yml` still watches `nexus-core-rs/src` on L12, L24 and L97. These watches are now inert. The coordinator will remove them in a separate owner-credential PR, which the Owner has approved.
