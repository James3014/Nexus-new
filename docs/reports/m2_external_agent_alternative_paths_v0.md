# M2 External Agent Alternative Verification Paths

## Status

`AGENT_OPERATED_LOCAL_ASSIST_PROVEN_ON_PUBLIC_FIXTURE`

Track A is complete for a public toy fixture. Track B is prepared and intentionally stopped at `USER_RELAY_REQUIRED`. Neither result promotes full M2 productization, M4 cloud integration, or public value claims for Nexus.

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

- `context_package.json` records `external_delivery_mode=human_relay`, `delivery_authority=user`, `automated_exfiltration=false`, `local_assist_receipt_present=true`, `agent_output_imported=false`, and `agent_consumed_proven=false`.
- `relay_prompt.md` is pasteable material for a user-controlled external Agent session.
- Absolute-path and secret scans passed; private-content presence is explicitly classified, so the package cannot be treated as public data.
- Status remains `USER_RELAY_REQUIRED`; no automated delivery occurred.

## Claim Boundary

Track A proves `AGENT_OPERATED_LOCAL_ASSIST_PROVEN_ON_PUBLIC_FIXTURE` only. Track B does not prove Agent consumption until the user manually relays the package and imports a response that can be checked against the receipt lineage.
