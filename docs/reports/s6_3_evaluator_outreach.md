# S6.3 Evaluator Outreach + First Real Session Scheduling

**Date**: 2026-06-18
**Status**: OUTREACH READY — PENDING EVALUATOR IDENTIFICATION

---

## 1. Evaluator Outreach Tracker

| Evaluator | Category | Contact | Invite Sent | Response | NDA | Session Date |
|-----------|----------|---------|-------------|----------|-----|-------------|
| [TBD] | Internal Engineer | [TBD] | ⏳ | ⏳ | ⏳ | ⏳ |
| [TBD] | Tech Advisor | [TBD] | ⏳ | ⏳ | ⏳ | ⏳ |
| [TBD] | Engineering Manager | [TBD] | ⏳ | ⏳ | ⏳ | ⏳ |

## 2. Evaluator Categories

### Category A: Internal Engineer
- **Profile**: Works on code repair / patch generation tools
- **Value**: Can evaluate technical depth and reproducibility
- **Risk**: May have prior context (mitigate with structured briefing)

### Category B: Trusted Tech Advisor
- **Profile**: External technical advisor under NDA
- **Value**: Independent perspective, no prior context
- **Risk**: May not understand Nexus internals (mitigate with runbook)

### Category C: Engineering Manager
- **Profile**: Manages engineering teams, evaluates tools
- **Value**: Can assess operational readiness and adoption path
- **Risk**: May focus on business value (mitigate with technical scope)

## 3. Invitation Packet

### Email Template
```
Subject: Internal Technical Evaluation — Nexus Model-Candidate Evidence Path

Hi [Name],

We'd like to invite you to a controlled technical evaluation of Nexus's
internal model-candidate evidence path. This is NOT a public benchmark
or product launch.

Session details:
- Duration: 60-90 minutes
- Format: Structured demo + feedback
- Confidentiality: Internal use only
- Scope: Technical evaluation only

Please confirm:
1. Availability
2. NDA status
3. Technical background

Best,
[Agent B / Nexus Team]
```

## 4. Confidentiality / Sharing Boundary

### May Share After Session
- Internal technical findings
- Architecture observations
- Improvement suggestions

### May NOT Share
- Candidate instance_ids
- Model output excerpts
- Receipt file contents
- Any public-facing claims

## 5. Claim-Boundary Acknowledgement

Before session, evaluator must acknowledge:
- "Everything shown is internal controlled evidence"
- "NOT a public benchmark"
- "NOT a Qwen solve rate"
- "NOT comparable to official SWE-bench"
- "Human review required before training/export"

## 6. Response Tracking

| Status | Meaning |
|--------|---------|
| pending | Outreach not yet sent |
| sent | Invitation sent, awaiting response |
| accepted | Evaluator accepted, session scheduled |
| declined | Evaluator declined |
| no_response | No response after 7 days |

## 7. Session Scheduling

Once evaluator accepts:
1. Confirm date/time
2. Send pre-reading materials
3. Confirm NDA status
4. Send claim boundary reminder
5. Prepare session notes template
6. Prepare receipt template
7. Mark session_status=ready_to_execute

---

**Status**: S6.3 outreach ready. Awaiting evaluator identification to begin outreach.
