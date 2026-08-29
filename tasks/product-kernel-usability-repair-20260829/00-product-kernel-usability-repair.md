# Task Card: PRODUCT-KERNEL-USABILITY-REPAIR-01

Status: `ACTIVE`

Goal: produce an acceptance-quality Candidate that adds provider-neutral trusted evidence ingestion, prerequisite provenance validation, runtime/source freshness classification, and safe Legacy normalization without changing the existing factual or certification reducers.

## Authority and claim ceiling

- Binding Owner handoff SHA-256: `618bfad0b7a27d5e4ff580cb5c314faa6d7540f019d459820c4d49195f998299`.
- Repository: `James3014/Nexus-new`.
- Base commit/tree: `c00c299152599a87efd831c3e146ecadd8f8b21f` / `d7cf79efc3ef86eaa084f597aad420dd36e13172`.
- Branch: `codex/product-kernel-usability-repair`.
- Authority ends at scoped implementation, commits, exact Candidate verification, and acceptance evidence.
- No push, PR mutation, merge, release, production, enforcement, Cloud, commercial, or public-protocol-stability authority.
- `AUTO_CHAIN=false`.

## Immutable inputs

- Baseline manifest: `/private/tmp/nexus-product-kernel-usability.LR9utT/baseline-manifest.json`, SHA-256 `13ce91331682fccd8238101c121986df3f9c3896bb4d7740ac26b7e381e4d4a7`.
- Baseline result: `b7a053cb7d9ea7e7f24434d44166edda5cc3f5e0f860737c0b967ca3d658f4f6`.
- Baseline ledger: `071b59524fe6defc0e6cc00714f08b3ec7e399e788dc036cff498ec523c347ed`.
- Baseline reproducibility receipt: `099f96ce516832b85efeaf610a9bc3344755aa4b20091bf808eae8286b6ef88f`.
- Same 20 opaque cases, sealed case key, ground truth, denominators, and cutoffs must remain unchanged.

## Safety invariants

1. `FAILED_VERIFICATION` and `UNVERIFIABLE` never become `VERIFIED` through ingestion.
2. Missing, stale, spoofed, substituted, downgraded, duplicate, or ambiguous provenance produces no trusted bundle/prerequisite.
3. Missing authority, approval, policy, or signing provenance never becomes `CERTIFIED`.
4. Caller assertions and Legacy narrative `PASS` never mint provenance.
5. Existing `product.verification.verify` and `product.certification.certify_result` remain the sole factual and certification reducers.
6. New trusted output wraps and binds the existing core receipt; it does not create merge authority or a second disposition.
7. Historical outcomes/ground truth remain unchanged; usability improvement is measured separately from outcome truth.

## Allowed repository paths

- `tasks/product-kernel-usability-repair-20260829/INDEX.md`
- `tasks/product-kernel-usability-repair-20260829/00-product-kernel-usability-repair.md`
- `docs/superpowers/plans/2026-08-29-product-kernel-usability-repair.md`
- `docs/testing/test_impact_map.md`
- `product/protocol/__init__.py`
- `product/evidence/ingestion.py`
- `product/adapters/trusted.py`
- `product/adapters/legacy.py`
- `tests/product/test_trusted_evidence_ingestion.py`
- `tests/product/test_trusted_certification_adapter.py`
- `tests/product/test_legacy_evidence_adapter.py`
- `tests/product/test_kernel.py`

Maximum changed paths: `12`.

## Forbidden scope

- `product/verification/**`
- `product/certification/**`
- existing receipt or reducer semantics
- `product/kernel/**`
- `product/adapters/github.py`
- `product/adapters/changeset_certification_v2.py`
- baseline/corpus/ground-truth rewrites
- provider SDK, network, filesystem fetch, subprocess, key management, or secret storage
- current-case hardcoding
- branch push, PR, merge, release, production/runtime activation

## Required implementation

1. Provider-neutral exact provenance and trust profile types.
2. Raw artifact content-hash recomputation and exact subject/change/tree/diff binding.
3. Producer/execution/environment identity validation against a separately supplied trust profile.
4. Runtime/source observation generation and freshness classification without treating liveness as readiness.
5. Provenance-capable policy/authority/approval/signing validation with exact action, subject, validity, revocation, payload, and signed-payload binding.
6. Trusted normalization into the existing `EvidenceBundle`; admission failure emits no trusted bundle.
7. Trusted certification adapter that derives internal booleans only from validated prerequisites and wraps the existing core result/receipt.
8. Legacy adapter that preserves structured facts but maps narrative PASS/FAIL to `LEGACY_NON_CERTIFIABLE`.
9. Ingestion receipt records machine-verified artifacts and remaining human-open reasons.
10. H1-H12 fail-closed controls plus positive/determinism/architecture controls.

## Quantitative usability gate

- Exact 20-case core outcomes and denominators must remain byte-for-byte semantically identical.
- `artifacts_human_must_open_after <= 12` and at least `8/20` artifacts must be machine-verified through the trusted seam.
- `manual_followups_after` must not exceed baseline `234`.
- A result of `20/20` human opens fails the usability gate even if safety metrics remain green.
- Each case records `artifacts_available`, `artifacts_machine_verified`, `artifacts_human_must_open`, and `reason_human_open_required`; missing artifacts are never counted as machine verified.

## Verification

- RED evidence for each new behavior before production implementation.
- `python -m pytest -q tests/product/test_trusted_evidence_ingestion.py`
- `python -m pytest -q tests/product/test_trusted_certification_adapter.py`
- `python -m pytest -q tests/product/test_legacy_evidence_adapter.py`
- `python -m pytest -q tests/product tests/contracts/test_changeset_certification.py tests/ops/test_select_tests.py tests/ops/test_trusted_deletion_anchor.py`
- exact 20-case BEFORE/AFTER replay with unchanged input/ground-truth hashes.
- 3–5 recent read-only controls after the exact corpus comparison.
- Ruff check/format, Pyright Product, compile/import, offline package build, `git diff --check`.
- complete changed/deleted path audit and exact-base classification of unrelated failures.
- independent spec, code-quality, hostile/security, and metric-denominator reviews.

## Exit criteria

- High-risk false certification, replay nondeterminism, and evidence-binding failures remain zero.
- Exact 20 historical outcomes remain semantically unchanged.
- Avoidable review/follow-up and artifact-open burden is reduced only where provenance is machine-verifiable.
- Genuine historical absence remains `UNVERIFIABLE`.
- No hidden legacy fallback or parallel certification authority exists.
- Artifact human opens fall from `20` to at most `12` under the frozen per-case accounting contract.
- Exact Candidate commit/tree/diff and independent acceptance are recorded.
- Terminal is either `PRODUCT_KERNEL_USABILITY_REPAIR_VALIDATED` or, if merge authority remains absent, Candidate truth with `READY_FOR_OWNER_INTEGRATION` only after the full campaign is complete.
