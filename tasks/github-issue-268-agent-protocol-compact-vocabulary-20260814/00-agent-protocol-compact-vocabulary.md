---
task_id: github-issue-268-agent-protocol-compact-vocabulary
issue: 268
repository: James3014/Nexus-new
status: READY
baseline_revision: eb668fb76f0c30d8f025db42cdb8e320d556c037
execution_lane: ISOLATED_TARGET
claim_intent: MANUAL_DISPATCH
claim_enforcement_state: PROJECTION_ONLY
AUTO_CHAIN: false
max_files: 4
allowed_files:
  - scripts/ops/agent_protocol_contract.json
  - tests/ops/test_agent_protocol_check.py
  - tasks/github-issue-268-agent-protocol-compact-vocabulary-20260814/INDEX.md
  - tasks/github-issue-268-agent-protocol-compact-vocabulary-20260814/00-agent-protocol-compact-vocabulary.md
authorized_deletions: []
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
claim_ceiling: AGENT_PROTOCOL_COMPACT_VOCABULARY_ACCEPTANCE_CANDIDATE_ONLY
---

# Objective

Update the agent-protocol contract and focused test to accept the compact
`Direct authority` and `Governed authority` vocabulary already present in the
current root `AGENTS.md`.

Only replace the two historical required strings in:

- `scripts/ops/agent_protocol_contract.json`
- `tests/ops/test_agent_protocol_check.py`

# Required behavior

The pre-change focused suite is RED with 27 passes and one failure at
`test_repository_contract_accepts_current_compact_agents`. The post-change
suite must be 28/28 green.

All five dispositions, required identity bindings, missing-file behavior,
forbidden paths, maximum-file ceiling, and strict-boundary checks remain
unchanged and fail closed. No vocabulary alias beyond the two exact compact
phrases is added.

# Forbidden

- Do not edit `AGENTS.md`.
- Do not reopen or rewrite Issue #122 or Issue #128.
- Do not change dispositions, identity bindings, boundary semantics, or any
  other required term.
- No provider, runtime, route, Workforce, lifecycle, approval, integration,
  merge, release, or production claim.

# Verification

```text
python3 -m pytest -q tests/ops/test_agent_protocol_check.py
python3 -m compileall -q scripts/ops/agent_protocol_check.py tests/ops/test_agent_protocol_check.py
git diff --check
```

Exit at a Candidate PR. Independent hostile acceptance and protected merge
authority remain separate.
