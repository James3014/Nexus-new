---
artifact_authority: owner_learning_reference
owner: James Chen
status: active_learning_reference
purpose: Reusable real-case library for building James's engineering judgment during Nexus work.
non_authority: Learning reference only; never repository, product, routing, verification, acceptance, merge, release, or production authority.
---

# Owner Engineering Casebook

This casebook turns real Nexus engineering events into reusable judgment exercises. It is intentionally separate from the system Learning Closure Matrix: that matrix records Nexus prevention rules; this file records what an Owner can learn from selected cases.

## How to use this file

Use a case only when it matches the current engineering problem. Prefer this sequence:

1. Present the **Owner question** without revealing the answer when a prediction would help.
2. Capture James's short prediction.
3. Inspect current physical evidence rather than trusting this historical case as live truth.
4. Compare the prediction with the evidence.
5. Extract one reusable rule.
6. Record demonstrated learning in `OWNER_ENGINEERING_LEARNING_LEDGER.md` only if judgment actually changed or transferred.

Historical case facts are examples, not current runtime truth. Re-bind repository/revision/runtime evidence for any current decision.

---

## Case 001 — 73 failing tests were not 73 independent bugs

**Learning domain:** Root cause / failure clustering

**Historical case:** A Nexus closure run reported 236 tests: 159 pass, 73 fail, 4 skip. The 73 failures clustered into four shared domains: provider binding (61), fixture-contract drift (9), workforce mismatch (1), and required-gate mismatch (2).

**Owner question:** When dozens of tests fail at once, should we start repairing tests one by one?

**Common misread:** Large failure count implies a large number of unrelated defects.

**What the evidence showed:** Most failures shared a small number of common seams. The dominant provider-binding failure alone accounted for 61 tests.

**Reusable rule:** Count root causes before counting fixes. A failure total is an observation surface, not a defect count.

**High-value falsification:** Pick failures from different apparent modules and test whether the same shared dependency or fixture explains them. If not, split the cluster.

**Next harder variant:** A mixed cluster where one shared root cause explains 80% of failures and several true independent regressions remain.

---

## Case 002 — Workforce Admission was not real until the deny path could stop execution

**Learning domain:** Fail-closed / authority enforcement

**Historical case:** Workforce Admission existed and had tests before it was wired into the gateway path. By 2026-08-16 the mainline path validated `gateway_invocation_authority` before dispatch and `unified_runtime.py` failed closed when admission was missing or blocked.

**Owner question:** What proves an admission or permission system is actually enforced?

**Common misread:** A class, policy file, or passing unit test proves the control is active in the real execution path.

**What the evidence showed:** The decisive property is downstream enforcement: a missing/BLOCK admission must prevent executor/provider start.

**Reusable rule:** An authority check is real only when the protected side effect cannot occur without it.

**High-value falsification:** Force BLOCK or missing admission and prove provider/executor call count remains zero.

**Next harder variant:** Admission is checked once, then a retry/fallback path bypasses it.

---

## Case 003 — MiMo reasoned at a high level but still could not receive high mutation authority

**Learning domain:** AI worker capability / reliability / tool discipline / authority

**Historical case:** MiMo V2.5 accumulated strong semantic evidence, including L3 milestone reasoning and 15/15 frontier-stress semantic results. In one bounded task, however, it created out-of-scope caller files and ran pytest despite explicit restrictions. The resulting judgment kept trusted mutation authority at L1.

**Owner question:** If a model solves difficult reasoning tasks correctly, should we increase how much repository mutation it may perform?

**Common misread:** Semantic intelligence and operational trustworthiness rise together.

**What the evidence showed:** The model could reason beyond the authority that was safe to grant. Tool/scope discipline was an independent hard gate.

**Reusable rule:** `capability != reliability != authority`. Higher reasoning ability justifies harder candidate work, not automatic permission expansion.

**High-value falsification:** Give a bounded task with explicit `writePaths`/file-count limits and verify the physical filesystem/diff, not the model's declared scope.

**Next harder variant:** The model stays in scope but performs an unauthorized network or Git side effect.

---

## Case 004 — A passing test result belongs to a revision, not to a project forever

**Learning domain:** Git / revision-bound evidence

**Historical case:** A workforce-admission-focused suite recorded 115 passing tests at one historical HEAD. Later commits changed repository state. The old result remained valid historical evidence but was not automatically claimed as a fresh result for the newer HEAD.

**Owner question:** If a suite passed yesterday and today's changes appear unrelated, can we still say the current branch passed it?

**Common misread:** A green test result is a property of the feature rather than of an exact source/environment identity.

**What the evidence showed:** The evidence remained tied to the tested revision. Reuse requires a justified impact argument; otherwise the new HEAD is unverified for that claim.

**Reusable rule:** Always ask, "Which exact revision did this evidence test?"

**High-value falsification:** Compare candidate/merged HEAD and inspect whether changed paths, dependencies, configuration, or environment can affect the tested behavior.

**Next harder variant:** Source files are unchanged but a dependency lockfile, workflow, environment, or generated contract changed.

---

## Case 005 — Components existed, but World A and World C were still not one runtime

**Learning domain:** Architecture / wiring / SSOT

**Historical case:** Nexus had a proven Agent-Operated world, a proven Local Armor pipeline, adapters, planners, executors, verifiers, and receipts. Yet the Core Mental Model still identified no runtime bridge between daily World A dispatch and World C LocalModelExecutor.

**Owner question:** When all required modules exist and have tests, is the feature complete?

**Common misread:** Presence of components implies end-to-end product behavior.

**What the evidence showed:** The missing caller/wiring path meant the capability was not reachable from the daily execution flow.

**Reusable rule:** `defined/implemented != reachable/invoked`. Trace the golden path from user entry to side effect.

**High-value falsification:** Start at the real entrypoint and prove the intended executor is physically called with the expected lineage and evidence.

**Next harder variant:** The path is wired but only under a test flag or benchmark-only entrypoint.

---

## Case 006 — Benchmark success was not runtime or product proof

**Learning domain:** Verification / claim boundaries

**Historical case:** Nexus World B benchmark harness could prove comparative behavior and World C could demonstrate a full local execution pipeline, while documents still explicitly separated benchmark evidence from product runtime and kept public/production claims false.

**Owner question:** If a benchmark shows uplift or a pipeline works in a harness, can we say the product now performs better in daily use?

**Common misread:** Benchmark validity automatically transfers to runtime effectiveness and product claims.

**What the evidence showed:** The benchmark was a verification instrument with different entrypoints and conditions. Runtime integration and real-world value required separate evidence.

**Reusable rule:** Benchmark, integration, runtime, and outcome are different claim layers.

**High-value falsification:** Reproduce the claimed behavior from the real daily entrypoint and measure the same outcome under production-relevant conditions.

**Next harder variant:** Runtime canary works technically, but cost/latency/value gate remains inconclusive.

---

## Candidate cases to add only when fresh evidence warrants them

Do not pre-fill these as lessons. Promote them into full cases after a real event provides evidence:

- retry after timeout with uncertain remote state;
- idempotency and duplicate external effects;
- lost acknowledgement and reconciliation;
- test-oracle weakness / false-green suite;
- mutation-testing style evidence that a suite constrains the intended behavior;
- rollback that restores source state but not external side effects;
- two documents or tools claiming the same authority;
- independent reviewer that merely repeats the implementer's assumptions.

## Maintenance rules

- Add a case only when it teaches a reusable engineering distinction.
- Prefer one case per failure mechanism, not one per Issue number.
- Preserve the original misconception; do not rewrite history to make the lesson look obvious.
- Keep current-state decisions out of this file. Current repository truth must come from current source/tests/receipts/authoritative policy.
- Link to exact Issue/PR/revision when a future case is created from live work.
- A case may be retired from active teaching when James repeatedly transfers the concept correctly; keep it as historical reference rather than deleting it.
