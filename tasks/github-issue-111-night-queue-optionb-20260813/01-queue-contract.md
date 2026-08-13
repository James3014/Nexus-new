# Queue contract implementation

Allowed files: `nexus/app/nightshift_runner_service.py`, `nexus/services/nightshift_queue_consumer.py`, `scripts/nightshift.py`, `tests/services/test_nightshift_queue_consumer.py`, `tests/ops/test_issue111_nightshift_impact_map.py`, `docs/testing/test_impact_map.md`, this campaign card.

The producer writes a versioned `bounded_candidate_generation` manifest with explicit safety controls. The official NightShift entrypoint wires the consumer to the same canonical manifest. The consumer validates the manifest, calls the existing `UnifiedRuntime`/`CapabilityPlanner` workforce-admission seam, dispatches only on `ALLOW`, and is idempotent by task and source revision. It never selects a provider/model or grants worker permissions.

Verification: `uv run pytest -q tests/services/test_nightshift_queue_consumer.py tests/ops/test_issue111_nightshift_impact_map.py`, `uv run ruff check nexus/app/nightshift_runner_service.py nexus/services/nightshift_queue_consumer.py scripts/nightshift.py tests/services/test_nightshift_queue_consumer.py tests/ops/test_issue111_nightshift_impact_map.py`.
