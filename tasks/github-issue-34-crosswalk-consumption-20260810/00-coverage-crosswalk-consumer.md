---
artifact_authority: current
owner: James Chen
status: READY
task_id: github-issue-34-crosswalk-consumption
campaign_id: github-issue-34-crosswalk-consumption-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/34
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Consume the OpenWiki Authority Crosswalk in Wiki Coverage

## Objective

Make the existing Wiki coverage audit consume the physically merged
`nexus.openwiki_wiki_crosswalk.v1` contract through one deterministic,
fail-closed alignment seam. Current source remains implementation truth and the
authority manifest remains governed-Wiki authority.

## Inputs and dependencies

- Issue #15 and PR #35 physically merged as
  `b6644968e56563095a3ac935f6236040aef6f1cf`.
- Issue #34 is Ready because its physical dependency is satisfied.
- Fresh overlap audit found no open pull requests.
- First-gate localization selected `scripts/ops/wiki_coverage_audit.py` as the
  sole canonical consumer; `wiki_drift_audit.py` remains out of scope.

## Allowed files

- `scripts/ops/wiki_coverage_audit.py`
- `tests/ops/test_wiki_coverage_policy.py`
- `tasks/github-issue-34-crosswalk-consumption-20260810/INDEX.md`
- `tasks/github-issue-34-crosswalk-consumption-20260810/00-coverage-crosswalk-consumer.md`

Maximum changed files: 4.

## Forbidden scope

- `scripts/ops/wiki_drift_audit.py`
- `scripts/ops/openwiki_authority_crosswalk.py`
- OpenWiki or governed-Wiki prose and authority-manifest mutation
- new top-level report family or parallel mapping/policy engine
- fuzzy matching, embeddings, filename similarity, or LLM authority selection
- Planner, workforce, lifecycle, runtime, release, or public-claim authority

## Required behavior

- Consume the existing compiler/public schema rather than reproducing its
  path-resolution logic.
- Validate the exact schema, `derived_non_authoritative` authority ceiling,
  deterministic input identity, record count, status counts, and records.
- Prefer regeneration from current committed OpenWiki and manifest inputs. If
  an external artifact is accepted, byte-compare it to canonical regenerated
  output; missing, malformed, stale, tampered, or schema-mismatched input fails
  closed.
- Expose `EXACT_PATH_MATCH`, `EXACT_PREFIX_MATCH`, `UNMAPPED`, and `AMBIGUOUS`
  outcomes in the existing coverage result without guessing.
- Any `AMBIGUOUS` record fails the alignment gate. `UNMAPPED` remains explicit
  and must fail when it belongs to the formal alignment scope; out-of-scope
  records may be reported without being promoted to mapped coverage.
- Preserve the existing coverage schema/consumer compatibility where possible;
  no second report authority.

## Verification

- `uv run pytest -q tests/ops/test_openwiki_authority_crosswalk.py tests/ops/test_openwiki_source_contract.py tests/ops/test_wiki_coverage_policy.py`
- `uv run ruff check scripts/ops/wiki_coverage_audit.py tests/ops/test_wiki_coverage_policy.py`
- `uv run ruff format --check scripts/ops/wiki_coverage_audit.py tests/ops/test_wiki_coverage_policy.py`
- `git diff --check`
- allowed-file, deletion, staged-diff, and card-hash audit

## Required evidence and exit criteria

- Positive current-input regeneration/consumption test.
- Deterministic mapped, `UNMAPPED`, and `AMBIGUOUS` tests.
- Missing/malformed/schema-mismatched/stale/tampered input fails closed when an
  external artifact path is supported.
- Existing formal coverage behavior remains covered and no drift tool changes.
- Exact tests, Ruff gates, and diff gate pass.
- Independent primary-agent and separate reviewer acceptance.

Maximum claim: the canonical Wiki coverage surface consumes and reports the
deterministic OpenWiki authority crosswalk. It does not make OpenWiki
authoritative and does not prove all documentation is complete.

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation or test defect.
- `HARD_BLOCK`: satisfying acceptance would require forbidden authority,
  manifest, drift, or second-framework changes.
