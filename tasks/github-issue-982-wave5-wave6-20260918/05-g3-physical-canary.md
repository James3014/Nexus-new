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

## Fresh MCP-session gate

Before physical canaries:
1. connect a fresh authenticated MCP client to the live DevSpace service;
2. perform `tools/list`;
3. prove the returned `agent_start.executionContract` schema includes both `authorizedToolCeiling` and `toolProjectionManifest`;
4. bind the fresh session/catalog generation and live source/build identity.

The stale ChatGPT-native tool schema must not be used as proof that the fresh production tool contract is absent.

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
