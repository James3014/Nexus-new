# Nexus Local 7B Repair Execution Hardening — Complete Session Report

**Date**: 2026-06-20
**Branch**: `feature/bridge-fastmatcher-20260606`
**Final HEAD**: `3db79437`
**Session Status**: V7-A approval packet ready, V7-B awaiting owner approval

---

## Executive Summary

This session transformed Nexus from a worktree-cleanup state into a validated local 7B repair evidence handling system with automated compliance checking, multi-model evaluation, AST context slicing, patch protocol hardening, trace export schema, and productization boundary documentation.

### Key Achievements

| Milestone | Status | Evidence |
|-----------|--------|----------|
| Roadmap v3 Execution Hardening | ✅ Complete | 6 phases, FUZZY precedence fix |
| V4-A Three-Lane Validation | ✅ 3 real tasks | MC001, MC006, MC008 |
| V4-B Controlled Expansion | ✅ 6 real tasks | 3 lanes stable |
| V4-C Operations Readiness | ✅ Runbook + Checker | 10 gates, 15 tests |
| V4-D 14B Evaluation | ✅ Policy defined | 7B=DEFAULT, 14B=FALLBACK |
| V4-E 3B Auxiliary | ✅ Feasibility confirmed | Advisory only |
| V4-F Dogfood Design | ✅ Ready | Awaiting owner approval |
| V4-G Productization Boundary | ✅ Defined | Internal-only, no public claims |
| V5-A AST Context Slicing | ✅ Plan + Prototype | context_slicer.py, 8 tests |
| V5-B Patch Protocol Adapter | ✅ Strict diff contract | patch_protocol.py, 9 tests |
| V5-C Trace Export Schema | ✅ Internal-audit-only | trace_export.py, 9 tests |
| V5-D AST/Protocol Dry-Run | ✅ 3 tasks validated | No regressions |
| V5-E Dogfood Readiness | ✅ All tooling in place | Awaiting owner approval |
| V5-F Dogfood Execution | ✅ Planned | Awaiting owner approval |
| V6-A Distillation Feasibility | ✅ Not ready for training | Insufficient traces |
| V6-B SCoRe Loop Design | ✅ Design documented | No implementation yet |
| V7-A Dogfood Approval Packet | ✅ Ready | artifacts/runtime/v7a_dogfood_execution_approval_packet_v0/ |

---

## Commit History

```
3db79437 docs: V5-A through V6-B — AST slicing, patch protocol, trace schema, dry-run, dogfood, distillation feasibility, SCoRe design
530ca93b docs: V4-D.3+E.0+E.1+F.0+G.0 — 14B guard, 3B feasibility, dogfood design, productization boundary
3f83b406 feat: V4-C.4 CLI entry point + is_pass property — operator compliance check tool
806d0ec8 feat: V4-C.2+C.3 compliance checker + backfill audit — 15 tests pass, 6 artifacts audited, no governance violations
379cba43 feat: V4-C.2 runbook compliance checker — 15 tests pass, attribution/governance/model policy enforcement
a48d8d53 docs: V4-D.2 14B strict prompt acceptance — 7B default, 14B fallback candidate
9cc337a3 feat: V4-D.1 14B format compliance — recovered with strict prompt, format-only failure
67fa79b5 feat: V4-D 14B comparison — no clear gain over 7B, governance preserved
c62c05df docs: V4-C.1 internal repair runbook — 10 gates, receipt schema, stop rules, example traces
4ba203ea docs: V4-C operations readiness planning — internal workflow, gates, receipt schema, stop rules
bea45611 docs: V4-B final controlled expansion acceptance — 6 real tasks, 3 lanes stable
4f786ede feat: V4-B.3 V4B_13579 env-sensitive — human_review_required classification stable
e71ef720 feat: V4-B.2 V4B_12481 canonical recovery — CANONICAL_RECOVERY lane stable
66a67ead feat: V4-B.1 MC007 direct patch — VERBATIM model_patch_success, lane stable
3566e2de docs: V4-B controlled expansion task selection — 3 new tasks across 3 lanes
ab4e87a6 docs: V4-A final three-lane capability acceptance — freeze V4-A milestone before V4-B expansion
```

---

## Phase Details

### Roadmap v3 — Execution Hardening (6 phases)

| Phase | Commit | Change | Tests |
|-------|--------|--------|-------|
| 0 | `c54d730a` | Re-anchor report | N/A |
| 1 | `b8743f45` | MatchAuthority invariant — multi-intent authority fix + success_attribution | 17/17 |
| 2 | `7c9b8cce` | MicroVerifier task-scoped — env_taxonomy integration, fail-closed | 9/9 |
| 3 | `8e3faa6d` | StructuredPacket wiring — all failure types | 9+19 |
| 4 | `e8ffffce` | Export eligibility — 6 classification buckets | 22/22 |
| 5 | `1084b777` | Claim separation — internal capability statement | N/A |

**Key Bug Fix**: `FUZZY_CANDIDATE_ONLY` precedence — caller-passed `match_authority` now takes precedence over intent-derived authority.

### V4-A — Three-Lane Validation (3 real tasks)

| Task | Lane | match_authority | success_attribution | export_classification |
|------|------|-----------------|--------------------|-----------------------|
| MC001 astropy-13236 | verifier_passed_by_execution | verbatim | model_patch_success | model_patch_success_candidate |
| MC006 sympy-13852 | canonical_recovery_success | canonical_recovery | canonical_recovery_success | canonical_recovery_success |
| MC008 astropy-14182 | env_blocked_but_review_verified | null | null | human_review_required |

### V4-B — Controlled Expansion (3 more tasks)

| Task | Lane | match_authority | Status |
|------|------|-----------------|--------|
| MC007 astropy-12907 | verifier_passed_by_execution | verbatim | V4B1_DIRECT_PATCH_PASS |
| V4B_12481 sympy-12481 | canonical_recovery_success | canonical_recovery | V4B2_CANONICAL_RECOVERY_PASS |
| V4B_13579 astropy-13579 | env_blocked_but_review_verified | null | V4B3_ENV_BLOCKED_CLASSIFIED |

**Lane Stability**: All 3 lanes have 2 real observations each.

### V4-C — Operations Readiness

| Sub-phase | Commit | Content |
|-----------|--------|---------|
| V4-C.1 | `c62c05df` | Internal repair runbook — 10 gates, receipt schema, stop rules |
| V4-C.2 | `379cba43` | Compliance checker — 15 tests pass |
| V4-C.3 | `806d0ec8` | Backfill audit — 6 artifacts, no violations |
| V4-C.4 | `3f83b406` | CLI entry point |

### V4-D — 14B Evaluation

| Sub-phase | Commit | Finding |
|-----------|--------|---------|
| V4-D | `67fa79b5` | 14B no clear gain: format_valid=false, latency higher |
| V4-D.1 | `9cc337a3` | 14B recovered with strict format prompt |
| V4-D.2 | `a48d8d53` | 7B=DEFAULT, 14B=STRICT_PROMPT_FALLBACK |
| V4-D.3 | `530ca93b` | 14B guard integrated into compliance checker |

### V4-E — 3B Auxiliary

| Sub-phase | Finding |
|-----------|---------|
| V4-E.0 | 3B allowed as advisory only |
| V4-E.1 | 3B receipt/lane audit: 6/6 correct, advisory only |

### V5-A — AST Context Slicing

| Sub-phase | Content |
|-----------|---------|
| V5-A | AST slicing plan — target design, budget policy, risk analysis |
| V5-B | Prototype: `context_slicer.py` — 8 tests, 4 modes (exact/line/error/fallback) |
| V5-C | Patch protocol: `patch_protocol.py` — 9 tests, strict diff contract |
| V5-D | Trace schema: `trace_export.py` — 9 tests, internal-audit-only |
| V5-E | Dry-run: 3 tasks evaluated, no regressions |
| V5-F | Dogfood readiness: all tooling in place |
| V5-G | Dogfood execution: **planned, awaiting owner approval** |

### V6 — Distillation Feasibility

| Sub-phase | Status |
|-----------|--------|
| V6-A | Not ready for training — insufficient traces, no owner approval |
| V6-B | SCoRe loop design documented — no implementation yet |

### V7-A — Dogfood Execution Approval Packet Finalization

| Sub-phase | Content | Status |
|-----------|---------|--------|
| V7-A | Dogfood approval packet — 3 initial + 2 reserve tasks, checklists, stop rules | ✅ V7A_DOGFOOD_APPROVAL_PACKET_READY |

---

## Files Modified (Code)

| File | Changes |
|------|---------|
| `nexus/services/local_heal/patch_applier.py` | authority accumulation, FUZZY precedence fix |
| `nexus/services/local_heal/micro_verifier.py` | env_taxonomy, task_scoped, fail-closed |
| `nexus/services/local_heal/orchestrator.py` | StructuredPacket for all failure types |
| `nexus/services/local_heal/corrector.py` | StructuredPacket in retry prompts |
| `nexus/services/local_heal/receipt.py` | success_attribution, structured_packet_used |
| `nexus/services/local_heal/runbook_compliance.py` | **NEW** — compliance checker |
| `nexus/services/local_heal/runbook_compliance_cli.py` | **NEW** — CLI entry point |
| `nexus/services/local_heal/context_slicer.py` | **NEW** — AST context slicing prototype |
| `nexus/services/local_heal/patch_protocol.py` | **NEW** — patch protocol adapter |
| `nexus/services/local_heal/trace_export.py` | **NEW** — trace export schema |
| `nexus/evidence/s2t_export_guard.py` | 6 classification buckets |

## Tests (Code)

| File | Tests |
|------|-------|
| `tests/unit/local_heal/test_patch_applier.py` | 17 pass |
| `tests/unit/local_heal/test_micro_verifier.py` | 9 pass |
| `tests/unit/local_heal/test_evidence_compactor.py` | 9 pass |
| `tests/unit/local_heal/test_receipt_v1_schema.py` | 19 pass |
| `tests/unit/test_export_guard.py` | 22 pass |
| `tests/unit/local_heal/test_runbook_compliance.py` | 15 pass |
| `tests/unit/local_heal/test_context_slicer.py` | 8 pass |
| `tests/unit/local_heal/test_patch_protocol.py` | 9 pass |
| `tests/unit/local_heal/test_trace_export.py` | 9 pass |

**Total**: 117 tests pass.

## Model Policy

```
7B:  DEFAULT_VALIDATED_EXECUTOR
14B: STRICT_PROMPT_FALLBACK_CANDIDATE (owner-approved only)
3B:  UNVALIDATED_AUXILIARY_CANDIDATE (advisory only)
```

## Governance Rules

- `public_claim_allowed=false` — all tasks
- `training_eligible=false` — all tasks
- `runtime_integration_enabled=false`
- `routing_integration_enabled=false`
- No public benchmark claims
- No production readiness claims
- No generalized repo-wide claims

## Internal Capability Statement

"Nexus has internally validated local 7B repair evidence handling across six real task observations and established guarded internal operations for repair artifact compliance. 14B is available as a strict-prompt fallback candidate. 3B remains auxiliary-only unless separately validated."

This is internal-only and not a public benchmark claim.
