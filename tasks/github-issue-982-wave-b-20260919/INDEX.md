# Issue #982 Wave B — governed tool authority

campaign_id: `github-issue-982-wave-b-20260919`
owner: James Chen
status: B3_CONTRACT_DELTA_TRACKED_PENDING_GATEWAY_REBIND
AUTO_CHAIN: false

## Contract

- Spec: `docs/specs/ISSUE_982_WAVE_B_GOVERNED_TOOL_AUTHORITY_001.md`
- Parent Issue: `James3014/Nexus-new#982`
- Durable producer-ownership freeze: #982 comment `5723728222`
- Wave A closure: #982 comment `5739580640`

## Frontier

1. `01-nexus-governed-tool-authority.md`
   - Nexus-new tracked implementation authority.
   - Produces the canonical governed tool-authority/JIT materialization primitives.
2. DevSpace B2
   - separate Owner-inline authority from the explicit Wave B request;
   - bounded by the Spec and DevSpace `AGENTS.md`;
   - must extend `nexus.devspace.execution_grant.v1` with backward-compatible tool-authority validation.
3. `02-governed-opencode-runtime-witness.md`
   - B1+B2 and #1032 route source integration are complete;
   - blocked until the live Nexus Gateway/runtime source contains `d7b2e359b9d4700b33186a2633310b84ab7b502c` or a later verified descendant and fresh MiMo admission passes;
   - creates the tracked canary grant/evidence and runs the positive + widening-negative governed witness.

## Dependency graph

```text
Spec + tracked cards
       |
       +--> B1 Nexus-new implementation ----+
       |                                     |
       +--> B2 DevSpace implementation ------+--> live DevSpace cutover/rebind
                                             |
                                             v
                                  B3 NEXUS_GOVERNED canary
                                             |
                                             v
                                      #982 receipt
                                             |
                                             STOP
```

B1 and B2 source implementation may proceed in parallel only after this contract is tracked and each repository has its own valid mutation authority.

## Stop boundary

No card or Owner-inline Wave B authority starts G4 benchmark, Wave C, release, or production promotion.

`AUTO_CHAIN=false`.

## B3 2026-09-20 contract delta

The historical `opencode/big-pickle` B3 witness binding is superseded.

Current exact B3 witness route:

```text
verified campaign github-issue-982-wave-b-20260919
  -> bounded_candidate_generation / L1 / nexus_bounded / mutation_intent=false
  -> opencode_mimo_free
  -> opencode / opencode/mimo-v2.5-free
```

Owning source delta: #1032 / PR #1039 / merge `d7b2e359b9d4700b33186a2633310b84ab7b502c`.

No caller provider/model override, global MiMo promotion, OWNER_DIRECT fallback, Wave 4, release, or production claim is authorized.
