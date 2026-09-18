# Task Card: Issue #982 Wave 3 Provider Enforcement Adapters

artifact_authority: current
task_id: `issue-982-wave3-provider-adapters-20260918`
owner: James Chen
status: PREPARED_NOT_CANONICAL
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Wire the validated `ToolProjectionManifest.selectedTools` from the durable DevSpace execution contract into provider execution without creating a second authority source. Enforce the selected subset at proven native provider seams for OMP and OpenCode. For Codex, Grok, Agy, and Cline, fail closed for an enforced projection unless current source exposes a real per-tool restriction seam; do not silently run a wider surface.

## Source fence

- Nexus-new authority base: `a258be3d0946d37f038a8d58d9d5c836cf2a96d4`
- DevSpace foundation dependency: PR `James3014/devspace#191`
- DevSpace implementation base: `PENDING_POST_MERGE_READBACK_OF_PR_191`
- Durable authority owner: `ExecutionContract.authorizedToolCeiling`
- Derived selection: `ExecutionContract.toolProjectionManifest.selectedTools`
- Canonical namespace: `devspace.tool_intent.v1`
- No production Nexus JIT producer is invented by this card.

## Required behavior

1. The run layer may transport only an already-validated selected set from the persisted ExecutionContract; it may not choose, widen, or infer tool authority.
2. Provider translation is deterministic and local to adapter/runtime code; no provider-native tool registry is added to CapabilityPlanner or Nexus.
3. OMP must derive its `--tools` value from the selected canonical intents, intersected with what OMP can physically enforce. Unsupported selected intents cause explicit pre-launch failure; no fixed full-tool fallback.
4. OpenCode must derive per-tool PermissionConfig from the selected canonical intents. Unselected native tools are denied; `task` and external-directory policy remain denied unless separately authorized by existing write-mode policy.
5. Codex current app-server path, Grok ACP, Agy CLI, and Cline ACP must not claim enforcement without a current per-tool restriction seam. A non-empty enforced projection on those transports must fail before semantic provider execution with an explicit unsupported classification.
6. Empty/no ToolProjectionManifest preserves legacy behavior for callers not participating in Issue #982.
7. Provider adapters receive selected intents as transport input only. The durable ceiling remains in ExecutionContract.
8. No fuzzy aliases, prompt-based enforcement, or provider-default expansion.

## Allowed DevSpace mutation scope

- `src/local-agent-runtime.ts`
- `src/local-agent-sessions.ts`
- `src/local-agent-omp.ts`
- `src/local-agent-omp.test.ts`
- `src/local-agent-opencode.ts`
- `src/local-agent-opencode.test.ts`
- `src/local-agent-codex.ts`
- `src/local-agent-codex.test.ts`
- `src/local-agent-adapters.ts`
- `src/local-agent-adapters.test.ts`
- `src/local-agent-acp.ts`
- `src/local-agent-acp.test.ts`

Maximum changed files: 12.

## Canonical-to-provider mappings frozen for this wave

OMP:
- `workspace.read -> read`
- `workspace.search_text -> grep`
- `workspace.search_paths -> glob`
- `workspace.mutate -> edit,write`
- `workspace.list` and `process.execute`: unsupported unless exact current OMP evidence proves a native enforceable mapping before implementation.

OpenCode:
- `workspace.read -> read`
- `workspace.search_text -> grep`
- `workspace.search_paths -> glob`
- `workspace.list -> list`
- `workspace.mutate -> edit`
- `process.execute -> bash`

Provider-native mappings are translation only; they do not authorize the canonical intent.

## Negative controls

- selected intent outside the already-validated manifest never reaches adapter launch.
- OMP cannot append write/edit/bash or other defaults not selected.
- OpenCode cannot leave an unselected native tool allowed.
- Unsupported selected intent on OMP fails before spawn.
- Any enforced projection on Codex/Grok/Agy/Cline fails before semantic execution while those transports lack a proven restriction seam.
- Legacy no-manifest execution remains backward-compatible.
- Adapter behavior cannot mutate the durable ceiling or manifest.

## Verification

At minimum:
- focused OMP adapter tests
- focused OpenCode adapter tests
- focused Codex/Grok/Agy/Cline rejection/legacy tests
- relevant local-agent session propagation tests
- `npm run typecheck`
- `git diff --check`
- complete changed-path audit

## Forbidden scope

- No 11-model physical canary or provider account smoke.
- No actual-exposed-tools receipt/certification claim.
- No G4 benchmark or benchmark-validity claim.
- No runtime reload, deployment, release, or production activation.
- No CapabilityPlanner/JIT producer implementation.
- No new Tool Registry, ToolAuthorityStore, or manifest store.
- No provider/model selection or Workforce Admission changes.

## Claim ceiling

This wave may establish only source-integrated provider adapter behavior and exact test evidence. It cannot claim physical provider exposure, G3 canary completion, benchmark validity, release, or production status.

## Exit criterion

Wave 3 is complete at the source-integration layer when the exact DevSpace Candidate is merged with focused tests proving OMP/OpenCode deterministic enforcement, the other four in-scope provider families fail closed rather than widen an enforced projection, legacy no-manifest behavior remains compatible, and all changes remain within this card. Then STOP before physical G3/G4 gates.
