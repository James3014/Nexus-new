# Nexus Publication-Ready 12x2 Summary

## Status

PASS. The frozen 12-task x2 public candidate lane produced publication-ready delivery, trust, wall-cost, and claim-gate evidence for the internal Nexus public-readiness check.

## Claim-Safe Result

On the frozen 12-task x2 public candidate lane, Gemini+Nexus reached 24/24 verified delivery (100.0%) versus Gemini bare at 16/24 verified delivery (66.7%). Trust mismatch remained 0.0% for both arms and infra-invalid rows were 0 for both arms.

Wall-time efficiency improved in this run: Gemini+Nexus averaged 0.9152 seconds per row, while Gemini bare averaged 39.2984 seconds per row.

Do not claim token savings or model-token uplift from this run. The token public-safe claim is NO because formal token treatment was valid for 0/24 rows.

## Gate Separation

- Public claim gate: PASS
- Performance claim gate: PASS
- Cost claim gate: PASS
- Cost efficiency gate: IMPROVED
- Runtime default apply: not implied
- SF catalog replacement: not implied
- Token public-safe claim: NO

## Evidence Bundle

- `.nexus/reports/publication_ready_value12x2_20260520/evidence_bundle.json`
- `.nexus/reports/publication_ready_value12x2_20260520/public_ready_evidence_manifest.json`
- `.nexus/reports/publication_ready_value12x2_20260520/public_ready_read_model.json`
- `.nexus/reports/publication_ready_value12x2_20260520/publication_benchmark_summary.json`
- `.nexus/reports/publication_ready_value12x2_20260520/publication_readiness_gate.json`
- `.nexus/reports/publication_ready_value12x2_20260520/gemini_nexus_report_1779230790.md`

## Retention

Keep the evidence bundle and read-model artifacts together. They are a single publication-ready evidence set; removing one artifact makes the claim reconstruction incomplete.

This summary is a tracked readout, not a replacement for the evidence bundle.
