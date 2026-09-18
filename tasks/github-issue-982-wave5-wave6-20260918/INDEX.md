# Issue #982 Wave 5–6 execution frontier

artifact_authority: current
status: ACTIVE
owner: James Chen
AUTO_CHAIN: false

## Source fence

- Durable owner: `James3014/Nexus-new#982`
- Nexus-new base: `cc76280a1db0744f63e078cc6075971557a45025`
- DevSpace main/live source: `bbf265621ab68dcd9676276fc22b67e99c85391a`
- DevSpace live build: `devspace-1.0.7-bbf26562`
- live tool-projection capabilities: present
- current ChatGPT-loaded DevSpace tool schema: stale; native `agent_start` schema does not expose the new fields, so Wave 5 must use a fresh authenticated MCP client and `tools/list` acknowledgement before canary execution.

## Dependency frontier

1. Wave 5 prerequisite: re-land the already-decided symmetric fail-closed invariant so `authorizedToolCeiling` and `toolProjectionManifest` either both participate or neither participates.
2. Wave 5 G3: bind the historical 11-identity baseline to current admission state, execute A/B physical witnesses for the current-admissible identities, and record explicit unavailable/unsupported dispositions without inventing enforcement.
3. Wave 6 G4 remains blocked until Wave 5 produces at least one physically enforceable transport family with a valid intervention witness.
4. Wave 6 benchmarks transport/enforcement behavior, not political/model-quality ranking, and may only include identities with a valid G3 witness.
5. G4 token/schema metrics remain `NOT_OBSERVED` where provider telemetry cannot truthfully provide them.

The Owner's explicit request on 2026-09-18 is to complete Wave 5 and Wave 6 in sequence. This is explicit successor authority for those two gates, not generic AUTO_CHAIN authority.
