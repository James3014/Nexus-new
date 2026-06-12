# Walkthrough - Phase 4.5: Qwen2.5-3B-Instruct Student Fine-Tuning Complete

We have successfully completed **Phase 4.5: 3B Student Fine-Tuning** by executing remote QLoRA training on a Google Colab T4 GPU instance, resolving multiple API compatibility issues, and retrieving the resulting model adapter weights locally.

## 🛠️ Changes Made

### 1. Training Code Hardening
- **`scripts/train/finetune_3b_student.py`**:
  - **TRL v1.0+ Compatibility**: Migrated `max_seq_length` to `max_length` in `SFTConfig`, and `tokenizer` to `processing_class` in `SFTTrainer`.
  - **LoRA Wrapping Resolution**: Removed manual `get_peft_model` wrapping to let `SFTTrainer` handle it internally, preventing parameter collision.
  - **BFloat16 Migration**: Changed training mode to `bf16=True` and compute dtype to `torch.bfloat16` to bypass the `GradScaler` unscale NotImplementedError on T4 GPU.
  - **Auto-packaging**: Configured the script to automatically zip the final adapter weights into `/content/qwen3b_s2t_adapter.tar.gz` upon completion.

### 2. Guide Documentation
- **`training/COLAB_TRAIN_GUIDE.md`**: Updated parameters and troubleshooting sections detailing TRL v1.0+ changes and download commands.

---

## 🧬 Learning Closure Matrix (Failure-to-Lesson Writeback)

| Failure | Root Cause | Lesson Learned / Plan Mitigation |
| --- | --- | --- |
| **SFTConfig parameter error** | `max_seq_length` is deprecated inside `SFTConfig` in newer TRL releases. | Replace `max_seq_length=512` with `max_length=512` in `SFTConfig`. |
| **SFTTrainer parameter error** | `tokenizer` parameter is unified under `processing_class` in TRL v1.0+. | Replace `tokenizer=tokenizer` with `processing_class=tokenizer` in `SFTTrainer`. |
| **Duplicate PeftModel conflict** | Passing a pre-wrapped `PeftModel` along with a `peft_config` to `SFTTrainer` is forbidden. | Pass the raw `prepare_model_for_kbit_training` base model to the trainer and let it wrap LoRA internally. |
| **GradScaler BFloat16 Limitation** | Qwen2.5 base weights are BFloat16; training with `fp16=True` triggers `GradScaler` unscale errors. | Run mixed precision with `bf16=True` to skip gradient scaling logic, resolving the `NotImplementedError`. |
| **Colab VM Lifetime / Download Limit** | Colab VMs auto-reclaim quickly after run, and `colab download` cannot fetch directory trees. | Zip adapter outputs to `.tar.gz` in script and fetch the single archive file immediately via `colab download`. |

---

## 🧪 Validation & Verification Evidence

1. **Successful Training Run**: Task `task-689` completed successfully with the following log snippet:
   ```text
   trainable params: 29,933,568 || all params: 3,115,872,256 || trainable%: 0.9607
   🚀 Starting training...
   🎉 Saving adapter weights to .nexus/training/adapters/qwen3b_s2t_adapter...
   ✅ Done!
   📦 Packaging adapter weights...
   📦 Archive created at /content/qwen3b_s2t_adapter.tar.gz.
   ```
2. **Tunnel Download**: Successfully pulled the zipped adapter locally via `colab download` (`task-699`):
   ```text
   [colab] Downloading '/content/qwen3b_s2t_adapter.tar.gz' to 'scratch/qwen3b_s2t_adapter.tar.gz' (27.22 MB)...
   [colab] Download complete.
   ```
3. **Local Restoration**: Unpacked and verified directory structure under [qwen3b_s2t_adapter](file:///Users/jameschen/Workspace/nexus/training/adapters/qwen3b_s2t_adapter/):
   - `adapter_config.json` (1.1 KB)
   - `adapter_model.safetensors` (59.9 MB)
   - `tokenizer.json` (11.4 MB)
   - `tokenizer_config.json` (691 B)
   - `chat_template.jinja` (2.5 KB)
   - `README.md` (5.2 KB)

---
*Verified by Antigravity*
*Date: 2026-06-12*
