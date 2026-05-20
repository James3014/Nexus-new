# Nexus Optimization Contract and Evidence Retention

Status: `CLOSED_WITH_SUCCESSOR_ITEMS`
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

Before route/context/harness optimization changes:

- AutonomicRouter hardened mode compatibility is checked when route semantics change;
- MFP thresholds are recorded, including `NEXUS_MFP_CONFIDENCE_MIN`;
- CompletionEnvelope requirements are represented in closeout read models;
- HallucinationGuard risk is considered before dropping context/evidence sources;
- mutation assurance is required for high-risk or public-claim-affecting changes;
- BDD harness preflight is run when task text contains Given-When-Then or business acceptance intent.
- route DAG fallback policy distinguishes `cost_capped` from `required` protected capabilities;
- context assembly validates skill source/tier before any skill content can enter prompt context;
- research supply gaps block live benchmark escalation unless a local mock receipt seam is explicitly marked diagnostic-only;
- forced-swarm AutonomicRouter outcomes are serialized in DAG execution and never parallelized as standard nodes.
- skeleton/codeintel optimization proves AST graph freshness after code edits before using blast-radius edges;
- PRM/evidence exports separate happy-path phase tokens from polluted retry tokens;
- memory and findings writeback passes a sanitizer for `<private>` and credential-like values;
- Spec Kit or large generated-output runs are blocked while the worktree is dirty unless outputs are isolated under a transient root.

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
- a route/context optimization bypasses hardened router, completion envelope, hallucination, mutation, or BDD preflight gates.

## 7. Hard Gate Compatibility Layer

The optimization plan must run through this `G0` compatibility layer before deeper M1-M8 runtime architecture work.

| Gate | Required evidence | Blocks |
| --- | --- | --- |
| `G0-A Hardened Router Compatibility` | route dry-run with hardened router/MFP threshold metadata | route DAG output that cannot pass hardened intent gating |
| `G0-B Completion Envelope Closeout` | `completion_envelope_ref` or explicit completion envelope status | closeout promotion from evidence summaries only |
| `G0-C Hallucination Guard Forecast` | dropped-source risk and replacement evidence refs | context slimming that creates evidence gaps |
| `G0-D Mutation Assurance Pregate` | mutation assurance summary when high-risk or public-claim-affecting | release/apply gates with survived deterministic mutants |
| `G0-E BDD Harness Sensor Pregate` | harness preflight sensor output for BDD/business acceptance tasks | route DAGs missing `bdd_acceptance_skill` when required |
| `G0-F Capability Contract Rescue Guard` | capability activation contract and rescue plan | pre-model rescue on required protected capability paths |
| `G0-G Skill Tier Quarantine Guard` | skill tier/status validation before context assembly | candidate/quarantine/vendor/worktree skills entering public or runtime context |
| `G0-H Research Supply Gap Guard` | research candidate readiness or diagnostic-only mock receipt | live benchmark escalation while research alternate/default is absent |
| `G0-I AutonomicRouter-Forward DAG Guard` | pre-route mode and forced-swarm serialization status | static parallel DAG topology that conflicts with runtime swarm escalation |
| `G0-J AST Freshness Guard` | changed-symbol graph freshness receipt | skeleton-first blast-radius reads from stale call graph |
| `G0-K Retry Pollution Guard` | phase token sentinel and polluted retry isolation | PRM/evidence records that reward failed retry trajectories |
| `G0-L Memory Sanitizer Guard` | sanitizer status and private leak scan result | SQLite/markdown memory writeback containing private or credential-like text |
| `G0-M Worktree/SpecKit Hygiene Guard` | clean worktree or isolated transient output root | Spec Kit init or report-sprawl operations in a dirty worktree |
| `G0-N Rationale Preservation Guard` | rationale extraction receipt with autogenerated-file filtering | skeleton-first context that strips design intent or treats generated boilerplate as rationale |
| `G0-O Evidence Union-Merge Guard` | append-only evidence merge driver status, size/node caps, and post-merge schema validation | evidence ledgers/graphs that require humans to resolve commutative merge conflicts or silently accept poisoned merges |
| `G0-P Packed Context Exfiltration Guard` | context-pack secret scan, remote-config trust status, and output self-exclusion status | packed context or evidence export that includes secrets, suspicious git diff/log content, or trusted remote config by default |
| `G0-Q Evidence Seal Guard` | sealed evidence status, hash status, and partial telemetry scan | claim/evidence readers consuming dirty, half-written, or unsigned telemetry |
| `G0-R Network Fetch Guard` | SSRF/DNS/redirect revalidation status | remote research/source refresh touching private networks, link-local metadata, or stale DNS-resolved targets |
| `G0-S Entity Graph Integrity Guard` | namespace validation and dangling-edge scan | cross-project entity collisions or graph/evidence edges pointing to missing nodes |
| `G0-T Dedup/Entropy Precision Guard` | dedup precision status and low-entropy merge scan | short-token fuzzy merges or noisy labels collapsing distinct skills/entities/evidence rows |

These gates do not approve runtime updates or public benchmark claims. They only prove that optimization artifacts remain compatible with existing Nexus hard gates.

## 8. Next Implementation Gate

After this contract:

1. run `OPT-NEXT-1` dry-run retention only;
2. inspect keep/archive counts;
3. run `G0` compatibility checks before any route/context/harness runtime change;
4. continue SF skill adjustment only after current evidence roots are classified;
5. defer broad M1-M7 runtime rewrites until the narrow contracts are green.

## 9. Closeout Map 2026-05-20

Status: `CLOSED_WITH_SUCCESSOR_ITEMS`

This contract is closed as the active pre-skill-adjustment optimization
contract. It remains the governance reference for future optimization work, but
its initial implementation obligations have been either completed by later task
plans or carried forward as explicit successor items.

| Contract area | Current disposition | Evidence |
| --- | --- | --- |
| Claim classes and readiness boundaries | `DONE_BY_OPT_CONTRACT` | Sections 2 and 3 define `PLAN_ONLY`, `INTERNAL_DIAGNOSTIC`, `SF_DISCOVERY`, `RUNTIME_APPLY_REVIEW`, and `PUBLIC_READY`. |
| Evidence/report retention classes | `DONE_BY_CBO_AND_RETENTION_DRY_RUN` | `docs/reports/NEXUS_CBO_IO_MEASUREMENT_2026-05-20.json` and CBO closeout keep generated reports observation-only. |
| Network fetch guard | `DONE_BY_CBO` | `nexus/infrastructure/guarded_fetch.py` and network fetch guard tests. |
| Retrieval query shape guard | `DONE_BY_CBO` | `nexus/contracts/retrieval_query.py` and doc-scout integration tests. |
| Skill replacement cleanliness boundary | `DONE_BY_PRIOR_SF_WORK` | This contract continues to require same-window receipt-clean current-best/challenger evidence before replacement. |
| Public benchmark gate | `DEFERRED_PUBLIC_LANE` | No CBO or closeout artifact unlocks public benchmark claims. |
| Runtime default apply | `DEFERRED_APPLY_GATE` | Runtime updates remain `false` unless a separate apply gate passes. |

Dirty workspace retention decision:

| Path | Disposition | Reason |
| --- | --- | --- |
| `.obsidian/workspace.json` | `user_local_keep` | Forbidden-path/user-local workspace state; do not stage or clean in refactor closeout. |
| `.serena/project.yml` | `user_local_keep` | Local agent/tooling state not owned by CBO or Clean Code tasks. |
| `.antigravitycli/` | `user_local_keep` | Local CLI/session artifact; not part of repo refactor deliverables. |

CI warning ownership:

- `Wiki Eval pass rate 20.00% below required 80.00%` is classified as
  `governance_eval_quality_debt`.
- It is not release-blocking under the current warning enforcement level.
- Follow-up owner should be a dedicated wiki-eval quality task, not the CBO or
  Clean Code refactor closeout.

RLM repair debt ownership:

- Recursive repair loop failures observed during broad exploratory testing are
  classified as `rlm_repair_policy_composition_debt`.
- They remain outside this contract closeout and outside CBO completion.
- Reopening requires a dedicated RLM acceptance gate and should not be folded
  into repair split or optimization closeout work.

## 9. Implementation Status 2026-05-20

- `M2 Skeleton-First CodeIntel`: implemented as a bounded adapter over exact symbol lookup, rationale preservation, generated-file filtering, and last-known-good AST fallback.
- `M3 Hybrid Retrieval`: implemented as a retrieval receipt plus BM25/dense fusion contract with snapshot and chunk-hash blockers.
- `M5 Route Runtime`: implemented as route DAG pregate plus runtime dispatcher plan-consume preparation; forced-swarm and required-rescue guards remain fail-closed.
- `M6 Claim/Evidence`: implemented as read-model validation with CompletionEnvelope state, mutation assurance state, sealed evidence, and hash-valid evidence blockers.
- `M7 SF Replacement`: implemented as a two-step cleanliness gate plus explicit apply plan; runtime apply still requires authorization and post-apply smoke.
- `M8 Workspace Hygiene`: implemented as retention dry-run classification plus per-run report output routing.
- `RLM Routing Spec V2`: implemented as bounded X/R-loop orchestration receipts plus OutcomeMemory writeback; full recursive dispatch remains a separate runtime authorization gate.
- Public benchmark and publication claims remain separate gates and are not unlocked by these contracts.
