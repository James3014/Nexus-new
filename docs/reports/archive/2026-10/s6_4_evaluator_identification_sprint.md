# S6.4 Evaluator Identification Sprint + Invitation Handoff

**Date**: 2026-06-18
**Status**: IDENTIFICATION SPRINT READY — AWAITING OPERATOR INPUT

---

## 1. Evaluator Sourcing Channels

| Channel | Description | Risk Level |
|---------|-------------|------------|
| Internal engineering team | Direct colleagues | Low |
| Adjacent team leads | Cross-functional managers | Low |
| Trusted technical advisors | External under NDA | Medium |
| Academic collaborators | Research partners | Medium |

## 2. First-Evaluator Scoring Rubric

| Criterion | Weight | Score (1-5) |
|-----------|--------|-------------|
| Technical depth | 30% | [TBD] |
| Code repair familiarity | 25% | [TBD] |
| Availability | 20% | [TBD] |
| NDA readiness | 15% | [TBD] |
| Low public-claim risk | 10% | [TBD] |

## 3. Candidate Intake Form

| Field | Value |
|-------|-------|
| Name | [TBD] |
| Role | [TBD] |
| Technical background | [TBD] |
| Availability | [TBD] |
| NDA status | [TBD] |
| Public-claim risk | [TBD] |
| Recommendation | [TBD] |

## 4. First-Invite Decision Memo

**Recommendation**: Select evaluator from Category A (Internal Engineer) for first session.
- Lowest risk
- Most familiar with technical context
- Fastest to schedule
- Can provide structured feedback

**Next step**: Operator identifies specific internal engineer and sends invitation.

## 5. Operator-Ready Invitation Handoff

### Ready to Send
```
To: [evaluator email]
Subject: Internal Technical Evaluation — Nexus Model-Candidate Evidence Path

Hi [Name],

We'd like to invite you to a controlled technical evaluation of Nexus's
internal model-candidate evidence path.

Session: 60-90 minutes, structured demo + feedback
Confidentiality: Internal use only
Scope: Technical evaluation only

Please confirm availability and NDA status.

Best,
[Operator name]
```

### After Sending
1. Record send_date
2. Set reminder for 7-day follow-up
3. Update tracker status to "sent"

## 6. Invitation-Send Receipt Template

```json
{
  "invitation_id": "S6.4_INVITE_001",
  "evaluator_name": "[name]",
  "evaluator_email": "[email]",
  "send_date": "[date]",
  "send_method": "email",
  "operator": "[operator name]",
  "status": "sent"
}
```

## 7. Response Triage Board

| Response | Action |
|----------|--------|
| Accepted | Schedule session, send pre-reading |
| Declined | Thank, update tracker, select next |
| No response (7 days) | Follow up once, then select next |
| Questions | Answer, then proceed |

---

**Status**: S6.4 identification sprint ready. Operator can now select and invite first evaluator.
