# Issue #52 Legacy Adapter Cleanup

- artifact_authority: current
- owner: James Chen
- status: active
- source_issue: `#52`
- baseline_main: `069596056fff852bad8c826725902d25361aa9c7`
- current_frontier: `00-remove-six-legacy-adapters.md`
- completed_cards: `[]`
- blocked_cards: `[]`
- SOURCES serializer: `#52`; `#55 SERIALIZE_AFTER #52`
- `AUTO_CHAIN=false`

This campaign removes six self-archived, caller-free adapters and exactly their
six stale source-inventory rows. It does not own active service behavior.

Owner-authorized impact-map amendment: the exact six deleted adapter paths are
mapped to focused verification targets in `docs/testing/test_impact_map.md`,
with selector coverage asserted by `tests/ops/test_issue52_cleanup_impact_map.py`.
Unknown legacy siblings remain fail-closed fallback inputs.
