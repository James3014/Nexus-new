---
name: github2-superpowers-verification-before-completion
description: 當使用者要求 Nexus 執行 ultra_review, artifact_gate, claim_gate, delivery_acceptance_gate, or regression_guard 工作且即將宣稱完成、修復、通過、可替換、或可交付前，需要 fresh verification evidence 和 fail-closed claim boundary 時使用；不要用於未執行驗證就生成成功宣稱。
metadata: {"source_repo":"https://github.com/obra/superpowers","source_commit":"f2cbfbefebbfef77321e4c9abc9e949826bea9d7","source_skill":"skills/verification-before-completion/SKILL.md","source_status":"external_challenger","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Round2 Superpowers Verification Before Completion

Candidate-only adaptation of `obra/superpowers/skills/verification-before-completion`.

## Load when

- A Nexus route needs artifact, claim, delivery, ultra-review, or regression evidence before a completion claim.
- A row verdict depends on reading fresh command output, receipt state, or evidence bundle status.
- The task risks confusing planner selection, diagnostic smoke, or partial pass with runtime-confirmed success.

## Do not load when

- No verification command, receipt, or evidence bundle is available.
- The workflow is trying to convert diagnostic-only evidence into public or runtime promotion claims.
- The task only needs brainstorming or source discovery.

## Required receipts

- claim_under_review
- verification_command
- verification_exit_code
- evidence_path
- receipt_path
- claim_boundary
- final_verdict

## Operating contract

1. Identify the exact claim being made.
2. Identify the command or artifact that proves or disproves it.
3. Run or read the fresh evidence.
4. Mark the claim PASS only if the evidence directly supports it.
5. Mark missing, stale, partial, or single-arm evidence as RETURN/HOLD, not PASS.

## SF boundary

This skill is an external challenger. It may participate in ablation-only Flash+Nexus comparison, but it must not update runtime default policy without a separate promotion/apply gate.
