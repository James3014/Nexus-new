# M2 Agent Workflow Integration

## Status

`M2_IMPLEMENTED_AWAITING_ONLINE_AGENT_SMOKE`

The enforced briefing, closeout contract, CLI surface, and runner failure path are implemented and locally verified. The required Gemini/Grok audited task is not yet claim-eligible because the external invocation requires explicit user authorization in this environment.

## Change Log

- `nexus/services/local_assist_closeout.py`: validates Agent consumption and contribution fields against replayable Local Assist receipts; rejects receipt-only consumption claims.
- `scripts/engine/commands/local_assist_actions.py` and `scripts/engine/nexus_cli.py`: add `nexus local-assist closeout`.
- `scripts/ops/_nexus_enforced_briefing.sh`: documents advisor/candidate/verified-subtask selection, receipt citation, and fail-closed claim boundaries.
- `scripts/ops/run_gemini_nexus_round.sh`: repairs briefing/delegated-contract quoting and preserves machine-readable failure handling.
- `tests/services/test_local_assist_closeout.py` and `tests/ops/test_local_assist_agent_workflow.py`: cover consumption evidence, receipt validation, briefing content, and runner syntax.

## Verification Evidence

- `.venv/bin/python -m pytest -q tests/services/test_local_assist_closeout.py tests/ops/test_local_assist_agent_workflow.py` → `6 passed`.
- M1 + M2 focused regression (`test_local_assist_service.py`, closeout, and Agent workflow suites) → `11 passed`.
- `py_compile` passed for the new closeout service and changed CLI action module.
- `nexus local-assist --help` exposes `advisor`, `candidate`, `closeout`, and `verified-subtask`.
- Closeout CLI accepted a local contract smoke using the existing real M1 Ollama receipts and emitted `.tmp/m2_local_receipt_closeout_report.json`; this proves receipt validation only, not Agent consumption.
- `bash -n scripts/ops/_nexus_enforced_briefing.sh scripts/ops/run_gemini_nexus_round.sh` passed.
- The closeout contract rejects `local_assist_output_consumed=true` when only receipts are supplied, and requires explicit output/evidence references to every receipt identity.

## Claim Boundary

Local evidence proves the M2 contract and briefing integration only. It does not prove `AGENT_OPERATED_LOCAL_ASSIST_PROVEN`, `local_assist_output_consumed=true` in a real Agent task, or any outcome/value contribution.

## Residual Debt

- Run one authorized Gemini/Grok audited task that invokes advisor plus candidate or verified-subtask, consumes both outputs, and cites both receipts in final closeout.
- Preserve the online task report, two Local Assist receipt pairs, and closeout report before sealing M2.
- Keep M3 automatic dispatch and all benchmark/value claims out of scope.
