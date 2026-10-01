# Nexus AI Control Plane Boundary

**Status:** architecture/ownership navigation; not execution authority  
**Scope:** cross-repository maintenance boundary  
**Authority ceiling:** `NAVIGATION_ONLY_NOT_AUTHORITY`

## Decision

Nexus should converge toward the smallest model-independent control plane that lets increasingly capable agents act safely and verifiably.

The durable distinction is not "AI vs non-AI". It is:

```text
system-enforced MUST / MUST NOT
        vs
replaceable HOW strategy
```

A stronger model may replace planning heuristics, decomposition, semantic review strategy, committee topology or prompt machinery. It must not be able to replace physical authority, effect identity, reconciliation, evidence integrity or Completion truth with its own prose.

This document classifies maintenance responsibility. It does not change the current execution lanes, CapabilityPlanner authority, Workforce Admission, approval, protected merge, release or production authority.

## Four maintenance classes

### 1. CONTROL / TRUTH — preserve and strengthen

These responsibilities remain necessary even if a frontier agent becomes much more capable:

- authority and permission references;
- repository/source/attempt/effect identity;
- allowed resource/effect/path scope;
- physical state and preimage fences;
- transaction/idempotency semantics;
- durable state and crash recovery;
- `OUTCOME_UNKNOWN` reconciliation and no-blind-retry behavior;
- required verifier observations;
- evidence integrity/provenance;
- Completion/certification truth and claim ceilings.

These are not prompt suggestions. A model cannot grant itself permission, turn an unknown external effect into retry permission, or replace a required physical verifier with a statement that verification passed.

### 2. ADVISORY — retain quality, do not make universally mandatory

Examples:

- Repository Intelligence;
- Learning/effectiveness analysis;
- impact/readiness/CI evidence;
- bounded semantic diagnosis or review advice;
- memory/retrieval recommendations.

Advisory components may improve engineering decisions, but advisory output is not authority. A task that does not need an advisory subsystem must not manufacture fake evidence merely to pass through it.

### 3. STRATEGY / ADAPTER — replaceable and empirically justified

Examples include:

- Swarm or fixed multi-agent topology;
- Committee/Judge/AutoReason choreography;
- research strategy;
- prompt compilation/compression heuristics;
- model/provider selection adapters after hard authority gates;
- browser/model carriers;
- specific semantic-review prompts;
- repair-loop strategy.

These capabilities may be valuable, but they are optimizations rather than permanent system truth. They should remain removable, disableable or replaceable without changing CONTROL/TRUTH semantics. Their default use should be justified by measured task-class value rather than architectural sunk cost.

### 4. LEGACY / COMPATIBILITY — preserve only while a real consumer needs it

Examples include:

- historical implementations retained in `Nexus-new` after canonical extraction;
- forwarding-only Repository Intelligence shims in `nexus-opencli-reviewer`;
- compatibility namespaces in `nexus-runtime`;
- historical `James3014/Nexus` lineage that is not a default development target.

Do not add new canonical behavior to a compatibility surface. Retire it only after proving callers/consumers no longer require it.

## Repository ownership map

| Repository | Long-term owner boundary | Must not silently absorb |
|---|---|---|
| `James3014/Nexus-new` | governance/collaboration, current CapabilityPlanner authority, execution-lane policy, cross-repository integration and compatibility host | canonical Core/Learning/Open SWE/RI implementation, a second completion truth |
| `James3014/devspace` | local execution/control transport, workspace/process/session/effect identity, durable operation and reconciliation mechanics | Nexus route authority, Completion truth, provider strategy as permanent architecture |
| `James3014/nexus-core` | Evidence Trust + Completion Certification truth | planning, lane selection, worker/model selection, agent launching, merge/release/deployment authority |
| `James3014/nexus-learning` | evidence-bounded learning/effectiveness/recommendation contracts | self-promotion, route/workforce/approval authority |
| `James3014/nexus-open-swe-runtime` | replaceable semantic/diagnosis/bounded-repair execution runtime and model transport | Completion truth, Repository Intelligence truth, Nexus governance |
| `James3014/repository-intelligence-engine` | deterministic repository/PR/CI advisory intelligence | LLM semantics, worker dispatch, repository writes, approval/merge |
| `James3014/nexus-runtime` | planning/admission package composition, execution coordination, retry/replan state, writer/event boundaries and durable context/state | implicit provider/service selection, Core/Learning/Open SWE/RI ownership |
| `James3014/nexus-opencli-reviewer` | optional semantic PR-review application, durable semantic attempts and advisory publication compatibility | duplicate Repository Intelligence classifiers or acceptance/merge authority |

## CapabilityPlanner boundary

Current repository authority still treats CapabilityPlanner as the sole route/capability-selection authority. This wave does **not** transfer that authority.

Current source also contains planner implementation lineage in more than one package/repository. That is an ownership-convergence question for a later bounded change, not permission to introduce another planner or to delete one implementation based only on file-name duplication.

The desired conceptual split for future work is:

```text
HARD obligations
  authority / permissions / scope / risk floors /
  required evidence / verifier obligations / stop conditions

SOFT strategies
  decomposition / swarm / research / judge / committee /
  context compression / repair approach
```

Until a later implementation and acceptance gate changes source semantics, existing Planner behavior remains authoritative.

## Dependency direction

Prefer this direction:

```text
Nexus policy / authority
        ↓
explicit Runtime + DevSpace control contracts
        ↓
replaceable executor / semantic adapters
        ↓
physical effects
        ↓
Repository Intelligence / verifier evidence
        ↓
Nexus Core Completion truth
        ↓
Learning recommendations
```

No lower layer gains the authority of a later or earlier layer merely because it is called in the same workflow.

## Development rule

For new work:

1. identify the contract being changed;
2. change its canonical owner repository;
3. keep adapters/consumers thin;
4. verify only actual downstream consumers;
5. preserve source, package/pin, installed artifact and loaded-service identities as separate clocks;
6. do not assume every repository's default branch is `main`;
7. do not promote a strategy into a mandatory architecture layer without measured value.

## Non-goals of this boundary document

This document does not:

- modify runtime behavior;
- change execution-lane selection;
- change Task Card requirements;
- change Workforce Admission or model ceilings;
- move CapabilityPlanner authority;
- change Core Certification dispositions;
- authorize merge, deployment, release or production claims;
- declare Swarm/Committee/Judge useless;
- authorize deletion of legacy code.

Its sole purpose is to make future repository changes land in the correct owner and prevent increasingly capable agents from turning replaceable reasoning strategy into duplicated system authority.
