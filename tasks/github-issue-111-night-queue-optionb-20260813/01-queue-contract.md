# Queue contract implementation

Allowed files: `nexus/app/nightshift_runner_service.py`, `nexus/services/nightshift_queue_consumer.py`, `scripts/nightshift.py`, `tests/services/test_nightshift_queue_consumer.py`, `tests/ops/test_issue111_nightshift_impact_map.py`, `docs/testing/test_impact_map.md`, this campaign card.

The producer writes a versioned `bounded_candidate_generation` manifest with explicit safety controls. The official NightShift entrypoint wires the consumer to the same canonical manifest. The consumer validates the manifest, calls the existing `UnifiedRuntime`/`CapabilityPlanner` workforce-admission seam, dispatches only on `ALLOW`, and is idempotent by task and source revision. It never selects a provider/model or grants worker permissions.

Verification: `uv run pytest -q tests/services/test_nightshift_queue_consumer.py tests/ops/test_issue111_nightshift_impact_map.py`, `uv run ruff check nexus/app/nightshift_runner_service.py nexus/services/nightshift_queue_consumer.py scripts/nightshift.py tests/services/test_nightshift_queue_consumer.py tests/ops/test_issue111_nightshift_impact_map.py`.

## Terminal reconciliation

Issue #111 is closed/completed after PR #220 physically merged (2026-08-13):

- PR #220 base `2c820eab67669ab63297bf76fcf1751aaa9496ba`, head `da426a0d170a662048cc0a226e181153ddd00585`, merge `587aa4b1d6026dc85efe35930f2067fbd1ead3cc`; exact 8-file scope; required checks 6/6 SUCCESS.
- Current main readback (`eb668fb76f0c30d8f025db42cdb8e320d556c037`): `nexus/services/nightshift_queue_consumer.py` enforces `SCHEMA=nexus.nightshift_candidate_demand.v1`, six required controls, forbidden worker actions `{commit, push, approve, integrate}`, canonical Workforce `ALLOW` plus gateway invocation authority gating, and atomic/idempotent writes; `tests/services/test_nightshift_queue_consumer.py` holds 7 tests covering restart idempotency, malformed/tampered fail-closed, fake-ALLOW block, and producer Option B contract.

Marker: `NIGHTSHIFT_OPTION_B_QUEUE_CONSUMER_PROVEN`; ceiling: `NIGHTSHIFT_OPTION_B_QUEUE_CONSUMER_PROVEN_ONLY`.

This proves only that the NightShift queue producer/consumer bound to `bounded_candidate_generation` is present and tested on current main. It grants no provider/model identity change, route/Workforce selection, approval, integration, push, runtime, release, or production authority.
