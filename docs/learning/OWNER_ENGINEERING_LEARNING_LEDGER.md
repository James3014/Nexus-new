---
artifact_authority: owner_learning_record
owner: James Chen
status: active_learning_record
purpose: Durable cross-session, cross-repository record of James's demonstrated system-architecture judgment development during Nexus work.
non_authority: Personal learning state only; never repository, product, routing, workforce, verification, acceptance, merge, release, security, or production authority.
interaction_policy: docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md
case_reference: docs/learning/OWNER_ENGINEERING_CASEBOOK.md
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner System Architecture Learning Ledger

This Ledger is the **single canonical record/history** of James's demonstrated architecture-learning evidence for Nexus work.

It is intentionally separate from Nexus's system Learning Closure / `nexus-learning` product data and from `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.

Use `OWNER_ENGINEERING_CASEBOOK.md` as the reusable real-case teaching library. The Casebook stores historical cases; this Ledger stores James's demonstrated judgment and learning progression.

The file name is retained for continuity. The learning objective is now broader than engineering evidence judgment: it is high-level system-architecture judgment.

---

## Current Learning State — bounded bootstrap projection

This section is the bounded current-state projection that fresh Owner-facing sessions should prefer before reading the full history.

**Projection rule:** this section is derived from reviewed evidence in this same Ledger. It is not an independent mastery authority. Do not manually promote mastery here without corresponding evidence/history below.

**Current-state revision:** `2026-09-15 / Issue #965 candidate design`

**Applicability:** Owner-facing Nexus architecture/development work across the current ecosystem, including `Nexus-new`, `devspace`, `nexus-core`, `nexus-learning`, `nexus-open-swe-runtime`, `repository-intelligence-engine`, `nexus-runtime`, and `nexus-opencli-reviewer`.

### Current priority frontiers — maximum three

1. **跨 repository 的責任 / authority / SSOT 邊界** — learn to identify the correct owner when runtime, compatibility host, intelligence engine, reviewer, Core, Learning, and execution repos interact.
2. **durable / ephemeral identity and state continuity** — learn which identity/state must survive session/process/runtime replacement and which should remain transport-local.
3. **architecture evolution and context economics** — learn when a new abstraction, repository, projection, compatibility layer, or bootstrap mechanism reduces complexity versus merely moving or duplicating it.

### Domain-level mastery view

The six architecture domains are new grouping categories. Existing historical subtopic evidence does **not** automatically promote an entire domain.

| Architecture domain | Current level | Evidence boundary | Next useful real case |
|---|---|---|---|
| 問題與目標界定 | UNASSESSED | No direct cross-case evaluation yet | A proposed new mechanism where reuse/no-change is a credible alternative |
| 責任、介面與權責劃分 | UNASSESSED | Historical SSOT/authority subtopics exist at L1, but domain-wide transfer has not been assessed | Cross-repo owner vs compatibility-consumer decision |
| 資料、狀態與身分設計 | UNASSESSED | Relevant discussions exist, but no reviewed current transfer evidence is recorded | Durable semantic identity vs replaceable session/runtime identity |
| 整體運作與失敗控制 | UNASSESSED | Retry/reconciliation topics were historically queued but not assessed as an architecture domain | Timeout/lost-ack/retry case with external side effect |
| 成本、組織與系統演進取捨 | UNASSESSED | No direct evaluated evidence yet | Decide whether a new projection/repo/service reduces total maintenance/context cost |
| 假設、證據與反證 | UNASSESSED | Historical falsification subtopic is L1; no domain-wide transfer assessment | Challenge an architecture conclusion before implementation |

### Existing subtopic evidence that remains valid as historical baseline

These are not domain-wide scores and are not silently upgraded by the 2026-09-15 redesign:

- `SSOT / duplicate authority`: historical baseline L1.
- `Revision-bound evidence`: historical baseline L1.
- `Candidate != integrated != runtime-verified`: historical baseline L1.
- `Capability != reliability != authority`: historical baseline L1.
- `Fail-closed`: historical baseline L1.
- `Failure clustering / shared root cause`: historical baseline L1.
- `Falsification / negative testing`: historical baseline L1.
- `Test oracle quality`, `Idempotency`, `Timeout/reconciliation`: historical baseline L0 in the old program, but do not use those old L0 values to infer a new architecture-domain score.

### Recent interaction notes — not mastery evidence

- 2026-09-15: Owner clarified that the primary learning target should be **high-level system architecture judgment**, not engineering judgment alone.
- 2026-09-15: Owner clarified that Owner-facing technical interaction must be understandable in **Traditional Chinese**, because excessive English terminology creates comprehension friction.
- 2026-09-15: Owner identified the multi-repository split as material to the learning design; the learning state should span the Nexus ecosystem without becoming engineering authority over any repository.

These are requirements/preferences and architecture-design inputs. They are **not** evidence that James has demonstrated L2/L3/L4 mastery in the corresponding domains.

### Repetition guard / next frontier

Do not quiz James merely on definitions of SSOT, authority, durable state, or repository ownership. Prefer a materially real trade-off such as:

- which repository should own a cross-repo contract and which should remain a consumer/projection;
- whether a compact current-state artifact becomes a second source of truth;
- whether a runtime composition layer is also becoming a product truth owner;
- what identity should survive a fresh ChatGPT session or loaded-service replacement.

---

## Mastery scale

Use `UNASSESSED` when there is not enough evidence. `UNASSESSED` is different from L0.

- **UNASSESSED — 尚未評估**: insufficient evidence to classify demonstrated judgment.
- **L0 — 未接觸**: evidence supports that the concept has not yet had meaningful exposure in this learning program.
- **L1 — 看過**: has seen the concept in a real case but has not yet demonstrated independent judgment.
- **L2 — 能解釋**: can explain the decisive distinction and why it matters in his own language.
- **L3 — 能在不同案例中判斷**: can apply the distinction to a materially different real case and defend a reasonable architecture conclusion/trade-off.
- **L4 — 能主動提出反證**: before being told the decisive gap, can identify a credible falsifier, hidden failure, or applicability boundary.

Do not promote mastery from explanation alone. Prefer evidence from real predictions, architecture decisions, corrections, teach-back, transfer, or falsification proposals.

Additional constraints:

- Prompted falsification is useful evidence but does not automatically prove proactive L4.
- A different repository with the same problem structure is not automatically a new transfer case.
- One subtopic level does not generalize to the whole architecture domain.
- English vocabulary difficulty, a skipped learning question, or unavailable bootstrap state does not automatically reduce mastery.
- Agreement with ChatGPT is not the scoring criterion; reasoning quality, constraints, trade-offs, and evidence are.

## Architecture learning domains

Use these as grouping dimensions, not as another level scale:

1. 問題與目標界定
2. 責任、介面與權責劃分
3. 資料、狀態與身分設計
4. 整體運作與失敗控制
5. 成本、組織與系統演進取捨
6. 假設、證據與反證

Engineering subtopics such as testing, Git, debugging, retry, idempotency, model reliability, and receipts remain supporting evidence within those domains.

---

## Historical baseline — 2026-08-22

This is a conservative historical starting baseline derived from then-recent Nexus discussions. It is **not** the current domain-level assessment and does not claim mastery that James has not demonstrated explicitly.

| Concept | Historical level | Evidence so far | Next useful practice |
|---|---|---|---|
| Worker self-report != independent evidence | L1 | Discussed through candidate/acceptance workflow and Agent completions | On a real completed worker task, decide what must be independently re-run before acceptance |
| Revision-bound evidence | L1 | Discussed that a test result belongs to an exact commit/HEAD and does not automatically transfer after merge | On a PR, identify Candidate SHA, merged HEAD, and which evidence must be re-bound |
| Candidate != integrated != runtime-verified | L1 | Repeated Nexus examples distinguish implementation, merge, and runtime truth | On a merged change, classify exactly which layer is proven and which remains open |
| Capability != reliability != authority | L1 | Model calibration examples discussed | Given strong semantic result plus tool-discipline failure, choose safe authority ceiling and explain why |
| Fail-closed | L1 | Workforce Admission example discussed: BLOCK should prevent provider calls | Propose a negative test proving denied path performs zero calls |
| Failure clustering / shared root cause | L1 | 73 failures versus a few shared failure domains discussed | Given a failing-test cluster, predict individual fixes versus shared-seam repair |
| Test oracle quality | L0 | Introduced conceptually but not yet practiced in the old program | For one passing suite, state what behavior the assertions prove and do not prove |
| Falsification / negative testing | L1 | WHY_CORRECT framing introduced | Before acceptance, propose high-value cases that could disprove the fix |
| Mutation-testing mindset | L0 | Mentioned as research basis for engineering evidence | Identify one plausible wrong implementation the tests should catch |
| Idempotency / duplicate-effect handling | L0 | Not practiced in the old program | Use a retry/duplicate dispatch case from Nexus |
| Timeout / lost acknowledgement / reconciliation | L0 | Relevant but not practiced in the old program | Examine a real timeout and decide safe retry/reconciliation conditions |
| SSOT / duplicate authority | L1 | Central Nexus theme and Skill boundary discussion | Given two apparent decision sources, identify decision owner vs projection |

---

## Prediction & Misconception Register

Purpose: preserve judgment **before** decisive evidence is known. This prevents hindsight from making a lesson look easier than it was and lets later sessions measure transfer.

Record only meaningful predictions that test architecture/engineering judgment. Do not quiz James on syntax, trivia, English vocabulary, or mechanically searchable facts.

| ID | Date | Real case | Concept tested | James prediction before evidence | Evidence/result | Misconception or correct heuristic | Transfer status | Re-test trigger |
|---|---|---|---|---|---|---|---|---|
| P-001 | 2026-08-22 | Learning program initialization | failure clustering | Not yet captured | Historical Nexus example: 73 failures clustered into 4 failure domains | Baseline only; no demonstrated prediction yet | UNTESTED | Next natural multi-failure incident |
| P-002 | 2026-08-22 | Learning program initialization | capability vs authority | Not yet captured | Historical model example: strong semantic frontier plus tool/scope hard failure kept mutation ceiling low | Baseline only; no demonstrated prediction yet | UNTESTED | Next model-promotion or dispatch-authority decision |
| P-003 | 2026-08-22 | Learning program initialization | revision-bound evidence | Not yet captured | Historical passing suite remained bound to its tested HEAD | Baseline only; no demonstrated prediction yet | UNTESTED | Next Candidate -> merge -> post-merge verification flow |

### Prediction capture rules

When a real task presents a useful learning moment:

1. Ask at most one short judgment/prediction question before revealing decisive evidence.
2. Make choices reflect real architecture alternatives; avoid obvious answer cues.
3. Record the answer only when it teaches something reusable.
4. Record the scaffold/prompt level so prompted performance is not confused with proactive discovery.
5. After evidence is inspected, classify the result as:
   - `CORRECT_TRANSFER` — correct reasoning on a materially different case;
   - `CORRECT_BUT_CUED` — correct but materially scaffolded;
   - `MISCONCEPTION_FOUND` — wrong model or missing distinction was exposed;
   - `EVIDENCE_INSUFFICIENT` — evidence did not actually resolve the question;
   - `UNTESTED` — baseline only, no prediction captured.
6. Preserve wrong predictions verbatim or faithfully paraphrased. Never rewrite them after seeing the answer.
7. A single correct prediction does not automatically promote to L3; prefer transfer across a materially different case.

---

## Spaced Recall / Natural Transfer Queue

Prefer new real work over calendar quizzes.

| Concept / domain | Current evidence | Next recall mode | Trigger condition | Status |
|---|---|---|---|---|
| Cross-repo responsibility / authority | historical SSOT subtopic L1; domain UNASSESSED | Architecture judgment | Two repos appear to own the same decision or contract | WAIT_FOR_NATURAL_CASE |
| Durable vs ephemeral identity/state | UNASSESSED | Short architecture prediction | Session/runtime/process replacement with durable state | WAIT_FOR_NATURAL_CASE |
| Architecture evolution / context economics | UNASSESSED | Trade-off comparison | New repo/projection/daemon/pointer proposed | WAIT_FOR_NATURAL_CASE |
| Revision-bound evidence | historical L1 | Identify exact evidence clocks | Candidate/main/package/runtime identities diverge | WAIT_FOR_NATURAL_CASE |
| Test oracle / false green | historical L0 | Falsification | A suite passes and acceptance depends on what it truly proves | WAIT_FOR_NATURAL_CASE |
| Timeout/reconciliation | historical L0 | Scenario judgment | Real worker timeout, disconnect, unknown acknowledgement, or retry | WAIT_FOR_NATURAL_CASE |
| Idempotency | historical L0 | Scenario judgment | Duplicate dispatch, webhook, retry, or external side effect | WAIT_FOR_NATURAL_CASE |

Rules:

- Do not re-teach a concept merely because time passed.
- If James demonstrates `CORRECT_TRANSFER` twice on materially different cases, reduce prompting and move toward silent application.
- If James reaches L4 on a narrow concept, revisit only on a substantially harder variant or regression evidence.
- Avoid definition-only recall when a real architecture trade-off is available.

---

## Teach-back evidence

Use teach-back sparingly. It is useful when James can explain a distinction in plain Chinese after seeing evidence.

Record:

- exact concept;
- case and repository identities;
- James's concise explanation;
- whether it captured the decisive boundary;
- scaffold level;
- whether it transferred later.

Teach-back can support L2. It does not prove L3/L4 without transfer or proactive falsification evidence.

---

## Learning-event template

Append only when there is meaningful demonstrated judgment or a meaningful correction. Use a stable event ID such as `LA-YYYYMMDD-NNN`.

### LA-YYYYMMDD-NNN — [architecture concept]

- **Date observed:** YYYY-MM-DD
- **Repositories:** full `owner/repo` identities; use multiple entries when cross-repo.
- **Real case:** Issue / PR / Candidate / runtime / architecture decision.
- **Revision / runtime refs:** exact SHAs/identities when material; do not collapse source, installed package, loaded runtime, and acceptance evidence clocks.
- **Architecture domain:** one primary domain.
- **Concept tested:** narrow concept, not just “architecture”.
- **Before decisive evidence:** James's prediction or initial judgment, only if genuinely captured.
- **Scaffold level:** `NONE` / `LIGHT` / `HEAVY` / `NOT_APPLICABLE`.
- **Evidence inspected:** exact evidence that resolved or constrained the question.
- **Result / feedback:** what was actually true and what distinction mattered.
- **Reusable principle:** concise architecture rule.
- **Applicability boundary:** when the rule does not apply or what could falsify it.
- **Prediction classification:** `CORRECT_TRANSFER` / `CORRECT_BUT_CUED` / `MISCONCEPTION_FOUND` / `EVIDENCE_INSUFFICIENT` / `UNTESTED` / not applicable.
- **Mastery impact:** `NO_CHANGE` or exact concept-level L0-L4 change with reason. Never infer domain-wide mastery automatically.
- **Next challenge:** smallest materially harder real variant.

Do not append routine status updates. Do not invent historical predictions or demonstrations.

---

## Promotion and reassessment rules

Use conservative evidence:

- **UNASSESSED -> L0/L1** only when the evidence justifies that exact classification.
- **L0 -> L1:** meaningful real exposure occurs.
- **L1 -> L2:** James can explain the decisive distinction without merely repeating terminology.
- **L2 -> L3:** applies the distinction correctly to a materially different real case and explains trade-offs.
- **L3 -> L4:** proactively proposes a credible falsifier, hidden failure, or applicability gap before being told.

Demotion/reassessment is allowed if repeated new evidence shows the mental model is unstable. Preserve the prior evidence and record why the current view changed; do not rewrite history.

Conflicting evidence should produce `REASSESSMENT_REQUIRED` until reviewed. Do not use max-score-wins or last-write-wins.

---

## Concurrency / writeback rules

- Re-read the current Ledger before every writeback.
- Every appended learning event must have a stable event ID.
- A duplicate event ID must not be appended as a second event.
- If two sessions report conflicting evidence for the same concept, preserve both and require reassessment.
- When possible, append reviewed evidence and refresh the Current Learning State in the same reviewable change.
- A bounded worker may produce engineering evidence, but it does not independently quiz or grade James unless explicitly asked by the Owner.
- If the current session lacks write authority to this Ledger, label the item `PENDING_WRITEBACK`; do not claim durable persistence.
- On unknown remote write outcome, reconcile/read back before retrying.
- Do not put secrets, private links, full private conversation transcripts, or unnecessary personal information into this public artifact.

---

## Update rules

- Do not duplicate Nexus's system failure-learning records.
- Record at most one primary learning item from a normal engineering task unless James explicitly asks for a deeper review.
- Preserve wrong predictions when useful; do not rewrite history after seeing the answer.
- If new evidence contradicts an earlier learning conclusion, append/update the assessment transparently and state why.
- Prefer full repository identity + exact Issue/PR/revision references over generic prose.
- Prefer new problem structure over a renamed duplicate case.
- Do not turn every engineering interaction into a quiz; execution remains primary.
- This Ledger never authorizes implementation, approval, integration, merge, release, security changes, or production claims.
- Storage in `Nexus-new` is a continuity choice, not engineering authority over the other repositories.
