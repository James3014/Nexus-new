# D2 Report Retention Governance Baseline Closure

**status: D2_REPORT_RETENTION_GOVERNANCE_BASELINE_CLOSED**

## Start-state

- Start HEAD: `b1bcdead4688ebf624818b82acaba522ba4def80`
- End pre-commit HEAD: `b1bcdead4688ebf624818b82acaba522ba4def80`
- Required D2 commits in ancestry:
  - `37c1bbc3d` ops: restore report retention generator
  - `0cb49f4d0` docs: regenerate report retention inventory
  - `f43ef5b5e` ops: externalize report retention policy
  - `f10000b55` ops: enforce report retention policy authority

## Scope completed

| Phase | Commit | Description |
|---|---|---|
| D2-G1R | `37c1bbc3d` | Generator Recovery — restored truncated generator to 362 lines |
| D2-G2 | `0cb49f4d0` | Formal Inventory Regeneration — deterministic fixed-point inventory |
| D2-G3 | `f43ef5b5e` | Policy Externalization — moved CURRENT_KEEP_FILES, RAW_HINTS, ACTIVE_WORKSTREAM_PATTERNS to manifest |
| D2-G3C | `f10000b55` | Policy Authority Closure — repository-default execution fails closed without manifest |
| D2-C1 | this commit | Current-Corpus Seal — final deterministic inventory/plan pair |

## Final authority chain

```
report_area_manifest.json
  -> nested report-area classification authority

report_retention_policy_manifest.json
  -> root retention/exclusion policy authority

build_report_retention_inventory.py
  -> deterministic inventory generator (policy-authoritative)

NEXUS_REPORT_RETENTION_INVENTORY_2026-05-22.json
  -> machine-readable current snapshot

NEXUS_REPORT_RETENTION_PLAN_2026-05-22.md
  -> human-readable current snapshot
```

## Final evidence

- Focused tests: 21 passed
- Direct CLI: status=PASS, dry_run=True, rows=2081
- Module CLI: status=PASS, dry_run=True, rows=2081
- Missing-policy negative test: exit=1, FileNotFoundError
- Generation runs for convergence: 3
- Final JSON hash: `9f79d61eef4f20bfce672279fd60e3a229f44256b379758b06b780767431500c`
- Final Plan hash: `d8ac77a372dc3d2efe57e08ab42456ec7b29498a5f7f2b159629e395b70b9de6`
- Final row count: 2081
- Excluded count: 49
- Total report files: 2130
- Corpus fingerprint before: `28588ba82bbe573047ce6e5186952ce7350800889492929e76a518d42c228392`
- Corpus fingerprint after: `28588ba82bbe573047ce6e5186952ce7350800889492929e76a518d42c228392`
- Corpus unchanged: YES
- Fixed-point convergence: PASS (run 2 == run 3)
- Deletion audit: no deleted files

### Area counts

| Area | Count |
|---|---|
| root | 1326 |
| unknown | 27 |
| archive | 670 |
| experiment | 20 |
| generated | 19 |
| asset | 11 |
| handoff | 8 |

### Retention class counts

| Class | Count |
|---|---|
| unknown_hold | 1217 |
| historical_preserved | 670 |
| keep_review | 71 |
| archive_candidate | 26 |
| keep_current_entrypoint | 26 |
| experiment_evidence | 20 |
| generated_evidence | 19 |
| keep_human_entrypoint | 13 |
| supporting_asset | 11 |
| bounded_handoff | 8 |

### Topic counts

| Topic | Count |
|---|---|
| UNKNOWN_HOLD | 1354 |
| SF | 649 |
| HEEP | 37 |
| PUBLIC_CLAIM | 16 |
| ENGINEERING_HYGIENE | 12 |
| OPTIMIZATION | 9 |
| LEGACY | 4 |

## Closure boundary

D2 establishes a reproducible, policy-authoritative, non-destructive report-retention governance baseline.

D2 does not assert that all reports have been manually reviewed.

D2 does not assert that reports have been deduplicated, archived, moved, renamed, or deleted.

Inventory schema v2 is not required for D2 closure.

Duplicate metadata is not required for D2 closure.

Schema v2 and duplicate detection remain optional future enhancements and must be justified by a concrete consumer or operational bottleneck before implementation.

## Transition

Per the latest Nexus roadmap, the next mainline should return to:

**N30R / Hybrid Runtime value proof**

Report retention tooling is closed. Runtime execution is the next priority.
