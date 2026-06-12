# Qwen2.5-3B-Instruct S2T Adapter Integrity and Smoke Test Report

- **Date**: 2026-06-12
- **Originating Commit**: `72c24f16`
- **Adapter Status**: `synthetic smoke adapter, not runtime adoption candidate`

> [!WARNING]
> This adapter was trained on an embedded synthetic dataset (`sim-task-0..34`) for setup validation and toolchain debugging. It is strictly forbidden to deploy this adapter to production, utilize it as a default router, or smuggle it into runtime gates. Promotion to a runtime candidate requires passing the shadow evaluation phase with at least 30+ eligible real S2T trace rows.

---

## 🔒 Adapter Checksums (SHA-256)

These hashes lock the downloaded fine-tuning output assets locally. They are verified bi-directionally by the local smoke test script.

| File Name | SHA-256 Checksum |
| --- | --- |
| `adapter_model.safetensors` | `6f2d7923bcfa93cfa1d4e4be0eb25ae6578d95f2ebec785cbe61e5bf89e2ca6c` |
| `adapter_config.json` | `a13cdbe6188f2a60f2fafdc51706a8460cfba7df996904d638d63a63bf46dd0d` |
| `tokenizer.json` | `3fd169731d2cbde95e10bf356d66d5997fd885dd8dbb6fb4684da3f23b2585d8` |
| `tokenizer_config.json` | `fbb05e8a722a05e92e8da2eabbb5820bbdd0d1482351a38cb14efa52fc8bdadb` |
| `chat_template.jinja` | `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f` |
| `README.md` | `a6f7b9573427cf03af8c5204cd9074efe8b86980790a1053283391b90168af40` |

---

## 🛠️ PEFT configuration Verification Specs

- **Base Model**: `Qwen/Qwen2.5-3B-Instruct`
- **PEFT Type**: `LORA`
- **LoRA Rank (r)**: `16`
- **LoRA Alpha (alpha)**: `32`
- **Target Modules**: `["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]`
- **Bias Setting**: `none`
- **Task Type**: `CAUSAL_LM`

---

## 🧪 Verification Commands

### 1. Mock Integrity Verification (Required Gate)
To verify files exist, sizes are non-zero, PEFT parameters are correct, and checksums match this report, run:
```bash
python3 scripts/train/smoke_test_adapter.py --verify-report docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
```

### 2. Physical Load Smoke Verification (Optional Phase 5 Pre-gate)
To perform a dry run of the unified model loading and test output JSON schema compliance offline (using cached files only):
```bash
python3 scripts/train/smoke_test_adapter.py --run-real --offline --device cpu
```

---

## 🏁 Gate Invariants and Adoption Checklist

- **[x] Git Pollution Defense**: `training/adapters/`, `scratch/qwen3b_s2t_adapter.tar.gz`, and `.nexus/training/adapters/` are registered in `.gitignore`.
- **[x] Trainer Sanitization**: Removed all anonymous external upload fallbacks in `finetune_3b_student.py` (external uploading is now strict opt-in via `--upload`).
- **[ ] Phase 5 Shadow Evaluation Gate**: Minimum 30+ eligible real trace rows comparison, positive `selector_override_verified_rate` lift, and zero `trust_mismatch_rate` increase.
- **[ ] Phase 6 Runtime Adoption Gate**: Strict-gated feature-flag advisory mode only; no default replacement of autopilot routers or receipt verifiers.
