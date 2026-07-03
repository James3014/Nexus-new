# LocalHeal Sprint C15-4C: Delegated Retry First-Attempt Isolation Design

**Status**: `C15_4C_DESIGN_ONLY`

**Date**: 2026-07-03

---

## Current C15-4B Blocker

The model can still solve the delegated probe on first patch attempt, so delegated retry is bypassed by first-pass correctness. This means:

1. First patch attempt produces a correct patch
2. Verifier passes
3. `solved=true` via first-pass
4. Delegated retry is never triggered because first-pass already solved

The proof path requires making the first attempt fail verifier, then verifying delegated retry can produce the correct repair.

---

## Candidate Proof Design 1: Controlled Verifier Failure via Reproduction Script

**Concept**: Use a task where the first patch attempt passes syntax check but fails the actual test (reproduction script). The verifier failure exposes information unavailable in the initial prompt, and delegated retry uses that information to produce the correct repair.

**How it works**:
1. Task has a known bug that requires understanding test output to fix
2. First patch attempt fixes syntax but not the logic
3. Verifier runs reproduction script, fails with specific error
4. Verifier failure evidence (stdout/stderr) contains the actual error message
5. Delegated retry receives verifier evidence and produces correct fix

**Acceptance criteria**:
- `pipeline_final_patch_len > 0` (patch was produced)
- `verifier_result = fail` (first attempt failed)
- `semantic_retry_evidence_ready = true` (evidence available)
- `pipeline_retry_delegated = true` (delegated retry triggered)
- After delegated retry: `verifier_result = pass` and `solved = true`

**Risk**: Model might still produce correct patch on first attempt.

---

## Candidate Proof Design 2: Two-Stage Task with Explicit Evidence Gap

**Concept**: Create a task where the first stage produces a patch that passes syntax but fails semantic verification. The verifier failure evidence reveals the actual bug, which was not visible in the initial problem statement.

**How it works**:
1. Task has a bug that is not obvious from the problem statement
2. First patch attempt makes a plausible but incorrect fix
3. Verifier runs and fails with specific error
4. Verifier failure evidence (stdout) shows the actual error
5. Delegated retry uses verifier evidence to produce correct fix

**Acceptance criteria**:
- Same as Design 1

**Risk**: Model might still produce correct patch on first attempt.

---

## Candidate Proof Design 3: Multi-File Task with Incomplete Context

**Concept**: Create a task where the first patch attempt modifies the wrong file or uses incorrect context. Verifier failure reveals the correct file or context, and delegated retry uses that information.

**How it works**:
1. Task involves multiple files
2. First patch attempt targets wrong file
3. Verifier fails with file-not-found or similar error
4. Verifier failure evidence reveals correct file path
5. Delegated retry uses correct file path

**Acceptance criteria**:
- Same as Design 1

**Risk**: Model might still target correct file on first attempt.

---

## Recommended Design

**Design 1: Controlled Verifier Failure via Reproduction Script**

This is the most promising because:
1. It leverages the existing reproduction script mechanism
2. Verifier failure evidence is naturally available
3. The delegated retry path already consumes verifier evidence
4. It does not require creating new task infrastructure

---

## Exact Acceptance Criteria

A delegated_retry solved claim requires one live row with:

```text
pipeline_retry_delegated=true
delegated_retry_stage indicates delegated retry path
delegated_retry_status=SUCCESS or equivalent
verifier_result=pass
solved=true
solve_mechanism=delegated_retry
primary first-pass did not solve
pipeline_semantic_retry did not preempt delegated retry
public_claim_allowed=false unless separately approved
```

---

## Forbidden Shortcuts

- Do not fake model output.
- Do not hardcode toy solution.
- Do not weaken verifier.
- Do not relax parser.
- Do not bypass candidate isolation.
- Do not modify CapabilityPlanner or HybridRouteDecision.
- Do not claim proof from unit mocks alone.
- Do not equate benchmark knob existence with capability proof.

---

## Implementation Plan Split into Agent B-Sized Stages

### Stage 1: Task Design (Agent B)

- Design a task where first attempt is likely to fail verifier
- Define expected failure mode
- Define expected delegated retry success
- Create task specification

### Stage 2: Deterministic Tests (Agent B)

- Add tests proving delegated retry eligibility conditions
- Add tests proving delegated retry stage tracking
- Add tests proving solve_mechanism field

### Stage 3: Live Proof (Agent B)

- Run bounded live attempts
- Verify delegated retry is triggered
- Verify delegated retry produces correct patch
- Verify verifier passes after delegated retry

### Stage 4: Claim Gate (Agent B)

- Verify all acceptance criteria met
- Verify no forbidden shortcuts used
- Verify public_claim_allowed remains false
- Create claim report

---

## Explicit Non-Claims

- Do not claim delegated_retry solved unless all acceptance criteria met.
- Do not claim Nexus full capability ready.
- Do not claim production_ready.
- Do not claim public_claim_allowed.
- Do not claim C15-4C implemented (this is design only).
