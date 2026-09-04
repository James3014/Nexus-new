# Nexus

**Independent verification and completion governance for AI-generated code changes.**

Coding agents can report that a task is complete. Nexus is designed to determine whether the resulting ChangeSet is actually supported by current source identity, authorized scope, deterministic verification, and durable evidence.

Nexus is not another coding model. It is an evidence and governance layer around agent-produced software changes.

The current productization focus starts with provider-neutral ChangeSet certification:

```text
AI coding agent
      |
      v
  ChangeSet
      |
      v
    Nexus
      |
      +-- source identity
      +-- allowed scope
      +-- verifier evidence
      +-- candidate / artifact identity
      |
      v
CERTIFIED / REJECTED / BLOCKED
```

## What Nexus is

- An independent verification layer for agent-produced ChangeSets.
- An evidence-bound completion governance system.
- Provider/model-neutral at the certification boundary.
- Designed to fail closed when completion cannot be proven from current evidence.

## What Nexus is not

- Another coding LLM or coding agent.
- An autonomous approval or merge authority.
- A replacement for repository CI and tests.
- A claim that model output is trustworthy by itself.

## Engineering foundation

Nexus also contains the execution-governance machinery needed to support trustworthy agent workflows, including explicit planning and authority boundaries, Workforce Admission, local/online execution paths, candidate isolation, deterministic verification, evidence receipts, CI intelligence, and timeout/reconciliation controls.

The broader system uses the **P-X-D-R-A-C** lifecycle (Plan, Execute, Diagnose, Research, Audit, Crystallize) to turn model-assisted engineering work into evidence-bound artifacts. These mechanisms support the product direction; they are not themselves a claim of autonomous production readiness.

Representative engineering work:

- [#367 — Local ChangeSet Certification v1 contract](https://github.com/James3014/Nexus-new/issues/367)
- [#398 — bounded GPT -> Dev MCP -> DeepSeek execution-control E2E](https://github.com/James3014/Nexus-new/issues/398)
- [#358 — CI Failure Intelligence evidence capsule and advisory diagnosis](https://github.com/James3014/Nexus-new/issues/358)
- [#29 — same-task Online consumption of Local / World C evidence](https://github.com/James3014/Nexus-new/issues/29)

## Current product boundary

See **[Current Product](docs/CURRENT_PRODUCT.md)** for the current public-facing product definition, supported claims, target workflow, and non-claims.

Historical engineering documents remain in the repository for lineage, but they should not be used as the current product definition unless they are explicitly marked current.

## Quick Start

```bash
# Align the local environment
bash scripts/ops/_nexus_preflight.sh

# Inspect system status
uv run nexus status

# Run a governed task through the current CLI surface
uv run nexus run --task "your task description"
```

## Technical navigation

- **[Current Product](docs/CURRENT_PRODUCT.md)**: current product-facing definition and claim boundary.
- **[Testing Runbook](docs/testing/test_runbook.md)**: CI gates and local verification.
- **[Module Inventory](docs/arch/module-inventory.md)**: generated package/module inventory.
- **[Historical Engineering Index](docs/INDEX.md)**: frozen historical navigation; not the current product SSoT.

Current maturity: **Beta / active productization**. Public claims should remain evidence-bound to the exact revision, runtime, and verification surface that produced them.
