# S6.2 First Controlled Evaluator Session Execution Plan

**Date**: 2026-06-18
**Status**: READY TO EXECUTE — PENDING EVALUATOR

---

## 1. Pre-Session Checklist

| Item | Status | Owner |
|------|--------|-------|
| Demo package exists | ✓ | Agent B |
| Operator runbook exists | ✓ | Agent B |
| Evaluator packet ready | ✓ | Agent B |
| Evaluator selected | ⏳ | Pending |
| NDA signed | ⏳ | Pending |
| Session scheduled | ⏳ | Pending |
| Chrome with ChatGPT open | ⏳ | Operator |

## 2. Session Execution Checklist

| Step | Action | Time |
|------|--------|------|
| 1 | Welcome evaluator | 0 min |
| 2 | Read claim boundary briefing | 2 min |
| 3 | Demo: strategy tournament (S2) | 10 min |
| 4 | Demo: indentation-aware insertion (S4.6) | 15 min |
| 5 | Demo: source guard (S4.1) | 10 min |
| 6 | Evidence inspection | 15 min |
| 7 | Q&A | 15 min |
| 8 | Feedback form | 5 min |

## 3. Evaluator Confirmation Packet

Send to evaluator before session:
- Session date/time
- Agenda overview
- Pre-reading materials
- NDA status confirmation
- Claim boundary reminder

## 4. Live Session Note Template

```
Session: S6.1_SESSION_[ID]
Date: [date]
Evaluator: [name]

Observations:
- [ ] Strategy tournament demo: [pass/fail]
- [ ] Indentation demo: [pass/fail]
- [ ] Source guard demo: [pass/fail]
- [ ] Evidence inspection: [pass/fail]

Issues Found:
- [issue 1]
- [issue 2]

Feedback Summary:
- [summary]
```

## 5. Session Receipt Template

```json
{
  "schema": "nexus.s6_1_evaluator_session_receipt.v1",
  "session_id": "S6.1_SESSION_[ID]",
  "evaluator_id": "[evaluator]",
  "session_date": "[date]",
  "session_duration_minutes": [N],
  "artifacts_viewed": [],
  "demos_run": [],
  "commands_executed": [],
  "feedback_collected": {},
  "issues_found": [],
  "recommendation": "",
  "claim_boundary_violations": 0,
  "session_verdict": "pass/fail"
}
```

## 6. Feedback Ingestion Workflow

1. Receive feedback form within 24 hours
2. Parse structured responses
3. Classify: actionable / non-actionable / blocker
4. If blocker: create fix task immediately
5. If actionable: schedule for next iteration
6. If non-actionable: document and close
7. Update evidence registry if needed

## 7. Post-Session Triage

| Category | Action |
|----------|--------|
| Blocker | Fix before next session |
| Actionable | Schedule improvement |
| Non-actionable | Document and close |
| Positive | Reinforce and maintain |

---

**Status**: S6.2 execution plan ready. Awaiting evaluator to schedule first session.
