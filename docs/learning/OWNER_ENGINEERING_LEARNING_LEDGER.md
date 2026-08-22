---
artifact_authority: owner_learning_record
owner: James Chen
status: active_learning_record
purpose: Durable cross-session record of James's engineering judgment development during Nexus work.
non_authority: Personal learning state only; never repository, product, routing, verification, acceptance, merge, release, or production authority.
---

# Owner Engineering Learning Ledger

This ledger tracks James's engineering judgment development. It is intentionally separate from Nexus's system `Learning Closure Matrix` and `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.

Use `OWNER_ENGINEERING_CASEBOOK.md` as the reusable real-case teaching library. The Casebook stores cases; this Ledger stores James's demonstrated judgment and learning progression.

## Mastery scale

- **L0 — 未接觸**: no meaningful exposure yet.
- **L1 — 看過**: has seen the concept in a real case but has not yet demonstrated independent judgment.
- **L2 — 能解釋**: can explain the concept and why it matters.
- **L3 — 能在案例中判斷**: can apply it to a new real case and choose the right engineering conclusion.
- **L4 — 能主動提出反證**: can identify what evidence would disprove the current conclusion or expose a hidden failure.

Do not promote mastery from explanation alone. Prefer evidence from real predictions, decisions, corrections, teach-back, or falsification proposals.

## Current learning priorities

1. Architecture / SSOT / authority boundaries
2. Root cause and failure clustering
3. Testing / verification / test-oracle quality / falsification
4. Git and revision-bound evidence
5. Distributed failure semantics and reconciliation
6. AI worker capability / reliability / tool discipline / authority

## Initial baseline — 2026-08-22

This is a conservative starting baseline derived from recent Nexus discussions. It does not claim mastery that James has not demonstrated explicitly.

| Concept | Current level | Evidence so far | Next useful practice |
|---|---|---|---|
| Worker self-report != independent evidence | L1 | Discussed through candidate/acceptance workflow and recent Agent completions | On a real completed worker task, decide what must be independently re-run before acceptance |
| Revision-bound evidence | L1 | Discussed that a test result belongs to an exact commit/HEAD and does not automatically transfer after merge | On next PR, identify Candidate SHA, merged HEAD, and which evidence must be re-bound |
| Candidate != integrated != runtime-verified | L1 | Repeated Nexus examples distinguish implementation, merge, and runtime truth | On next merged change, classify exactly which layer is proven and which remains open |
| Capability != reliability != authority | L1 | MiMo/DeepSeek/Gemini calibration examples discussed | Given a strong semantic result plus one tool-discipline failure, choose the safe authority ceiling and explain why |
| Fail-closed | L1 | Workforce Admission example discussed: BLOCK should prevent provider calls | Propose a negative test that proves the denied path truly performs zero calls |
| Failure clustering / shared root cause | L1 | 73 failures versus a few shared failure domains discussed | Given a failing-test cluster, predict whether to repair individual tests or a shared seam |
| Test oracle quality | L0 | Introduced conceptually but not yet practiced | For one passing test suite, state what behavior the assertions actually prove and what they do not |
| Falsification / negative testing | L1 | WHY_CORRECT framework introduced | Before acceptance, propose 1-3 high-value cases that could disprove the proposed fix |
| Mutation-testing mindset | L0 | Mentioned as research basis for engineering evidence | Identify one plausible wrong implementation that the current tests should catch |
| Idempotency / duplicate-effect handling | L0 | Not yet practiced in this learning program | Use a retry/duplicate dispatch case from Nexus |
| Timeout / lost acknowledgement / reconciliation | L0 | Relevant to current Agent workflows but not yet practiced here | Examine one real OpenCode/Agy timeout and decide safe retry conditions |
| SSOT / duplicate authority | L1 | Central Nexus theme and recent Skill boundary discussion | Given two apparent decision sources, identify which one may actually decide and which is projection |

## Prediction & Misconception Register

Purpose: preserve the judgment *before* the answer is known. This prevents hindsight from making a lesson look easier than it was and lets later sessions measure transfer.

Record only meaningful predictions that test engineering judgment. Do not quiz James on routine syntax, trivia, or facts that can be looked up mechanically.

| ID | Date | Real case | Concept tested | James prediction before evidence | Evidence/result | Misconception or correct heuristic | Transfer status | Re-test trigger |
|---|---|---|---|---|---|---|---|---|
| P-001 | 2026-08-22 | Learning program initialization | failure clustering | Not yet captured | Historical Nexus example: 73 failures clustered into 4 failure domains | Baseline only; no demonstrated prediction yet | UNTESTED | Next natural multi-failure incident |
| P-002 | 2026-08-22 | Learning program initialization | capability vs authority | Not yet captured | Historical MiMo example: strong semantic frontier plus tool/scope hard failure kept mutation ceiling low | Baseline only; no demonstrated prediction yet | UNTESTED | Next model-promotion or dispatch-authority decision |
| P-003 | 2026-08-22 | Learning program initialization | revision-bound evidence | Not yet captured | Historical passing suite remained bound to its tested HEAD | Baseline only; no demonstrated prediction yet | UNTESTED | Next Candidate -> merge -> post-merge verification flow |

### Prediction capture rules

When a real task presents a useful learning moment:

1. Ask at most one short prediction question before revealing decisive evidence.
2. Make the choices reflect real engineering alternatives; avoid obvious answer cues.
3. Record the answer only when it teaches something reusable.
4. After evidence is inspected, classify the result as:
   - `CORRECT_TRANSFER` — correct reasoning on a materially new case;
   - `CORRECT_BUT_CUED` — answer was correct but heavily scaffolded;
   - `MISCONCEPTION_FOUND` — wrong model or missing distinction was exposed;
   - `EVIDENCE_INSUFFICIENT` — evidence did not actually resolve the question;
   - `UNTESTED` — baseline only, no prediction captured.
5. Preserve wrong predictions verbatim or faithfully paraphrased. Never rewrite them after seeing the answer.
6. A single correct prediction does not automatically promote to L3; prefer transfer across at least one new case.

## Spaced Recall Queue

Purpose: revisit concepts through *new real work*, not through repetitive classroom questions.

| Concept | Current mastery | Last meaningful exposure | Next recall mode | Trigger condition | Status |
|---|---|---|---|---|---|
| Failure clustering | L1 | 2026-08-22 baseline | Prediction | A task has many failures or symptoms | WAIT_FOR_NATURAL_CASE |
| Capability != reliability != authority | L1 | 2026-08-22 baseline | Prediction + short teach-back | Selecting/promoting a model after mixed evidence | WAIT_FOR_NATURAL_CASE |
| Revision-bound evidence | L1 | 2026-08-22 baseline | Identify exact Candidate/merged HEAD | PR or Candidate moves revisions | WAIT_FOR_NATURAL_CASE |
| Fail-closed | L1 | 2026-08-22 baseline | Propose falsification | Permission/admission/claim gate is changed or reviewed | WAIT_FOR_NATURAL_CASE |
| Test oracle quality | L0 | none | Guided question | A suite passes and acceptance depends on what it truly proves | WAIT_FOR_NATURAL_CASE |
| Timeout/reconciliation | L0 | none | Scenario prediction | Real worker timeout, disconnect, uncertain acknowledgement, or retry | WAIT_FOR_NATURAL_CASE |
| Idempotency | L0 | none | Scenario prediction | Duplicate dispatch, webhook, retry, or external side effect appears | WAIT_FOR_NATURAL_CASE |

### Spaced recall rules

- Prefer natural triggers from active Nexus work over calendar-based quizzes.
- Do not re-teach a concept merely because time passed.
- If James demonstrates `CORRECT_TRANSFER` twice on materially different cases, reduce prompting and move toward silent application.
- If James reaches L4, only revisit when a substantially harder variant appears or evidence shows regression.
- If a concept has not appeared naturally for a long period and remains strategically important, a short monthly challenge may be used.

## Teach-back evidence

Use teach-back sparingly. A teach-back is useful when James can explain a distinction in plain language after seeing evidence.

Record:

- concept;
- case;
- James's explanation in concise paraphrase;
- whether the explanation captured the decisive boundary;
- whether it transferred to a new case later.

Teach-back alone can support L2, but not L3 or L4 without application or falsification evidence.

## Learning-event template

Append only when there is a meaningful change in demonstrated judgment.

### YYYY-MM-DD — [concept]

- **Real case:** Issue / PR / Candidate / failure / runtime event.
- **Before evidence:** James's prediction or initial judgment, if captured.
- **Evidence inspected:** exact evidence that resolved the question.
- **Result:** what was actually true.
- **Reusable rule:** one concise engineering principle.
- **Teach-back:** optional plain-language explanation from James.
- **Prediction classification:** `CORRECT_TRANSFER` / `CORRECT_BUT_CUED` / `MISCONCEPTION_FOUND` / `EVIDENCE_INSUFFICIENT` / not applicable.
- **Demonstrated level:** L0-L4, with a reason.
- **Next challenge:** the smallest harder variant worth practicing.

## Promotion rules

Use conservative evidence to change mastery:

- **L0 -> L1:** encountered the concept in a real case.
- **L1 -> L2:** can explain the decisive distinction without merely repeating terminology.
- **L2 -> L3:** applies the distinction correctly to a materially new real case.
- **L3 -> L4:** proactively proposes a credible falsification, hidden failure, or evidence gap before being told.

Demotion is allowed if repeated new cases show the mental model is not stable. Record the reason; do not treat mastery as permanent merely because a prior row was green.

## Update rules

- Do not append routine status updates.
- Do not duplicate Nexus's system failure-learning records.
- Record at most one primary learning item from a normal engineering task unless James explicitly asks for a deeper review.
- Preserve wrong predictions when useful; do not rewrite history after seeing the answer.
- If new evidence contradicts an earlier learning conclusion, update the entry and state why.
- Prefer concrete Issue/PR/revision references over generic prose.
- Prefer new cases over repeating the same demonstration fixture.
- Do not turn every engineering interaction into a quiz; execution remains primary.
- This ledger never authorizes implementation, approval, integration, merge, or production claims.
