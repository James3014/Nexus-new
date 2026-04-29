# Nexus Public Benchmark Portfolio

## Status
Accepted planning note.

## Date
2026-04-29

## What
Nexus public claims must be measured on three independent benchmark lanes:

1. Capability lift: can the same model solve more tasks when wearing Nexus?
2. Governed delivery: can the same model produce more verified, auditable, low-trust-mismatch deliveries when wearing Nexus?
3. Cost efficiency: can Nexus keep the cost per verified delivery acceptable through routing, JIT, DDTree, self-heal, and light/full mode selection?

The benchmark is always same model bare versus same model wearing Nexus. Nexus is the battlesuit, not a separate agent.

## Why
Single solve-rate numbers are not enough for commercial evaluation. A buyer cares whether Nexus improves task success, whether the output is safe enough to deliver, and whether the added governance cost is justified.

Hidden-verifier leakage invalidates value claims. Public-candidate runs must split visible tests from hidden final gates so a model can iterate against normal feedback without seeing the actual acceptance edge cases.

## How

### Lane 1: Capability Lift
Goal: prove the model completes more real work when wearing Nexus.

Representative task families:

- SWE-style bugfix fixtures with hidden tests.
- Multi-file contract repair.
- Evidence-aware repair where visible tests pass but hidden claims fail without artifact logic.
- Governance boundary repair where a naive patch over-allows risky actions.
- Context-dependent code changes that require CodeIntel or Research context.

Primary metrics:

- eligible solve rate
- semantic verified rate
- first-pass rate
- self-heal wins
- RLM second-round wins
- hidden verifier pass rate

### Lane 2: Governed Delivery
Goal: prove the output can be trusted and handed off.

Representative task families:

- Artifact/Claim receipt validation.
- MemPalace policy and deny-by-default checks.
- CodeIntel impact evidence required for code-change tasks.
- Ultra Review high-risk review gates.
- Swarm or multi-review consensus on ambiguous changes.
- Delivery-gate and public-claim-gate replay.

Primary metrics:

- verified delivery rate
- trust mismatch rate
- public claim gate pass rate
- evidence bundle completeness
- five-pillar receipt coverage
- six-phase S/P/X/D/R/A/C trace coverage

### Lane 3: Cost Efficiency
Goal: prove Nexus chooses the right amount of armor.

Representative task families:

- Easy tasks that should route to light Nexus.
- Medium tasks that need CodeIntel/JIT but not full swarm.
- High-risk tasks that justify Ultra Review, RLM, or Swarm.
- Slow tasks where DDTree or JIT should reduce work.
- Flaky or repeated tasks where Memory should reduce repeated investigation.

Primary metrics:

- wall time per verified delivery
- token cost per verified delivery
- model calls per verified delivery
- route friction
- capability stack size
- timeout and stop-loss rate
- promotion/discard/quarantine decisions for route experiments

## Commercial-Style Suites To Consider
These are not all required for the first public claim, but they should shape the roadmap:

- SWE-bench Verified style: bugfix tasks with hidden tests and frozen repos.
- Regression selection benchmark: JIT selected tests versus full test run, with missed-candidate tracking.
- Security/governance benchmark: unsafe action, secret redaction, privilege boundary, and audit replay.
- Long-context benchmark: code-context retrieval, docs-code sync, and stale documentation traps.
- CI/ops benchmark: flaky retry, timeout handling, infra invalid classification, and reproducible reports.
- Agentic workflow benchmark: RLM trace, self-heal, rollback, swarm review, and human-handoff readiness.

## Public Claim Rules
Do not publish a headline unless:

- hidden verifier is enabled and confirmed in the report;
- bare and Nexus arms use the same model name;
- infra-invalid rows are excluded from both denominators;
- Nexus wearing evidence is present for treatment rows;
- visible tests and hidden final tests are separate for public-candidate fixtures;
- raw JSONL, markdown report, command line, and commit/diff are preserved.

Allowed headline shape:

> On a frozen N-task benchmark with T trials per task, using the same model, Nexus changed verified delivery from X% to Y%, changed hidden verifier pass rate from A% to B%, changed average wall time by C%, changed measured tokens by D%, and kept trust mismatch at E%.

## Next Implementation Notes

1. Treat `public_benchmark_rlm_harder_v2.json` as the current governance/evidence lane after hidden-test splitting.
2. Do not use `public_benchmark_nexus_value_v1.json` for public value claims until it also has visible/hidden split fixtures.
3. Add a cost-efficiency lane after route decisions are stable enough to compare light Nexus, full Nexus, and bare.
4. Add a commercial suite manifest that groups tasks by lane instead of mixing all task types into one headline.
