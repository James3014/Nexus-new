# S6.1 Controlled Evaluator Session Packet

**Date**: 2026-06-18
**Status**: PACKET READY — SESSION PENDING EVALUATOR

---

## 1. Evaluator Selection Criteria

### Required Qualifications
- Technical engineering background
- Familiar with code repair / patch generation
- Can follow structured runbooks
- Available for 60-90 minute session
- Willing to provide structured feedback

### Exclusions
- Marketing/PR personnel
- Public benchmark evaluators
- External competitors
- Social media influencers

## 2. Evaluator Shortlist Template

| Name | Role | Availability | NDA Status |
|------|------|-------------|------------|
| [Name 1] | [Role] | [Date] | [Status] |
| [Name 2] | [Role] | [Date] | [Status] |
| [Name 3] | [Role] | [Date] | [Status] |

## 3. Session Agenda (60-90 min)

| Time | Activity | Notes |
|------|----------|-------|
| 0-10 min | Welcome + scope briefing | Non-claims emphasis |
| 10-25 min | Demo: strategy tournament | Show S2 flow |
| 25-40 min | Demo: indentation-aware insertion | Show S4.6 flow |
| 40-55 min | Demo: source guard | Show S4.1 flow |
| 55-70 min | Evidence inspection | Show receipts, tiers |
| 70-85 min | Q&A | Structured feedback |
| 85-90 min | Feedback form | Capture responses |

## 4. NDA / Sharing Boundary

### May Share
- Internal technical findings
- Architecture observations
- Improvement suggestions

### May NOT Share
- Candidate instance_ids (without approval)
- Model output excerpts (without approval)
- Receipt file contents (without approval)
- Any public-facing claims

## 5. Session Evidence Receipt

```json
{
  "session_id": "S6.1_SESSION_001",
  "evaluator_id": "[evaluator]",
  "session_date": "[date]",
  "artifacts_viewed": ["demo_package", "runbook", "evidence"],
  "commands_run": [],
  "feedback_collected": {},
  "issues_found": [],
  "recommendation": ""
}
```

## 6. Claim Boundary Briefing (Verbal)

"Everything you see is internal controlled evidence. It is NOT a public benchmark. It is NOT a Qwen solve rate. It is NOT comparable to official SWE-bench. Human review is required before any training or export use."

## 7. Post-Demo Triage

1. Collect feedback within 24 hours
2. Classify: actionable / non-actionable / blocker
3. If blocker: fix before next evaluation
4. If actionable: schedule for next iteration
5. If non-actionable: document and close

---

**Status**: Session packet ready. Awaiting evaluator selection to schedule session.
