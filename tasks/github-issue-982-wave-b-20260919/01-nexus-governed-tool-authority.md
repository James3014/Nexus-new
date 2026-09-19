# Task Card: Issue #982 Wave B1 — Nexus governed tool-authority producer

artifact_authority: current
task_id: `issue-982-wave-b1-nexus-governed-tool-authority-20260919`
campaign_id: `github-issue-982-wave-b-20260919`
owner: James Chen
status: READY_AFTER_TRACKING
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Source Spec

- path: `docs/specs/ISSUE_982_WAVE_B_GOVERNED_TOOL_AUTHORITY_001.md`
- contract-branch blob SHA: `a402d709800aad4d4282b6006343d5d4c4ca65aa`
- Spec status: `READY_FOR_TASK_CARDS`
- Issue: `James3014/Nexus-new#982`

This card becomes executable only after this card and the Spec are tracked on canonical Nexus-new main. At execution start, rebind current main and verify the tracked Spec/Card bytes are unchanged or record an explicit bounded contract delta.

## Objective

Implement the Nexus-new half of Wave B:

```text
CanonicalDispatchEnvelope
  -> deterministic governed tool-authority projection
  -> canonical JIT narrowing
  -> existing devspace.tool_projection_manifest.v1 shape
  -> deterministic Nexus grant toolAuthority fragment
```

The implementation must bind exact Planner decision/plan identity and tool policy identity without creating a second Planner/router/tool registry or DevSpace adapter.

## Bound planning base

- Nexus-new main at compilation: `9e2e3bf72becae4461b707666be4f1d063ecdd30`
- tree: `dbb142cf041064d0ac02e3daf7ace9ece37ffe92`
- canonical task seam blob: `4a468aeee413657121523313a30d3a8a056feb88`
- JIT blob: `74b6647a5ccf255723d60dfb3f078ac79781ab36`

The implementation attempt must use a clean isolated worktree created from freshly rebound canonical main. It must not modify the user's shared dirty checkout.

## Allowed files

Only:

- `nexus/contracts/devspace_tool_authority.py` (new)
- `nexus/core/jit_tool_injector.py`
- `scripts/ops/build_devspace_governed_tool_contract.py` (new, only if needed for deterministic host materialization)
- `tests/contracts/test_devspace_tool_authority.py` (new)
- `tests/core/test_jit_tool_injector.py` (new)
- `tests/ops/test_build_devspace_governed_tool_contract.py` (new, only when the ops helper is added)

Any additional source path requires a contract delta before mutation.

## Required behavior

1. Define `nexus.devspace.tool_authority.v1` as a derived authority projection bound to:
   - exact `plannerDecisionHash`
   - exact `plannerPlanHash`
   - deterministic `policyHash`
   - canonical `devspace.tool_intent.v1` ceiling.
2. Implement the Spec's effect-ceiling projection policy:
   - `READ_ONLY` -> four read/search/list intents.
   - `WORKSPACE_MUTATION` and `CANDIDATE` -> all six intents.
3. Add a separate canonical JIT narrowing path; do not change legacy `apply_mask()` semantics.
4. Build the existing `devspace.tool_projection_manifest.v1` shape with `NEXUS_GOVERNED / nexus`.
5. Validate both subset relations before output.
6. Emit the exact optional `toolAuthority` fragment expected by the DevSpace grant extension.
7. Any helper/CLI must be deterministic and must never fetch provider/model/catalog state or choose route/provider/model/worker.

## Negative controls

Must prove:

- unknown effect ceiling fails closed;
- malformed/duplicate/unknown canonical intents fail closed;
- planner decision/plan identity mismatch fails closed;
- JIT never widens candidate/ceiling;
- explicit single-file read narrows 4 -> 1;
- search/verify/mutation classes remain subset-safe;
- policy hash is stable for same policy and changes with policy content;
- legacy `apply_mask()` behavior is unchanged;
- `nexus/executors/worker_registry.py` remains untouched and contains no new DevSpace adapter.

## Verifiers

At minimum:

```bash
pytest -q tests/contracts/test_devspace_tool_authority.py tests/core/test_jit_tool_injector.py
pytest -q tests/contracts/test_canonical_execution.py tests/test_layer_boundaries.py
git diff --check
```

If the ops helper is added:

```bash
pytest -q tests/ops/test_build_devspace_governed_tool_contract.py
```

Run the narrowest additional affected tests required by actual imports.

## Candidate / acceptance

- implementation occurs in an isolated worktree;
- Candidate commit is required;
- complete changed-path set and exact diff must be captured;
- all required verifiers must pass;
- independent reviewer distinct from the implementer must inspect exact Candidate source/diff and authority invariants;
- implementer cannot self-accept or merge;
- only an accepted exact Candidate may proceed to integration under separate merge authority.

## Non-goals

- no DevSpace source changes under this card;
- no `nexus-runtime` changes;
- no WorkerRegistry DevSpace adapter;
- no provider/model routing changes;
- no G4 benchmark;
- no release or production-readiness claim.

## Exit

`B1_NEXUS_TOOL_AUTHORITY_CANDIDATE_ACCEPTED_AND_MERGED` only after independent acceptance and source integration.

Then STOP this card. It does not authorize B2/B3 automatically.
