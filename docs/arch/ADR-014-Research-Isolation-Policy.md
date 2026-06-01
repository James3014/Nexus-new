# ADR 014: Research Isolation Policy

## Status

accepted

## Context

Research-heavy Nexus routes can contaminate downstream design if the research
stage sees the final user goal, solution hints, or target patch shape. The
existing route policy, capability planner, research pack, and receipt adapters
already provide the control-plane seams needed for a small fail-closed policy.

## Decision

Add research isolation as a sidecar policy instead of embedding all behavior in
the capability planner or research pipeline.

- `L0`: direct research with full goal visibility.
- `L1`: masked research with facts-only output.
- `L2`: no-goal-visibility research contract. The first implementation records
  the decision and receipt semantics without adding a new multi-agent runner.

The implementation is split by concern:

- `isolation_policy`: classify the isolation level.
- `masked_brief`: build the masked research input.
- `research_facts`: shape facts-only output and isolation receipts.
- `contamination_guard`: reject design language in facts-only artifacts.
- `ResearchReceiptAdapter`: fail closed unless L1/L2 facts-only receipts pass;
  it must not infer success from legacy `research_pack.v1` artifacts.

## Consequences

- Legacy `research_pack.v1` remains compatible for L0.
- L1/L2 require `research_facts.v1`, `research_isolation_receipt.v1`, and a
  passing contamination guard before the research capability gate passes.
- The planner exposes only a minimal summary in
  `signal_snapshot.research_isolation_policy`: level, goal visibility, output
  mode, and whether confirmation is required. It must not expose policy reasons,
  forbidden-field lists, prompt details, artifact shaping, or receipt validation
  state.

## Hard Rules

- Planner must not assemble or mutate research prompts from isolation summary.
  The summary is a routing signal, not a prompt authoring surface.
- `ResearchReceiptAdapter` must fail closed for L1/L2 and must never infer gate
  success from legacy `research_pack.v1` compatibility artifacts.
- Residual debt in tactical route policy or local-heal receipt registries must
  be fixed in their own change families and must not expand isolation scope.

## Lessons

- The GitNexus MCP tools were not exposed in this run, and `npx gitnexus --help`
  failed inside the sandbox because npm could not write logs under the home
  directory. Unsandboxed execution was rejected because `npx` could fetch and
  execute unverified npm code against a private repo. The safe fallback is to
  record the missing GitNexus check, use local call-site and test-impact grep for
  bounded blast-radius review, and avoid treating that fallback as equivalent to
  a real GitNexus impact report.
- Future GitNexus access should prefer a preinstalled, pinned local binary or MCP
  server over ad-hoc `npx` execution.
- Impacted regression expansion exposed failures outside this change family:
  `local_heal` receipt registration from the active LocalHeal worktree and a
  tactical-route expectation that currently wants `research` in a high-risk
  sequence. The safe response is not to broaden research selection from the new
  isolation policy; isolation records visibility and facts-only requirements, but
  substantive research selection still belongs to the existing evidence-demand
  policy.

## Verification

- `uv run pytest tests/research/test_research_isolation.py tests/research/test_research_pack.py tests/engine/test_capability_receipt_adapters.py -q`
- `uv run pytest tests/engine/test_capability_planner.py tests/engine/test_pipeline_stages.py tests/engine/test_research_auto_trigger.py -q`
- `uv run pytest tests/app/test_research_flow_service.py -q`
- `uv run pytest tests/engine/test_route_tactical_policy.py tests/engine/test_route_contracts.py tests/engine/test_capability_receipt_policy.py::test_receipt_backed_capabilities_match_adapter_registry_after_alias_normalization tests/engine/test_capability_planner.py::test_capability_planner_research_isolation_snapshot_stays_minimal tests/research/test_research_isolation.py::test_capability_planner_exposes_research_isolation_snapshot tests/research/test_research_isolation.py::test_research_receipt_l1_does_not_infer_success_from_legacy_pack -q`
- `uv run python -m py_compile nexus/engine/capability_receipt_policy.py nexus/engine/route_tactical_policy.py tests/engine/test_capability_planner.py`

## Impact Evidence Follow-up (2026-06-02)

- GitNexus MCP tools are still unavailable in this runtime (`tool_search` returned
  no GitNexus tools).
- `npx gitnexus analyze` remains non-viable in this sandboxed flow (long-running
  npm exec, no trustworthy pinned local binary in this environment).
- Local fallback was used for this iteration: tactical and receipt contract
  coverage through targeted route/receipt/planner/research tests above. This is
  still non-equivalent to GitNexus graph impact evidence and remains an explicit
  residual audit gap.
