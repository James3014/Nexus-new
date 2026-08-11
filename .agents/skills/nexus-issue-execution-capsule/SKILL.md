---
name: nexus-issue-execution-capsule
description: Execute bounded worker-side Nexus GitHub Issue, PR, or CI repair and implementation with authoritative context, exact-environment reproduction, bounded sibling checks, and revision-fresh evidence. Use when repeated exploration, environment drift, or sibling call-site failures could invalidate the fix or its claim. Do not use for nexus-mcp-task-executor, nexus-bug-diagnosis, Candidate acceptance, approval or promotion, route authority, or lifecycle authority.
---

# Nexus Issue Execution Capsule

Use this skill for one bounded, worker-side Nexus GitHub Issue, PR, or CI repair
or implementation. It is an execution-discipline overlay only: it structures
investigation, repair, and evidence without becoming an executor, diagnostician,
Candidate acceptance gate, route authority, or lifecycle controller. Optimize
for correctness over speed. Do not widen scope or perform a repository-wide
refactor.

Do not invoke this skill for `nexus-mcp-task-executor` or
`nexus-bug-diagnosis`; those skills retain their own execution and diagnosis
contracts. Do not use it to create, accept, approve, promote, integrate, or
release a Candidate, or to select routes, mutate lifecycle state, or replace
the governing route/lifecycle authority. Stop and hand off at those gates.

## Establish the capsule

1. Anchor to the authoritative repository, current main and HEAD, governing
   Task Card or explicit Owner authority, and the contract watermark. Load the
   smallest authoritative context needed for the seam; treat reports, chat,
   generated indexes, and model suggestions as non-authoritative.
2. Record the exact first failure before changing code. Capture the allowed and
   forbidden paths, required verification, claim ceiling, disproven findings,
   do-not-repeat explorations, and next gate.
3. Reproduce in the exact environment: record `cwd`, shallow/full history,
   refs and revision, permissions, credentials/auth state, event/workflow,
   provider/model, feature flags, and relevant dependency/runtime versions.
   Preserve the failure delta between the baseline and the attempted fix.
4. If authority, scope, source revision, credentials, or environment identity
   is missing or contradictory, fail closed. Report the gap; do not infer
   permission or promote a candidate.

## Investigate and repair

- Trace the confirmed failure through its API/trust seam and inspect a bounded
  set of sibling call sites sharing that seam. Use the same failure mechanism
  to choose siblings; do not turn the sweep into broad cleanup.
- Make the smallest coherent change inside the allowed paths. Preserve the
  architecture and explicitly reject scope widening and repository-wide
  refactoring.
- Run two test stages: first the minimal reproducer or focused regression,
  then the required bounded integration/acceptance checks. Run the card-defined
  verifier, structural checks, and `git diff --check` where applicable.
- Bind every claim to the exact source revision, environment, test command,
  result, and verifier artifact. Treat evidence as stale after a source,
  environment, dependency, or test-input revision; rerun before claiming.
- Keep the claim ceiling at the evidence ceiling: a local fix or green focused
  test is not integration, approval, production, or general correctness.

## Minimal execution capsule

```text
capsule:
  authority: <Owner | task-card id and hash>
  current_main: <ref and commit>
  head: <ref and commit>
  contract_watermark: <document/card revision or hash>
  first_failure: <exact command, output, and location>
  environment: {cwd, history, refs, permissions, credentials, event, workflow, provider}
  allowed: [<paths>]
  forbidden: [<paths/actions>]
  failure_delta: <baseline -> attempted behavior>
  sibling_sweep: <same API/trust seam and bounded call sites>
  verification: [<stage 1>, <stage 2>, <verifier>]
  disproven: [<hypotheses/findings>]
  do_not_repeat: [<failed explorations>]
  claim_ceiling: <what the evidence permits>
  next_gate: <exact owner/verifier/lifecycle gate>
```

## Compact receipt

```text
receipt: <task/issue>
revision: <commit>
environment: <cwd + topology fingerprint>
delta: <failure before / result after>
tests: <stage-1>; <stage-2>; verifier=<status>
siblings: <bounded seam sweep result>
freshness: <source/test/environment revisions checked>
claim: <bounded claim only>
next_gate: <remaining gate or FAIL_CLOSED reason>
```

Never claim completion when the capsule is incomplete, evidence is stale, or a
required gate is absent. Keep the receipt compact and leave unresolved work at
the next explicit gate.
