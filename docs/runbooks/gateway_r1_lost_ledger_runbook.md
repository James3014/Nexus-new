# Gateway R1: a lost recovery ledger

Status: current (2026-10-15, #2177; follows #1995 / PR #2170). Applies to the
unified MCP Gateway manager `scripts/ops/mcp_gateway_durable.py` on a host where
R1 durable recovery has run at least once.

## Background

The Gateway ledger is `ledger.jsonl` in the Gateway state root
(`$NEXUS_GATEWAY_STATE_ROOT`, default
`~/Library/Application Support/Nexus/gateway-direct`). R1 recovery rows live in
it. If the ledger disappears after R1 rows existed, Nexus must not treat the
host as a first run, because that could replay an R1 effect or start a v1 effect
while an R1 request is still open.

The manager detects the loss through files that only exist once R1 has run:

- `r1-ledger-genesis.json` is written **before** the first R1 row (#2177). Any
  R1 operation on an older ledger that already holds R1 rows writes it first and
  fails closed with `R1_LEDGER_GENESIS_UNAVAILABLE_FAIL_CLOSED:<reason>` if it
  cannot.
- `r1-owner-reconciles/` holds Owner reconcile records.
- The v1 effect guard also counts `recovery-authority.json`,
  `recovery-actuator-bootstrap-consumed.json` and a non-empty
  `recovery-materializations/`.

Plain ledger scans used by v1 effects never write the marker.

## Symptom

These operations refuse with
`R1_LEDGER_MISSING_WITH_PRIOR_STATE_FAIL_CLOSED:<signals>`:

- v1 `gateway-reload`, `gateway-install-artifact` and `gateway-rollback`;
- the auto-deployer (`com.nexus.gateway-auto-deploy`), which calls
  `open_r1_recovery_blocks_effect()`;
- R1 materialization, R1 recovery (`gateway-recover`) and Owner reconcile.

`<signals>` lists the files found, for example `r1-ledger-genesis.json`.
Materialization checks this before it writes its receipt, the predecessor
artifact, or the authority and request stores, so a refused run leaves those
unchanged.

## Recovery

1. **Restore `ledger.jsonl` from backup if possible.** Put it back at the same
   path with mode `0600`, owned by the Gateway user. Then rerun the refused
   operation. Do not edit the rows; the manager checks the hash chain.
2. **If it cannot be restored, the Owner approves in chat.** Explain what was
   lost and which R1 request was last known to the Owner. Do not continue
   without that approval.
3. **Only after that approval**, first put the auto-deployer on hold
   (`python scripts/ops/nexus_gateway_auto_deploy.py hold --reason "<Issue #2177 reset>"`,
   the `com.nexus.gateway-auto-deploy` hold from `docs/ops/release-gates.md`)
   and stop the Gateway service, so nothing reads or writes the state root
   while you work. Then deliberately move `r1-ledger-genesis.json` and, if
   present, `r1-owner-reconciles/` out of the Gateway state root into a dated
   evidence folder outside it. This re-establishes first-run semantics for R1.
   `r1-owner-reconciles/` holds Owner-approval evidence, so move it into the
   same dated folder as the other files; never remove it. If the v1 guard still
   lists `recovery-authority.json`, `recovery-actuator-bootstrap-consumed.json`
   or `recovery-materializations`, those are part of the same Owner-approved
   reset and go into the same dated folder; do not delete them. Afterwards
   restart the Gateway and release the hold
   (`python scripts/ops/nexus_gateway_auto_deploy.py release`).
4. **Record** the Owner approval reference (chat session and quote, or Issue
   comment URL) on Issue #2177.

### Marker left by a crash on a host with no ledger

The marker is written before the first R1 row. If the manager crashes between
the two on a host that had no `ledger.jsonl` yet, the host shows the same
symptom with no ledger. Nexus cannot tell this apart from a lost ledger, so it
fails closed. Use the same recovery steps: confirm there is no backup, get the
Owner's approval in chat, then remove the marker.

### Genesis marker cannot be written

`R1_LEDGER_GENESIS_UNAVAILABLE_FAIL_CLOSED:<reason>` means an R1 operation found
R1 rows in the ledger but could not create or verify `r1-ledger-genesis.json`.
Typical reasons are a permission problem, an unsafe path (a symlink or wrong
mode on the state root), a file system without hard links, or a marker whose
bytes were changed. Fix the cause. Do not create the file by hand with different
contents. v1 effects are not blocked by this.

## Related

- An R1 request stuck in `EFFECT_STARTED` or `UNCERTAIN_EFFECT` blocks v1
  rollback, install and reload until R1 reconciliation completes
  (`R1_OPEN_RECOVERY_BLOCKS_V1_EFFECT:<request_id>:<state>`).
- After a post-effect `BLOCKED` R1 request, record the Owner's chat approval
  before starting a successor:

  ```
  python3 scripts/ops/mcp_gateway_durable.py gateway-r1-owner-reconcile \
    --request-id <blocked request id> --note "<why>" \
    --owner-approval-ref "<chat session + quote, or Issue comment URL>"
  ```
