---
artifact_authority: current
owner: James Chen
status: active
purpose: Provide a lock-bound offline Python test runtime to the unprivileged executor.
---

# Task Card: Issue #104 offline executor runtime artifact

- task_id: `github-issue-104-offline-runtime-artifact-20260811`
- issue: `#104`
- owner_contract: `APPROVE_CONTRACT_DELTA:#104_OFFLINE_RUNTIME_ARTIFACT_V1`
- base_sha: `d81644e740889adc304d2243d41697a91e08a60c`
- target: `/private/tmp/nexus-issue104-offline-runtime-artifact`
- branch: `codex/issue-104-offline-runtime-artifact`
- execution_authority: `GOVERNED_CANDIDATE_REPAIR`
- worker_role: primary implementation plus independent Luna hostile review
- AUTO_CHAIN: false

## Objective and exact failure

Repair protected run `31468890356`, whose trusted controller passed and whose
unprivileged executor reached extracted source execution before failing with
`/usr/bin/python: No module named pytest`. This is an
`EXECUTOR_ENVIRONMENT_BOOTSTRAP_FAILURE`, not a PR #118/#75 semantic failure.

The trusted controller must produce a default-branch lock-bound Python runtime
artifact. The executor must consume that artifact without dependency network
resolution, token, checkout, secrets, credentials, cache authority, or wider
permissions. The trusted verifier must recompute every new identity before
PASS.

## Contract design

- Trusted controller network acquisition is allowed only to materialize the
  runtime from the exact trusted default-branch `pyproject.toml` and `uv.lock`.
- Bind `pyproject.toml` SHA-256, `uv.lock` SHA-256, exported requirements
  SHA-256, runtime archive SHA-256, Python implementation/version/cache tag,
  ABI/platform/machine, and build tool identity into the manifest.
- Export the lock's default and dev groups only; do not include optional extras.
  The protected test inventory remains the existing two allowlisted #75 tests.
- The executor performs no package/index resolution. It extracts the
  controller artifact with `tarfile.data_filter`, validates runtime metadata
  against its own interpreter, prepends the bound site-packages directory to
  `PYTHONPATH`, and runs only manifest-selected tests.
- The verifier recomputes source/runtime/archive/lock/workflow/run/base/head,
  tree, test-inventory, evidence and metadata identities. Missing, modified,
  incompatible, stale or replayed runtime material remains `IMPACT_UNKNOWN`.
- This does not claim network egress isolation for untrusted tests. GitHub
  permissions are not a network sandbox.

## Allowed files

Maximum five repository files:

1. `.github/workflows/trusted-deletion-anchor.yml`
2. `scripts/ops/trusted_deletion_anchor.py`
3. `tests/ops/test_trusted_deletion_anchor.py`
4. `tasks/github-issue-104-offline-runtime-artifact-20260811/INDEX.md`
5. `tasks/github-issue-104-offline-runtime-artifact-20260811/01-offline-runtime-artifact.md`

## Forbidden scope

- PR #118 implementation files or #75 evidence semantics.
- `pyproject.toml`, `uv.lock`, other workflows/tests/source, dependency or
  lockfile regeneration.
- Executor permissions, checkout, GitHub token, secrets, persisted
  credentials, cache-derived authority, or PR-head trusted acquisition.
- Route, workforce, lifecycle, Candidate acceptance, approval, integration,
  ruleset/protected-check, cleanup, release or production authority.
- #105/#106/#113/#138 implementation or rebind.

## Required RED/GREEN/tamper evidence

- RED: an isolated Python 3.12 runtime without pytest, non-Git cwd and extracted
  source reproduces `No module named pytest`; omission of the runtime artifact
  cannot produce COMPLETE evidence.
- GREEN: a valid lock/runtime-bound artifact allows the isolated executor to
  run only the selected tests and emit COMPLETE evidence.
- TAMPER: reject missing/modified runtime archive, runtime metadata or exported
  requirements; trusted lock/project digest drift; ABI/platform mismatch;
  cross-run replay; source/test inventory/base/head/workflow substitution.
- Preserve archive traversal/device fail-closed behavior, token isolation,
  cleanup, controller/executor/verifier separation, exact Git identities and
  the `EXACT_GIT_EVIDENCE_ONLY` ceiling.
- Bounded sibling sweep covers only Python executable, pytest/uv/PATH/virtualenv
  assumptions and other protected executor jobs. No CI-wide refactor.

## Exact verification

```bash
uv run pytest -q tests/ops/test_trusted_deletion_anchor.py
uv run ruff check scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
uv run ruff format --check --preview scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
uv run python -m compileall -q scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/trusted-deletion-anchor.yml'))"
git diff --check
git diff --name-status d81644e740889adc304d2243d41697a91e08a60c...HEAD
```

Before commit, inspect complete staged diff, tracked/unstaged deletion status and
the exact five-file ceiling. After commit, bind Candidate evidence to the Task
Card SHA-256 and exact commit SHA. Independent Luna review must report no P0/P1
or authority leakage before push/PR.

## Exit, claim ceiling and block classes

- Exit: scoped commit, all required local evidence PASS, independent hostile
  review ACCEPT, normal exact-base PR gates terminal PASS, then ordinary
  exact-head merge only under existing Owner merge authorization.
- Maximum pre-live claim: `OFFLINE_RUNTIME_ARTIFACT_REPAIR_CANDIDATE`.
- #104/#75 remain open until the repair is physically merged, PR #118 is
  re-bound to new main, and a fresh protected controller/executor/verifier run
  proves all three jobs terminal PASS.
- `RECOVERABLE_BLOCK`: bounded implementation/test defect or transient CI.
- `HARD_BLOCK`: permission/token/cache expansion, lock mutation, untrusted
  runtime authority, missing exact identity, or need to widen allowed files.
