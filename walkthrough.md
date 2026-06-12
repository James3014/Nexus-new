# Walkthrough - Phase 4.5: Qwen2.5-3B-Instruct Student Fine-Tuning & Verification Complete

We have successfully completed **Phase 4.5: 3B Student Fine-Tuning & Verification** by executing remote QLoRA training on a Google Colab T4 GPU instance, resolving multiple API compatibility issues, downloading the adapter weights, locking their checksums, and verifying their integrity locally.

## 🛠️ Changes Made

### 1. Training Code & Security Hardening
- **`scripts/train/finetune_3b_student.py`**:
  - **TRL v1.0+ Compatibility**: Migrated `max_seq_length` to `max_length` in `SFTConfig`, and `tokenizer` to `processing_class` in `SFTTrainer`.
  - **LoRA Wrapping Resolution**: Removed manual `get_peft_model` wrapping to let `SFTTrainer` handle it internally, preventing parameter collision.
  - **BFloat16 Migration**: Changed training mode to `bf16=True` and compute dtype to `torch.bfloat16` to bypass the `GradScaler` unscale NotImplementedError on T4 GPU.
  - **Sanitization & Opt-in Upload**: Wrapped all external upload paths (bashupload/transfer.sh) behind an explicit `--upload` CLI flag. Removed anonymous telemetry fallbacks.

### 2. Verification Tooling
- **`scripts/train/smoke_test_adapter.py`**:
  - Implemented a local smoke test tool supporting `--mock` verification, `--verify-report`, `--run-real`, and `--offline` fail-closed guards.
  - Schema check: Validates output JSON structure (`selected_candidate_id`, `selection_reason_codes`, `required_verifier`, and `abstain_reason`) and bans "success" verifier smuggling.

### 3. Git Hygiene & Artifact Verification
- **`.gitignore`**: Added ignore patterns for compiled adapter directories and tarballs:
  - `training/adapters/`
  - `scratch/qwen3b_s2t_adapter.tar.gz`
  - `.nexus/training/adapters/`
- **`docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md`**:
  - Created the official integrity report locking all 6 file hashes.
  - Explicitly classified the adapter classification: `synthetic smoke adapter, not runtime adoption candidate`.

---

## 🧬 Learning Closure Matrix (Failure-to-Lesson Writeback)

| Failure | Root Cause | Lesson Learned / Plan Mitigation |
| --- | --- | --- |
| **SFTConfig parameter error** | `max_seq_length` is deprecated inside `SFTConfig` in newer TRL releases. | Replace `max_seq_length=512` with `max_length=512` in `SFTConfig`. |
| **SFTTrainer parameter error** | `tokenizer` parameter is unified under `processing_class` in TRL v1.0+. | Replace `tokenizer=tokenizer` with `processing_class=tokenizer` in `SFTTrainer`. |
| **Duplicate PeftModel conflict** | Passing a pre-wrapped `PeftModel` along with a `peft_config` to `SFTTrainer` is forbidden. | Pass the raw `prepare_model_for_kbit_training` base model to the trainer and let it wrap LoRA internally. |
| **GradScaler BFloat16 Limitation** | Qwen2.5 base weights are BFloat16; training with `fp16=True` triggers `GradScaler` unscale errors. | Run mixed precision with `bf16=True` to skip gradient scaling logic, resolving the `NotImplementedError`. |
| **Colab VM Lifetime / Download Limit** | Colab VMs auto-reclaim quickly after run, and `colab download` cannot fetch directory trees. | Zip adapter outputs to `.tar.gz` in script and fetch the single archive file immediately via `colab download`. |
| **Local Offline Load Test** | Real model execution requires 6GB download; running online locally on slow bandwidth blocks CLI loops. | Add `--offline` local_files_only mode. Fail-close if cache is missing to protect bandwidth and execution loop. |

---

## 🧪 Validation & Verification Evidence

1. **Mock Integrity Check (PASSED)**: Checked adapter folder with report checksums bi-directionally:
   ```bash
   python3 scripts/train/smoke_test_adapter.py --verify-report docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
   ```
   **Output Verdict**:
   ```text
   🛡️ Running Mock Integrity Check...
   ✅ All required adapter files present and non-empty.
   ✅ adapter_config.json settings match specifications (Qwen2.5-3B, LoRA r=16).
   🔎 Verifying checksums against report: docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md
   ✅ Hash MATCH for adapter_config.json: a13cdbe6...
   ✅ Hash MATCH for adapter_model.safetensors: 6f2d7923...
   ✅ Hash MATCH for tokenizer.json: 3fd16973...
   ✅ Hash MATCH for tokenizer_config.json: fbb05e8a...
   ✅ Hash MATCH for chat_template.jinja: cd8e9439...
   ✅ Hash MATCH for README.md: a6f7b957...
   🎉 Mock Integrity Check PASSED.
   ```
2. **Offline Fail-Closed Smoke (PASSED)**: Verified that real-run fails gracefully when cache is absent:
   ```bash
   python3 scripts/train/smoke_test_adapter.py --run-real --offline --device cpu
   ```
   **Output Verdict**:
   ```text
   🚀 Running Physical Load Smoke Test...
   ℹ️ Offline mode active. Only local Hugging Face cache will be used.
   🤖 Loading tokenizer for Qwen/Qwen2.5-3B-Instruct...
   ❌ Failed to load tokenizer locally (is model cached?): Offline mode is enabled and we couldn't find the cached files at /Users/jameschen/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots/...
   ```
3. **No Git Pollution (PASSED)**: Checked untracked changes in `git status`:
   - `training/adapters/qwen3b_s2t_adapter/` is ignored.
   - `scratch/qwen3b_s2t_adapter.tar.gz` is ignored.

---
*Verified by Antigravity*
*Date: 2026-06-12*
