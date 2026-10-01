# Task Card: Issue #982 Wave 5 — G3 physical tool-exposure canary

artifact_authority: current
task_id: `issue-982-wave5-g3-physical-canary-20260918`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Complete the G3 physical exposure gate for Issue #982 against current DevSpace runtime identity, without pretending unavailable or non-enforceable transports are enforced.

## Source fence

- Nexus-new authority base: `cc76280a1db0744f63e078cc6075971557a45025`
- DevSpace source/runtime: `bbf265621ab68dcd9676276fc22b67e99c85391a` / `devspace-1.0.7-bbf26562`
- Historical G3 baseline: 11 exact identities recorded in #982.
- Current preflight rebind:
  - Codex `gpt-5.6-terra`: BLOCKED, `RUNTIME_STARTUP_NOT_READY`
  - Codex `gpt-5.6-sol`: BLOCKED, `RUNTIME_STARTUP_NOT_READY`
  - OMP `google/gemini-3.7-flash`: provider disabled
  - Grok `grok-4.6`: current runtime ready / reachability unknown
  - Agy `gemini-3.8-flash-medium`: current runtime ready / reachability unknown
  - Cline `poolside/laguna-s-2.1:free`: current runtime ready / reachability unknown
  - OpenCode `big-pickle`, `mimo-v2.5-free`, `muse-spark-1.2-contributor-free`, `nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`: current runtime ready / reachability unknown

Historical baseline identities that are currently unavailable remain in the receipt with explicit disposition; they are not silently removed from history and are not counted as current-admissible physical-canary successes.

## Required prerequisite repair

Current DevSpace main still accepts `authorizedToolCeiling` without `toolProjectionManifest`, even though #982 comments 5723700649 / 5723723318 already froze the symmetric fail-closed invariant.

Allowed DevSpace mutation scope for this prerequisite:
- `src/local-agent-contract.ts`
- `src/local-agent-execution-contract.test.ts`

Required invariant:
- neither ceiling nor manifest => legacy compatibility permitted
- manifest without ceiling => reject
- ceiling without manifest => reject
- both => existing exact ceiling/subset/authority/task validation remains unchanged

No provider adapter change is authorized by this prerequisite.

## Authenticated transport / freshness gate

Before physical canaries, bind the actual authorized ChatGPT -> DevSpace transport to the live server generation without handling, extracting, bypassing, or reissuing Owner OAuth credentials.

Preferred witness remains a fresh authenticated MCP `tools/list` acknowledgement when the host exposes a safe reconnect primitive.

When the host fixes tool metadata at conversation start and does not expose a safe fresh-session primitive, the following stronger execution-path witness is accepted instead:

1. live `capability_convergence_status` shows the authoritative production role `CONVERGED`, exact live source/build identity, and both required capabilities:
   - `agent_start.executionContract.authorizedToolCeiling`
   - `agent_start.executionContract.toolProjectionManifest`;
2. the already-authorized ChatGPT connector sends a bounded `agent_start` request containing both fields to that exact live server, even if the host-side displayed schema is stale;
3. DevSpace returns a durable `agentId`;
4. post-readback of the durable `local_agent_sessions.execution_contract` proves the exact ceiling, manifest schema, task/attempt identity, and selected set survived the public MCP admission path;
5. provider-boundary behavior reflects that projection (for example, a provider lacking a proven seam fails closed with `PROVIDER_PROTOCOL_ERROR` rather than running the legacy wider surface).

This alternative is an execution/readback freshness witness, not a permission to bypass OAuth. Do not read, export, synthesize, or privately mint Owner credentials merely to manufacture a new client session.

The stale ChatGPT-native tool metadata must not be used as proof that the live production contract is absent when the exact authenticated round-trip and durable readback prove otherwise.

## Canary contract

Use OWNER_DIRECT solely because the Owner explicitly authorized this bounded evidence run. DevSpace validates/persists/enforces; it does not invent the ceiling.

Harmless canonical ceiling for both arms:
- `workspace.read`
- `workspace.search_text`
- `workspace.search_paths`
- `workspace.list`

Arm A selected set: all four intents.
Arm B selected set: `workspace.read` only.

Use the same read-only fixture, task/prompt, provider/model, source/build, retry policy, and output expectation across arms. No `workspace.mutate` or `process.execute` intent is authorized.

For every current-admissible baseline identity, capture:
- exact provider/model
- live source/build and fresh MCP catalog identity
- exact manifest identity/selected set
- start/terminal status
- provider session identity when observable
- physical enforcement classification
- strongest authoritative exposure evidence available
- excluded-search behavior for Arm B
- wall time / failure state
- tool/schema/token telemetry only when actually available

Expected source-level classifications remain evidence hypotheses, not pre-awarded verdicts:
- OpenCode: native permission seam should be enforceable
- Grok/Agy/Cline: current Wave 3 source should fail closed before semantic execution when a projection is present
- Codex/OMP: current admission state is unavailable unless rebind proves otherwise

## Physical witness rules

An `ENFORCED_*` result requires:
1. selected-set difference is bound to the exact run;
2. exact native/managed construction evidence differs consistently with the selected set;
3. excluded search capability in Arm B is physically unavailable/rejected or the strongest provider-owned equivalent proves it absent;
4. no provider adapter appends defaults outside the selected set;
5. replay/second arm does not silently widen;
6. source/build/provider/model/session identity remains bound.

If exact provider schema introspection is unavailable, use the strongest deterministic native permission/config construction plus observed denied/unavailable behavior and state the remaining observation ceiling explicitly.

## Verification / stop

- prerequisite repair unit + negative tests PASS
- full relevant DevSpace regression/typecheck/diff-check PASS
- repair merged and live before canary
- fresh MCP schema acknowledgement PASS
- all current-admissible baseline identities receive both A/B dispositions
- historical unavailable identities receive explicit current-state disposition
- no false `ENFORCED_*` classification
- durable #982 Wave 5 receipt records denominator and results

Wave 5 may set `BENCHMARK_VALIDITY=TRUE` only for transport families/identities with valid physical intervention witnesses. It does not authorize benchmark execution beyond the separately tracked Wave 6 card.

## Evidence-gate amendment — 2026-09-18

Host/tooling observation:
- ChatGPT's loaded `agent_start` metadata predates the live Wave 4 schema and reports `RECONNECT_REQUIRED` because no safe active-session generation snapshot is exposed to this request context.
- The host does not expose an authorized generic reconnect/raw-MCP primitive, and automation is not permitted to extract or bypass the Owner OAuth token merely to create one.
- A bounded authenticated connector probe on live DevSpace accepted metadata-hidden `authorizedToolCeiling` + `toolProjectionManifest`, persisted the exact contract in the durable agent row, and Grok then failed closed at the provider boundary with `PROVIDER_PROTOCOL_ERROR`.

Therefore G3 freshness is bound to the live server capability manifest plus exact authenticated admission/persistence/provider-behavior round trip. This changes only the evidence mechanism; tool authority, selected-set semantics, denominator, canary arms, and provider classifications are unchanged.
