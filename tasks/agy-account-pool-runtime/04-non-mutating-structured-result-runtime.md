---
artifact_authority: current
owner: James Chen
status: READY
task_id: non-mutating-structured-result-runtime
campaign_id: agy-account-pool-runtime
triggered_by:
  - agy-card01-live-dispatch-acceptance
depends_on_evidence:
  - 6170fb9951c5587a08f8d64812cba687b19f18ea
AUTO_CHAIN: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Non-mutating Structured Result Runtime

## Objective

Add one explicit, hash-bound structured-response result mode to the existing
self-hosted isolated-target lifecycle.

The new mode must allow a governed worker to return a schema-validated result
without modifying repository files, while preserving the existing non-empty-diff
requirement for implementation tasks.

This is a result-contract extension. It must not create another route,
planner, verifier, receipt authority, provider runtime or execution lane.

## Existing authority

- CapabilityPlanner remains route authority.
- Workforce Admission remains worker eligibility authority.
- SelfHostedTaskService remains lifecycle execution authority.
- CandidateVerifier remains repository-state verifier.
- The existing provider adapter remains provider invocation authority.
- Receipt and Claim Gate remain claim authority.

## Required design

Introduce one explicit result mode:

```text
CANDIDATE_DIFF
STRUCTURED_RESPONSE
```

Default:

```text
CANDIDATE_DIFF
```

Existing tasks without the new field must behave exactly as before.

### CANDIDATE_DIFF

Preserve all current requirements:

* `allowed_files` must contain 1–4 bounded paths at the public Gateway seam;
* candidate diff must be non-empty;
* existing CandidateVerifier and candidate commit flow remain unchanged;
* zero-file requests remain rejected;
* no existing implementation test may become weaker.

### STRUCTURED_RESPONSE

Required semantics:

* allow 0–4 bounded `allowed_files`;
* require a bounded `output_schema`;
* bind result mode and output schema into the immutable Task Contract/hash;
* execute in an isolated Target;
* repository mutation is forbidden;
* a non-empty diff is a hard failure;
* provider exit code must be zero;
* provider output must decode successfully;
* decoded output must validate against `output_schema`;
* CandidateVerifier must still verify:

  * controller unchanged;
  * target has no repository delta;
  * no deletion;
  * no protected-contract mutation;
  * verifier commands pass;

* success must not create a Candidate commit;
* success must not enter approval, promotion or integration flow;
* terminal state must represent verified non-mutating evidence, not Candidate readiness.

Use one existing lifecycle terminal vocabulary where semantically correct, or
introduce one narrowly scoped state such as:

```text
STRUCTURED_RESULT_VERIFIED
```

Do not call it `CANDIDATE_VERIFIED`.

## Result receipt

Extend the existing provider-neutral execution receipt only as needed to record:

```yaml
result_mode:
result_present:
result_sha256:
result_schema_valid:
result_schema_sha256:
account_alias_hash:
isolated_home_hash:
provider_attempt_count:
```

Do not persist raw credential data, raw HOME, raw account name or raw environment.

The isolated HOME hash must be computed from the actual HOME passed to the
provider subprocess, not inferred from account alias.

## AGY output decoding

AGY stdout may contain an outer CLI envelope around the model result.

Reuse the existing AGY/provider decoding semantics currently used by the
Gateway model-probe path.

Do not create a second parser authority with divergent behavior.

If the decoder must be shared, extract it into one small provider-neutral module
and have both current Gateway probe and `AgyWorkerAdapter` consume it.

Preserve current malformed-output fail-closed behavior.

## Prompt contract

For `STRUCTURED_RESPONSE`, the worker prompt must state:

* return only the requested structured result;
* do not edit files;
* do not generate a patch;
* do not commit;
* obey the supplied output schema.

For source-bound structured tasks, include only explicitly allowed files.

For zero-file canaries, provide no repository source context.

## Attempt resolution

Do not globally remove the `candidate_non_empty` requirement.

Resolution must be conditional:

```text
CANDIDATE_DIFF
→ requires non-empty candidate diff

STRUCTURED_RESPONSE
→ requires schema-valid result
→ requires empty repository delta
```

A response-only success cannot become a Candidate or promotion packet.

## Gateway contract

Add result-mode and output-schema fields to the formal `nexus_task_run` request.

Gateway validation:

```text
CANDIDATE_DIFF + zero allowed_files
→ reject

STRUCTURED_RESPONSE + zero allowed_files
→ allow

STRUCTURED_RESPONSE + more than 4 allowed_files
→ reject

STRUCTURED_RESPONSE + missing/oversized/invalid output_schema
→ reject
```

The action/request hash, lifecycle identity and persisted Task Contract must
change when result mode or schema changes.

## Required production scope

Determine the minimum physical diff from current code.

Expected production seams include:

```text
nexus/orchestrator/task_contract.py
nexus/executors/worker_contract.py
nexus/executors/worker_registry.py
nexus/orchestrator/self_hosted_task_service.py
nexus/orchestrator/unified_mcp_gateway.py
```

A small shared decoder module may be created only if required to avoid duplicate
parser authority.

Do not modify:

```text
CapabilityPlanner
Workforce Admission
model workforce policy
route selection
manager account-selection logic
agy-cli-manager installation
launchd configuration
CandidateVerifier repository gate semantics
```

CandidateVerifier may continue verifying the empty Target state. The conditional
result decision belongs in result-contract/attempt-resolution logic, not as a
weakening of CandidateVerifier.

## Required tests

### Backward compatibility

1. Existing implementation task with non-empty diff still passes.
2. Existing implementation task with empty diff still fails.
3. Existing zero-file implementation request still fails.
4. Default result mode remains `CANDIDATE_DIFF`.
5. Existing contract hashes remain deterministic.

### Structured response

6. Zero-file structured-response request is accepted.
7. One-file source-bound structured-response request is accepted.
8. Missing output schema fails closed.
9. Oversized or malformed schema fails closed.
10. Provider exit zero plus schema-valid result passes.
11. Provider exit zero plus schema-invalid result fails.
12. Missing decoded result fails.
13. Any repository diff in structured-response mode fails.
14. Target and controller unchanged are required.
15. Structured success creates no commit, candidate ref, merge or push.
16. Result mode and schema affect action/request/contract hashes.
17. Raw result, account identity and HOME are absent from sanitized receipts.
18. AGY envelope decoding uses the same behavior as Gateway model probe.
19. Account alias hash and isolated HOME hash are bound to the actual invocation.
20. CANDIDATE_DIFF behavior is unchanged.

### Lifecycle terminal behavior

21. Structured result receives a non-candidate terminal state.
22. Structured result cannot enter candidate approval/integration APIs.
23. Retry with a different result mode/schema under the same task ID fails
    contract identity checks.

## Mandatory verification

Use current repository test paths discovered from the actual diff. At minimum:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/nexus/executors/test_worker_contract.py \
  tests/nexus/orchestrator/test_self_hosted_task_service.py \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py \
  tests/services/test_agy_account_pool.py

PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q \
  nexus/orchestrator/task_contract.py \
  nexus/executors/worker_contract.py \
  nexus/executors/worker_registry.py \
  nexus/orchestrator/self_hosted_task_service.py \
  nexus/orchestrator/unified_mcp_gateway.py

git diff --check
```

Add any focused shared-decoder test if a module is extracted.

## Live smoke after implementation

The implementer may run one zero-file synthetic structured-response smoke using
the currently active AGY account, but this remains implementer-reported evidence.

Do not rotate accounts and do not start Card 05 in this task.

Expected schema:

```json
{
  "type": "object",
  "required": ["probe", "mutation_requested"],
  "properties": {
    "probe": {"const": "ok"},
    "mutation_requested": {"const": false}
  },
  "additionalProperties": false
}
```

## Pass conditions

* result mode is hash-bound;
* legacy candidate semantics remain unchanged;
* structured output is schema-validated;
* zero-file structured canary works;
* source-bound structured result works in focused tests;
* repository mutation fails closed;
* no Candidate/promotion is created for structured results;
* exact tests pass;
* one scoped implementation commit is created;
* no push.

## Claim ceiling

Allowed:

```text
NON_MUTATING_STRUCTURED_RESULT_RUNTIME_IMPLEMENTED
AGY_STRUCTURED_RESULT_CANARY_IMPLEMENTER_PASS
```

Not allowed:

```text
AGY_TWO_ACCOUNT_SWITCH_AND_DISPATCH_LIVE_PASS
AGY_CARD03_ACCEPTED
PRODUCTION_READY
PUBLIC_CLAIM_ALLOWED
```

Independent live acceptance remains required.

## Completion receipt

```yaml
verdict:
starting_head:
ending_head:
task_card_hash:
changed_paths:
result_contract:
  default_mode:
  new_mode:
  schema_hash_bound:
legacy_candidate_semantics_unchanged:
structured_result:
  zero_file_supported:
  source_bound_supported:
  schema_validation:
  repository_delta_forbidden:
  candidate_created: false
tests:
live_single_account_smoke:
commit:
  sha:
  pushed: false
remaining_blockers:
claim_ceiling:
NEXT_GATE: AGY_TWO_ACCOUNT_STRUCTURED_DISPATCH_LIVE_ACCEPTANCE
```
