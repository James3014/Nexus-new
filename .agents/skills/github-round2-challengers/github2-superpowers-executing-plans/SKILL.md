---
name: github2-superpowers-executing-plans
description: 當使用者要求 Nexus 執行 metabolism_resume, learning_closure, direct_master_loop, or forecast_pregate 工作且已有明確 plan，需要逐步執行、檢查阻塞、保留驗證證據與回報完成邊界時使用；不要用於無 plan 的探索、runtime default promotion，或未經驗證的完成宣稱。
metadata: {"source_repo":"https://github.com/obra/superpowers","source_commit":"f2cbfbefebbfef77321e4c9abc9e949826bea9d7","source_skill":"skills/executing-plans/SKILL.md","source_status":"external_challenger","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Round2 Superpowers Executing Plans

Candidate-only adaptation of `obra/superpowers/skills/executing-plans`.

## Load when

- A Nexus route needs to continue a written plan through execution, verification, and closure.
- A task needs checkpointed progress, blocker classification, and evidence-backed completion.
- A learning-closure or resume route must prove which planned steps were actually completed.

## Do not load when

- There is no written plan or executable task list.
- The workflow tries to ask for clarification instead of making safe evidence-based progress.
- The result would be used as runtime default promotion without a separate apply gate.

## Required receipts

- input_plan_ref
- executed_step_ids
- blocker_or_completion_status
- verification_evidence
- closure_summary
- rollback_or_followup_path

## Operating contract

1. Read and sanity-check the plan.
2. Execute only bounded, verifiable steps.
3. Stop or branch when a blocker has a concrete failure class.
4. Verify each completed step before claiming progress.
5. Emit closure state suitable for Nexus learning writeback.

## SF boundary

This skill is an external challenger. It may participate in ablation-only Flash+Nexus comparison, but it must not update runtime default policy without a separate promotion/apply gate.
