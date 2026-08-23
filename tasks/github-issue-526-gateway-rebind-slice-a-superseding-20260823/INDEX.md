# Issue #526 — Superseding Gateway Deployment Contract Slice A

```yaml
campaign_id: GITHUB_ISSUE_526_GATEWAY_REBIND_SLICE_A
source_issue: 526
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 2df9a429eb30aca9b20aaa46be9a96ba13c4334a
base_tree: ff8a854ff33fd656044fe80c99d41b1e1984cbd4
work_branch: codex/issue-526-gateway-deployment-contract
task_id: TASK-526-A
supersedes_card_sha256: d4b66f4a96ee52287a5805f5e1fdc438a4f94cab7f98fb9be35a691aaef5bb4d
supersedes_failed_attempt: 44f228e15878b3cae4620db7d7510e4b51cf932c
claim_ceiling: NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY
```

## Frontier

| Task | Card | Status | Outcome |
|---|---|---|---|
| `TASK-526-A` | `00-gateway-deployment-sole-owner.md` | ACTIVE | four-file source/test Candidate only |
| Slice B | separate DevSpace contract | BLOCKED | `SERIALIZE_AFTER:#398`; not activated here |

## Supersession

The prior two-file Card and local attempt are retained as failed evidence under
marker `ISSUE526_SLICE_A_HARD_BLOCK_CARD_REDESIGN_REQUIRED`. This Card keeps
the stable task identity `TASK-526-A` and replaces only the implementation
seam. It does not rewrite or approve the failed Candidate.

## Frozen scope

- `nexus/contracts/gateway_deployment.py`
- `scripts/ops/mcp_gateway_durable.py`
- `tests/contracts/test_gateway_deployment_contract.py`
- `tests/ops/test_mcp_gateway_durable.py`

Maximum four tracked paths. Zero deletions. The contract module is pure and
creates no second process owner; all host/process effects remain solely in
`mcp_gateway_durable.py`.

