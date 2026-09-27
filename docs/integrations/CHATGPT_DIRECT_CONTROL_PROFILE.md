---
artifact_authority: derived_operational_profile
status: wave4_candidate
owner: James Chen
issue: 1154
not_authority_source: true
---

# ChatGPT Direct Control Profile

This profile records the current direct-control composition through Wave 4
reconciliation. It does not create a Router, Planner, verifier, lifecycle,
approval source, or execution lane. Repository authority remains in `AGENTS.md`
and the applicable execution contract.

## Controller

```text
James
  -> Main ChatGPT
       |-- Desktop Commander -> direct host/repository effects
       +-- Chat On Steroids -> GPT Web peer workers
```

Main ChatGPT remains the coordinator for the initial pilot.

## Desktop Commander boundary

Desktop Commander is an Owner-approved direct host execution tool for bounded
`DIRECT_CANONICAL` work. Its presence does not grant Nexus route, worker,
approval, completion, merge, release, deployment, or production authority.

Wave 1 observed two online macOS devices running Desktop Commander `0.2.51`.
Their exact device ids are runtime identities and must be rebound before each
host-bound pilot. Current file roots are host-specific: the M5 Pro host is
bounded to `/Users/james` and `/Workspace`; the second Mac remains bounded to
`/Users/jameschen` and `/Workspace`. These file roots are containment evidence,
not an OS-level shell sandbox claim.

Desktop Commander has not been proven equivalent to DevSpace governed execution,
durable operation replay, exact restart reconciliation, or effect receipts. Do
not make those claims from this profile.

## Chat On Steroids boundary

Chat On Steroids is the GPT Web peer runtime candidate for analysis, research,
review, and counterexample search. Initial CoS workers have no repository
mutation, merge, release, deployment, or production authority.

Wave 1 binds CoS release `v2.1.15` as the current pilot release observed on
2026-09-27. The upstream external-controller feature request
`totec448-spec/chat-on-steroids#82` remains open at this profile watermark.

Therefore the supported initial topology is:

```text
Main ChatGPT / Prime
  -> CoS agents
       -> worker A
       -> worker B
       -> worker C
```

Do not build or depend on a private `Nexus backend -> CoS internals` controller.
External-controller integration requires a separately supported and authenticated
upstream interface.

## Evidence and completion

- CoS worker prose is advisory evidence only.
- Desktop Commander tool history is operational evidence only and is not durable
  completion truth.
- Final repository mutation evidence must be rebound from physical Git state.
- Relevant tests/verifiers remain required by the selected Nexus execution lane.
- Nexus Core verification may be used when applicable; it does not become merge,
  release, deployment, or production authority.

## Validated direct-control state

By the Wave 3 canary in Nexus-new #1154, the composition has been exercised on
one real bounded repository task through peer analysis, isolated physical
mutation, Git/test verification, push, and a green PR Candidate without Dev MCP.
That proof does not establish DevSpace-governed equivalence, external CoS
controller support, merge authority, release authority, or production readiness.

## Legacy compatibility boundary

The repository-local `.devspace/agents/*.md` profiles are retained as
`COMPATIBILITY_ONLY` for explicit DevSpace transport selection. A bounded caller
audit found no current non-historical repository references to those profile
names. They are not a direct-control dependency and must not be used to infer
that `DIRECT_CANONICAL` or `DIRECT_DELEGATED` requires DevSpace.

Historical DevSpace ChatSwarm/OpenCLI/macOS-worker-pool Issues are reconciled by
the Wave 4 Issue writeback rather than rewritten as if they were never valid.
Residual future work such as supported external CoS control or cross-client
worker-family migration remains a separate optional frontier.

`AUTO_CHAIN=false`.
