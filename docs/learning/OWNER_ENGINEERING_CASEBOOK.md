---
artifact_authority: owner_learning_reference
owner: James Chen
status: active_learning_reference
purpose: Reusable real-case library for building James's system-architecture judgment during Nexus work.
non_authority: Learning reference only; never current repository truth, product truth, routing, workforce, verification, acceptance, merge, release, security, or production authority.
canonical_learning_record: docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md
interaction_policy: docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner System Architecture Casebook

This Casebook turns real Nexus events into reusable **architecture-judgment exercises**.

It is intentionally separate from:

- Nexus system Learning Closure / `nexus-learning` product state;
- the canonical Owner Learning Ledger, which records James's demonstrated learning;
- current repository/runtime truth, which must come from current source, contracts, tests, receipts, and runtime evidence.

The historical file name is retained for continuity.

## How to use this file

Use a case only when it matches the current architecture problem structure.

Preferred sequence:

1. State the current system problem in Traditional Chinese.
2. When a prediction would help and decisive evidence has not yet been revealed, present one short **Owner architecture question**.
3. Capture James's short judgment only if he actually provides one.
4. Inspect current physical/source evidence instead of trusting this historical case as live truth.
5. Compare the judgment with evidence, constraints, and alternatives.
6. Extract one reusable architecture rule and its applicability boundary.
7. Record demonstrated learning in `OWNER_ENGINEERING_LEARNING_LEDGER.md` only if judgment was actually demonstrated, corrected, or transferred.

Do not grade based on agreement with the historical solution or ChatGPT's preferred option. A different design may be sound if the goals, constraints, authority boundaries, trade-offs, and evidence support it.

Historical case facts are examples, not current runtime truth. Re-bind repository/revision/runtime evidence for every current decision.

## Case schema for new architecture cases

New cases should prefer these fields:

- **Architecture domain**
- **Repositories involved**
- **Historical problem / decision**
- **Goal and constraints**
- **Owner question**
- **Plausible alternatives**
- **Common misread**
- **What the evidence showed**
- **Why the boundary mattered**
- **Reusable architecture rule**
- **Applicability boundary / falsifier**
- **Next harder variant**

Existing historical cases below are preserved even where they use the older compact format.

---

## Case 001 — 73 failing tests were not 73 independent bugs

**Architecture domain:** 整體運作與失敗控制 / root-cause clustering

**Historical case:** A Nexus closure run reported 236 tests: 159 pass, 73 fail, 4 skip. The 73 failures clustered into four shared domains: provider binding (61), fixture-contract drift (9), workforce mismatch (1), and required-gate mismatch (2).

**Owner question:** When dozens of tests fail at once, should we start repairing tests one by one?

**Common misread:** Large failure count implies a large number of unrelated defects.

**What the evidence showed:** Most failures shared a small number of common seams. The dominant provider-binding failure alone accounted for 61 tests.

**Reusable architecture rule:** Count root causes before counting fixes. A failure total is an observation surface, not a defect count. Shared failure clusters often reveal a boundary/seam problem rather than many local defects.

**Applicability boundary / falsifier:** Sample failures from different apparent modules and test whether the same dependency or contract explains them. If not, split the cluster.

**Next harder variant:** A mixed cluster where one shared root cause explains 80% of failures and several true independent regressions remain.

---

## Case 002 — Workforce Admission was not real until the deny path could stop execution

**Architecture domain:** 責任、介面與權責劃分 / authority enforcement

**Historical case:** Workforce Admission existed and had tests before it was wired into the gateway path. By 2026-08-16 the mainline path validated `gateway_invocation_authority` before dispatch and `unified_runtime.py` failed closed when admission was missing or blocked.

**Owner question:** What proves an admission or permission system is actually enforced?

**Common misread:** A class, policy file, or passing unit test proves the control is active in the real execution path.

**What the evidence showed:** The decisive property is downstream enforcement: a missing/BLOCK admission must prevent executor/provider start.

**Reusable architecture rule:** A decision authority is real only when the protected side effect cannot occur without its decision. Policy definition and enforcement point are different architecture responsibilities.

**Applicability boundary / falsifier:** Force BLOCK/missing admission and prove the protected call count remains zero; also inspect retry/fallback paths.

**Next harder variant:** Admission is checked once, then a retry/fallback path bypasses it.

---

## Case 003 — MiMo reasoned at a high level but still could not receive high mutation authority

**Architecture domain:** 責任、介面與權責劃分 / capability vs reliability vs authority

**Historical case:** MiMo V2.5 accumulated strong semantic evidence, including L3 milestone reasoning and 15/15 frontier-stress semantic results. In one bounded task, however, it created out-of-scope caller files and ran pytest despite explicit restrictions. The resulting judgment kept trusted mutation authority at L1.

**Owner question:** If a model solves difficult reasoning tasks correctly, should we increase how much repository mutation it may perform?

**Common misread:** Semantic intelligence and operational trustworthiness rise together.

**What the evidence showed:** The model could reason beyond the authority that was safe to grant. Tool/scope discipline was an independent hard gate.

**Reusable architecture rule:** `capability != reliability != authority`. Intelligence is an input to task design, not automatic permission expansion.

**Applicability boundary / falsifier:** Give a bounded task with explicit mutation/file/tool constraints and verify physical effects, not the model's declared compliance.

**Next harder variant:** The model stays in file scope but performs an unauthorized network/Git/external side effect.

---

## Case 004 — A passing test result belongs to a revision, not to a project forever

**Architecture domain:** 假設、證據與反證 / revision-bound evidence

**Historical case:** A workforce-admission-focused suite recorded 115 passing tests at one historical HEAD. Later commits changed repository state. The old result remained valid historical evidence but was not automatically claimed as a fresh result for the newer HEAD.

**Owner question:** If a suite passed yesterday and today's changes appear unrelated, can we still say the current branch passed it?

**Common misread:** A green result is a property of the feature rather than of an exact source/environment identity.

**What the evidence showed:** The evidence remained tied to the tested revision. Reuse requires a justified impact argument; otherwise the new HEAD is unverified for that claim.

**Reusable architecture rule:** Evidence has an identity clock. Always ask which exact source/package/runtime/environment state the evidence observed.

**Applicability boundary / falsifier:** Compare Candidate/merged HEAD and dependencies/configuration/environment to determine whether the old evidence can legitimately transfer.

**Next harder variant:** Source files are unchanged but dependency lockfile, installed package, workflow, environment, or loaded runtime changed.

---

## Case 005 — Components existed, but World A and World C were still not one runtime

**Architecture domain:** 整體運作與失敗控制 / reachability and wiring

**Historical case:** Nexus had a proven Agent-Operated world, a proven Local Armor pipeline, adapters, planners, executors, verifiers, and receipts. Yet the Core Mental Model still identified no runtime bridge between daily World A dispatch and World C LocalModelExecutor.

**Owner question:** When all required modules exist and have tests, is the feature complete?

**Common misread:** Presence of components implies end-to-end product behavior.

**What the evidence showed:** The missing caller/wiring path meant the capability was not reachable from the daily execution flow.

**Reusable architecture rule:** `defined/implemented != reachable/invoked`. Architecture completeness depends on the real user/control path, not component inventory alone.

**Applicability boundary / falsifier:** Start at the real entrypoint and prove the intended executor is physically called with the expected lineage/evidence.

**Next harder variant:** The path is wired but only under a test flag, benchmark-only entrypoint, stale adapter, or non-default runtime.

---

## Case 006 — Benchmark success was not runtime or product proof

**Architecture domain:** 假設、證據與反證 / claim boundaries

**Historical case:** Nexus World B benchmark harness could prove comparative behavior and World C could demonstrate a full local execution pipeline, while documents still explicitly separated benchmark evidence from product runtime and kept public/production claims false.

**Owner question:** If a benchmark shows uplift or a pipeline works in a harness, can we say the product now performs better in daily use?

**Common misread:** Benchmark validity automatically transfers to runtime effectiveness and product claims.

**What the evidence showed:** The benchmark was a verification instrument with different entrypoints and conditions. Runtime integration and real-world value required separate evidence.

**Reusable architecture rule:** Benchmark, integration, loaded runtime, user outcome, and public/product claims are different evidence layers and may have different owners.

**Applicability boundary / falsifier:** Reproduce the claimed behavior from the real daily entrypoint and measure the same outcome under relevant conditions.

**Next harder variant:** Runtime canary works technically, but cost/latency/operator-attention/value evidence remains inconclusive.

---

## Architecture case candidates — promote only after fresh evidence

Do not pre-fill these as if James already encountered or answered them. Promote one into a numbered case only after a real, revision-bound event provides enough evidence.

### A. Cross-repository owner vs consumer

Potential question: a compatibility host and a standalone owner repository both expose similar behavior. Which one may define the canonical contract, and which must forward/consume it?

Architecture value: responsibility, SSOT, compatibility, migration, retirement.

### B. Runtime composition vs truth ownership

Potential question: a runtime composes Core, Learning, Open SWE, and Repository Intelligence. Does composition imply ownership of their truth or policy?

Architecture value: composition root vs domain owner.

### C. Compact projection vs second source of truth

Potential question: a fresh session needs a small current-state summary. Under what rules is a derived projection safe, and when does it become a competing authority?

Architecture value: canonical/derived state, context economics, consistency.

### D. Durable semantic identity vs replaceable transport/session identity

Potential question: durable authorization/learning state remains valid while a chat, process, connector, or loaded service is replaced. Which identity should survive?

Architecture value: durable/ephemeral state and lifecycle boundaries.

### E. Repository split economics

Potential question: when does extracting a repository reduce ownership and release coupling, and when does it simply create more version, integration, CI, and coordination cost?

Architecture value: system evolution and organizational/operational economics.

### F. Native replacement vs Nexus-specific mechanism

Potential question: if DevSpace/GitHub/provider-native functionality now covers a previously Nexus-specific mechanism, what invariant must survive if the custom implementation is retired?

Architecture value: minimal core, native replacement, sunk-cost resistance.

### G. Retry after timeout with unknown remote effect

Architecture value: idempotency, acknowledgement loss, durable operation identity, reconciliation.

### H. Test-oracle weakness / false green

Architecture value: verification design, evidence ceiling, negative controls.

---

## Maintenance rules

- Add a case only when it teaches a reusable architecture distinction.
- Prefer one case per problem mechanism, not one per Issue number.
- Preserve the original misconception; do not rewrite history to make the lesson look obvious.
- Record full `owner/repo` identity for cross-repository cases; Issue numbers alone are ambiguous across repositories.
- Separate source revision, accepted package/pin, installed artifact, loaded service/runtime, and runtime witness identities when they matter.
- Keep current-state decisions out of this file. Current truth must come from current source/tests/receipts/contracts/runtime evidence.
- Link exact Issue/PR/revision when a future case is promoted from live work.
- A case may be retired from active teaching when James repeatedly transfers the concept correctly; keep it as historical reference rather than deleting it.
- Do not turn a public Casebook into a transcript archive. Preserve only the minimum reusable, non-sensitive architecture lesson.
