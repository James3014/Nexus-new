# Nexus Candidate-Acceptance Regression Lessons

Historical Nexus case studies only. Re-read current GitHub/repository state before using any concrete SHA or status operationally.

## 1. Exact-base debt is not Candidate success

Issue #422 / PR #423 closure evidence recorded an exact-base CI comparison where the same 31 infrastructure failures occurred on base and head with zero new Candidate failures. Nexus treated this as `EXACT_BASELINE_DEBT`, not as a claim that the verifier passed. The source/test contract could close only because Candidate-specific behavior and required checks had separate supporting evidence, while runtime/daemon/production claims remained explicitly outside scope.

Durable handle: https://github.com/James3014/Nexus-new/issues/422

Reusable rule: identical base/head failure can establish non-regression attribution; it cannot manufacture green evidence or erase an unmet contract requirement.

## 2. GitHub green checks are not formal Candidate acceptance

PR #477 recorded exact base/head/tree, focused tests, independent review, and GitHub CI while explicitly preserving the boundary that formal `nexus.candidate_acceptance.v3` still required physical executor/contract lineage.

Durable handle: https://github.com/James3014/Nexus-new/pull/477

Reusable rule: CI/check success supports acceptance but cannot replace contract, attempt, executor, Candidate-subject, or oracle binding.

## 3. A format-only follow-up claim must be proven

PR #477 also contained a follow-up commit described as Ruff-format-only and recorded a whitespace-insensitive diff as empty. The important pattern is not that whitespace diff is always enough; it is that a semantic-neutrality claim needs physical comparison plus the relevant verifier evidence, rather than trust in the commit title.

Reusable rule: treat `format-only`, `generated-only`, and `no semantic change` as claims requiring evidence.

## 4. Candidate, merge group, and post-merge main are different subjects

The original Candidate can be accepted relative to its expected base while the target branch later advances. Merge-queue or post-merge checks operate on different immutable subjects and answer a later integration question.

Reusable rule: never backfill missing Candidate acceptance evidence using a later merge result, and never treat Candidate acceptance as proof that the eventual integrated subject remains valid.
