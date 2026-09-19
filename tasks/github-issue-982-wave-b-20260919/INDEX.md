# Issue #982 Wave B — governed tool authority

campaign_id: `github-issue-982-wave-b-20260919`
owner: James Chen
status: READY_PENDING_CONTRACT_TRACKING
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
   - blocked until B1+B2 source integration and DevSpace live runtime rebind;
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
