# NEXUS_SUPERVISED_BARE_FIRST_P61_FLASH_3TASK_2026-05-13

## Target

Make Gemini 3 Flash wearing Nexus keep verified delivery and trust safety while reducing unnecessary R/hyper wall cost. This slice specifically checks whether `context_sync_capped` and hidden-lite supervised bare-first routes avoid full Hyper and whether token accounting remains public-safe.

## Changes

- `context_sync_capped` now treats `codeintel` and `memory` as preflight-supervisable expected capabilities, so their expected-capability contract no longer disables supervised bare-first.
- `feature:public-docs-code-sync-hard-neutral-context-capped` now explicitly allows medium-risk supervised bare-first.
- Direct Gemini CLI stats outliers are no longer accepted as provider-measured token telemetry. Cumulative-looking `stats` totals are converted to `estimated_from_stats_outlier` and fail cost-safety instead of masquerading as single-call measured tokens.

## Evidence

### Unit / Regression

```text
uv run pytest tests/benchmark/test_capability_ab_runner.py tests/engine/test_capability_planner.py -q
271 passed in 7.00s
```

### P60 Single Docs Probe

Report root: `.nexus/reports/p60_flash_docs_context_sync_outlier_fields_1trial`

- with Nexus: `VERIFIED`, wall `68.5765s`, tokens `66744`, model calls `1`, `provider_token_measured=1.0`.
- without Nexus: `UNVERIFIED`, wall `147.7999s`, tokens `67679`, model calls `1`.
- route: `nexus_supervised_bare_first_deterministic_pre_rescue`, `context_sync_capped`, `hidden_verifier_passed=True`.
- public gates: delivery `PASS`, cost safety `PASS`, cost efficiency `IMPROVED` on this single pair, but sample sufficient `false`.

### P61 Three-Task Flash Probe

Report root: `.nexus/reports/p61_flash_model_required_supervised_bare_first_3task_1trial`

- with Nexus: semantic verified `3/3`, trust mismatch `0`, avg wall `66.5008s`, avg tokens `64225.3333`, avg model calls `1.0`.
- without Nexus: semantic verified `1/3`, trust mismatch `0`, avg wall `60.0575s`, avg tokens `64189.6667`, avg model calls `1.0`.
- public delivery claim gate: `PASS`.
- public cost safety gate: `PASS`.
- public cost efficiency gate: `REGRESSED`; wall ratio `1.1073`, token ratio `1.0006`.
- main remaining cost source: `model-required-feature-001` still routes `evidence_standard` through Hyper, with `phase_wall_r_sec=38.3923`.

## Acceptance Matrix

| Check | Expected | Result | Evidence |
|---|---:|---:|---|
| Verified delivery | with Nexus > bare | PASS | P61 `3/3` vs `1/3` |
| Trust safety | trust mismatch `0` | PASS | P61 bundle |
| Token safety | measured provider tokens | PASS | P61 provider measured rate `1.0` |
| R/hyper suppression for hidden/docs | no R/hyper | PASS | repair/docs use supervised bare-first deterministic pre-rescue |
| Cost efficiency | wall/token not worse | FAIL | P61 cost efficiency `REGRESSED` |
| Root cause localized | one dominant route offender identified | PASS | feature task `evidence_standard` Hyper `38.3923s` |

## Residual Debt

- P62 must address `public_feature` / `evidence_standard`; it still opens Hyper and is now the only obvious R/hyper long-tail in the 3-task slice.
- P63 should decide whether `model-required-feature-001` can safely use a supervised bare-first admission rule or needs a slimmer non-Hyper evidence route.
- P64 should rerun the same 3-task x1 after feature-lane slimming; do not expand to Pro or 12x3 until P61 cost efficiency is no longer regressed.

