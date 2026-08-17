---
task_id: ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01
issue: 401
repository: James3014/Nexus-new
status: ACTIVE
baseline_revision: 9296d68fe19d933cb78b9a0470a054ea5efd4c2f
execution_lane: GOVERNED_GITHUB_ISSUE_BRANCH
worker_role: primary_implementer
worker_identity: codex_luna
claim_intent: MANUAL_DISPATCH
claim_enforcement_state: PROJECTION_ONLY
claim_mode: MANUAL_DISPATCH
AUTO_CHAIN: false
max_files: 7
max_implementation_files: 5
allowed_files:
  - AGENTS.md
  - docs/agents/TASK_EXECUTION_CONTRACT.md
  - nexus/contracts/semantic_authority_delta.py
  - tests/contracts/test_semantic_authority_delta.py
  - tests/ops/test_bootstrap_authority_files.py
  - tasks/github-issue-401-semantic-authority-delta-20260817/INDEX.md
  - tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md
authorized_deletions: []
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
claim_ceiling: SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY
---

# Issue #401 — semantic authority delta contract

## Goal

Implement a pure, side-effect-free semantic predicate plus normative authority
wording and executable contract tests. A bounded evidence/provenance writeback
may remain in the existing `DIRECT_CANONICAL` lane only when every effective
authority invariant is explicitly proven unchanged. Any ambiguity fails closed
to `GOVERNED`.

## Source and authority binding

- **Owner decision:** current Owner direction makes #401 P0, selects Luna, and
  authorizes parallel work in isolated, non-overlapping worktrees.
- **Issue contract:** GitHub Issue #401, open and `READY_NOW`, observed
  2026-08-17 at `main=9296d68fe19d933cb78b9a0470a054ea5efd4c2f`.
- **Starting branch:** `codex/issue-401-semantic-authority-delta` at the exact
  baseline above, clean before this Task Card bootstrap.
- **Execution authority:** this Git-tracked card authorizes one bounded Luna
  implementation attempt after the primary commits and re-reads the card hash.
- **Verification authority:** focused executable tests plus primary physical
  diff verification and independent spec/code-quality review.
- **Integration authority:** excluded. PR #113 overlap, exact-head CI,
  independent acceptance, and protected merge authority remain separate gates.

## Required predicate

Create `nexus.contracts.semantic_authority_delta` with a typed envelope and one
deterministic classifier equivalent to:

```text
classify_semantic_authority_delta(envelope)
  -> DIRECT_CANONICAL | GOVERNED_REQUIRED
```

The classifier must not inspect filenames, line counts, model quality, or
historical prose. It may return `DIRECT_CANONICAL` only when all of these are
explicitly true and mutually consistent:

1. current Owner authorization is present;
2. write kind is evidence/provenance writeback;
3. evidence change is additive/append-only and preserves bound source, task,
   attempt, receipt, and provenance identity;
4. no deletion, historical rewrite, receipt mutation, or authority state
   transition occurs;
5. autonomy, roles/capabilities, workforce admission, provider/model worker
   authority, default route, semantic authority lineage, parser/verifier,
   independent review, forbidden actions, claim ceilings, CapabilityPlanner,
   lifecycle, Candidate, approval, integration, merge, release, security,
   migration/schema, production-data, production, and public-claim authority
   are all explicitly unchanged;
6. bounded scope, focused verifier contract, exact changed-file audit, no
   deletion, and `git diff --check` requirements remain declared;
7. no protected push/merge/release action is bundled into the writeback.

Any false, missing, unknown, malformed, contradictory, or unprovable field must
return `GOVERNED_REQUIRED`. `DIRECT_DELEGATED` is not a classifier outcome and
remains a separately Owner-selected existing lane.

## Normative documentation

- Update root `AGENTS.md` so repository authority explicitly states the
  semantic boundary, preserves existing lanes, and says ambiguity is governed.
- Update `docs/agents/TASK_EXECUTION_CONTRACT.md` with the same predicate
  contract and future-only/non-retroactive boundary.
- Preserve all exact Candidate/approval/integration/merge/release separation,
  `MERGE_SLOT_GRANTED`, `MERGE_INTENT`, expected-head/CAS, and no-direct-main
  semantics.

## Test matrix

Positive cases must include additive calibration/provenance evidence and
non-authoritative descriptive corrections with all authority dimensions
explicitly unchanged.

Negative cases must include at least autonomy increase; role/capability
expansion; new/admitted worker/provider/model; route/default broadening;
authority-lineage equivalence; parser/verifier/reviewer/forbidden-action/claim
weakening; lifecycle/Candidate/approval/integration/merge/release/security/
migration/schema/production-data/production/public-claim change; deletion or
historical rewrite; bundled protected action; missing/unknown/malformed fields;
and contradictory evidence-only plus authority-change assertions. A tiny diff
or protected filename alone must never decide the result.

Bootstrap tests must preserve exact existing merge-slot and Candidate boundary
witnesses and confirm the new authority text is loaded from both normative
documents.

## TDD and implementation constraints

1. Write the new contract tests first and record the expected RED failure.
2. Implement the smallest typed pure predicate and make the focused tests GREEN.
3. Update normative documents and bootstrap witnesses.
4. Do not integrate the predicate into `self_hosted_task_service.py` or another
   runtime selector in this first Candidate.
5. Do not change workforce YAML/policy, routes, lifecycle code, CI workflows,
   or any file outside the allowlist.
6. Do not rewrite or bless the motivating MiMo commit. The rule applies only to
   future classifications after this Candidate is independently accepted and
   integrated.

## Machine policy overlay

```json
{
  "allowed_paths": [
    "AGENTS.md",
    "docs/agents/TASK_EXECUTION_CONTRACT.md",
    "nexus/contracts/semantic_authority_delta.py",
    "tests/contracts/test_semantic_authority_delta.py",
    "tests/ops/test_bootstrap_authority_files.py",
    "tasks/github-issue-401-semantic-authority-delta-20260817/INDEX.md",
    "tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md"
  ],
  "forbidden_paths": [],
  "max_files_touched": 7
}
```

## Mandatory verification

```text
python3 -m pytest -q tests/contracts/test_semantic_authority_delta.py tests/ops/test_bootstrap_authority_files.py
python3 -m compileall -q nexus/contracts/semantic_authority_delta.py tests/contracts/test_semantic_authority_delta.py
python3 scripts/ops/agent_protocol_check.py --task-card tasks/github-issue-401-semantic-authority-delta-20260817/00-semantic-authority-delta.md --strict-boundary --check-files AGENTS.md,docs/agents/TASK_EXECUTION_CONTRACT.md,nexus/contracts/semantic_authority_delta.py,tests/contracts/test_semantic_authority_delta.py,tests/ops/test_bootstrap_authority_files.py
git diff --check
git diff --name-status 9296d68fe19d933cb78b9a0470a054ea5efd4c2f HEAD
git grep -n 'MERGE_SLOT_GRANTED\|MERGE_INTENT' AGENTS.md docs/agents/TASK_EXECUTION_CONTRACT.md tests/ops/test_bootstrap_authority_files.py
```

## Exit conditions

- **Candidate-ready:** exact allowlist, zero deletions, predicate matrix and
  bootstrap witnesses pass, card/provenance hashes are bound, and independent
  review finds no authority weakening.
- **Block:** scope expansion, ambiguity, out-of-scope path, deletion, runtime
  integration, authority weakening, stale baseline, failed verifier, or
  unresolved semantic contradiction.
- **Maximum claim:** `SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY`.
- **Next gate:** independent exact-head Candidate acceptance; PR #113 overlap
  reconciliation; exact protected-merge Owner slot. No auto-chain.
