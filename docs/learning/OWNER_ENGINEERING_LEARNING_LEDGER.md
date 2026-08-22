---
artifact_authority: owner_learning_record
owner: James Chen
status: active_learning_record
purpose: Durable cross-session record of James's engineering judgment development during Nexus work.
non_authority: Personal learning state only; never repository, product, routing, verification, acceptance, merge, release, or production authority.
---

# Owner Engineering Learning Ledger

This ledger tracks James's engineering judgment development. It is intentionally separate from Nexus's system `Learning Closure Matrix` and `docs/agents/LEARNING_WRITEBACK_OVERLAY.md`.

## Mastery scale

- **L0 — 未接觸**: no meaningful exposure yet.
- **L1 — 看過**: has seen the concept in a real case but has not yet demonstrated independent judgment.
- **L2 — 能解釋**: can explain the concept and why it matters.
- **L3 — 能在案例中判斷**: can apply it to a new real case and choose the right engineering conclusion.
- **L4 — 能主動提出反證**: can identify what evidence would disprove the current conclusion or expose a hidden failure.

Do not promote mastery from explanation alone. Prefer evidence from real predictions, decisions, corrections, or falsification proposals.

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

## Learning-event template

Append only when there is a meaningful change in demonstrated judgment.

### YYYY-MM-DD — [concept]

- **Real case:** Issue / PR / Candidate / failure / runtime event.
- **Before evidence:** James's prediction or initial judgment, if captured.
- **Evidence inspected:** exact evidence that resolved the question.
- **Result:** what was actually true.
- **Reusable rule:** one concise engineering principle.
- **Demonstrated level:** L0-L4, with a reason.
- **Next challenge:** the smallest harder variant worth practicing.

## Update rules

- Do not append routine status updates.
- Do not duplicate Nexus's system failure-learning records.
- Record at most one primary learning item from a normal engineering task unless James explicitly asks for a deeper review.
- Preserve wrong predictions when useful; do not rewrite history after seeing the answer.
- If new evidence contradicts an earlier learning conclusion, update the entry and state why.
- Prefer concrete Issue/PR/revision references over generic prose.
- This ledger never authorizes implementation, approval, integration, merge, or production claims.
