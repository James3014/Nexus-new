# Nexus Optimization Contract and Evidence Retention

Status: `ACTIVE_PRE_SKILL_ADJUSTMENT`
Date: `2026-05-19`
Parent plan: `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`

## 1. Contract Scope

This contract freezes the pre-SF-adjustment boundaries for Nexus optimization work.

Applies to:

- context engineering;
- learning/data flywheel;
- harness and route evidence;
- skill-fit discovery/replacement;
- public benchmark readiness;
- generated report retention.

Does not apply to:

- runtime default skill promotion;
- public benchmark claim unlock;
- large ContextHub / harness rewrites;
- Spec Kit initialization while the worktree is dirty.

## 2. Claim Boundary

Every optimization artifact must declare one claim class:

| Claim class | Meaning | Allowed output | Forbidden output |
| --- | --- | --- | --- |
| `PLAN_ONLY` | architecture or task plan | task cards, risks, validation commands | runtime or public claim |
| `INTERNAL_DIAGNOSTIC` | smoke, RCA, or dry-run | blocker reason, next action | replacement or promotion |
| `SF_DISCOVERY` | skill candidate comparison | catalog/ledger candidate verdict | runtime default update |
| `RUNTIME_APPLY_REVIEW` | apply-gate input | approve/hold/reject recommendation | public benchmark claim |
| `PUBLIC_READY` | audited public evidence | public delivery/cost/trust claim | hidden or single-arm evidence |

Default claim class for new optimization reports is `PLAN_ONLY` unless an evidence bundle proves otherwise.

## 3. Readiness Checklist

Before executing a task card:

- worktree state checked with `git status --short`;
- source docs and current local code seam read;
- no forbidden paths touched;
- claim class selected;
- validation command identified;
- failure-to-lesson target identified.

Before skill replacement:

- current-best and challenger both have receipt-clean PASS rows;
- comparison happened in the same provider-cleanliness window;
- selected/injected/used/evidence/gate/outcome are all true;
- provider token state is not `estimated` when cost is part of the decision;
- `runtime_update_allowed` remains false unless a separate apply gate passes.

Before public benchmark:

- fixed taskset and disclosure manifest are frozen;
- hidden verifier is active;
- outbound prompt ledger is clean when applicable;
- provider-token telemetry is measured for model-cost rows;
- public claim gates consume evidence bundles, not markdown summaries.

## 4. Artifact Naming Rule

Generated evidence should use one of these prefixes:

- `NEXUS_OPT_` for optimization plans, contracts, retention, and architecture rollups;
- `NEXUS_SF_` for skill-fit discovery, comparison, catalog, overlay, and replacement ledgers;
- `NEXUS_7R_`, `NEXUS_8R_`, `NEXUS_9R_` for benchmark-lane artifacts;
- `NEXUS_LEARN_` for learning/data flywheel records.

Every generated report must include:

- date suffix;
- schema/status field when JSON;
- claim boundary;
- source report or evidence path where applicable;
- replacement/update permission flags when touching SF or runtime policy.

## 5. Retention Classes

| Class | Rule |
| --- | --- |
| `keep_tracked_source` | Anything tracked by git stays in place. |
| `keep_current_evidence` | Latest closure, overlay, ledger, and directly referenced reports stay in place. |
| `archive_candidate` | Untracked superseded reports may be moved to `docs/reports/archive/`. |
| `transient_receipt_root` | `.nexus/` and `/private/tmp/` receipt roots are not moved by report-retention dry-runs. |
| `delete_candidate` | Not allowed by this contract. Deletion needs a separate explicit command. |

## 6. Stop Conditions

Stop and write a lesson if:

- a dry-run attempts to move tracked reports;
- a replacement ledger is written from provider-blocked rows;
- a report lacks claim boundary;
- a new optimization script writes outside allowed paths;
- a public claim is inferred from internal smoke.

## 7. Next Implementation Gate

After this contract:

1. run `OPT-NEXT-1` dry-run retention only;
2. inspect keep/archive counts;
3. continue SF skill adjustment only after current evidence roots are classified;
4. defer M1-M7 runtime architecture changes until SF evidence is cleaner.

