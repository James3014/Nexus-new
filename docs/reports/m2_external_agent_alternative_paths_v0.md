# M2 External Agent Alternative Verification Paths

## Status

Track A: `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_ON_PUBLIC_FIXTURE`
Track B: `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_WITH_USER_RELAY`
Any-Agent audited task: `AGENT_OPERATED_LOCAL_ASSIST_PROVEN`

Track A is complete for a public toy fixture. Track B is now closed through the user-authorized relay artifact and local receipt-lineage validator. These alternative paths do not promote full M2 productization, M4 cloud integration, or public value claims for Nexus.

## Track A: Public Fixture External Agent Smoke

Fixture contents were limited to a toy calculator source, one failing test, a relative-only task file, and sanitized Local Assist artifacts. No Nexus source, absolute repository path, secret, credential, or historical report was included in the external Agent workspace.

Evidence:

- Local advisor response and raw execution receipt are under `.nexus/reports/local_assist/m2-public-fixture-20260713/`.
- Local advisor: `provider=ollama`, `resolved_model=qwen2.5-s2t-advisor:3b`, `provider_call_count=1`, `receipt_complete=true`, `runtime_invoked=true`, `output_delivered=true`.
- External entry: `agy --new-project --add-dir` with only the public fixture mounted; agy log resolved the model label as `Gemini 3.5 Flash (Medium)`.
- Imported external response: `agy_response.json` reports `local_assist_consumed=true` and references task `public-calculator-advisor-20260713`.
- Independent verification: only `calculator.py` changed from subtraction to addition; `python3 -m pytest -q test_calculator.py` → `1 passed`.
- Claim boundary: `outcome_contributed=false`, `value_measured=false`.

The first `agy` invocation used an invalid duration (`300`); the CLI rejected it before dispatch. The successful retry used `300s`. `agy` also attempted an out-of-scope discovery command, which its sandbox blocked; no private file was exposed.

## Track B: User Relay Real Repository Smoke

The local package is under `.nexus/reports/local_assist/m2-user-relay-20260713/`:

- `context_package.json` records `external_delivery_mode=human_relay`, `delivery_authority=user`, `automated_exfiltration=false`, and `local_assist_receipt_present=true`.
- `relay_prompt.md` is pasteable material for a user-controlled external Agent session.
- `agent_response_imported.json` preserves the user-imported response with `status=IMPORTED_PENDING_VALIDATION`, false imported/consumed/contribution/value flags, and both receipt identities.
- The user-provided external Agent response explicitly consumed both receipt identities and proposed `test_closeout_requires_every_receipt_identity_in_final_output_and_consumption_evidence`; it produced no patch and changed no authority.
- `nexus local-assist user-relay-validate` produced `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_WITH_USER_RELAY`, `agent_output_imported=true`, `agent_consumed_proven=true`, `modified_files=[]`, `outcome_contributed=false`, and `value_measured=false`.
- Validator tests cover missing response, valid imported response, pending-import normalization, missing receipt citation, contribution-claim rejection, and machine-report output.
- Absolute-path and secret scans passed; private-content presence is explicitly classified, so the package cannot be treated as public data.
- The response was supplied by the current user-authorized ChatGPT relay session; this is an allowed Agent identity under the revised any-Agent smoke rule. No automated repository delivery occurred.

## Any-Agent Audited Task Smoke

The bounded task `m2-agent-audit-20260713` closes the revised any-Agent six-step sequence:

- ChatGPT received the development task to add a focused nested contribution/value-claim regression test.
- Local Assist advisor was invoked with `provider=ollama`, `resolved_model=qwen2.5-s2t-advisor:3b`, `runtime_invoked=true`, `output_delivered=true`, and a complete receipt.
- ChatGPT consumed the advisor output and selected `tests/services/test_local_assist_user_relay.py` / `test_import_rejects_contribution_claims`.
- Local Assist candidate was invoked with `provider=ollama`, `resolved_model=qwen2.5-coder:7b-instruct`; the successful retry recorded `isolation_status=isolated`, `patch_apply_status=applied`, and `selected_candidate_hash_matches_applied=true`.
- ChatGPT consumed the candidate patch, applied the bounded test to the formal workspace, and ran `uv run pytest -q tests/services/test_local_assist_user_relay.py` → `7 passed`.
- The closeout report is `VERIFIED` and cites both receipt identities with `output_consumed=true`, `outcome_contributed=false`, and `value_measured=false`.

## Claim Boundary

Track A proves `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_ON_PUBLIC_FIXTURE`. Track B proves `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_WITH_USER_RELAY`. The bounded any-Agent audited task proves `AGENT_OPERATED_LOCAL_ASSIST_PROVEN` for the recorded task sequence. None of these statuses proves `outcome_contributed`, `value_measured`, M4 cloud integration, or broad M2 productization.
