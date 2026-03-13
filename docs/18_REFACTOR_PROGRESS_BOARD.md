# Refactor Progress Board

## Snapshot

This board tracks current migration progress from script-driven Nexus toward the target contract-first architecture.

Status legend:

- DONE
- IN_PROGRESS
- TODO

## Visual Map

```text
Current Runtime
Plan/Diag -> Gemini Repair -> Codex Gate -> Wrap-up/Learn
                               |
                               +-> next_action JSON + Gemini handoff prompt

Target Runtime
Commander -> Context Hub -> P/D/X/R/A/C state machine -> Crystal
```

## Completed

```text
[DONE] Codex failure classification hardening
[DONE] Escalation policy extraction (gemini_repair / felo_research / codex_patch)
[DONE] Action brief generation for next-step handoff
[DONE] Report enrichment with next-step section
[DONE] Machine-readable handoff sidecar (/tmp/codex_next_action.json)
[DONE] Gemini handoff adapter (scripts/core/gemini_handoff.py)
[DONE] codex-loop.sh handoff flags (--emit-gemini-handoff, --handoff-only, --handoff-output)
[DONE] TDD coverage for escalation/action-brief/reporter/handoff modules
```

## In Progress

```text
[IN_PROGRESS] Runtime handoff adoption by multi-agent Gemini operators
[IN_PROGRESS] Documentation consolidation for operational use
```

## Not Done Yet

```text
[TODO] state_contracts.py v1.5.2+ schema fields integration
[TODO] state_io.py compatibility-safe read/write layer
[TODO] context_hub.py formal context assembly API
[TODO] skills_router.py decision execution with score outputs
[TODO] migration_safety_validator.py gatekeeper CLI
[TODO] diag_context_pack/repair_context_pack/audit_context_pack formalization
[TODO] commander entrypoint and phase orchestration
[TODO] research_pack lifecycle with X/Felo gating in core path
[TODO] war-room/viz rendering for new state fields
```

## Dependency Order

```text
Contracts/State I/O
  -> Context Hub
    -> Skills Router
      -> Phase integration (D/R/A)
        -> Validator gatekeeper
          -> Commander orchestration
```

## Acceptance Gates (Short)

1. Token overhead for internal path <= 1.2x baseline.
2. Half-upgraded state should not crash.
3. Legacy tasks remain readable with missing new fields.
4. Escalation output must remain deterministic and machine-readable.
