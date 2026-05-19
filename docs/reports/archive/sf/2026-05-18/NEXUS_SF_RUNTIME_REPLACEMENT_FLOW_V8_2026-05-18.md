# NEXUS SF Runtime Replacement Flow V8

## Single Exit
- COMPLETE only when V8 overlay is loadable and post-apply runtime receipt smoke is PASS.
- Public benchmark remains separate and BLOCKED.

## Replacement Steps
1. discover: candidate source screen + capability bucket -> candidate intake only
2. compare: Flash+Nexus without skill vs Flash+Nexus with skill paired evidence -> delta + receipt-backed verdict
3. seal: selected/injected/used/evidence/gate/outcome all true -> promotion seal report
4. approve_for_apply: evidence-approved V8 apply review, no human taste decision -> runtime_update_allowed=true
5. replace_runtime_default: load V8 runtime overlay via NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY or NEXUS_RUNTIME_SKILL_POLICY_OVERLAY -> primary_skill_by_capability active
6. post_apply_smoke: runtime-final receipt confirms selected/injected/used/evidence/gate/outcome -> replacement complete
7. ledger: applied_primary/held_alternate/rejected split -> replacement ledger

## Runtime Load Command
```bash
export NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V8_2026-05-18.json
export NEXUS_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V8_2026-05-18.json
```
