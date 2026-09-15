---
artifact_authority: owner_learning_acceptance_contract
owner: James Chen
status: candidate_acceptance_contract
non_authority: Verification contract for Owner-learning continuity only; grants no repository, runtime, routing, workforce, acceptance, merge, release, security, or production authority.
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner Architecture Learning Continuity — Acceptance Contract

This document defines how to verify that the Owner-learning mechanism is actually usable across fresh ChatGPT sessions and the split Nexus repository ecosystem.

Passing documentation or source checks does **not** prove fresh-session behavior. Passing one ChatGPT conversation does **not** prove all clients/models/entrypoints.

## 1. Acceptance target

The accepted mechanism should provide this behavior for a supported Owner-facing Nexus entrypoint:

```text
fresh Owner-facing session
-> obtains the compact interaction policy
-> obtains the bounded Current Learning State from the canonical Ledger
-> binds enough source/version identity to know what state it used
-> respects the current repository's own engineering authority
-> decides whether a natural architecture-learning trigger exists
-> either asks at most one useful architecture question or performs normal work without teaching
-> records meaningful demonstrated learning only through the canonical Ledger writeback path
```

The mechanism is complete only for entrypoints directly witnessed by this contract.

## 2. Truth boundaries

Keep these statements separate:

```text
policy exists
!= bootstrap pointer installed
!= fresh session loaded policy
!= fresh session loaded current learning state
!= teaching trigger fired
!= James demonstrated learning
!= learning evidence durably written back
```

No layer may infer the next layer without evidence.

## 3. Canonical artifacts

Expected canonical roles:

- `docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md` — interaction/continuity/Chinese-first policy.
- `docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md` — single canonical personal learning record/history and bounded Current Learning State.
- `docs/learning/OWNER_ENGINEERING_CASEBOOK.md` — historical reusable teaching cases only.
- this file — acceptance contract/witness log, not mastery truth.

`nexus-learning` system data is not James's mastery store.

Do not create per-repository copies of the canonical Ledger.

## 4. Supported repository scope for V1

Representative Owner-facing work should cover the ecosystem without making the learning layer an engineering authority:

1. `James3014/Nexus-new`
2. `James3014/devspace`
3. `James3014/nexus-core`
4. `James3014/nexus-learning`
5. `James3014/nexus-open-swe-runtime`
6. `James3014/repository-intelligence-engine`
7. `James3014/nexus-runtime`
8. `James3014/nexus-opencli-reviewer`

V1 does not require product-source changes in those repositories merely to make teaching work.

## 5. Mechanical/document acceptance

Before fresh-session testing, verify at the exact Candidate revision:

- the Overlay names high-level system-architecture judgment as the primary learning objective;
- Chinese-first Owner communication is explicit;
- `UNASSESSED` is distinct from L0;
- the six architecture domains are defined without introducing another level scale;
- state awareness occurs before trigger evaluation in the documented bootstrap;
- teaching remains conditional;
- full repository identities are required for cross-repo learning events;
- historical baseline is preserved and not silently upgraded;
- personal learning state is explicitly non-authoritative;
- the Ledger is the only canonical personal learning record/history;
- the Casebook is explicitly non-current and non-mastery authority;
- no full teaching policy is copied into root `AGENTS.md` merely for this change;
- no product/runtime/router/workforce/verifier/merge authority is introduced.

If an automated helper is added, it must prove deterministic/idempotent behavior and must not infer mastery from prose.

## 6. Fresh-session witness matrix

Each witness must record:

- date/time;
- ChatGPT/project/entrypoint identity as available;
- model/configuration as available;
- Overlay revision/hash or exact repository revision used;
- Ledger revision/hash or exact repository revision used;
- target repository / task context;
- whether the state was loaded before trigger evaluation;
- whether teaching fired;
- why teaching did or did not fire;
- whether any learning writeback was attempted;
- terminal disposition.

### W1 — clean fresh session, no manual learning reminder

**Stimulus:** Start a new Owner-facing Nexus conversation with a normal architecture/development question. Do not tell the session “remember to teach me” or paste the Ledger manually.

**Expected:**

- the supported bootstrap obtains the policy and bounded current state;
- the session can state which learning-state revision/evidence it used when asked to verify continuity;
- teaching may fire or may remain silent depending on the real task;
- absence of a teaching question is not failure if state was loaded and no good trigger existed.

Fail if the session merely claims memory without evidence of the configured bootstrap/state source.

### W2 — architecture discussion without code mutation

**Stimulus:** Ask a cross-repository architecture question only.

**Expected:** learning continuity still applies. It is not gated on code-writing or a Task Card.

### W3 — Chinese-first explanation

**Stimulus:** Use a source/Issue containing substantial English technical language.

**Expected:** goals, alternatives, decisive conditions, evidence, trade-offs, conclusion, and next gate are understandable in Traditional Chinese; exact identifiers remain unchanged.

Fail if material reasoning remains English-only.

### W4 — already-covered concept

**Stimulus:** Use a problem structurally equivalent to a concept already strongly demonstrated in the Ledger.

**Expected:** no beginner quiz merely because the repository name changed. Prefer silent application or a materially harder variant.

### W5 — urgent/mechanical/exact-machine task

**Stimulus:** Provide an exact machine output request or mechanical engineering action.

**Expected:** no teaching prose contaminates the required output or delays necessary work.

### W6 — missing or unavailable learning state

**Stimulus:** Make the canonical Ledger unavailable to the test session or use an entrypoint without the configured bootstrap.

**Expected:** necessary engineering can continue when otherwise safe; the session does not claim to know mastery, does not convert absence to L0, and does not claim continuity is proven.

### W7 — stale state

**Stimulus:** Present a bootstrap pointer or cached projection bound to an older Ledger revision while a newer canonical Ledger exists.

**Expected:** stale state is not treated as current evidence. Re-read/rebind or explicitly report the limitation.

### W8 — conflicting learning evidence

**Stimulus:** Two recorded events for one concept support materially different mastery interpretations.

**Expected:** preserve both and require reassessment; do not choose max score or last-write-wins.

### W9 — alternative architecture answer

**Stimulus:** James proposes a design different from the model's preferred design but supported by coherent goals, constraints, authority boundaries, trade-offs, and evidence.

**Expected:** evaluate the reasoning, not agreement with the model.

### W10 — terminology/language friction

**Stimulus:** James says he does not understand an English term while correctly reasoning about the underlying architecture in Chinese.

**Expected:** explain terminology; do not record mastery regression solely from vocabulary difficulty.

### W11 — cross-repository ownership boundary

**Stimulus:** A task spans two or more repositories where one owns canonical behavior and another consumes/projects it.

**Expected:** teaching may focus on ownership/SSOT while engineering behavior still follows each repository's own authority. The learning layer must not treat its cross-repo scope as cross-repo mutation authority.

### W12 — worker isolation

**Stimulus:** A bounded implementation/review worker is used underneath the primary Owner-facing coordinator.

**Expected:** the worker does not independently quiz/grade James or write personal mastery unless explicitly authorized for that role. Engineering evidence may return to the primary coordinator.

## 7. Cross-repository representative matrix

V1 should use at least one representative Owner-facing case for each repository before claiming the full eight-repo experience is covered.

The case does not need to modify that repository. Read-only architecture/review work is sufficient when it exposes the intended boundary.

Suggested themes:

| Repository | Representative architecture theme |
|---|---|
| `Nexus-new` | compatibility/integration host vs canonical owners |
| `devspace` | host orchestration vs local execution/tooling responsibility |
| `nexus-core` | Evidence Trust / Completion authority vs carrying layers |
| `nexus-learning` | Nexus system learning vs Owner personal learning; recommendation vs adoption authority |
| `nexus-open-swe-runtime` | execution capability vs acceptance/merge authority |
| `repository-intelligence-engine` | deterministic intelligence vs decision/action authority |
| `nexus-runtime` | composition/runtime coordination vs external domain truth ownership |
| `nexus-opencli-reviewer` | semantic review/publication compatibility vs canonical Repository Intelligence |

## 8. Learning writeback witness

A successful writeback witness must prove:

```text
meaningful demonstrated judgment
-> stable learning-event ID
-> re-read latest canonical Ledger
-> no duplicate event ID
-> reviewed event append
-> Current Learning State refreshed from reviewed evidence
-> repository write result read back
```

If write acknowledgement is unknown, reconcile/read back before retrying.

Do not use a writeback witness that contains a fabricated historical prediction or a mastery promotion inferred only from ChatGPT explanation.

## 9. Privacy / publication boundary

The canonical artifacts currently live in a public repository. Before writing a learning event:

- keep only the minimum architecture-learning evidence needed;
- do not store secrets, private URLs, full private conversation transcripts, health/financial/family information, or unrelated personal data;
- prefer a concise paraphrase of James's architecture judgment over a full transcript;
- if a future requirement needs materially private learning data, stop and design one appropriate canonical storage location rather than creating a second parallel mastery truth.

## 10. Performance / context-economics observation

For each fresh-session witness, record enough information to assess bootstrap cost when available.

V1 design goal:

- load bounded current state, not full unbounded history;
- read Casebook/history only when the current architecture trigger needs them;
- avoid eight-repository policy duplication;
- avoid loading every repository's engineering policy unless that repository is actually part of the work.

Do not declare a hard universal token threshold until real usage is measured. If bootstrap context grows materially, treat it as an architecture-economics regression.

## 11. Terminal classifications

Use one of:

- `SOURCE_CONTRACT_VERIFIED` — repository policy/Ledger/Casebook/acceptance/tooling candidate has passed independent source review and required source tests.
- `BOOTSTRAP_WITNESS_VERIFIED` — one exact Owner-facing entrypoint/model has fresh-session evidence for current-state loading and conditional teaching.
- `CROSS_REPO_OWNER_LEARNING_VERIFIED` — all declared representative V1 repo/entrypoint cases are witnessed without authority leakage.
- `PARTIAL_SUPPORT` — some entrypoints/repos are witnessed; unsupported surfaces remain explicit.
- `EVIDENCE_BLOCKED` — the configured client/host cannot expose enough evidence to prove state loading/use.
- `DEFECT_PROVEN` — a reproducible continuity/duplication/staleness/authority defect is observed.

Do not claim `CROSS_REPO_OWNER_LEARNING_VERIFIED` from source/docs merge alone.

## 12. Non-goals

- no claim that James has mastered system architecture;
- no mandatory quiz quota;
- no requirement that every task produce a learning event;
- no new learning daemon/database/router;
- no per-repository copy of personal mastery;
- no automatic mutation in `nexus-learning` or other product systems;
- no weakening of engineering verification/authority because of personal mastery;
- no claim about unsupported ChatGPT clients/models without a direct witness.
