# Nexus Current Product

Status: active productization definition

This document is the public-facing product definition for Nexus. It is intentionally narrower than the full internal architecture and historical engineering lineage.

## Product definition

Nexus is an independent completion-governance and verification layer for AI-generated software changes.

Its job is not to decide which coding model is smartest or to replace the coding agent. Its job is to determine whether an agent-produced ChangeSet is supported by the evidence required to claim completion.

The core product question is:

> An AI coding agent says the task is complete. What independent evidence proves that the resulting software change is actually complete?

## Initial productization path

The current productization path starts with provider-neutral ChangeSet certification.

A certification decision is evidence-bound and uses the state vocabulary:

- `CERTIFIED`
- `REJECTED`
- `BLOCKED`

At the certification boundary, the decision must be bound to the relevant task/attempt identity, repository and source identity, base and ChangeSet identity, allowed scope, Candidate identity when applicable, verifier evidence, and deterministic artifact hashes.

Missing, stale, substituted, contradictory, or failed evidence must not produce `CERTIFIED`.

## Target workflow

```text
AI coding agent
      |
      v
  produces code change
      |
      v
   ChangeSet
      |
      v
     Nexus
      |
      +-- bind source / task identity
      +-- check authorized change scope
      +-- acquire deterministic verifier evidence
      +-- bind Candidate and evidence artifacts
      +-- reject stale / substituted / incomplete evidence
      |
      v
CERTIFIED / REJECTED / BLOCKED
      |
      v
PR / CI / engineering decision support
```

## Why this exists

Coding agents are probabilistic workers. Their natural-language completion statement is not sufficient evidence that the requested engineering outcome is physically true in the repository.

Typical failure modes include:

- a model reports completion while the physical diff is incomplete;
- tests cited by the worker were not the authoritative verification surface;
- the source revision changed after the worker started;
- the Candidate exceeded the authorized file scope;
- a timeout makes it ambiguous whether a remote action executed;
- a verifier or receipt belongs to another task, attempt, source revision, or Candidate;
- a successful model response is mistaken for approval, integration, or release authority.

Nexus is designed to make those boundaries explicit and machine-verifiable.

## Supporting engineering capabilities

The repository contains broader mechanisms that support the certification and completion-governance direction, including:

- explicit route/capability planning and authority separation;
- Workforce Admission and provider/model identity binding;
- local and online execution paths;
- Candidate isolation and scope enforcement;
- deterministic verifier execution;
- evidence/receipt identity and hashing;
- timeout recovery and reconciliation;
- CI failure evidence acquisition and advisory diagnosis;
- independent acceptance boundaries.

These are supporting capabilities. They do not imply that every capability is part of the first commercial surface or that every historical subsystem is current product authority.

## Current non-claims

Unless a specific current evidence package proves otherwise, Nexus does not claim that:

- model output is verification truth;
- a `CERTIFIED` result grants approval, merge, deployment, release, or publication authority;
- every coding agent or provider is fully integrated into one production runtime;
- benchmark success alone proves product-runtime performance;
- every historical Nexus architecture document describes current implementation state;
- autonomous execution is safe without explicit scope, identity, verification, and authority boundaries.

## Public evidence examples

Representative engineering contracts and evidence surfaces include:

- [Issue #367 — Local ChangeSet Certification v1](https://github.com/James3014/Nexus-new/issues/367)
- [Issue #398 — DevSpace execution-control and GPT -> DeepSeek E2E proof](https://github.com/James3014/Nexus-new/issues/398)
- [Issue #358 — CI Failure Intelligence](https://github.com/James3014/Nexus-new/issues/358)
- [Issue #29 — Online consumption of Local / World C evidence](https://github.com/James3014/Nexus-new/issues/29)

Each Issue has its own exact evidence and claim ceiling. A repository-level product description must not strengthen those individual claims.

## Relationship to P-X-D-R-A-C

Nexus retains the broader P-X-D-R-A-C engineering lifecycle:

`Plan -> Execute -> Diagnose -> Research -> Audit -> Crystallize`

That lifecycle describes internal governance and execution architecture. The public product surface is intentionally simpler: trustworthy completion and ChangeSet certification for agent-produced software changes.

## Historical documentation

`docs/INDEX.md` is a frozen historical engineering index and should not be treated as the current product definition.

When historical architecture documents and current product/repository evidence disagree, current source, exact runtime evidence, current verification contracts, and current product decisions take precedence within their respective authority boundaries.
