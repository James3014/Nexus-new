# ARCHIVED 2026-10-16 (dead-code batches B1 + B5)

Physical deletion of two batches of proven-unused `nexus/services` modules. Tracking issue: #2340.
Decision: Owner (James), 2026-10-16, chat 「好」: delete batches B1 and B5 of the dead-code proof via
the trusted deletion anchor, as #2197 did for the Rust `nexus_core` extension. This is a physical
deletion, not the "unreachable + manifest" variant of `ARCHIVED_2026-10-12.md` /
`ARCHIVED_2026-10-13*.md`. Originals are preserved on branch `archive/2026-10-16-deadcode-b1-b5`
(cut from `origin/main` f573a24eebfc98a2e24f4800e9e1d00a0116990e before this change).

Evidence: `~/Workspace/nexus-handoffs/2026-10-13-online-ab/DEADCODE_PROOF_20261016.md`
(§2 batches B1/B5, §5 method and re-run commands, §6 per-module appendix; scripts in
`deadcode_proof_scripts/`). Verdict for every module below: **PROVEN-UNUSED**, i.e. zero non-test
references by static AST imports (function-level and relative included), dotted/slash path text,
string/registry tables, `import_module`/`__import__`/`_try_import_class` literals, `scripts/ops`,
`scripts/*`, workflows, pyproject/Taskfile and the launchd plists on both Macs; references only
from other modules in the same batch or from tests. The `rg` commands of §5 were re-run on
f573a24ee before deleting; the only reference the report did not list was a test-only allowlist
entry (below).

## B1: `local_assist_*` canaries/gates (8 modules, 1,076 lines)

| path | lines |
|---|---:|
| `nexus/services/local_assist_advisor_canary.py` | 136 |
| `nexus/services/local_assist_bounded_dispatch.py` | 136 |
| `nexus/services/local_assist_candidate_canary.py` | 145 |
| `nexus/services/local_assist_contribution.py` | 75 |
| `nexus/services/local_assist_default_policy.py` | 80 |
| `nexus/services/local_assist_preflight.py` | 256 |
| `nexus/services/local_assist_value_matrix.py` | 124 |
| `nexus/services/local_assist_verified_canary.py` | 124 |

Inside the batch: `local_assist_bounded_dispatch` imports the advisor, candidate and verified
canaries; `local_assist_default_policy` imports `local_assist_value_matrix`. No module outside the
batch imports any of them. The live `local_assist_*` modules (`local_assist_service`, `_closeout`,
`_final_gate`, `_health`, `_live_proof`, `_live_smoke`, `_universal_interface`, `_user_relay`) are
untouched; `local_assist_closeout` only shares the field-name prefix `local_assist_contribution_claim`.

Tests deleted with the batch (they import only B1 modules; 902 lines):
`tests/services/test_local_assist_advisor_canary.py` (202),
`tests/services/test_local_assist_bounded_dispatch.py` (177),
`tests/services/test_local_assist_candidate_canary.py` (157),
`tests/services/test_local_assist_contribution.py` (78),
`tests/services/test_local_assist_default_policy.py` (61),
`tests/services/test_local_assist_value_matrix.py` (90),
`tests/services/test_local_assist_verified_canary.py` (137).

Test edited: `tests/integration/test_legacy_path_blocked.py` drops the
`NON_MODEL_JSON_PARSE_ALLOWLIST` entry for `nexus/services/local_assist_advisor_canary.py`
(`run_advisor_canary`); the test fails on stale entries. No test function was removed or renamed.

## B5: `reach.resolvers` (2 files, 50 lines)

| path | lines |
|---|---:|
| `nexus/services/reach/resolvers/__init__.py` | 0 |
| `nexus/services/reach/resolvers/yt_dlp.py` | 50 |

`yt_dlp.fetch_transcript` returned hard-coded mock data. The live `nexus/services/reach/ucc_router.py`
has its own `_yt_dlp` method and never imported the package. No tests.

## Guard

`tests/services/test_archived_deadcode_b1_b5_2026_10_16.py` asserts that each path is absent, each
dotted module is not importable, and no file under `nexus/` imports or names one (AST import graph
with relative imports resolved, plus a text scan). Re-adding one of these modules has to edit that
test.

Historical mentions left as is: `docs/reports/runtime_contract_stabilization_baseline_20260714.md`,
`docs/reports/local_assist_campaign_20260714T0532Z/m1_preflight.json`,
`perf_regression_pack_v22.5/SWARM_STATUS_AUDIT_3.705.0.md`, `nexus_wiki_vault/90_Sources/`.
