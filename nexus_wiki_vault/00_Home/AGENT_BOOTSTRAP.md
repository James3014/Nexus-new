---
title: Agent Bootstrap
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

# Agent Bootstrap

This is the canonical Agent startup sequence. All Agents entering the Nexus workspace must follow this sequence.

## Startup sequence

### Step 1: Read CURRENT_STATE

Read [CURRENT_STATE](CURRENT_STATE.md) to understand what is currently proven and what is not. Do not assume prior knowledge.

### Step 2: Identify task class

Classify your task into one of the supported classes:

| Task class | Description |
|------------|-------------|
| runtime implementation | Implementing new runtime behavior |
| bug repair | Fixing a defect in existing code |
| route or planner change | Modifying CapabilityPlanner, SkillsRouter, or route authority |
| LocalHeal change | Modifying LocalHeal or local model execution |
| benchmark task | Running or modifying benchmark harness |
| Wiki/documentation update | Updating documentation only |
| security/governance change | Modifying security or governance controls |
| research-only task | Read-only investigation with no code changes |

### Step 3: Derive 3-8 targeted retrieval handles

From the task description, extract specific search handles: filenames, module names, error strings, gate names, route names, benchmark names. Do not perform broad searches.

### Step 4: Retrieve relevant lessons and ADRs

Search targeted lesson sources:
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- `nexus_wiki_vault/01_System/ADR/`
- `docs/reports/`, `docs/arch/`, `docs/testing/`

Read only the top relevant files. Report retrieved lessons with source path and applicability.

### Step 5: Inspect code and blast radius

Before modifying any symbol:
- Use `gitnexus_impact` if available to assess blast radius
- If GitNexus is unavailable, perform targeted `rg` and manual inspection
- Report direct callers and affected processes

### Step 6: Declare status boundary

Before writing code, declare:
- **Allowed files**: which files you will touch
- **Forbidden files**: which files you must not modify
- **Status boundary**: what this task does and does not cover

### Step 7: Plan the smallest verifiable task

Define:
- What will change
- How it will be verified
- What evidence will be produced
- What the claim ceiling is (see [CLAIM_TAXONOMY](../01_System/CLAIM_TAXONOMY.md))

### Step 8: Execute in isolation

Make changes only within declared boundaries. Do not expand scope.

### Step 9: Run focused verification

Run the specific verification commands for your task class. See the per-class table below.

### Step 10: Report change, evidence, residual debt, and next gate

Produce a structured report:
- Files changed
- Verification evidence (commands + output)
- Residual debt
- Next gate or promotion step

### Step 11: Write back reusable lessons

When a failure or unexpected behavior is encountered, write it back to the Learning Closure Matrix before task finalization.

## Per-class requirements

| Task class | Minimum required reading | Preferred inspection tool | Mandatory evidence | Forbidden shortcut |
|------------|------------------------|--------------------------|-------------------|-------------------|
| runtime implementation | CURRENT_STATE, architecture blueprint | gitnexus_impact | pytest pass + runtime trace | Claiming integration without bridge evidence |
| bug repair | CURRENT_STATE, relevant ADR | gitnexus_impact | Reproduction + fix + regression test | Fixing without root cause |
| route or planner change | CURRENT_STATE, architecture blueprint, route authority docs | gitnexus_impact (upstream + downstream) | Full route test suite | Adding route without architecture authorization |
| LocalHeal change | CURRENT_STATE, LocalHeal specs | gitnexus_impact | Unit + contract tests | Claiming runtime invocation without benchmark evidence |
| benchmark task | CURRENT_STATE, benchmark methodology docs | Benchmark scripts | Reproducible benchmark run | Citing benchmark as product runtime |
| Wiki/documentation update | CURRENT_STATE, relevant source pages | Manual review | Link check + frontmatter validation | Claiming alignment without code evidence |
| security/governance change | CURRENT_STATE, governance charter | Security audit tools | Security review receipt | Weakening verifier or claim gate |
| research-only task | CURRENT_STATE, relevant sources | Read-only tools | Research report | Making code changes |

## Hard boundaries

- **Do not perform full-corpus reading for normal tasks.** Use targeted retrieval.
- **Do not modify a symbol before impact analysis when GitNexus is available.**
- **Do not treat a plan, stub, unit test, or benchmark as product runtime proof.**
- **Do not weaken verifier, claim gate, candidate isolation, or route authority.**
- **Do not add a new route, router, planner, or topology selector without explicit architecture authorization.**
- **Do not claim the entire Wiki is aligned, current, complete, or production-ready.**
- **Do not use "complete", "sealed", "productized", "production", or "ready" when evidence only proves file existence, unit tests, contracts, or benchmark execution.**

## Related pages

- [CURRENT_STATE](CURRENT_STATE.md) - what is proven
- [CLAIM_TAXONOMY](../01_System/CLAIM_TAXONOMY.md) - evidence thresholds
- [PARTNER_ONBOARDING](PARTNER_ONBOARDING.md) - human partner path
- [System Overview](System Overview.md) - architecture and entry portals
