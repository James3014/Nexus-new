# Campaign Index: Provider Registry Open / Cline GLM-5.2

artifact_authority: current
owner: James Chen
status: active, governed and sequential
source_specification: /Users/jameschen/Downloads/Nexus_多模型分級協作工作規範_v2.2_20260801.md
AUTO_CHAIN: false

## Objective

Remove the accidental `auto`/`agy`-only assisted-provider gate. All registered
Nexus providers remain selectable through their explicit adapters; Cline CLI
with the exact `glm-5.2` model identity is admitted as a bounded candidate
worker. Provider opening must not remove executable, authorization, model
identity, parser, verifier, or receipt gates.

## Authority boundaries

- Canonical root: `/Users/jameschen/Workspace/nexus`.
- CapabilityPlanner remains route authority.
- Unknown providers fail closed; “open” means every registered provider is
  selectable, not arbitrary shell execution.
- Cline/GLM-5.2 is a conditional bounded candidate until physical verification
  evidence exists; it cannot approve, integrate, push, or make claims.
- No provider task may modify the protected main branch or old worktrees.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `provider-registry-open-cline-glm-52` | `00-provider-registry-open-cline-glm-52.md` | COMPLETED | none |

## Current frontier

`provider-registry-open-cline-glm-52` is complete. Lifecycle campaign P2 may
resume as a separate explicit frontier after this card's scoped commit is
formed; no provider call or model promotion is implied by this closure.
