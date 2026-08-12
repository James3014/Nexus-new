# Issue #52 Legacy Adapter Cleanup

- artifact_authority: current
- owner: James Chen
- status: active
- source_issue: `#52`
- baseline_main: `c994b24c57c1ad7cfec1cb407074995925e7deb6`
- current_frontier: `00-remove-six-legacy-adapters.md`
- completed_cards: `[]`
- blocked_cards: `[]`
- SOURCES serializer: `#52`; `#55 SERIALIZE_AFTER #52`
- `AUTO_CHAIN=false`

This campaign removes six self-archived, caller-free adapters and exactly their
six stale source-inventory rows. It does not own active service behavior.
