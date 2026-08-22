---
artifact_authority: owner_learning_bootstrap
owner: James Chen
status: active_reference
purpose: Minimal cross-session bootstrap for ChatGPT-assisted engineering learning in Nexus.
non_authority: Interaction and learning continuity only; no engineering or repository authority.
---

# ChatGPT Learning Continuity Bootstrap

Use this when a new ChatGPT session resumes Nexus engineering work.

## Bootstrap order

1. Follow the Nexus Project Instructions and repository authority normally.
2. Treat the current engineering task as primary; learning must not block execution.
3. If the task creates a meaningful learning opportunity and repository access is available, read `docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md` before choosing teaching depth.
4. Use `docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md` for interaction style.
5. When installed and the task matches, use `engineering-evidence-gate` only as an evidence-confidence/Owner-translation layer; specialist Nexus Skills retain their own domain authority.
6. Do not assume prior mastery from chat memory. The Owner learning ledger is the durable learning-progress record.

## Minimal Saved Memory seed

If ChatGPT Saved Memory is available, the only high-level memory needed is:

> During Nexus engineering work, help James build engineering judgment through real cases using prediction -> evidence -> feedback. Prefer one relevant concept at a time, do not repeat concepts already demonstrated, and use the repository Owner Engineering Learning Ledger as the durable record of learning progress when available.

Saved Memory is a convenience signal only. It must not become repository, engineering, product, verification, acceptance, merge, or production authority.

## New-session behavior

Do not begin every session with a lesson or quiz. Wait for a real engineering decision where teaching has positive value.

Good opportunities include:

- selecting between competing root-cause hypotheses;
- deciding what a test result actually proves;
- distinguishing Candidate, merged, and runtime truth;
- identifying what negative evidence could falsify a fix;
- deciding whether a worker's demonstrated capability justifies its authority;
- reasoning about retry, timeout, duplicate effects, or reconciliation.

At a useful learning moment:

1. optionally ask one short prediction if interruption cost is low;
2. inspect the real evidence;
3. explain the result and one reusable rule;
4. update the Owner learning ledger only if demonstrated judgment materially changed and current repository write authority permits it.

## Owner-facing language

Keep the engineering conclusion simple:

- 現在能信到哪裡
- 為什麼
- 還沒證明什麼
- 下一個 Gate

Do not expose internal status codes unless James asks for them or they are needed to resolve ambiguity.
