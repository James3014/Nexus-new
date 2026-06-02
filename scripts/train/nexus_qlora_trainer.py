import os
from pathlib import Path
import yaml
import json

# MLX LoRA Trainer Template for M4 16GB
# Usage: uv run --with mlx-lm python3 scripts/train/nexus_qlora_trainer.py --data training/dataset_sft_skeleton_v1.jsonl

def generate_trainer_command(data_path, config_path):
    """
    產生 MLX 訓練指令。
    針對 M4 16GB 優化：4-bit, Rank 16, Batch 1
    """
    command = [
        "python3 -m mlx_lm.lora",
        "--model Qwen/Qwen2.5-Coder-7B-Instruct",
        f"--train --data {data_path}",
        "--iters 200",               # Smoke Test 後的首輪迭代
        "--batch-size 1",            # 嚴格記憶體控制
        "--steps-per-report 10",
        "--steps-per-eval 50",
        "--resume-adapter-file false",
        "--rank 16",                 # 骨架模型不需要過高 Rank
        "--lora-layers 8",           # 僅微調後 8 層以節省資源
        "--learning-rate 1e-5",
        "--save-every 100",
        "--adapter-file training/adapters/skeleton_v1.safetensors"
    ]
    return " ".join(command)

def main():
    config = {
        "dataset": "training/dataset_sft_skeleton_v1.jsonl",
        "base_model": "Qwen2.5-Coder-7B-Instruct",
        "quantization": "4-bit",
        "lora_rank": 16,
        "memory_target": "16GB",
        "target_modules": ["q_proj", "v_proj"]
    }
    
    config_path = Path("training/train_config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(config, f)
        
    print(f"✅ Trainer config saved at {config_path}")
    print("\n🚀 Suggested MLX Training Command (Run on M4 Local):")
    print("-" * 50)
    print(generate_trainer_command(config["dataset"], config_path))
    print("-" * 50)
    print("\n💡 NOTE: Ensure 'mlx-lm' is installed in your local environment.")

if __name__ == "__main__":
    main()
