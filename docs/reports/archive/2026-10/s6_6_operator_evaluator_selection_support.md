# S6.6 Operator Evaluator Selection Required + First Invite Support

**Date**: 2026-06-18
**Status**: BLOCKED — OPERATOR ACTION REQUIRED

---

## 1. Operator Decision Request

### What Agent B Needs from Operator

| Item | Required | Format |
|------|----------|--------|
| Evaluator name | YES | Full name |
| Evaluator role | YES | Job title / function |
| Evaluator email | YES | Work email |
| Availability window | YES | Date range |
| NDA status | YES | Signed / pending / not needed |
| Technical background | Optional | Brief description |

### What Agent B Will Do After Receiving

1. Score evaluator using rubric (S6.4)
2. Check against exclusion list
3. Prepare evaluator-specific invitation
4. Generate invitation receipt (pending send)
5. Operator confirms send → update status

## 2. Minimal Evaluator Input Form

```
Evaluator Selection Form

Name: _______________
Role: _______________
Email: _______________
Availability: _______________
NDA: [ ] Signed [ ] Pending [ ] Not needed
Background: _______________

Operator: _______________
Date: _______________
```

## 3. Evaluator Scoring (auto-applied after input)

| Criterion | Weight | Auto-score |
|-----------|--------|------------|
| Technical depth | 30% | [from role] |
| Code repair familiarity | 25% | [from background] |
| Availability | 20% | [from window] |
| NDA readiness | 15% | [from status] |
| Low public-claim risk | 10% | [default: 4] |

## 4. Outcomes After Operator Input

| Outcome | Meaning | Next Step |
|---------|---------|-----------|
| operator_selected_evaluator_ready_to_send | Input received, scored, packet ready | Operator sends |
| invitation_sent_by_operator | Operator confirms send | Wait for response |
| evaluator_accepted | Evaluator accepted | Schedule session |
| still_blocked_pending_operator | No input received | Agent B waits |
| blocked_due_evaluator_risk | Score too low | Select different evaluator |

## 5. What Agent B Cannot Do

- ❌ Create fake evaluator identity
- ❌ Send invitation automatically
- ❌ Claim invitation was sent
- ❌ Invent evaluator response
- ❌ Create fake feedback
- ❌ Create fake session receipt

## 6. What Agent B Can Do

- ✅ Score evaluator after input
- ✅ Prepare invitation packet
- ✅ Record invitation receipt (pending send)
- ✅ Validate invitation content
- ✅ Track response status

---

**Status**: S6.6 ready to support operator. Awaiting operator evaluator input.
