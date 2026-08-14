# Issue #52 Legacy Adapter Cleanup

- artifact_authority: current
- owner: James Chen
- status: COMPLETE / TERMINAL_RECONCILIATION
- source_issue: `#52`
- baseline_main: `069596056fff852bad8c826725902d25361aa9c7`
- historical_reconciled_main: `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`
- reconciled_main: `cdf2570ede5ae218f36f886b696c8da45458043a`
- current_frontier: `00-remove-six-legacy-adapters.md`
- completed_cards: `[00-remove-six-legacy-adapters.md]`
- blocked_cards: `[]`
- SOURCES serializer: `#52`; `#55 SERIALIZE_AFTER #52`
- `AUTO_CHAIN=false`
- terminal_marker: `LEGACY_ADAPTERS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED`
- claim_ceiling: `LEGACY_ADAPTERS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED_PROVEN_ONLY`

This campaign removes six self-archived, caller-free adapters and exactly their
six stale source-inventory rows. It does not own active service behavior.

Owner-authorized impact-map amendment: the exact six deleted adapter paths are
mapped to focused verification targets in `docs/testing/test_impact_map.md`,
with selector coverage asserted by `tests/ops/test_issue52_cleanup_impact_map.py`.
Unknown legacy siblings remain fail-closed fallback inputs.

## Terminal reconciliation (post-merge)

Physically merged by PR #215:

- PR #215 base: `069596056fff852bad8c826725902d25361aa9c7`
- PR #215 head: `845954d1498e7afffce9b278f5827edb7682dd01`
- PR #215 merge: `2c820eab67669ab63297bf76fcf1751aaa9496ba`
- stale predecessor PR #87 is closed and superseded; it grants no authority.

Historical reconciliation receipt: `eb668fb76f0c30d8f025db42cdb8e320d556c037`
(original 2026-08-13 verification snapshot).

Historical current-main readback at `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`
(recorded on repair head `2cf77ca6eabce03e5ebbacf18feced6b6b7cce11`):

- all six `scripts/legacy/{git_manager,linter,llm_client,patcher,reporter,
  workspace_manager}.py` paths are absent;
- `muse_nexus.egg-info/SOURCES.txt` contains zero `scripts/legacy` rows;
- PR #215 merge is an ancestor of current main.

Current-main readback at `cdf2570ede5ae218f36f886b696c8da45458043a`
(post-PR236 rebind, merge commit `663ea1660c03c07627c050af91ca3fa393133150`):

- all six `scripts/legacy/{git_manager,linter,llm_client,patcher,reporter,
  workspace_manager}.py` paths are absent;
- `muse_nexus.egg-info/SOURCES.txt` contains zero `scripts/legacy` rows;
- PR #215 merge is an ancestor of current main.

Evidence bound from PR #215: 539 focused replacement/migration/CLI tests
passed; wheel and sdist contain none of the six deleted paths. The historical
live required-check rollup for PR #215 is `NOT_RECOVERED`/`NOT_ASSERTED`; this
reconciliation does not claim a CI/check receipt that was not independently
read back.

`AUTO_CHAIN=false`. Claim ceiling:
`LEGACY_ADAPTERS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED_PROVEN_ONLY`. This
metadata states only the exact GitHub collaboration deletion and source
inventory reconciliation; it grants no runtime, route, Workforce, lifecycle,
approval, integration, merge, release, or production authority.
