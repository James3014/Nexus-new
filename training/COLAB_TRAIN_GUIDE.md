# S2T 3B Student Fine-Tuning Guide (Using Google Colab CLI)

This guide walks you through using the **Google Colab CLI** to fine-tune `Qwen2.5-3B-Instruct` on a remote GPU, and then retrieve the resulting PEFT LoRA adapter.

## Prerequisites

1. Install the Google Colab CLI locally:
   ```bash
   pip install google-colab-cli
   ```
2. Log in with your Google Account:
   ```bash
   colab login
   ```

## Fine-Tuning Workflow

Follow these steps in your local terminal to run the remote training job:

### 1. Provision a GPU Instance
Request a new Colab runtime with a T4 GPU (or A100 if you have Colab Pro):
```bash
colab new --gpu T4
```

### 2. Install ML Libraries on the Remote Runtime
Install the training dependencies (PyTorch, PEFT, TRL, transformers, bitsandbytes):
```bash
colab install torch transformers datasets peft trl bitsandbytes accelerate
```

### 3. Upload the Dataset
Upload the exported SFT training dataset `s2t_3b_student_v1.jsonl` to the remote instance:
```bash
colab upload --file .nexus/training/s2t_3b_student_v1.jsonl --dest s2t_3b_student_v1.jsonl
```

### 4. Execute the Fine-Tuning Script
Run the local fine-tuning script on the remote Colab instance:
```bash
colab exec -f scripts/train/finetune_3b_student.py -- --data_path s2t_3b_student_v1.jsonl --epochs 3 --batch_size 4
```

### 5. Download the LoRA Adapter Weights
Once training completes, download the resulting adapter output directory to your local workspace:
```bash
colab download --path .nexus/training/adapters/qwen3b_s2t_adapter --dest training/adapters/qwen3b_s2t_adapter
```

### 6. Clean Up Resources
Terminate the remote Colab instance to avoid wasting compute credits:
```bash
colab stop
```

## Loading the Adapter in Nexus

After download, you can load the local 3B model and adapter using PEFT:
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-3B-Instruct")
model = PeftModel.from_pretrained(base_model, "training/adapters/qwen3b_s2t_adapter")
```
