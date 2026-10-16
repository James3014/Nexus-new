# Qwen2.5-3B S2T Adapter V2 Release Candidate

- **Release Date**: 2026-06-13
- **Adapter ID**: `qwen3b_s2t_adapter_v2`
- **Status**: RELEASE CANDIDATE (RC)
- **Base Model**: `Qwen/Qwen2.5-3B-Instruct`
- **Training Commit**: `3957e39c8af801310914b28901eba5feee4f1d6f`
- **Eval Commit**: `c6c6fe5bfe440a00b2804fd37d0f30cba66500c9`
- **Shadow Eval Report**: `.nexus/metrics/s2t_shadow_eval_v2_head_report.json`

## 🔒 Provenance & Checksums (Registry Locked)

This adapter is registered and locked under `.nexus/registry/s2t_adapters/qwen3b_s2t_adapter_v2.json`.

| File Name | Size (Bytes) | SHA256 Checksum |
| --- | --- | --- |
| `adapter_config.json` | 1103 | `fef8b9b770a0e6fed78c2e8118b8551d56e72166bda2cf232e6fe3446e6d19c0` |
| `adapter_model.safetensors` | 119801528 | `dfecf673dee604d2de517241f5f9d70108fad38bc861afd1d14488788f199c6a` |
| `tokenizer.json` | 11421892 | `3fd169731d2cbde95e10bf356d66d5997fd885dd8dbb6fb4684da3f23b2585d8` |
| `tokenizer_config.json` | 662 | `fce59775791ca7f322d54419d263b920ace3b24e975d7c5ad7d91e225875bcdc` |
| `chat_template.jinja` | 2507 | `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f` |
| `README.md` | 1489 | `630363bbbf46d133f54fe9e636a5d93e5de4071212caa6af8e07f89fee43d926` |

## 🚀 Release Verification Verdict

1. **Schema Compliance**: **100.0%** (PASSED on 35 shadow rows).
2. **Canary Telemetry**: Verified with real 3B inference in production-equivalent environment (`active_advising`).
3. **Kill Switch**: Enabled via environment variables.

All files are locked and registered. The model is cleared for Phase 3 Observation Canary.
