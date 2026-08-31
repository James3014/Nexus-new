# TASK-001 — Feature-flagged Open SWE semantic adapter

task_id: `TASK-001`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source groups:** `G1 Feature-flagged semantic adapter`
- **Requirements:** `REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006`
- **Acceptance:** `AC-001; AC-002; AC-003; AC-004; AC-005; AC-006`
- **Auto-chain:** `false`
- **Maximum claim:** A default-off Open SWE semantic adapter Candidate is implementation-correct for the tested External Intelligence seam; no activation, OpenCLI retirement, production readiness, merge, release, or deployment claim.
- **Depends on:** `none`
- **Dependency unlock evidence:** `none`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Add an optional Open SWE / Deep Agents semantic execution adapter at the existing External Intelligence transport seam, while preserving OpenCLI as the unchanged default and preserving all existing Nexus request/attempt/replay/reconciliation authority.

## Observable outcome

With default configuration, `build_automation()` still constructs the existing OpenCLI semantic path. With an explicit `open_swe` backend selection, the same `ExternalIntelligenceSidecar` can invoke a physically read-only Deep Agents semantic graph and consume a validated result without creating a second controller.

## Non-goals

- Do not enable Open SWE by default.
- Do not disable/delete OpenCLI or the reviewer LaunchAgent.
- Do not add diagnosis/repair automation in this card.
- Do not change RI Core, CapabilityPlanner, Workforce Admission, fanout/closure authority, Candidate acceptance, GitHub mutation, merge, release, or deploy authority.
- Do not vendor/fork Open SWE wholesale.
- Do not import experimental `/private/tmp` paths or depend on ad-hoc `PYTHONPATH`.
- Do not enable `task`/subagents, arbitrary execute, generic HTTP, Git/GitHub mutation, merge/release/deploy tools in the semantic graph.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| DEC-001 | replacement decision | `PARTIAL_REPLACE`, not full replacement |
| DEC-002 | execution architecture | use Open SWE / Deep Agents rather than custom semantic LLM graph |
| DEC-003 | authority boundary | Nexus retains RI/route/admission/replay/GitHub/verification/merge authority |
| DEC-004 | migration safety | OpenCLI remains default/control arm; Open SWE is non-default |
| CUR-002 | current seam | reuse `ExternalIntelligenceSidecar` and `build_automation()` |
| CUR-005 | packaging gap | no `/private/tmp` or manual path stitching |
| CUR-006 | security witness | semantic graph must be physically read-only |
| CON-001 | route authority | `CapabilityPlanner` remains sole selector/router authority |
| CON-002 | stage separation | worker cannot self-accept/integrate/merge/release |

## Owner decisions

`DEC-001; DEC-002; DEC-003; DEC-004; DEC-005` from the source spec are binding.

## Source and start state

- **Workspace/root:** `James3014/Nexus-new`
- **Branch:** execution Target/worktree selected by Nexus lifecycle; never canonical dirty checkout
- **Starting HEAD:** rebind fresh GitHub `main`; compilation basis was `c00c299152599a87efd831c3e146ecadd8f8b21f`
- **Dirty baseline:** must be clean in the governed Target/worktree
- **Required initial verification:** re-read `AGENTS.md`, this campaign INDEX, this card, `docs/agents/TASK_EXECUTION_CONTRACT.md`, `scripts/ops/external_intelligence_service.py`, `nexus/services/external_intelligence.py`, and focused tests; verify GitHub main and source seam have not materially drifted.
- **Freshness rule:** any drift in transport/attempt semantics, service construction, Open SWE/Deep Agents package identity, or task-card hash requires rebind before mutation.

## MCP execution profile

- **App/server and action snapshot:** current Nexus Gateway at dispatch time
- **Exact required actions:** `nexus_workspace_snapshot`; `nexus_worker_candidate` or equivalent current governed Candidate executor; task status/reconcile actions as required by the active schema
- **Confirmation-required actions:** Candidate approval/integration/merge are outside this card
- **Idempotency and attempt rule:** one exact task/attempt identity; timeout or disconnect must reconcile durable task and physical workspace before retry
- **Reconnect reconciliation:** use existing Nexus task/status/reconcile semantics; never launch a second mutating attempt solely because transport status is unknown
- **Transport blocker:** stale/missing governed Candidate action or required fields -> `TRANSPORT_CAPABILITY_GAP`

## Authority map

- **Selection authority:** CapabilityPlanner only
- **Execution authority:** governed Task Card + current Nexus lifecycle/Workforce Admission
- **Verification authority:** independent verifier/coordinator, not implementation model
- **Receipt authority:** existing Nexus lifecycle / External Intelligence receipt contracts
- **Approval/integration authority:** separate Owner/Nexus acceptance and integration gate; not this worker

## Allowed scope

- **Read:** `AGENTS.md`; `docs/agents/TASK_EXECUTION_CONTRACT.md`; `docs/spec/OPEN_SWE_EXECUTION_PRODUCTIONIZATION_V1.md`; `nexus/services/external_intelligence.py`; `nexus/services/external_intelligence_automation.py`; `scripts/ops/external_intelligence_service.py`; `pyproject.toml`; focused External Intelligence tests; pilot report as historical evidence only
- **Edit:** `nexus/services/external_intelligence.py`; `scripts/ops/external_intelligence_service.py`; `pyproject.toml`; `tests/services/test_external_intelligence.py`; `tests/services/test_external_intelligence_service.py`
- **Create:** at most one focused production adapter module under `nexus/services/` if keeping the Open SWE graph factory separate materially improves dependency isolation; at most one matching focused test module under `tests/services/`
- **Delete:** `none`
- **Maximum touched production files:** `4`
- **Maximum touched test files:** `3`

## Unknown scan

- **Known facts:** current service hard-wires OpenCLI; sidecar transport is already abstract; pilot proved real Deep Agents semantic execution and physical tool isolation; base Nexus install lacks Deep Agents.
- **Assumptions requiring verification:** exact current Deep Agents API remains compatible with pilot version; a clean optional dependency group can be added without making default install require Open SWE packages.
- **Architecture risks:** accidental second controller, silent fallback, direct provider/GitHub authority leakage, import-time dependency breakage.
- **Evidence risks:** fake-model tests alone could pass while real graph tool surface is unsafe; therefore compiled ToolNode inventory is mandatory.
- **Missing owner decision:** `none`

## Mandatory source audit

Before mutation, inspect the exact current constructors/callers of `OpenCLIExternalIntelligenceTransport`, `ExternalIntelligenceSidecar`, `build_automation()`, service config loading/validation, and the corresponding tests. Confirm no additional production callers would be silently changed by backend selection.

## Start-state classification

`GUARD_PREEXISTS` — durable attempt/replay/reconcile authority and transport abstraction already exist; this card adds one bounded compatible transport/runtime.

## RED or existing-guard proof

Prove before implementation that:

1. default/current service constructs only OpenCLI transport;
2. selecting an unknown semantic backend has no supported path;
3. current base environment does not import `deepagents`;
4. the pilot-qualified Open SWE graph capability set is not yet available from production code.

These are compatibility/absence witnesses, not a claim that current production is broken.

## Implementation constraints

- Implement Open SWE at the existing semantic transport boundary; do not alter durable request/attempt/reconcile state ownership.
- Preserve `TransportResult` semantics or create one deterministic conversion boundary into the same sidecar contract.
- `opencli` must remain default.
- Explicit `open_swe` selection must fail closed when dependency/runtime/graph qualification is unavailable; no silent fallback.
- Add Open SWE dependencies as optional/pinned compatible runtime dependencies. Default Nexus import/startup must remain functional without them.
- Semantic graph executable tools must be an allowlist equivalent to read-only repository/evidence operations plus bounded finding/result recording. `write_file`, `edit_file`, delete, execute/shell, `task`, network/HTTP, Git/GitHub mutation, merge, release, and deploy must be physically absent.
- No agent-readable reusable GitHub/provider credential propagation.
- No provider/model hard-code may become global route authority; exact provider/model remains a bound execution choice downstream of Nexus admission.
- Preserve existing OpenCLI tests and attempt/reconcile invariants.

## GREEN and regression gates

- `AC-001`: default service/config path still selects OpenCLI; invalid backend rejected.
- `AC-002`: production Open SWE semantic graph compiles with only approved executable tools; hidden forbidden tool calls are invalid and side-effect free.
- `AC-003`: declared optional dependency install imports Open SWE adapter without `/private/tmp`; default install path does not require Deep Agents.
- `AC-004`: sentinel controller-only sensitive environment names are not propagated to agent/sandbox execution scope; never inspect/log secret values.
- `AC-005`: ambiguous Open SWE model outcome uses same request/attempt reconciliation and never blind redispatch.
- `AC-006`: diff/source audit proves no new route, admission, direct GitHub, approval, merge, release, or deploy authority.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| V1 | repo root | `python3 -m pytest -q tests/services/test_external_intelligence.py tests/services/test_external_intelligence_service.py` | focused semantic transport/service regression | PASS |
| V2 | repo root | `python3 -m pytest -q tests/services/test_external_intelligence_automation.py` | preserve automation/replay semantics | PASS |
| V3 | repo root | `ruff check nexus/services/external_intelligence.py scripts/ops/external_intelligence_service.py tests/services/test_external_intelligence.py tests/services/test_external_intelligence_service.py` | lint affected core files | PASS; if a new adapter/test module is created, include it in the exact rerun |
| V4 | repo root | `pyright nexus/services/external_intelligence.py scripts/ops/external_intelligence_service.py` | type verification | 0 errors; include new adapter module if created |
| V5 | repo root | `git diff --check` | whitespace/patch validity | PASS |
| V6 | repo root | `git diff --name-status --diff-filter=D` | deletion guard | empty |

Additionally run the production adapter's exact compiled-tool-surface test and optional-dependency import test created by this card. Record their exact argv in the Candidate receipt.

## Physical evidence

Require exact task/attempt ID, starting main SHA, Task Card raw SHA-256, Candidate commit/tree, changed paths, dependency versions, compiled executable tool inventory, focused verifier results, replay/reconcile negative-control result, credential-propagation classification, and final clean/dirty state. Separate fake/capture-model evidence from any real model canary.

## Independent review

A fresh verifier must inspect source spec, exact Candidate diff, default OpenCLI compatibility, optional dependency boundary, graph tool inventory, replay/reconcile behavior, authority conservation, and focused test oracle strength. The implementer report alone is insufficient.

## Exit conditions

- **PASS:** exact Candidate changes only authorized paths, OpenCLI remains default, explicit Open SWE semantic execution is available and physically read-only, dependencies are optional/reproducible, existing replay/reconcile semantics are preserved, focused/negative checks pass, and independent review finds no authority expansion.
- **BLOCK:** default behavior changes; Open SWE requires `/private/tmp`/manual path stitching; forbidden tools remain executable; explicit Open SWE can silently fall back; credentials enter agent execution scope; duplicate dispatch is possible; route/admission/GitHub/merge authority leaks into adapter; required current MCP/governed execution actions are unavailable.
- **Residual debt:** portable sandbox qualification, diagnosis/repair integration, multi-canary portfolio, artifact-aware CI attribution, and activation decision.
- **Next gate:** `TASK-002` and `TASK-003` remain blocked until independent acceptance of this Candidate; no auto-chain.
