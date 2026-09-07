# Task Card: astra-research-attempt-identity-20260907

artifact_authority: current
task_id: `astra-research-attempt-identity-20260907`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Fix actual Research-to-canonical-Learning duplicate persistence by forwarding explicit caller task_id and attempt_id to EpisodeOutcomeRecord.from_task and a deterministic unambiguous task/attempt idempotency key. Missing or invalid identity on durable Research path fails closed before persistence; do not invent writer UUID/timestamp/task-slug-only keys or synthetic success. Transport redelivery reuses same attempt; new execution uses caller-supplied new attempt. Preserve actual PARKED/solved=false/capability receipts and no positive public claims. Wire CLI/request/action/benchmark callers within listed files; do not change external canonical Learning package. Tests must exercise real Research-produced failed records, unchanged canonical save, same-attempt no-op with unchanged history/policy bytes, distinct attempt separate rows, missing identity denial. Owner-authorized Luna source implementation in an isolated branch based on qualified subject 4887d8f6a3faf50d6b600f2c170526e08d4bf408 plus these exact coordinator-created card/index bytes; coordinator may transport the card-only commit without unrelated source deltas. This card is source implementation authority; a source commit does not claim formal local lifecycle Candidate, approval, integration or runtime execution. No API-key model calls, provider SDK calls, merge, deployment, live data changes, main mutation or self-approval. Independent root physical diff and verifier required.

## Allowed files

- `nexus/app/research_flow_service.py`
- `scripts/engine/commands/research_actions.py`
- `scripts/engine/nexus_cli.py`
- `scripts/ops/nexus_chatgpt_delivery.py`
- `scripts/bench/capability_ab_runner.py`
- `tests/app/test_research_flow_service.py`
- `tests/engine/test_cli_research_seams.py`
- `tests/engine/test_research_actions.py`

## Verification commands

```bash
python3 -m pytest tests/app/test_research_flow_service.py tests/engine/test_cli_research_seams.py tests/engine/test_research_actions.py -q
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
