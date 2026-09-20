# Issue #982 Wave B — governed tool authority

campaign_id: `github-issue-982-wave-b-20260919`
owner: James Chen
status: WAVE3_READY_PENDING_NEXUS_RUNTIME_REBIND
AUTO_CHAIN: false

## Contract

- Spec: `docs/specs/ISSUE_982_WAVE_B_GOVERNED_TOOL_AUTHORITY_001.md`
- Parent Issue: `James3014/Nexus-new#982`
- Durable producer-ownership freeze: #982 comment `5723728222`
- Wave A closure: #982 comment `5739580640`
- B3 MiMo route/Workforce delta: #1032 / PR #1039 / merge `d7b2e359b9d4700b33186a2633310b84ab7b502c`
- B3 runtime identity contract delta: #982 comment `5749000817`

## Frontier

1. `01-nexus-governed-tool-authority.md`
   - COMPLETE: valid governed Nexus-new B1 source integration.
2. DevSpace B2
   - COMPLETE: governed grant/tool cross-validation source integrated and live DevSpace runtime rebound.
3. #1032 B3 MiMo route/Workforce delta
   - COMPLETE: PR #1039 merged at `d7b2e359b9d4700b33186a2633310b84ab7b502c`;
   - exact B3 campaign resolves through canonical Planner/Workforce to `opencode_mimo_free`.
4. `02-governed-opencode-runtime-witness.md`
   - CURRENT FRONTIER: rebind the live Nexus Gateway/runtime to a verified source containing the merged #1032 route and this current contract;
   - require fresh MiMo catalog/preflight + Workforce Admission;
   - create the tracked canary grant/evidence and run the positive + widening-negative governed witness.

## Dependency graph

```text
Spec + tracked cards
       |
       +--> B1 Nexus-new implementation -----------+
       |                                           |
       +--> B2 DevSpace implementation ------------+--> live DevSpace rebind
       |                                           |
       +--> #1032 B3 MiMo route -------------------+
                                                   |
                                                   v
                                   live Nexus Gateway/runtime rebind
                                                   |
                                                   v
                                  B3 NEXUS_GOVERNED MiMo canary
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