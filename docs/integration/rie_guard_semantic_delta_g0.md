# RIE guard semantic delta: G0 guard-family inventory (Issue #1580)

Exact next gate: `RIE_GUARD_DELTA_G0_GUARD_FAMILY_INVENTORY_FREEZE`.
Source fence: Nexus-new `36c802ec8c0d0a675ef9af8213c3fd17fcc59ed9`;
RIE pin `88285acf570688befbc8e36eb73f46987171bd4e`.
Claim ceiling: `RIE_GUARD_SEMANTIC_DELTA_PR_REVIEW_ADVISORY_ONLY`.

This inventory is advisory. It selects what the adapter may normalize; it grants
no policy, merge, acceptance or runtime authority. Nexus does not classify
TIGHTENS/LOOSENS; RIE `guard-delta` does.

## Normalization rule

A family is SUPPORTED only if every field sent to RIE is read by deterministic
extraction from an exact `git show <sha>:<path>` blob (AST literal evaluation or
byte hashing), with unambiguous tighten/loosen polarity. Anything that would need
prose scraping, regex-guessing of rules, or an invented polarity is
UNSUPPORTED and stays UNKNOWN (no adapter, no report).

## Inventory

| Family | Source path(s) | Stable rule IDs | Impl digest source | Self-test digest source | Known-file corpus | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Canonical-owner boundary table | `scripts/ops/canonical_owner_guard.py` | Owner keys of the literal `CANONICAL_OWNERS` dict (`owner:<name>`) | sha256 of the blob | sha256 of `tests/ops/test_canonical_owner_guard.py` blob | the two paths above (the guard has no declarative trigger globs) | SUPPORTED (implemented) |
| Trusted merge lane gate constant sets | `scripts/ops/trusted_merge_lane_gate.py` (`ALL_LANES`, `DIRECT_LANES`, `CONTRACT_KINDS`, `VALID_ON_MERGE_ACTIONS`, `SUPPORTED_MERGE_METHODS`) | set members are literal | blob sha256 | `tests/ops/test_trusted_merge_lane_gate.py` | same pair | NORMALIZABLE, NOT IMPLEMENTED: these are allow-sets, so adding a member loosens; RIE sets treat "added" as tightening, so a polarity inversion convention must be agreed with RIE first. Until then UNSUPPORTED/UNKNOWN. |
| Mutation admission constants | `nexus/orchestrator/mutation_admission.py` (`_ALLOWED_LANES`, `_ALLOWED_AUTHORITY`, `CANONICAL_REPOSITORIES`, `_RECEIPT_FIELDS`) | literal members | blob sha256 | none dedicated and located | n/a | UNSUPPORTED for now: allow-sets (same polarity gap) and no single self-test file bound to the module. |
| Repository contract gate | `nexus/orchestrator/repository_contract_gate.py` | none: path/branch token tuples are heuristics embedded in class attributes and logic | blob sha256 | none bound | n/a | UNSUPPORTED: token tuples are classifier heuristics; mapping them to rules would be semantic invention. |
| Lifecycle guards | `nexus/orchestrator/lifecycle_guards.py` | none: checks are imperative function bodies (`pre_action_guard`, `validate_*`) | blob sha256 | none bound | n/a | UNSUPPORTED/UNKNOWN. |
| Evidence guard | `nexus/governance/evidence_guard.py` | none | blob sha256 | none bound | n/a | UNSUPPORTED/UNKNOWN: single imperative method plus an emoji status string. |
| Hallucination guard | `nexus/governance/hallucination_guard.py` | none stable: schema/metric weights loaded at runtime | blob sha256 | none bound | n/a | UNSUPPORTED/UNKNOWN: scoring heuristics, not enforcement bindings. |

## Chosen family: `canonical_owner_table`

Why it is genuinely normalizable:

- `CANONICAL_OWNERS` is a module-level literal dict; `ast.literal_eval` extracts
  it with no execution and no inference.
- Its keys are stable, human-named rule IDs.
- `forbidden_import_stems` and `forwarding_modules` are enforced by named
  functions (`_check_forbidden_tree_imports`, `_check_forwarding_module`), so
  each entry is a real enforcement binding with unambiguous polarity
  (adding one only adds a check, removing one only removes a check).
- A dedicated self-test (`tests/ops/test_canonical_owner_guard.py`) exists and
  can be byte-hashed independently of the implementation.
- The module docstring is the wording digest source.

Field mapping sent to RIE `guard-delta`:

| RIE field | Source |
| --- | --- |
| `rules` | `owner:<key>` per table key |
| `enforcement_bindings` | `forbidden_import_stem:<owner>:<stem>`, `forwarding_module:<owner>:<path>` |
| `lifecycle_phases`, `trigger_patterns`, `fail_fixtures` | empty: the guard declares none (not invented) |
| `implementation_sha256` | sha256 of the exact guard blob at base / head |
| `self_test_sha256` | sha256 of the exact self-test blob at base / head |
| `wording_sha256` | sha256 of the module docstring |
| `known_files` | guard path and self-test path |
| `behavioral_witnesses` | opt-in (`--run-behavioral-probes`): fixed probe fixtures run against the base and head guard blobs, `DENY` when `audit_repository_ownership` returns FAIL |

Deliberately NOT mapped (exception or allow lists whose growth loosens, so their
changes surface as UNKNOWN through the implementation digest unless a behavioral
witness exists): `allowed_retained_paths`, `canonical_package`,
`forwarding_reference_roots`, `forbidden_new_in_tree_modules` (declared but not
read by any check), and the hard-coded `frozen_prefixes` inside
`audit_repository_ownership` (covered only by the `frozen_path_modification`
probe).

Behavioral probes: `forbidden_import_in_nexus_tree`, `frozen_path_modification`,
`facade_without_canonical_reference`, `facade_duplicate_canonical_class`, plus a
`control_clean_fixture` that must be ALLOW on both sides or probes are dropped
with a collection error. Probes execute the base/head guard source in an
isolated subprocess, so they are opt-in and must only be enabled where running
PR-head Python is acceptable.

## Consequences for classification

Because the guard is a single file, any real change alters the implementation
digest. Without an independent behavioral witness RIE answers UNKNOWN
(`IMPLEMENTATION_CHANGED_BEHAVIOR_UNPROVEN` or
`IMPLEMENTATION_AND_SELF_TEST_CHANGED_TOGETHER`). That is intentional and is
rendered as explicit uncertainty, never as a direction.

## Boundaries

- RIE is invoked only as a subprocess from `NEXUS_RIE_ENGINE_ROOT` /
  `NEXUS_RIE_PYTHON_BIN` after `git rev-parse HEAD` equals the pinned revision
  and the checkout is clean (`scripts/ops/canonical_owner_guard.py` forbids
  importing `repository_intelligence` under `nexus/`).
- Output is a JSON artifact and step-summary markdown only. No required check,
  Planner capability, model selection, reviewer daemon, or Candidate state.
- Not in this change (follow-up): live PR run evidence and independent
  reviewer confirmation.

## Workflow wiring

`.github/workflows/repository-intelligence.yml` job `guard-delta` runs on every
PR as an advisory, non-required job (`permissions: contents read,
pull-requests read`, `timeout-minutes: 10`, every step `continue-on-error`).

- Checks out Nexus-new with `fetch-depth: 0` and the RIE engine at the pinned
  revision into `.rie-engine` (git-ignored); the engine is configured only if
  `git -C .rie-engine rev-parse HEAD` equals the pin, otherwise the script fails
  closed to `ADVISORY_INCOMPLETE` (exit 0).
- Calls `scripts/ops/rie_guard_delta_evidence.py` with the PR base/head SHAs,
  repository and PR number. Behavioral probes are NOT run in CI
  (`--run-behavioral-probes` is never passed), so PR-head Python is never
  executed; behavioral-witness-dependent changes therefore render as UNKNOWN.
- Uploads `repository-intelligence-guard-delta-pr-<number>-<head sha>`
  (JSON, 30-day retention).
- The step summary shows the classification and reviewer-attention level,
  reason codes, tightening/loosening witness refs, evidence gaps, the report
  content hash, exact old/new identity and the claim ceiling
  `RIE_GUARD_SEMANTIC_DELTA_PR_REVIEW_ADVISORY_ONLY`. Missing or incomplete
  evidence is rendered as incomplete, never as UNCHANGED.
- The job is not a required check and owns no policy, Candidate, or merge
  authority.

## Sticky comment surface (#1580 G2 reviewer projection)

The RIE sticky PR comment (`.github/workflows/repository-intelligence-comment.yml`,
`pull_request_target`) now shows the guard semantic delta, because the sticky
comment is the one surface reviewers actually read.

- A data-only, `continue-on-error` step runs `scripts/ops/rie_guard_delta_evidence.py`
  from the default-branch checkout (full history, `git fetch --no-tags origin
  <base> <head>`) with the RIE engine pinned at `88285acf570688befbc8e36eb73f46987171bd4e`
  in `.rie-guard-engine`, and writes `$RUNNER_TEMP/rie-guard-delta.json`.
- `scripts/ops/rie_pr_comment.py --guard-delta-json PATH` loads that file, checks
  schema, claim ceiling, the `content_sha256` seal and that `new_identity`
  matches this PR number and head SHA, and renders one line. TIGHTENS, LOOSENS,
  MIXED and UNKNOWN are flagged lines (so "nothing to flag" is not shown);
  UNCHANGED is a `Note:`; anything missing, incomplete, tampered or mismatched
  is a `Note:` "not observed (reason)" and is never shown as UNCHANGED. Without
  the flag the comment renders exactly as before.
- Trust argument: all executed code is default-branch code or the pinned engine;
  base and head guard sources are read as git blobs (data) and never imported or
  run; the behavioral probes are never enabled here (they would execute PR-head
  Python with a write token); the output is advisory only, not a required check,
  merge gate, policy decision or Candidate acceptance. The `pull_request`
  artifact job in `repository-intelligence.yml` is unchanged.
