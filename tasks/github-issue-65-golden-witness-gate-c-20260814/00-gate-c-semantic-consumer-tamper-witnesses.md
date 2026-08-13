artifact_authority: current
task_id: github-issue-65-gate-c-semantic-consumer-tamper-witnesses
campaign_id: github-issue-65-golden-witness-gate-c-20260814
source_issue: "#65"
owner: James Chen
status: IMPLEMENTATION_ACTIVE
baseline_revision: 8e0986b40db56016c79b03eb81ff3d03c85c6f32
commit_required: true
candidate_required: true
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
---

# Gate C semantic consumer/tamper witnesses

## Objective

Harden the remaining Issue #65 Golden witnesses `GB-003`, `GB-006`, `GB-029`,
`GB-030`, `GB-049`, `GB-056`, `GB-072`, and `GB-073` with behavioral positive
and hostile/tamper evidence. Each witness must reach a semantic consumer or
authority boundary and demonstrate the intended behavior and fail-closed
response. Wording, enum/default, serialization-shape, fixture-count, and other
shape-only assertions are explicitly insufficient and forbidden.

## Inputs and dependencies

- Gate B is physically merged by PR #231 at baseline
  `a74d838cc6bb14af47ce79207181c12a1aed1d35`.
- The `GB-029`/`GB-030` implementation slice overlaps
  `tests/nexus/orchestrator/test_self_hosted_task_service.py`, which is owned
  by PR #226; serialize any mutation until PR #226 is complete and re-anchor
  to the resulting accepted head.
- No Gate C implementation may begin from this card's commit without a fresh
  baseline and independent scope/authority check.

## Allowed implementation/test files (maximum eight files)

- `tests/contracts/test_canonical_execution.py` (`GB-003`, `GB-006`)
- `tests/nexus/orchestrator/test_self_hosted_task_service.py` (`GB-029`, `GB-030`; serialized after PR #226)
- `tests/contracts/test_unified_mcp_gateway_freshness.py` (`GB-049`)
- `tests/contracts/test_unified_mcp_gateway_search.py` (`GB-056`)
- `tests/nexus/orchestrator/test_repository_contract_gate.py` (`GB-072`)
- `tests/learning/test_nexus_learning_episode_contract.py` (`GB-073`)
- this Task Card
- this campaign's `INDEX.md`

No other file is in scope. No deletions are authorized.

## Required behavioral evidence

- `GB-003`: a formal route receipt is accepted only as evidence while the
  CapabilityPlanner decision remains the route authority; tampered or forged
  receipt authority cannot replace planning.
- `GB-006`: execution channels require explicit workforce demands at the
  canonical context boundary; missing, malformed, or conflicting demand data
  fails closed at the consuming behavior.
- `GB-029`: governed submission rejects raw prompts and unknown workers before
  execution, with the rejection observed at the service boundary.
- `GB-030`: approval is bound to exact evidence and remains non-integrating;
  altered bindings or an attempted merge/integration escalation fails closed.
- `GB-049`: HEAD-only drift remains informational in the freshness consumer and
  cannot invent reload or action-review work.
- `GB-056`: search behavior uses the Python fallback only when `rg` is absent;
  a general ripgrep execution error is surfaced rather than masked as success.
- `GB-072`: a new execution-topology configuration is rejected by the
  architecture-freeze consumer, including a tampered/bypass attempt.
- `GB-073`: equivalent learning evidence yields stable episode/idempotency
  identities while altered or incomplete identity evidence fails closed.

## Forbidden scope and authority

No production, corpus, evaluator, docs, manifest, workflow, route, Workforce
policy, lifecycle, schema, approval, integration, merge, runtime, release,
public/production claim, or generated-artifact mutation. No #191 or #143 work.
Do not weaken a witness when it exposes a product defect; stop that slice and
report a separate bounded issue. This card grants no self-acceptance authority.

## Verification and exit

- Run the exact mapped nodes and adjacent focused tests after the PR226
  serialization gate is satisfied.
- Run the canonical Golden evaluator for selectable affected cases, excluding
  findings only as its documented policy permits.
- Run Ruff on changed Python tests, `git diff --check`, exact eight-file scope,
  zero deletions, and a hostile false-green review.
- Exit only as a scoped Gate C Candidate PR pending independent acceptance.
  Maximum later implementation claim:
  `GOLDEN_WITNESS_GATE_C_SEMANTIC_TESTS_CANDIDATE_ONLY`.
