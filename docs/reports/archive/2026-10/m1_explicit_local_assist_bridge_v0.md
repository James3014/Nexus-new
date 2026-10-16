# M1 Explicit Local Assist Bridge

## Status

`EXPLICIT_LOCAL_ASSIST_BRIDGE_PROVEN` for the bounded explicit CLI seam only.

Fresh live closure receipts were persisted on 2026-07-13 under `.nexus/reports/local_assist/` for advisor, candidate, and verified-subtask.

This does not prove M2 enforced-briefing integration, M3 automatic planner dispatch, M4 real cloud integration, or M5 causal value.

## Change Log

- `nexus/services/local_assist_service.py`: canonical request/response contracts, fail-closed validation, advisor provider call, candidate/verified-subtask executor bridge, isolated apply, deterministic verifier, lineage, response and execution receipt.
- `scripts/engine/commands/local_assist_actions.py`: machine-readable task-file CLI adapter.
- `scripts/engine/nexus_cli.py`: `local-assist advisor`, `candidate`, and `verified-subtask` commands.
- `tests/services/test_local_assist_service.py`: contract, failure, isolation, verifier, and claim-boundary tests.

The product path does not import `capability_ab_runner.py`, `LocalHealCapabilityAdapter`, or `FakeCloudCandidateProvider`. It accepts an explicit `CapabilityPlanner` snapshot and does not perform automatic dispatch.

## Verification Evidence

- `.venv/bin/python -m pytest -q tests/services/test_local_assist_service.py` → `5 passed`.
- `UV_CACHE_DIR=.tmp/uv-cache uv run python scripts/engine/nexus_cli.py local-assist --help` reached all three commands; the first uv execution was blocked by local cache permissions, and workspace uv cache then panicked in the sandbox, so final smoke used the repo `.venv` directly.
- Ollama `/api/tags` showed `qwen2.5-s2t-advisor:3b` and `qwen2.5-coder:7b-instruct`.
- Live advisor CLI receipt: `provider=ollama`, `provider_call_count=1`, `runtime_invoked=true`, `output_delivered=true`, `receipt_complete=true`.
- Live candidate CLI receipt: 7B invocation, one candidate, `patch_apply_status=applied`, `isolation_status=isolated`, selected/applied hash reconciled, source workspace unchanged.
- Live verified-subtask CLI receipt: 7B invocation, isolated workspace verifier `exit_code=0`, `verifier_status=pass`, `receipt_complete=true`.
- Fresh replayable receipt set:
  - `.nexus/reports/local_assist/m1-closure-advisor-20260713/response.json` + `execution_receipt.json` — Ollama `qwen2.5-s2t-advisor:3b`, one provider call, delivered.
  - `.nexus/reports/local_assist/m1-closure-candidate-final-20260713/response.json` + `execution_receipt.json` — Ollama `qwen2.5-coder:7b-instruct`, one provider call, isolated candidate, selected/applied hash matched.
  - `.nexus/reports/local_assist/m1-closure-verified-final-20260713/response.json` + `execution_receipt.json` — Ollama `qwen2.5-coder:7b-instruct`, one provider call, isolated verifier pass.
- Source integrity check: the closure sentinel exists only in the isolated candidate diff; the formal source report hash matches the receipt `source_snapshot_hash`.
- Sandbox Ollama denial and malformed first candidate hunk both returned `status=FAILED` / incomplete receipt; no success claim was emitted.
- `.venv/bin/python scripts/ops/ci_gate.py --dry-run` passed protocol, lesson, report-trust, skill, and wiki checks but failed Delivery-Track on pre-existing untracked `nexus-core-rs/target/.rustc_info.json` and `nexus-core-rs/target/release/nexus-core-rs`.

## Claim Boundary

The live receipts prove `registry_known`, explicit planner snapshot validation, `runtime_invoked`, and `output_delivered`. They do not prove `agent_consumed`, `outcome_contributed`, or `value_measured`.

## Residual Debt

- Online Agent briefing/closeout consumption fields are M2.
- Automatic planner dispatch is M3.
- Real cloud provider adapter is M4; `FakeCloudCandidateProvider` remains outside this product path.
- Benchmark causal comparison is M5.
- GitNexus CLI was unavailable; impact evidence was replaced by targeted `rg`, focused tests, and live receipts.
- Pre-existing Rust target artifacts remain a repository hygiene blocker for the full CI dry-run; they were not touched.
