# Nexus Core V1 Golden Path Campaign

- **Campaign ID:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source basis snapshot:** `James3014/Nexus-new@785751e109e90aa66a87a863dbc223618eceeffd`, tree `79a8dd7b4bb40313e3872491fb5cd0a70bba5ba8`, clean detached snapshot `cd9fcc75416bb599e0783c1b0dbe9f20f1241b6e7c1b79629842859803a242fd`
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-CORE-V1-TG0-FREEZE-RECONCILE`
- **Maximum campaign claim:** `CORE_V1_SPEC_READY_FOR_TASK_CARDS`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| TG-0 Boundary/version/crosswalk freeze | REQ-001;REQ-002;REQ-005;REQ-006;REQ-009 | AC-001;AC-003;AC-006;AC-013;AC-015 | adopted two-core/version/invariant contract plus additive old-card reconciliation | DEC-007 through DEC-013 | static + simulation | `CORE_V1_BOUNDARY_ADOPTED` | medium | not applicable | none | TASK-CORE-V1-TG0-FREEZE-RECONCILE;TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-1 Live GitHub acquisition | REQ-004 | AC-002 | authenticated immutable PR snapshot | TG-0 | live read-only probes | `LIVE_PR_SNAPSHOT_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-2 Python profile | REQ-007 | AC-004 | clean deterministic witness bundle | TG-0 accepted contract | isolated runner matrix | `PYTHON_PROFILE_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG2-PYTHON-PROFILE;TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-3 Evidence Trust extraction | REQ-008 | AC-005 | canonical trust owner consumes TG-1/TG-2 | TG-1 + TG-2 accepted receipts | hostile ingestion tests | `EVIDENCE_TRUST_BOUNDARY_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG3-EVIDENCE-TRUST;TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-4 Durable ledger/reconciliation | REQ-010;REQ-011 | AC-007;AC-008 | idempotent crash-safe receipt history | TG-3 accepted identities | restart/tamper/CAS | `LOCAL_LEDGER_RECONCILIATION_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG4-LEDGER-RECONCILIATION;TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-5 HTTP tracer bullet | REQ-003;REQ-012 | AC-009;AC-014 | real PR to inspectable receipt | TG-1 + TG-2 + TG-3 + TG-4 accepted interfaces | live local E2E plus upstream witness consumption | `REAL_PR_TRACER_BULLET_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG5-HTTP-TRACER |
| TG-6 Thin clients/package | REQ-012;REQ-013 | AC-011;AC-012 | client parity and clean install journey | TG-5 | conformance/install/rollback | `OPERATOR_JOURNEY_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG6-CLIENTS-PACKAGE |
| TG-7 Corpus/second repo | REQ-014 | AC-010 | representative corpus and external shadow | TG-5 plus DER-003 selection | benchmark + shadow | `CROSS_REPO_TRUST_SHADOW_VERIFIED` | medium | not applicable | none | TASK-CORE-V1-TG7-CORPUS-SHADOW;TASK-CORE-V1-TG8-VALUE-GATE |
| TG-8 Protocol maturity | REQ-014 | AC-016 | evidence-gated RC/Stable readiness | TG-6 + TG-7 | compatibility/conformance/upgrade/rollback | bounded protocol-maturity claim | medium | not applicable | none | TASK-CORE-V1-TG8-VALUE-GATE |
| TG-9 Design-partner value | REQ-015 | AC-017 | paired usability and continuation/paid evidence | TG-8 | 3–5 partner, 4–8 week paired experiment | bounded usability/value claim | medium | not applicable | none | TASK-CORE-V1-TG9-VALUE-PILOT |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| REQ-001 | AC-001 | TASK-CORE-V1-TG0-FREEZE-RECONCILE | TASK-CORE-V1-TG0-FREEZE-RECONCILE | FULL |
| REQ-002 | AC-013 | TASK-CORE-V1-TG0-FREEZE-RECONCILE | TASK-CORE-V1-TG0-FREEZE-RECONCILE | FULL |
| REQ-003 | AC-014 | TASK-CORE-V1-TG5-HTTP-TRACER | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-004 | AC-002 | TASK-CORE-V1-TG1-GITHUB-ACQUISITION | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-005 | AC-003 | TASK-CORE-V1-TG0-FREEZE-RECONCILE | TASK-CORE-V1-TG0-FREEZE-RECONCILE | FULL |
| REQ-006 | AC-015 | TASK-CORE-V1-TG0-FREEZE-RECONCILE | TASK-CORE-V1-TG0-FREEZE-RECONCILE | FULL |
| REQ-007 | AC-004 | TASK-CORE-V1-TG2-PYTHON-PROFILE | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-008 | AC-005 | TASK-CORE-V1-TG3-EVIDENCE-TRUST | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-009 | AC-006 | TASK-CORE-V1-TG0-FREEZE-RECONCILE | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-010 | AC-007 | TASK-CORE-V1-TG4-LEDGER-RECONCILIATION | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-011 | AC-008 | TASK-CORE-V1-TG4-LEDGER-RECONCILIATION | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-012 | AC-009 | TASK-CORE-V1-TG5-HTTP-TRACER | TASK-CORE-V1-TG5-HTTP-TRACER | FULL |
| REQ-012 | AC-011 | TASK-CORE-V1-TG6-CLIENTS-PACKAGE | TASK-CORE-V1-TG6-CLIENTS-PACKAGE | FULL |
| REQ-013 | AC-012 | TASK-CORE-V1-TG6-CLIENTS-PACKAGE | TASK-CORE-V1-TG6-CLIENTS-PACKAGE | FULL |
| REQ-014 | AC-010 | TASK-CORE-V1-TG7-CORPUS-SHADOW | TASK-CORE-V1-TG7-CORPUS-SHADOW | FULL |
| REQ-014 | AC-016 | TASK-CORE-V1-TG8-VALUE-GATE | TASK-CORE-V1-TG8-VALUE-GATE | FULL |
| REQ-015 | AC-017 | TASK-CORE-V1-TG9-VALUE-PILOT | TASK-CORE-V1-TG9-VALUE-PILOT | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TASK-CORE-V1-TG0-FREEZE-RECONCILE | ACTIVE | CONTRACT | TRACER_BULLET | none | none | none | adopted two-core/version/invariant contract plus additive old-card reconciliation | static + simulation | `CORE_V1_BOUNDARY_ADOPTED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG1-GITHUB-ACQUISITION | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CORE-V1-TG0-FREEZE-RECONCILE | CONTRACT | TG-0 accepted receipt | authenticated immutable PR snapshot | live read-only probes | `LIVE_PR_SNAPSHOT_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG2-PYTHON-PROFILE | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CORE-V1-TG0-FREEZE-RECONCILE | CONTRACT | TG-0 accepted receipt | clean deterministic witness bundle | isolated runner matrix | `PYTHON_PROFILE_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG3-EVIDENCE-TRUST | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CORE-V1-TG0-FREEZE-RECONCILE;TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG2-PYTHON-PROFILE | CONTRACT;EVIDENCE;EVIDENCE | TG-0 interfaces;TG-1 receipt;TG-2 receipt | canonical trust owner consumes TG-1/TG-2 | hostile ingestion tests | `EVIDENCE_TRUST_BOUNDARY_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG4-LEDGER-RECONCILIATION | PLANNED | IMPLEMENTATION | TRACER_BULLET | TASK-CORE-V1-TG3-EVIDENCE-TRUST | DATA | TG-3 accepted identity receipt | idempotent crash-safe receipt history | restart/tamper/CAS | `LOCAL_LEDGER_RECONCILIATION_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG5-HTTP-TRACER | PLANNED | IMPLEMENTATION | EXPAND_CONTRACT | TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG2-PYTHON-PROFILE;TASK-CORE-V1-TG3-EVIDENCE-TRUST;TASK-CORE-V1-TG4-LEDGER-RECONCILIATION | CONTRACT;CONTRACT;CONTRACT;CONTRACT | TG-1 receipt;TG-2 receipt;TG-3 receipt;TG-4 receipt | real PR to inspectable receipt | live local E2E plus upstream witness consumption | `REAL_PR_TRACER_BULLET_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG6-CLIENTS-PACKAGE | PLANNED | IMPLEMENTATION | EXPAND_CONTRACT | TASK-CORE-V1-TG5-HTTP-TRACER | CONTRACT | TG-5 accepted receipt | client parity and clean install journey | conformance/install/rollback | `OPERATOR_JOURNEY_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG7-CORPUS-SHADOW | PLANNED | INTEGRATION_VERIFY | EXPAND_CONTRACT | TASK-CORE-V1-TG5-HTTP-TRACER | EVIDENCE | TG-5 accepted receipt and DER-003 selection | representative corpus and external shadow | benchmark + shadow | `CROSS_REPO_TRUST_SHADOW_VERIFIED` | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG8-VALUE-GATE | PLANNED | INTEGRATION_VERIFY | EXPAND_CONTRACT | TASK-CORE-V1-TG6-CLIENTS-PACKAGE;TASK-CORE-V1-TG7-CORPUS-SHADOW | EVIDENCE;EVIDENCE | TG-6 accepted receipt;TG-7 accepted report | evidence-gated RC/Stable readiness | compatibility/conformance/upgrade/rollback | bounded protocol-maturity claim | medium | not applicable | NOT_APPLICABLE |
| TASK-CORE-V1-TG9-VALUE-PILOT | PLANNED | INTEGRATION_VERIFY | EXPAND_CONTRACT | TASK-CORE-V1-TG8-VALUE-GATE | EVIDENCE | TG-8 independently accepted protocol-maturity evidence receipt | paired usability and continuation/paid evidence | 3–5 partner, 4–8 week paired experiment | bounded usability/value claim | medium | not applicable | NOT_APPLICABLE |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** TASK-CORE-V1-TG0-FREEZE-RECONCILE
- **Selected frontier:** TASK-CORE-V1-TG0-FREEZE-RECONCILE
- **Selection rationale:** TG-0 is the sole root and freezes the authority/version/crosswalk seam required by every downstream card.
- **Exact unblock condition:** independent acceptance of the TG-0 Candidate verifies AC-001, AC-003, AC-006, AC-013, and AC-015; then TG-1/TG-2 are parallel-ready in separate isolated worktrees, not automatically ACTIVE.

### Parallel orchestration semantics

The machine-validated metadata remains `Parallel execution: false` and `Parallel safe: false` because `AUTO_CHAIN=false`: no card, worker, or scheduler may self-start or infer another task's authority. The Owner's separate parallel campaign contract permits the controller to dispatch TG-1 and TG-2 concurrently as distinct Ready Issues in isolated non-overlapping worktrees after TG-0 acceptance, and later TG-6 and TG-7 after TG-5 acceptance. Physical concurrency is controller-coordinated across independently authorized attempts, never card-driven auto-chain.

### Accepted-source integration contract

An accepted receipt does not move source code. Before every downstream dispatch, the controller must create or verify a clean integration base whose HEAD/tree contains exactly the independently accepted upstream Candidate commits, record the ordered commit/tree set and merge-tree/conflict result, and bind the downstream Issue/worktree to that base. This integration base is evidence transport only: it does not merge `main`, approve a Candidate, or imply release/production truth. Missing, conflicting, or drifted upstream source blocks that downstream dispatch.

## 5. Campaign authority and non-goals

Owner/Campaign controller and CapabilityPlanner retain planning/selection authority. All implementation and evidence-tooling workers are Luna through `DIRECT_DELEGATED`/`NON_MCP`; the controller independently verifies and accepts evidence. TG-1/TG-2 are parallel after TG-0, and TG-6/TG-7 are parallel after TG-5, each in isolated disjoint worktrees. No card grants approval, integration, merge, push, release, deploy, production, Stable, or public/value authority. `AUTO_CHAIN=false`.

## 6. Supersession and change history

Compiled from the validated source on 2026-09-04 after Owner adoption of DEC-007 through DEC-013. Old Local ChangeSet history remains unchanged until TG-0 additive reconciliation. No task is executed by compilation.
