# Nexus Universal Local Assist Operator Runbook

## Scope and claim boundary

This runbook covers the provider-neutral Local Assist interface, planner recommendation, bounded canaries, cloud/local stage chain, quota degradation, receipt inspection, and rollback. It is internal-only. `production_ready=false` and `public_claim_allowed=false` remain in force until a separate release review.

## Health check

Run the Python API check before an operator session:

```python
from nexus.services.local_assist_health import run_local_assist_health_checks
report = run_local_assist_health_checks(workspace_root=".")
```

Required checks:

- Ollama executable availability and configured model identity.
- Provider-neutral adapter availability.
- Candidate isolation and Git metadata.
- Workspace verifier interpreter.
- Durable receipt storage.
- Workspace revision integrity.

Any `FAIL` yields `DEGRADED`; do not promote the result to a production or public claim.

## Provider setup

1. Configure the local provider and model identity in the workspace environment.
2. Confirm the health report before invoking `advisor`, `candidate`, or `verified-subtask`.
3. Use the provider-neutral Cloud Agent adapter for cloud integrations. Injected adapters are deterministic test providers and never count as real cloud calls.
4. Keep provider errors, quota errors, and verifier errors as separate receipt fields.

## Daily interface

Emit a provider-neutral Agent envelope without execution:

```bash
python scripts/engine/nexus_cli.py local-assist interface \
  --task-file task.json \
  --workspace .
```

The envelope contains task identity, Planner recommendation, available actions, Assist Envelope, receipt paths, candidate identities, verifier state, consumption contract, contribution contract, and claim boundary.

Canonical run policy is explicit:

- `disabled`: preserve existing `nexus run` behavior.
- `planner`: emit a recommendation receipt before the run; no automatic Local Assist invocation is implied by the receipt.
- `explicit`: preserve Agent-controlled Local Assist invocation.

## Receipt inspection

Every receipt must be linked by `task_id` and `workspace_revision`. Inspect, in order:

1. Planner recommendation and route truth source.
2. Provider call ledger, model, usage, latency, and error.
3. Candidate identity, isolation status, and selected/applied hash agreement.
4. Verifier command, environment, and terminal result.
5. Agent consumption evidence.
6. Causal contribution evidence.
7. Value matrix evidence, if measuring across arms.

Do not infer `invoked`, `delivered`, `consumed`, `contributed`, or `value measured` from an earlier field.

## Failure recovery

- Provider unavailable: retain the failed receipt; use the bounded local-only or fail-closed quota policy.
- Candidate isolation failure: reject the candidate; do not apply it to the formal workspace.
- Hash mismatch: reject adoption and preserve both hashes.
- Verifier failure: keep terminal failure; do not delete assertions, relax the parser, or silently retry through another authority.
- Stale workspace revision: discard the candidate or dispatch and regenerate from the current revision.
- Missing or malformed receipt: block closeout and retain `public_claim_allowed=false`.

## Rollback procedure

1. Stop automatic dispatch with policy `disabled`.
2. Preserve the task receipt bundle and rollback reference.
3. Reject pending candidate adoption.
4. Restore only through the Agent-controlled formal workspace workflow.
5. Re-run the deterministic verifier and record the result.
6. Reopen contribution/value claims only after lineage and comparison evidence are rebuilt.

## Compatibility matrix

| Surface | Default | Local Assist execution | Formal mutation | Evidence |
| --- | --- | --- | --- | --- |
| Explicit advisor | Existing CLI | Agent-controlled | No | Local Assist receipt |
| Explicit candidate | Existing CLI | Agent-controlled | Isolated only | Candidate isolation receipt |
| Explicit verified-subtask | Existing CLI | Agent-controlled | Isolated only | Verifier receipt |
| Planner policy | Opt-in | Shadow/bounded policy | No automatic formal mutation | Recommendation receipt |
| Cloud/local chain | Opt-in contract | Provider-neutral adapter | Canonical candidate pipeline | Stage-chain receipt |
| Quota exhausted | Degraded | Local-only if available | Agent-controlled | Quota reason chain |
| Provider unavailable | Fail-closed | No fake success | None | Failure receipt |

## Privacy and data boundary

Send only bounded context, allowed target files, semantic assertions, and evidence references through an adapter. Do not send secrets, credentials, absolute private paths, unrelated reports, or the formal workspace itself. Provider identity and response identity must be explicit.
