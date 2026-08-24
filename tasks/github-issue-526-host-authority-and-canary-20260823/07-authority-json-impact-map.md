# TASK-526-G-AUTHORITY-JSON-IMPACT-MAP — Fail-closed CI coverage for the issuance artifact

    task_id: TASK-526-G-AUTHORITY-JSON-IMPACT-MAP
    issue: 526
    repository: James3014/Nexus-new
    status: ACTIVE
    auto_chain: false
    claim_mode: MANUAL_DISPATCH
    base_main: 526d45f0dcc8a38d31844466b6f848f01aa0bfe0
    base_tree: 601b15be1cdeb24b48d590bfdc0c4885ac558182
    work_branch: codex/issue-526-authority-json-impact-map
    owner_approval_expires_at: 2026-08-25T22:50:00Z
    claim_ceiling: CI_IMPACT_MAPPING_SOURCE_CANDIDATE_ONLY

## Problem and authority

PR #542 adds exactly the approved Issue #526 host-effect authority bundle, but
the exact artifact path is absent from the default PR impact map. The exact-base
gate therefore classifies the one-file bundle PR as `IMPACT_UNKNOWN` and blocks.

This Card authorizes one fail-closed CI mapping Candidate. It grants no bundle
issuance, host-effect, DevSpace, service, approval, merge, activation, release,
or production authority. The Owner approval remains limited to
`com.nexus.mcp.gateway.direct` and the three later operations
`install-artifact`, `reload`, and `rollback`; this source Candidate performs none
of them.

## Exact worker mutation scope

Modify only:

- docs/testing/test_impact_map.md
- tests/ops/test_select_tests.py
- tests/ops/test_pr_impact_gate.py

Create/delete none. The coordinator-authored Card and INDEX update are authority
setup, not worker implementation scope. Do not edit the bundle JSON, Gateway or
deployment source, DevSpace, service configuration, runtime/generated state, or
unrelated formatting.

## Required behavior

Add one exact-path active mapping for:

`tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json`

The mapping must:

- classify the exact path as high risk and Tier 2 / `HIGH_RISK_INTEGRATION`;
- select `tests/contracts/test_gateway_deployment_contract.py` and
  `tests/ops/test_mcp_gateway_durable.py` directly;
- preserve all mandatory Tier 2 policy-gate targets;
- produce no fallback or unmatched entry for the exact path;
- use an exact match only, never a directory or filename-prefix wildcard.

Adjacent or derivative paths such as
`03-host-effect-authority-receipt.json`, `.tmp`, or `.bak` must remain unmatched,
fall back to broader verification, and retain `IMPACT_UNKNOWN`. The exact mapping
must not shadow or authorize any sibling artifact.

## Acceptance and negative controls

- exact fixed bundle path selects both direct contract/operations targets;
- exact fixed bundle path escalates to Tier 2 and `HIGH_RISK_INTEGRATION`;
- exact fixed bundle path has no fallback/unmatched path;
- at least one same-directory adjacent JSON path remains unmatched,
  `IMPACT_UNKNOWN`, and broader fallback;
- mandatory Tier 2 targets remain selected;
- existing selector and PR impact-gate tests remain green;
- no existing test is renamed, skipped, xfailed, deselected, or weakened;
- physical diff is limited to the coordinator Card/INDEX plus the three worker
  files, with zero deletions.

## Verification

    uv run pytest -q tests/ops/test_select_tests.py tests/ops/test_pr_impact_gate.py
    uv run ruff check tests/ops/test_select_tests.py tests/ops/test_pr_impact_gate.py
    git diff --check
    git diff --name-status 526d45f0dcc8a38d31844466b6f848f01aa0bfe0...HEAD

Independent review must confirm the positive exact-path mapping, the adjacent
unknown negative control, the Tier 2 target set, zero bundle-byte changes, and
the claim ceiling before push or PR.

## Forbidden actions

- do not edit, regenerate, materialize, install, or validate the bundle through
  a host-effect seam;
- do not invoke plist, launchctl, Gateway, DevSpace, or another service;
- do not push, open/approve/merge a PR, or alter protected refs;
- do not self-approve or advance TASK-526-HOST-1;
- `AUTO_CHAIN=false`; stop after the committed Candidate report.

