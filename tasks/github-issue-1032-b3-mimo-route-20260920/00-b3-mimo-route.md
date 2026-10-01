# Task Card: issue-1032-b3-mimo-route-20260920

artifact_authority: current
task_id: `issue-1032-b3-mimo-route-20260920`
owner: James Chen
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
independent_acceptance_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Source lineage

- durable Issue: `James3014/Nexus-new#1032`
- parent consumer: `James3014/Nexus-new#982`
- settled design correction: #1032 comment `5742546265`
- prior stale-Gateway block: #1032 comment `5742553136`
- dependency refinement: #1032 comment `5743157785`
- R2 physical convergence closure: #1025 comment `5748167161`
- Task Card bootstrap authority: #1032 comment `5748198059`
- collaboration base: `ed146f372842c9a3273c0e241a748fac7ef73735`
- collaboration tree: `a4efa00d88e663e15c07a0e1cab06ef234ded188`

The original broad ExperimentalWorkerClass design is superseded by current source discovery. This Card compiles only the bounded B3 MiMo route delta.

## Objective

Make the existing canonical Planner/Workforce path emit and admit the already-enrolled OpenCode MiMo worker for the exact verified #982 B3 campaign, without creating a new Worker class, calibration authority, selector, registry, admission reducer, or provider/model caller override.

Expected behavior:

```text
verified campaign github-issue-982-wave-b-20260919
  -> canonical task seam marks candidate_generation_only
  -> CapabilityPlanner demand
       role=bounded_candidate_generation
       minimum_autonomy=L1
       context=nexus_bounded
       mutation_intent=false
  -> existing Workforce campaign route
       opencode_mimo_free
       provider=opencode
       model=opencode/mimo-v2.5-free
  -> normal CanonicalDispatchEnvelope exact identity binding
```

Normal global `fast_bounded_implementation` routing must remain unchanged.

## Existing authority to reuse

Reuse, do not duplicate:

- `CapabilityPlanner` as sole route/capability authority;
- existing verified Task Card/campaign identity projection in `nexus/engine/canonical_task_seam.py`;
- existing Workforce policy/admission reducer;
- existing `nexus/services/model_capability_lineage.py` and `nexus/config/model_capability_lineage.yaml`;
- existing `WorkforceWorker` semantics;
- existing `CanonicalDispatchEnvelope`;
- existing B1 tool-authority derivation and DevSpace `NEXUS_GOVERNED` enforcement path.

No new logical ExperimentalWorkerClass is authorized.

## Exact worker binding

- worker_id: `opencode_mimo_free`
- provider: `opencode`
- model: `opencode/mimo-v2.5-free`
- state: `REGISTERED_CONDITIONAL`
- autonomy ceiling: `L1`
- admitted role: `bounded_candidate_generation`
- context: `nexus_bounded`

This is a bounded campaign route, not a global preference. Live catalog/preflight must be rebound before the B3 canary. Drift blocks/rebinds; it never silently substitutes another model.

## Allowed files

Production:
- `nexus/engine/canonical_task_seam.py`
- `nexus/config/model_workforce.yaml`

Focused tests:
- `tests/engine/test_canonical_task_seam.py`
- `tests/services/test_model_workforce_policy_loader.py`

Maximum changed files: 4.

## Forbidden scope

Do not change:

- `nexus/contracts/canonical_execution.py`
- `nexus/contracts/workforce_admission.py`
- `nexus/services/runtime_workforce_admission.py`
- `nexus/services/model_capability_lineage.py`
- `nexus/engine/capability_planner.py` unless a fresh contract delta proves the current seam cannot express the frozen behavior;
- DevSpace;
- nexus-core;
- global normal worker role/autonomy ceilings;
- model calibration/promotion state;
- B1 tool-authority semantics;
- release or production/public authority.

No new router, selector, worker registry, model registry, admission reducer, or second authority store.

## Required behavior

1. Only the exact verified campaign identity `github-issue-982-wave-b-20260919` may activate the B3 candidate-generation projection.
2. Task-id text, caller context, raw provider/model strings, or an unverified/unknown campaign cannot mint that projection.
3. The exact B3 verified campaign produces `bounded_candidate_generation / L1 / nexus_bounded` with `mutation_intent=false`.
4. The exact B3 campaign resolves through existing Workforce policy to `opencode_mimo_free`.
5. The canonical dispatch binding carries exact `provider=opencode` and `model=opencode/mimo-v2.5-free`.
6. Ordinary tasks continue the existing global `fast_bounded_implementation` route unchanged.
7. Campaign mismatch follows existing global/fail-closed semantics; no availability-based fallback selects MiMo.
8. Caller provider/model override remains forbidden.
9. Existing MiMo required controls remain intact.
10. Catalog/model drift before live canary blocks pending fresh rebind.
11. This change grants no model promotion, acceptance, integration, runtime activation, release, or production/public claim.

## Mandatory negative controls

Tests must prove:

- unverified/unknown campaign cannot mint B3 routing;
- task-id text alone cannot mint campaign identity;
- missing verified campaign leaves ordinary routing unchanged;
- caller cannot inject provider/model;
- campaign mismatch does not select MiMo;
- B3 mutation intent remains false;
- global `fast_bounded_implementation` routing remains behavior-compatible;
- the B3 MiMo mapping resolves only under the exact campaign/role pair.

## Verification commands

```bash
python -m pytest -q tests/engine/test_canonical_task_seam.py tests/services/test_model_workforce_policy_loader.py
python -m pytest -q tests/engine/test_capability_planner.py
python -m ruff check nexus/engine/canonical_task_seam.py tests/engine/test_canonical_task_seam.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

Run affected exact-base CI. Independent review is required because this changes route/Workforce authority semantics.

## Candidate / integration boundary

Implementation may produce one scoped commit/PR Candidate after the required commands pass.

Acceptance binds exact base/head/tree/diff, this Card hash, exact four-file scope, mandatory positive/negative controls, no new authority owner/registry, and exact-head CI.

The implementer may not approve or integrate its own Candidate. Protected integration remains a separate GOVERNED authority gate requiring fresh exact-head evidence plus current bounded `GITHUB_MERGE` authority. Source merge does not imply runtime deployment.

## Exit criteria

Source-complete only when the bounded delta is implemented, tests pass, independent acceptance is `ACCEPT`, the exact Candidate is governed-integrated, and post-merge main contains the accepted semantics.

Then #1032 may claim:

`B3_MIMO_ROUTE_SOURCE_VERIFIED`

This does not prove the #982 B3 live canary. Gateway/runtime must later bind a source containing this delta.

## Block classification

- extra authority owner, provider/model caller override, global route change, normal worker promotion, or out-of-scope production file: `HARD_BLOCK`;
- live model/catalog drift before canary: `RECOVERABLE_BLOCK / REBIND_REQUIRED`;
- Candidate test/review failure inside scope: `REVISE`.

`AUTO_CHAIN=false`.
