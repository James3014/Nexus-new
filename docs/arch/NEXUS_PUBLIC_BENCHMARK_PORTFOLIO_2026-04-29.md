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
2. Treat `public_benchmark_nexus_value_v1.json` as public-candidate only after every `nexus_value_*` fixture has distinct visible and hidden tests.
3. Add a cost-efficiency lane after route decisions are stable enough to compare light Nexus, full Nexus, and bare.
4. Add a commercial suite manifest that groups tasks by lane instead of mixing all task types into one headline.

## Route Optimization Loop

Use benchmark results to optimize routing, not just to score the model:

1. Run a fixed lane with hidden verifier enabled.
2. Classify every Nexus miss:
   - task too easy;
   - route did not select the needed capability;
   - capability selected but not invoked;
   - capability invoked without public-safe evidence;
   - hidden verifier too weak or too direct;
   - cost too high for the lift.
3. Change exactly one routing or fixture factor.
4. Re-run the same lane and compare verified delivery, hidden pass, trust mismatch, wall time, tokens, and model calls.
5. Promote only when the candidate route wins on verified delivery or cost per verified delivery without increasing trust mismatch.

## External Design Patterns Used

### Karpathy Autoresearch
Use the ratchet idea: fixed eval, fixed metric, small mutation, keep/discard. Nexus route experiments should produce `promote`, `discard`, or `quarantine`, never silent permanent changes.

### AutoResearchClaw
Use staged progress, SmartPause, and rollback discipline. Nexus should stop or downgrade when budget, confidence, evidence, or policy constraints fail.

### Nous Autoreason
Use tournament-style candidate comparison for high-risk or ambiguous work. LLM-style judging can rank candidates, but hidden verifier and Artifact/Claim gate remain the final authority.

## Current Capability Trigger Matrix

| Signal | Required route behavior |
|---|---|
| code change or cross-module risk | Select CodeIntel and JIT-related test evidence. |
| context gap or research source needed | Select Research/LanceDB/Memory before repair. |
| low confidence or multiple candidates | Select Autoreason and Belief. |
| repeated failure or self-heal signal | Select RLM/repair loop and consider DDTree. |
| candidate count >= 3 | Select DDTree for pruning. |
| governance, secret, auth, deny-by-default | Select MemPalace and Ultra Review. |
| high risk or hard signal | Select sandbox and Ultra Review. |
| cross-module high risk | Select Swarm as pending unless executor evidence exists. |
| parallel or split-work signal | Select Drone as pending unless executor evidence exists. |
| long-running or critical risk | Select Nightshift as pending unless report evidence exists. |
| public benchmark/report | Select benchmark and public claim gate. |

Public reports must distinguish selected capability from invoked public-safe capability.

## Failure-To-Lesson Writeback

- Hidden verifier lesson: a hidden file is not enough. Public-candidate fixtures must prove visible and hidden tests differ, and the final gate must execute the hidden test for both bare and Nexus arms.
- Routing signal lesson: short substring signals are unsafe. The `ui` signal must use token/phrase matching so words like `public` do not accidentally select UI validation.
- Smoke lesson: no-LLM benchmark runs are useful for harness and receipt validation, but not for Nexus value claims. They should be read as route/harness diagnostics only.
