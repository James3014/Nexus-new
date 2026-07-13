---
title: Partner Onboarding
type: operational
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: high
---

# Partner Onboarding

Audience: new human engineer, technical collaborator, reviewer, future maintainer.

## First 15 minutes

1. Read the [Root README](../README.md) for the single entry point and navigation.
2. Read [CURRENT_STATE](CURRENT_STATE.md) to understand what is currently proven and what is not.
3. Read [System Overview](System Overview.md) to understand the three execution worlds (A, B, C) and the architecture model.

## First 30 minutes

4. Identify the relevant flow or module for your area of work. Use the [Wiki Index](Wiki Index and Coverage Map.md) to find the right directory.
5. Read the [CLAIM_TAXONOMY](../01_System/CLAIM_TAXONOMY.md) to understand evidence thresholds and claim levels.
6. Run a read-only health or status command to verify your environment works.

## First 60 minutes

7. Complete one non-runtime or focused-test task (see starter exercises below).
8. Produce an evidence report following the format in [AGENT_BOOTSTRAP](AGENT_BOOTSTRAP.md) Step 10.

## First safe task

Your first task should be one of:
- A Wiki documentation change (Exercise 2)
- A read-only code trace (Exercise 1)
- A focused unit-test or fixture task (Exercise 3)

Do **not** begin with core routing, route authority, planner changes, or large refactors.

## First evidence-backed contribution

After completing a starter exercise, your contribution is evidence-backed when you can produce:
- The specific files changed
- The verification commands executed and their output
- A claim level from the CLAIM_TAXONOMY that matches your evidence
- Any residual debt or known limitations

## Starter exercises

### Exercise 1: Read-only system trace

| Field | Value |
|-------|-------|
| **Goal** | Trace how a specific component is called, without modifying any code |
| **Allowed scope** | Read-only: grep, file reads, GitNexus queries |
| **Required commands** | `gitnexus_context` or `rg` to find callers and callees |
| **Expected evidence** | A list of file:line references showing the call chain |
| **Forbidden claims** | "Integrated", "production ready", "complete" |
| **Exit condition** | You can name the upstream caller, the component, and the downstream consumer with file:line references |

### Exercise 2: Wiki documentation change

| Field | Value |
|-------|-------|
| **Goal** | Fix a link, add a clarification, or update a section in an existing Wiki page |
| **Allowed scope** | One file only; no new files; no runtime code |
| **Required commands** | Manual edit, then link check with `rg` |
| **Expected evidence** | The diff showing exactly what changed, and a link check showing no broken links |
| **Forbidden claims** | "Wiki is fully aligned", "all links verified" (unless you actually scanned all links) |
| **Exit condition** | The edited file renders correctly, links resolve, and the change is scoped to the declared boundary |

### Exercise 3: Focused unit-test or fixture task

| Field | Value |
|-------|-------|
| **Goal** | Write or fix a single unit test or test fixture |
| **Allowed scope** | One test file and its direct imports |
| **Required commands** | `pytest <test-file>` |
| **Expected evidence** | pytest pass output with the specific test name |
| **Forbidden claims** | "All tests pass" (unless you ran the full suite), "integrated" |
| **Exit condition** | The target test passes, no unrelated tests regress |

## Common mistakes

- Reading the entire Wiki before starting work (use targeted retrieval instead)
- Modifying code without checking blast radius
- Claiming "production ready" based on unit tests or benchmarks
- Treating World B benchmark results as product runtime evidence
- Adding new routes or planners without architecture authorization
- Using version numbers alone to determine current truth

## Where to ask for help

- Architecture questions: consult the [System Architecture Blueprint](../01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md)
- Claim level questions: consult the [CLAIM_TAXONOMY](../01_System/CLAIM_TAXONOMY.md)
- Operational questions: consult the [Learning Closure Matrix](../06_Ops/Ops - Learning Closure Matrix.md)
- Wiki structure questions: consult the [Wiki Governance Charter](../99_Schema/WIKI_GOVERNANCE_CHARTER.md)
