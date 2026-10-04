# Issue 29 — Physical Local-to-Online Causal Consumption Canary

- task_id: `github-issue-29-local-online-canary-20261005`
- campaign_id: `github-issue-29-local-online-canary-20261005`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/29`
- durable_marker: `ONLINE_LOCAL_SAME_TASK_CAUSAL_CONSUMPTION_VERIFIED`
- AUTO_CHAIN: `false`

## Objective

Establish a lawful, formal task execution that binds a physical Local model provider call (`qwen2.5-coder:7b-instruct` via local Ollama) and a physical Online model provider call (`gemini-3.8-flash` via Gemini API) under the same task. The Local evidence identity (VAP hash) is frozen prior to Online consumption, verified by World C verifier, and results in a live, complete receipt with `model_call_count >= 1` on both legs.

## Allowed Files

- `tasks/github-issue-29-local-online-canary-20261005/00-local-online-canary.md`
- `tasks/github-issue-29-local-online-canary-20261005/INDEX.md`
- `scripts/ops/canary_issue29_physical_local_online.py`
- `tests/ops/test_issue29_physical_canary.py`

## Acceptance Criteria

1. Starts from fresh current main (`bd8284b6f980b0477ea8406603e14e796738f7e3`).
2. Reaches real physical Local provider call (Ollama `qwen2.5-coder:7b-instruct`) and real Online provider call (Gemini `gemini-3.8-flash`).
3. Local evidence identity (VAP packet hash) is frozen before Online consumption.
4. Online input/context is physically bound to the exact Local evidence hash/identity.
5. Substituting or tampering Local evidence fails closed before an unsupported final claim.
6. Final receipt distinguishes `online_consumed` and records true values only from physical evidence (`model_call_count >= 1`).
7. Authoritative verifier and claim boundary remain separate from model judgment.
8. Caller route/world override and workforce/admission bypass remain rejected.
9. Focused positive/negative/tamper tests and `git diff --check` pass.
10. Live receipt is bound to exact current source, runtime, and provider identities.

## Claim Ceiling

Physical Canary Receipt and verified source/test artifacts only. No unauthorized runtime deployment, release, production activation, or public production claim.
