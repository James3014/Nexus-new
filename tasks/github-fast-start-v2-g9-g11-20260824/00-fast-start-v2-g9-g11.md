# TASK-FAST-START-V2-G9-G11

Status: ACTIVE
AUTO_CHAIN=false

## Objective
Implement and prove Fast Start v2 G9-G11 without changing Nexus product/runtime authority:
1. G9: deterministic read-only simulator for typed inputs, impact mapping, reconcile action/frontier classification, and blocked zero-retrieval accounting.
2. G10: shadow-only GitHub Actions canary that runs the simulator/tests and emits non-authoritative evidence; it must not update Issue #549 or execute untrusted PR code.
3. G11: after exact-head independent acceptance and merge gates, cut over the existing refresh configuration so v2 becomes the primary refresh policy while preserving v1 rollback.

## Authority
Current Owner request in this conversation authorizes this bounded governed milestone. This card grants implementation on the issue branch only; it grants no self-approval, merge without fresh exact-head gates, runtime, release, production, route, Workforce, claim, or autonomous worker-dispatch authority.

## Allowed repository files
- `scripts/ops/fast_start_v2.py`
- `tests/ops/test_fast_start_v2.py`
- `.github/workflows/fast-start-v2-shadow.yml`
- `.github/workflows/fast-start-v2-invalidator.yml`
- `openwiki/workflows/github-actions.md`
- `tests/ops/test_openwiki_source_contract.py`
- `tasks/github-fast-start-v2-g9-g11-20260824/00-fast-start-v2-g9-g11.md`
- `tasks/github-fast-start-v2-g9-g11-20260824/INDEX.md`

Maximum repository changed files: 8.

The OpenWiki page and its source-contract test are included only because the repository's exact-base CI requires the physical workflow inventory and derived OpenWiki workflow inventory to remain synchronized. They are derived/governance evidence, not a new Fast Start authority.

## Forbidden scope
- No product source changes.
- No Nexus route/Planner/Workforce/lifecycle/claim/approval/integration authority changes.
- No changes to Issue #549 canonical body during Candidate implementation/PR validation.
- Invalidation receipts may only append `WAKEUP_HINT_ONLY` comments to #549; they are never canonical registry state.
- No workflow may checkout or execute untrusted pull-request head code under elevated permissions.
- No secrets.
- No direct push to `main`; no force push; no branch deletion.

## G9 verification
- Deterministic reference cases for #129/#92/#419/#526/#398.
- Synthetic event cases: irrelevant main path, blocker head movement, blocker terminal without unlock witness, contract change while blocked, host-fact unavailable, duplicate impact edges, registry self-event suppression.
- BLOCKED/HOST cases must report source-body reads = 0 and test-body reads = 0.
- Malformed/unknown input fails closed.

## G10 verification
- Shadow workflow has read-only repository permissions.
- It runs only the simulator/tests and current GitHub read-only frontier; no canonical registry mutation.
- Exact PR-head workflow run must be green before G11.
- Shadow result must not produce a false READY for current blocked/host entries.

## G11 cutover
Only after independent exact-head review and terminal required checks:
- merge by exact-head/CAS bounded path;
- read back `main` and merged revision;
- preserve #549 as sole advisory registry;
- enable the merged event invalidator only as a non-authoritative wakeup source;
- keep Daily Guard observer/anti-entropy only with no direct #549 repair;
- preserve an exact rollback path to the v1 broad sweep/guard semantics.

## G11D scheduler-reliability correction

Fresh operational evidence after the original G11 cutover showed that the ChatGPT recurring Sweep can become disabled independently of Fast Start cache semantics. A ChatGPT Scheduled Task therefore cannot remain the sole production registry-body writer.

This is a goal-preserving correction inside the existing G11 authority and file scope:

- The trusted default-branch `.github/workflows/fast-start-v2-invalidator.yml` becomes the durable Fast Start v2 control workflow.
- Event invalidation remains `WAKEUP_HINT_ONLY`; the workflow also runs a canonical reconciler on relevant events, hourly `schedule`, and manual `workflow_dispatch`.
- The reconciler always checks out trusted `main`, never untrusted PR-head code.
- BLOCKED/host/decision/evidence-blocked rebinds use GitHub metadata only. No implementation source/test body, PR diff, patch, or changed-file body may be read to decide whether a blocker still exists.
- Current-main movement is wakeup evidence only. It never upgrades a frontier and does not by itself justify a #549 body rewrite.
- A blocker becoming terminal never auto-grants READY; absent a fresh unlock proof, the entry fails closed to `EVIDENCE_BLOCKED`.
- Explicit `WAKEUP_HINT_ONLY / NO_AUTHORITY` canary comments do not become material Issue-contract changes.
- No material semantic entry change => `NOOP` and no #549 body/revision mutation.
- Proven material entry change => update only #549 in place, increment `registry_revision` exactly once, recompute the deterministic payload hash, preserve unaffected entries, enforce a pre-write body/revision/hash fence, and verify post-write readback.
- The GitHub Actions workflow and the event invalidator share one concurrency group so independent runs do not race canonical registry state.
- After a merged default-branch live canary proves the GitHub reconciler can run and preserve/update #549 correctly, disable the ChatGPT Sweep writer. The ChatGPT Daily Guard may remain observer-only but must no longer require a ChatGPT Sweep to be the canonical writer.
- Rollback: disable the GitHub canonical reconciler, restore the previously verified ChatGPT broad Sweep as the temporary sole writer, then perform a full #549 reconcile before resuming normal use.

### G11D verification

Before completion claim:
1. focused Fast Start tests cover the hourly/default-branch writer structure, inline reconciler syntax, zero-retrieval markers, NOOP path, revision/hash fences, and fail-closed blocker semantics;
2. exact-head CI/independent review is green for the Candidate;
3. after merge, trigger one controlled real event or manual run on the default-branch workflow and read back the run plus #549;
4. prove #549 remains `ADVISORY_CACHE_ONLY`, no duplicate registry exists, and a no-material-change run does not increment revision merely because main moved;
5. disable the ChatGPT Sweep only after the GitHub writer proof exists; keep Daily Guard observer-only;
6. re-read writer/guard state and #549 after cutover.

## Exit criteria
G9 simulator/tests proven; G10 shadow run proven on exact candidate; G11 merged/cutover/readback proven; G11D canonical writer no longer depends on ChatGPT Scheduled Task lifecycle. If exact default-branch writer execution cannot be observed, stop before claiming G11D operational closure.
