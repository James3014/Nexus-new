---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-150-skill-descriptor-impact-map
campaign_id: github-issue-150-skill-descriptor-impact-map-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/150
baseline_main: 02d9ff25b1e5ac2dab12c8cb3d40a7a97416da6c
historical_baseline: 02d9ff25b1e5ac2dab12c8cb3d40a7a97416da6c
reconciled_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
current_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
block_class: NONE
completion_marker: SKILL_DESCRIPTOR_IMPACT_MAP_PROVEN
claim_ceiling: SKILL_DESCRIPTOR_ARTIFACT_CONTRACT_AND_IMPACT_MAP_ONLY
physical_receipt:
  pull_request: 160
  candidate_head: f5fa2a74aacb8481e1a40b7f1349e258ede73871
  merge_commit: c7e60f4c6798554e51cbc322ebfaf89e2c5cc346
  changed_files: 5
  focused_tests: 52
  required_checks: SUCCESS
  tier3: SKIPPED_EXPECTED
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

# Add Skill Descriptor Artifact Contract and Impact Mapping

## Objective

Validate the real repository `.agents/skills/**/SKILL.md` and optional
`agents/openai.yaml` artifacts fail-closed, then map the exact
`.agents/skills` prefix to conservative descriptor/catalog/schema/CI trust
tests.

## Dependencies and sequencing

- Exact GitHub main at dispatch:
  `9dddd018ad2761face3d2f3ce29dff8d8feae72d`.
- This mapping Candidate must physically merge before PR #138 rebases or
  normal-merges fresh main and reruns exact-base impact.
- No file from PR #138 belongs to this card.

## Allowed implementation files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_skill_file_contract.py` (new)
- `tests/ops/test_select_tests.py`

Maximum implementation/test files changed: 3. This card and its INDEX are
authorization artifacts outside that ceiling.

## Required behavior

- Scan the actual repository `.agents/skills/**/SKILL.md` inventory and any
  sibling `agents/openai.yaml` descriptors.
- Within each skill directory, admit the existing descriptor support layouts
  `references/`, `scripts/`, and `agents/`; any other unexpected layout fails
  closed.
- Require SKILL frontmatter delimiters and non-empty `name` and `description`;
  reject malformed YAML, invalid field types, and path/name mismatch.
- For `agents/openai.yaml`, require `interface.display_name`,
  `interface.short_description`, `interface.default_prompt`, and boolean
  `policy.allow_implicit_invocation`; metadata never grants runtime authority.
- Add exactly one active high-risk `.agents/skills` prefix row targeting:
  `tests/ops/test_skill_file_contract.py`,
  `tests/learning/test_skill_catalog.py`,
  `tests/learning/test_skill_schema.py`, and
  `tests/ops/test_ci_gate_report_trust_audit.py`, with reason
  `skill_artifact_contract_and_catalog_governance`.
- Add selector regression coverage for canonical `SKILL.md` and nested
  `agents/openai.yaml`; unrelated `.agents/**` paths remain fallback and
  visible in `unmatched_paths`.

## Verification

- RED fixtures: missing/malformed SKILL frontmatter, malformed descriptor,
  missing required interface/policy fields, invalid types, and name/path
  mismatch all fail closed.
- GREEN scan of the exact current repository inventory passes.
- Focused artifact and selector tests pass.
- Catalog/schema/CI trust target tests pass.
- Selector JSON for both descriptor path forms reports `fallback_used=false`,
  `unmatched_paths=[]`, high risk, the four declared targets, and the existing
  automatic high-risk `tests/services/test_policy_gate.py` escalation target.
- Ruff and compileall pass for changed Python tests.
- `git diff --check` and exact allowed-file/deletion audit pass.

## Forbidden scope

No PR #138 file, production/runtime/router/catalog implementation, workflow,
`scripts/ops/select_tests.py`, `scripts/ops/pr_impact_gate.py`, broad
`.agents/**` mapping, fallback/classifier suppression, dependency change,
approval, integration, merge, release, or production/public claim.

## Exit

PR #160 head `f5fa2a74aacb8481e1a40b7f1349e258ede73871` merged as
`c7e60f4c6798554e51cbc322ebfaf89e2c5cc346` with the exact five-file scope,
52 focused tests, required checks successful, and Tier3 skipped as expected.
The terminal claim remains limited to the skill-descriptor artifact contract
and impact mapping. No #138, runtime, catalog implementation, route,
Workforce, release, or production claim follows.

Prior readback binding `cdf2570ede5ae218f36f886b696c8da45458043a`
(2026-08-14) is retained as historical only.
