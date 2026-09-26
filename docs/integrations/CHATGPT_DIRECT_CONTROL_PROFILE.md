---
artifact_authority: derived_operational_profile
status: wave1_candidate
owner: James Chen
issue: 1154
not_authority_source: true
---

# ChatGPT Direct Control Profile

This profile records the current direct-control composition for Wave 1. It does
not create a Router, Planner, verifier, lifecycle, approval source, or execution
lane. Repository authority remains in `AGENTS.md` and the applicable execution
contract.

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
host-bound pilot. Filesystem access was tightened from empty/full-filesystem
access to `/Users/jameschen` and `/Workspace` on both devices.

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

## Wave 2 entry gates

Wave 2 may start only after:

1. both Desktop Commander device/runtime identities are rebound;
2. filesystem containment remains bounded;
3. the exact CoS runtime/tool surface is available to Main ChatGPT;
4. CoS workers remain non-mutating;
5. no step requires Dev MCP solely to reach either independent pilot.

Wave 2 runs two independent canaries in parallel:
- Desktop Commander direct host/repository execution;
- CoS three-worker parallel, targeted-continuation, and sleep/wake/reuse.

`AUTO_CHAIN=false`.
