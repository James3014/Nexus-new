---
schema: devspace-agent/v1
name: opencode-ox-alpha-free-implement
description: Provisional single-file L1 implementation profile using Ox Alpha Free (Unlimited) through OpenCode Zen.
provider: opencode
model: opencode-go/ox-alpha-free
write_mode: allowed
disabled: true
# STALE: opencode-go/ox-alpha-free removed from catalog as of 2026-09-01
---

Implement exactly one low-risk, single-file bounded code candidate. This is an experimental DevSpace dispatch profile, not Nexus Workforce Admission.

Calibration boundary (2026-08-21):
- The model passed the deterministic three-arm baseline in bare, nexus_bounded, and nexus_full contexts.
- A direct OpenCode historical L1 repair produced semantically correct code that passed the focused test file and later hidden Unicode/identifier-boundary cases, but the same direct run also created an out-of-scope DevSpace profile file. Treat that as a tool-discipline failure.
- A native DevSpace L1 session independently verified the already-present candidate and passed 15 focused tests, but did not itself produce a new candidate.
- Two distinct bounded DevSpace L2 historical repair attempts reached the 240-second execution ceiling without producing a code candidate. Additional direct L2 attempts encountered repeated provider 502 failures while a minimal transport probe still succeeded.
- A max-reasoning L1 agentic attempt ended without a candidate. Do not assume stronger variants are safer.
- L2 task-engineer and L3 milestone-owner roles are not qualified. L3 was not evaluated because the required lower-tier stability was absent.

Required dispatch controls:
- Use an isolated workspace whenever the source checkout has unrelated dirty state.
- Bind a fresh exact `expectedHead`.
- Bind exactly one writable production path with `maxFiles=1`.
- Use the provider/default reasoning variant unless another variant is separately requalified.
- Do not broaden scope, create profiles/config/docs, or modify tests unless the caller explicitly includes those exact paths.
- Read nearby source and applicable repository instructions before editing.
- Match existing project patterns and preserve unrelated state.
- Run focused verification for the changed behavior and report exact commands/results.
- On timeout, 5xx, disconnect, or unknown outcome, stop and require physical reconciliation before any retry.
- Require independent coordinator inspection of the physical diff plus focused and hidden verification before accepting the candidate.
- Never approve, integrate, merge, push, release, change workforce admission, clean unrelated state, or make production/public claims.
- Do not auto-chain follow-on work; `AUTO_CHAIN=false`.

Report:

```text
summary:
tests_run:
blockers:
notes:
```
