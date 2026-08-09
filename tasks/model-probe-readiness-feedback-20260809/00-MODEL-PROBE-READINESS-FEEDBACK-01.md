# Task Card: MODEL-PROBE-READINESS-FEEDBACK-01

artifact_authority: current
task_id: `MODEL-PROBE-READINESS-FEEDBACK-01`
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

Rebuild the useful parts of review commit
`eff7697055b743fae857be0dd0f46fb65d1128e6` on fresh canonical source without
merging that stale-base commit:

1. `VERSION_VERIFIED` alone must never authorize worker execution.
2. A successful isolated `nexus_model_probe` must produce bounded durable
   evidence bound to the exact provider, requested/resolved model, executable
   path and SHA-256, CLI version, command, output schema/result, action/attempt,
   completion time, and expiry.
3. A later `_provider_preflight` must validate and consume that exact evidence,
   surface `readiness_status=MODEL_VERIFIED` and `execution_ready=true`, and
   allow the same exact worker through `nexus_worker_candidate`.
4. Missing, stale, malformed, failed, incomplete, replayed, or identity-drifted
   evidence must fail closed before `SelfHostedTaskService.submit_task`.
5. Compact `get_task_snapshot` and `wait_task` responses for terminal worker
   failures must derive a bounded blocker from persisted canonical state when
   `state.blocker` is absent, while preserving an existing blocker unchanged.

## Baseline and references

- Canonical root: `/Users/jameschen/Workspace/nexus`
- Canonical branch: `nexus/integration/main`
- Exact implementation base: `a19d5357cddc0add21e7b8c11c6de21fd0af98d7`
- Review-only source: `eff7697055b743fae857be0dd0f46fb65d1128e6`
- The implementation must be made in this clean external worktree and must not
  copy whole files from the stale Candidate.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

No other source, test, policy, configuration, task, report, or generated file
may enter the implementation commit.

## Required design constraints

- Reuse `assisted_provider_jobs` and the existing provider registry/resolver.
  A small atomic probe-evidence receipt/index beneath the existing service
  state root is permitted; no second durable task system is permitted.
- The readiness receipt must have a canonical SHA-256 over all trust fields and
  a finite TTL. Preflight must re-resolve and re-hash the current executable and
  re-read CLI version before accepting it.
- A successful remote model invocation may establish authentication and model
  reachability only for the exact provider/model/binary/version identity in the
  receipt. Local-only providers must not invent a remote-auth requirement.
- A completed job is not evidence unless exit code is zero, durable exit marker
  exists, parsed result and bounded schema validation pass, stream artifact
  digests exist, isolated workspace cleanup succeeds, and filesystem delta is
  empty.
- Same task id plus identical probe semantics is idempotent and does not launch
  a second provider process. Same task id with changed provider/model/prompt/
  schema fails closed.
- Codex isolated model probes use `--ephemeral`, `--skip-git-repo-check`, and an
  explicit `--sandbox read-only`; remove deprecated `--full-auto` from this
  probe/advisor command path.
- `nexus_worker_candidate` must call the existing preflight and then a narrow
  execution-readiness gate. It must not create its own provider selector or
  route decision.
- FINAL_BLOCK projection remains derived presentation logic. It may expose only
  bounded normalized error text plus already persisted provider/model/exit/
  outcome fields; it must not rewrite durable state or reveal raw stderr.

## RED -> GREEN acceptance matrix

1. Initial exact preflight with no evidence returns
   `MODEL_PROBE_REQUIRED`, `execution_ready=false`, and service submit count 0.
2. Exact isolated probe completes with a schema-valid result and writes one
   hash-bound unexpired readiness receipt.
3. Repeated exact preflight validates that receipt and returns
   `readiness_status=MODEL_VERIFIED`, `execution_ready=true`,
   `model_reachable=true`, and `requested_model_verified=true`.
4. Exact `nexus_worker_candidate` then reaches the existing bounded submit seam
   once; it does not approve, integrate, push, reload, or mutate canonical.
5. Provider, requested/resolved model, binary path/hash, CLI version, command,
   action/attempt, result/schema hash, expiry, filesystem delta, process cleanup,
   or receipt-hash tamper fails closed and submit count remains 0.
6. Failed, cancelled, running, lost-process, malformed-output, or expired probes
   never become execution-ready.
7. Identical task replay launches no second provider; semantic collision fails
   with a typed conflict.
8. Codex command construction contains the isolated trust/sandbox flags and no
   deprecated `--full-auto`.
9. FINAL_BLOCK compact status and wait surfaces expose bounded derived failure
   evidence, preserve explicit blockers, and fabricate nothing without a
   persisted error.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python \
  -m py_compile \
  nexus/orchestrator/unified_mcp_gateway.py \
  nexus/orchestrator/self_hosted_task_service.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
git merge-base --is-ancestor a19d5357cddc0add21e7b8c11c6de21fd0af98d7 HEAD
```

## Required evidence

- Exact commit, parent, tree, Task Card SHA-256, and changed paths.
- Exact test argv, exit code, count, and stdout/stderr SHA-256.
- Receipt identity and positive four-step regression evidence.
- Negative-control matrix with zero submit/provider-relaunch assertions.
- `git diff --check`, deletion audit, staged/unstaged scope, and clean worktree.

## Forbidden scope

- No merge of `eff769705...`; no mutation of its managed worktree.
- No direct canonical mutation, approval, integration, reload, push, cleanup, or
  lifecycle JSON edit by the worker.
- No durable launcher, plist, expected-HEAD, OAuth client, auth token, OpenWiki,
  LocalHeal, model roster, workforce policy, CapabilityPlanner,
  HybridRouteDecision, provider onboarding, P1 closure, P2 cost telemetry, or
  P4 legacy-seam changes.
- No new public MCP tool, raw shell surface, router, planner, registry, fallback,
  direct-apply path, or production/public readiness claim.

## Exit criteria

One scoped Candidate commit on this authority parent, all exact tests and
negative controls green, no deletion or out-of-scope diff, and independent
primary review. The worker stops before approval, integration, Gateway reload,
live provider invocation, cleanup, push, or successor auto-promotion.

## Block classification

- `RECOVERABLE_BLOCK`: sandbox prevents provider-independent verification while
  source/unit evidence remains intact.
- `HARD_BLOCK`: exact identity evidence cannot be validated without weakening
  the gate, scope must expand into route/lifecycle/workforce/OAuth authority, or
  preserving compatibility requires accepting `VERSION_VERIFIED` as execution
  readiness.
