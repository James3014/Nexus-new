# Task Card: Issue #982 Wave 6 — G4 benchmark validity and bounded benchmark

artifact_authority: current
task_id: `issue-982-wave6-g4-benchmark-20260918`
owner: James Chen
status: BLOCKED_PENDING_G3
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Entry gate

Execute only after Wave 5 durable evidence proves a real intervention for at least one currently admitted transport family. The Owner explicitly requested Wave 5 then Wave 6 in this conversation; once this entry gate is satisfied, that request authorizes Wave 6 execution without creating generic auto-chain authority.

## Objective

Measure the operational effect of truthful tool projection only on G3-validated enforceable paths. Do not benchmark unavailable, request-only, or fail-closed-before-provider identities as if they received a smaller physical tool surface.

## Frozen benchmark design

Unit of comparison: paired A/B run on the same task + exact model identity.

Arms:
- A: four harmless read/search/list intents
- B: `workspace.read` only

Primary task family: read-only repository discovery questions whose verifier has an exact deterministic answer. Tasks must not require mutation, shell, network, or provider-specific hidden tools.

Sample rule:
- use at least 4 distinct deterministic tasks per enforceable transport family;
- include at least 2 exact model identities when the family has 2 or more G3-valid identities;
- run one paired A/B observation per task/model; exact retries are evidence reconciliation only, not extra samples.
This yields a bounded engineering benchmark, not a statistical model-quality ranking.

If G3 validates only OpenCode, default sample is 4 tasks × 2 representative G3-valid OpenCode identities × 2 arms = 16 physical runs. Other G3-valid OpenCode identities keep their G3 classification but are not included in a family-level benchmark claim unless separately sampled.

## Metrics

For each paired sample record:
- verifier correctness/pass
- required-tool success/failure
- wrong/unauthorized invocation
- physical allowed/exposed-surface count or strongest truthful equivalent
- exposure reduction
- wall latency
- provider/tool failure
- repair/retry
- token/schema bytes only if physically reported

Aggregate:
- verifier-pass noninferiority
- required-tool recall
- unauthorized invocation count
- exposure reduction
- p50/p95 latency
- failure/repair rate
- telemetry coverage

Missing token/schema telemetry remains `NOT_OBSERVED`; do not synthesize provider token counts.

## Acceptance interpretation

The benchmark may be called valid only if:
- every benchmarked identity has a valid G3 intervention witness;
- Arm B never physically gains tools outside its selected set;
- no high-risk required-tool miss is hidden;
- verifier correctness is not materially degraded on tasks whose required tool remains authorized;
- measured surface reduction is real, not prompt policy;
- denominator, exclusions, failed runs, and unavailable identities are preserved.

The previously discussed ~98% required-tool recall and ~30% schema/context-reduction figures are contextual targets, not automatic pass/fail claims when the bounded sample or telemetry cannot support them.

## Output / stop

Write one durable #982 Wave 6 receipt containing:
- exact G3-valid denominator
- task/sample manifest
- raw paired outcomes
- aggregate metrics
- explicit `NOT_OBSERVED` fields
- benchmark validity verdict and claim ceiling

Do not mutate provider routing, model admission, JIT selection policy, Workforce policy, or production code during benchmark execution. Do not close #982 unless all Issue-owned remaining gates are independently satisfied.
