---
name: github2-agent-browser-dogfood-safe-ui-validator
description: 當使用者要求 Nexus 執行 ui_validator work that needs browser-style QA planning, exploratory UI validation, repro evidence planning, UX issue taxonomy, screenshot checklist, or bug report structure without granting browser automation tools; return receipt/evidence/gate/outcome-backed guidance. Do not use to execute agent-browser, npx, cloud browser sessions, Slack/browser automation, or authenticated browsing.
metadata: {"source_repo":"https://github.com/vercel-labs/agent-browser","source_commit":"55f38f4d81981f0191c730005c419958c7d20605","source_status":"generated_safe_candidate_from_external_skill","runtime_eligible":false,"ablation_eligible":true,"safety_boundary":"prompt_only_no_browser_tool_execution"}
---

# Agent Browser Dogfood Safe UI Validator

Candidate-only adaptation of the agent-browser dogfood workflow for Nexus
`ui_validator` route-fit testing.

## Load When

- The route capability is `ui_validator`.
- The task needs UI QA planning, exploratory testing strategy, issue taxonomy,
  screenshot/repro evidence planning, or a structured validation report.
- The execution environment does not grant browser automation tools.

## Do Not Load When

- The task requires actually opening, clicking, typing, recording, or scraping
  with `agent-browser`, `npx agent-browser`, Chrome, Slack, AWS AgentCore, or
  Vercel Sandbox.
- Authentication, OTP, cookies, or user session state would be needed.
- The requested outcome is runtime tool execution rather than a validation
  plan or evidence checklist.

## Workflow

1. Identify target surface, scope, and user-visible workflows.
2. Classify expected checks into functional, visual, UX, accessibility, console,
   and data/state categories.
3. Produce a repro-first validation plan with expected evidence for each issue
   type.
4. Require every proposed finding to include severity, repro steps, expected
   evidence, and a gate decision.
5. Return fail-closed if the task requires live browser execution that is not
   available.

## Required Receipt Fields

- `selected`: this skill was selected for `ui_validator`.
- `used`: the output includes a concrete UI validation plan or issue evidence
  checklist.
- `evidence_present`: each finding/check maps to planned screenshot, console,
  trace, or repro evidence.
- `gate_passed`: the plan distinguishes validation-ready from blocked live
  browser execution.
- `outcome_contributed`: the output improves UI validation specificity without
  invoking disallowed tools.

## Output Contract

Return:

- `validation_scope`
- `test_matrix`
- `evidence_plan`
- `fail_closed_boundaries`
- `handoff_to_runtime_browser_tool_if_needed`

