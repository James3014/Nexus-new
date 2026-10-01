# SPEC-ISSUE-982-WAVE-B-GOVERNED-TOOL-AUTHORITY-001

status: READY_FOR_TASK_CARDS
issue: James3014/Nexus-new#982
owner: James Chen
date: 2026-09-19
AUTO_CHAIN: false

## 1. Goal

Close the Wave B production-governance gap without creating a second Planner, router, tool registry, or execution authority.

Wave B is complete only when a canonical Nexus-governed tool-authority projection is bound to the exact CapabilityPlanner decision and policy identity, carried by the existing tracked Nexus -> DevSpace execution grant, enforced by DevSpace against the existing `ExecutionContract.authorizedToolCeiling` + `devspace.tool_projection_manifest.v1`, and proven by one live `NEXUS_GOVERNED` positive canary plus one fail-closed widening control.

This Spec does not authorize G4 benchmark execution.

## 2. Evidence / source fence

### Nexus-new

- contract base: `9e2e3bf72becae4461b707666be4f1d063ecdd30`
- tree: `dbb142cf041064d0ac02e3daf7ace9ece37ffe92`
- `nexus/engine/canonical_task_seam.py` blob: `4a468aeee413657121523313a30d3a8a056feb88`
- `nexus/core/jit_tool_injector.py` blob: `74b6647a5ccf255723d60dfb3f078ac79781ab36`
- `nexus/core/capability_executor_registry.py` blob: `328b1445355cef83b09855c02699c07f4eb22b7c`

The source audit established:

- `CapabilityPlanner` / canonical `ExecutionDecision` remains the only route/capability-selection authority.
- `CanonicalDispatchEnvelope` already binds exact Planner decision/plan identity to admitted worker/provider/model and workforce policy identity.
- current `jit_validation` remains prompt/evidence-oriented and its `jit_all_tools` producer is not an authoritative production tool-ceiling source.
- legacy `CapabilityGate` names such as `read_file`, `grep_search`, and `run_command` are not the canonical DevSpace tool-intent namespace.
- `nexus/executors/worker_registry.py` is the local CLI worker surface and must not become a DevSpace adapter.

### DevSpace

- GitHub implementation base at Spec freeze: `a063482e2fab395740d89e71fe1d7f94b3849549`
- Wave A live runtime evidence later ran at `9b071fadde72b3850c8d1f5819692f634b008e8e`; that live-only source is runtime evidence, not the GitHub source authority for this Spec.

Existing canonical execution contracts already provide:

- `ExecutionContract.authorizedToolCeiling`
- `devspace.tool_projection_manifest.v1`
- canonical namespace `devspace.tool_intent.v1`
- canonical intents:
  - `workspace.read`
  - `workspace.search_text`
  - `workspace.search_paths`
  - `workspace.list`
  - `workspace.mutate`
  - `process.execute`
- `nexus.devspace.execution_grant.v1`
- immutable tracked Nexus grant resolution and current-main byte binding
- fail-closed `NEXUS_GOVERNED` grant validation
- no governed-to-direct fallback
- provider-native OpenCode projection enforcement.

### Durable #982 decisions

Comment `5723728222` freezes producer ownership:

- Planner-selected capabilities are not themselves tool intents.
- DevSpace must never infer tool authority from task prose, provider catalogs, profiles, or defaults.
- for `NEXUS_GOVERNED`, deterministic capability/effect -> canonical-tool projection must be bound to exact Planner decision + policy identity.
- JIT is a narrower only; it can choose less but cannot widen authority.

Wave A comment `5739580640` proves one physical OpenCode intervention under OWNER_DIRECT and leaves Wave B / G4 unstarted.

### Post-Spec B3 worker-identity delta (2026-09-20)

The governed #1032 route/Workforce delta is now integrated on Nexus-new main by PR #1039 / merge `d7b2e359b9d4700b33186a2633310b84ab7b502c`.

For the exact verified campaign `github-issue-982-wave-b-20260919`, the canonical Planner/Workforce path now binds:

- worker: `opencode_mimo_free`
- provider: `opencode`
- model: `opencode/mimo-v2.5-free`
- role: `bounded_candidate_generation`
- minimum autonomy: `L1`
- context: `nexus_bounded`
- mutation intent: `false`

This supersedes only the historical big-pickle-specific B3 witness identity below. It does not change the Wave B tool-authority architecture, does not promote MiMo globally, and does not permit caller provider/model override. Fresh catalog/preflight and Workforce Admission remain mandatory immediately before the live canary; identity drift blocks/rebinds rather than silently substituting another model.

## 3. Architecture decision

Classification: `MISSING_CANONICAL_WIRING`.

Reuse the existing authority owners:

```text
CapabilityPlanner / ExecutionDecision
        |
        | exact decision_hash + plan_hash
        v
CanonicalDispatchEnvelope
        |
        | deterministic governed tool-authority projection
        | bound to planner decision + policy identity
        v
NexusExecutionGrant.toolAuthority
        |
        | JIT narrowing only
        v
ExecutionContract.authorizedToolCeiling
ToolProjectionManifest(selected <= candidate <= ceiling)
        |
        v
DevSpace NEXUS_GOVERNED validation
        |
        v
existing provider adapter / physical tool surface
```

No new route chooser, provider selector, Workforce authority, tool registry, or acceptance authority is introduced.

The `nexus-runtime` package is not a Wave B mutation owner. Its effect-authorization pattern is useful prior art, but Issue #982 already froze one transport-neutral tool-projection contract: `devspace.tool_projection_manifest.v1`. Creating a second runtime tool-projection SSOT would violate the Issue contract.

## 4. Canonical governed tool-authority projection

Nexus-new owns one deterministic derived authority object:

```json
{
  "schema": "nexus.devspace.tool_authority.v1",
  "namespace": "devspace.tool_intent.v1",
  "plannerDecisionHash": "<sha256>",
  "plannerPlanHash": "<sha256>",
  "policyHash": "<sha256 of the exact tool-authority policy>",
  "authorizedToolCeiling": ["<canonical intent>", "..."]
}
```

Properties:

1. `plannerDecisionHash` and `plannerPlanHash` MUST equal the current canonical dispatch envelope.
2. `policyHash` binds the exact deterministic projection policy bytes/structure.
3. `authorizedToolCeiling` is an authority ceiling, not a recommendation.
4. the projection MUST NOT choose route/provider/model/worker.
5. the projection MUST NOT inspect provider availability or provider tool catalogs.
6. any unknown effect ceiling or unknown canonical intent fails closed.
7. output is canonically ordered and duplicate-free.

### Effect-ceiling projection policy v1

The existing Nexus execution effect ceiling is projected into the DevSpace canonical intent namespace:

| Nexus effect ceiling | Authorized canonical tool ceiling |
| --- | --- |
| `READ_ONLY` | `workspace.read`, `workspace.search_text`, `workspace.search_paths`, `workspace.list` |
| `WORKSPACE_MUTATION` | all six canonical intents |
| `CANDIDATE` | all six canonical intents |

This is a maximum authority projection only. It is intentionally broader than task-specific JIT selection and therefore cannot substitute for JIT.

The policy object itself MUST be hashed; changing this table changes `policyHash`.

## 5. Canonical JIT narrowing

Add a canonical-intent JIT path without changing legacy `JITToolInjector.apply_mask()` semantics for existing callers.

Required contract:

```text
selected_tools = apply_canonical_mask(task_statement, candidate_tools)

candidate_tools <= authorized_tool_ceiling
selected_tools <= candidate_tools
```

The canonical path MUST:

- accept only `devspace.tool_intent.v1` values;
- canonicalize order and reject duplicates/unknown values;
- never return an intent outside the supplied candidate set;
- never use a global full-tool fallback;
- never use provider/model/catalog state;
- use deterministic task semantics only to narrow;
- fall back to the supplied candidate set when it cannot safely narrow, rather than inventing authority.

Minimum deterministic v1 narrowing classes:

- explicit single-file/read-only task language -> `workspace.read` when present;
- search/find/locate/inspect/review/analyze task language -> read/search/list intents intersected with candidates;
- test/verify/audit/check/run/command task language -> read/search/list + `process.execute` intersected with candidates;
- implement/fix/repair/patch/write/edit/modify/refactor/build task language -> supplied candidates unchanged;
- otherwise -> supplied candidates unchanged.

The live Wave B positive canary uses an explicit single-file/read-only task so the JIT path has a real 4 -> 1 intervention.

## 6. ToolProjectionManifest construction

Nexus builds the existing DevSpace manifest shape; it does not create a competing schema:

```json
{
  "schema": "devspace.tool_projection_manifest.v1",
  "namespace": "devspace.tool_intent.v1",
  "identity": {
    "taskId": "<task>",
    "attemptId": "<attempt>"
  },
  "authority": {
    "mode": "NEXUS_GOVERNED",
    "issuer": "nexus"
  },
  "authorizedToolCeiling": ["..."],
  "candidateTools": ["..."],
  "selectedTools": ["..."],
  "orderingMode": "ORDER_INDEPENDENT"
}
```

Nexus construction MUST prove both subset relations before the request leaves the controller boundary.

## 7. Nexus execution grant extension

Extend `nexus.devspace.execution_grant.v1` backward compatibly with one optional object:

```json
{
  "toolAuthority": {
    "schema": "nexus.devspace.tool_authority.v1",
    "namespace": "devspace.tool_intent.v1",
    "plannerDecisionHash": "<sha256>",
    "plannerPlanHash": "<sha256>",
    "policyHash": "<sha256>",
    "authorizedToolCeiling": ["..."]
  }
}
```

Compatibility rule:

- historical governed grants without `toolAuthority` remain valid only when no tool projection participates.
- when a `NEXUS_GOVERNED` request supplies `authorizedToolCeiling` and `toolProjectionManifest`, the resolved grant MUST contain `toolAuthority`.
- partial grant tool authority is invalid.

Because `grantHash` covers the parsed grant payload, `toolAuthority` is covered by the immutable tracked grant hash when present.

## 8. DevSpace validation

Before provider launch, a governed projected request MUST fail closed unless all are true:

1. resolved tracked grant is canonical/current under the existing G9/G10 rules;
2. grant `toolAuthority.schema` and namespace match;
3. grant planner decision/plan/policy hashes are valid SHA-256 identities;
4. `executionContract.authorizedToolCeiling` exactly equals grant `toolAuthority.authorizedToolCeiling` as a canonical set;
5. manifest authority is `NEXUS_GOVERNED / nexus`;
6. manifest task/attempt match the execution request;
7. manifest ceiling exactly equals execution-contract ceiling;
8. `selectedTools <= candidateTools <= authorizedToolCeiling`;
9. no governed-to-direct fallback occurs.

A widening mismatch MUST fail before semantic provider execution and must not create a durable running provider session or repository mutation.

## 9. Repository ownership and mutation scope

### Nexus-new owns

- governed tool-authority policy and projection;
- Planner/dispatch identity binding;
- canonical JIT narrowing;
- construction of the existing DevSpace projection manifest;
- construction/validation helpers for the governed tracked grant payload;
- tests proving no route/provider/model/worker authority was added.

Expected minimal source scope:

- `nexus/contracts/devspace_tool_authority.py` (new)
- `nexus/core/jit_tool_injector.py`
- focused tests under `tests/contracts/` and/or `tests/core/`
- one bounded ops/helper surface only if required to generate the tracked canary grant deterministically.

Do not change `nexus/executors/worker_registry.py`.

### DevSpace owns

- parsing/hash inclusion of the optional governed `toolAuthority` grant member;
- cross-checking resolved grant tool authority against execution ceiling/manifest;
- fail-closed typed errors before provider launch;
- backward compatibility for historical grants without tool projection.

Expected minimal source scope:

- `src/execution-protocol.ts`
- `src/execution-protocol.test.ts`
- `src/local-agent-sessions.ts`
- `src/local-agent-execution-contract.test.ts`

Additional DevSpace source paths require an explicit contract delta.

The Nexus Task Card is not DevSpace mutation authority. DevSpace work is separately authorized by the Owner's explicit Wave B request and remains bounded by DevSpace `AGENTS.md`.

## 10. Required tests / negative controls

### Nexus-new

Prove:

- READ_ONLY policy ceiling is exactly four canonical read/search/list intents;
- mutation/Candidate ceilings are exactly all six;
- projection binds exact Planner decision/plan identity;
- policy hash is deterministic and changes on policy change;
- unknown effect ceiling fails closed;
- canonical JIT never widens;
- explicit single-file read narrows 4 -> 1;
- search/verify/mutation classes remain subset-safe;
- malformed/duplicate/unknown canonical intents fail closed;
- generated manifest is `NEXUS_GOVERNED / nexus`;
- no change to legacy `apply_mask()` behavior;
- no DevSpace adapter is added to `WorkerRegistry`.

Run focused tests plus relevant canonical-dispatch/layer-boundary tests and `git diff --check`.

### DevSpace

Prove:

- old governed grant without tool authority remains valid when no projection participates;
- governed projection without grant `toolAuthority` fails;
- grant tool ceiling mismatch fails;
- bad planner/policy hash fails;
- tool authority is covered by `grantHash`;
- task/attempt/ceiling/manifest mismatch fails before provider launch;
- valid governed tool authority reaches existing provider adapter unchanged;
- no governed-to-direct fallback;
- existing OWNER_DIRECT projection behavior remains unchanged.

Run:

```bash
npx tsx src/execution-protocol.test.ts
npx tsx src/local-agent-execution-contract.test.ts
npm run typecheck
git diff --check
```

plus any narrower tests added by the Candidate.

## 11. Live Wave B runtime witness

After both source changes are independently accepted, merged, and the current DevSpace runtime is rebound to the accepted DevSpace revision:

1. generate one tracked Nexus grant whose `toolAuthority` is produced from a real canonical Planner/dispatch identity and READ_ONLY policy;
2. grant/canary authority files must exist at the current canonical Nexus main revision used by DevSpace grant resolution;
3. use the #1032-bound OpenCode worker `opencode_mimo_free` (`provider=opencode`, `model=opencode/mimo-v2.5-free`) only when fresh catalog/preflight and Workforce Admission establish that exact identity as eligible; drift blocks/rebinds and MUST NOT silently substitute another model;
4. keep the same authorized ceiling as Wave A:
   - `workspace.read`
   - `workspace.search_text`
   - `workspace.search_paths`
   - `workspace.list`
5. use an explicit single-file/read-only task so canonical JIT selects `workspace.read` only;
6. call `agent_start` with `authorityMode=NEXUS_GOVERNED`, exact `nexusGrant`, dispatch intent, expected head, exact ceiling and manifest;
7. positive witness requires durable readback of:
   - `NEXUS_GOVERNED`
   - exact grant reference
   - exact four-tool ceiling
   - exact one-tool selected set
   - current source/build/provider/model/provider session
   - provider-native OpenCode permission surface with search/list denied;
8. negative control reuses the same authority identity but attempts to widen the execution ceiling/manifest beyond the tracked grant; it MUST fail before provider launch, with no durable agent/repository mutation.

## 12. Wave B exit criteria

Wave B may be marked COMPLETE only if:

- Nexus governed tool-authority source is merged;
- DevSpace grant/tool cross-validation source is merged;
- required tests and independent reviews pass at exact Candidate revisions;
- DevSpace live runtime is bound to the accepted implementation source;
- one real `NEXUS_GOVERNED` positive OpenCode witness succeeds;
- one widened-ceiling negative authority control fails closed before provider execution;
- #982 receives a durable receipt with exact source/runtime/agent/grant identities;
- no second Planner/router/tool registry/receipt authority is introduced;
- G4 remains NOT_STARTED;
- `AUTO_CHAIN=false`.

## 13. Claim ceiling

Before all exit criteria:

`WAVE_B_IN_PROGRESS`.

After all exit criteria:

`WAVE_B_COMPLETE_NEXUS_GOVERNED_TOOL_AUTHORITY_WITNESS_PROVEN`.

This does not prove all OpenCode identities, all provider families, G4 benchmark results, release readiness, or production-wide Nexus correctness.