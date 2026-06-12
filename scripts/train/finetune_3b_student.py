#!/usr/bin/env python3
"""
🚀 Nexus Phase 4.5: S2T 3B Student Model Fine-tuning Script (QLoRA)
用於在本地或 Colab T4 GPU 實例上微調 Qwen2.5-3B-Instruct。
"""

import os
import sys
import torch
import argparse
from pathlib import Path
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# 系統 Prompt，引導 3B 學生模型模仿 Nexus 的結構化決策
SYSTEM_PROMPT = (
    "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
    "and provide selection reason codes and required verifiers based on the route features "
    "and candidate summaries. You must strictly output the target JSON."
)

def format_prompt(sample):
    """將 SFT 資料格式化為對話範本格式 (ChatML)"""
    input_str = f"Route Features: {sample['input']['route_features']}\nCandidates: {sample['input']['candidate_summaries']}"
    target_str = str(sample['target'])
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": input_str},
        {"role": "assistant", "content": target_str}
    ]
    return {"messages": messages}

def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen2.5-3B-Instruct using QLoRA.")
    parser.add_argument("--data_path", type=str, default=".nexus/training/s2t_3b_student_v1.jsonl")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--output_dir", type=str, default=".nexus/training/adapters/")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    args, unknown = parser.parse_known_args()

    # 1. 載入與預處理資料集
    if not os.path.exists(args.data_path):
        fn = os.path.basename(args.data_path)
        candidates = [
            fn,
            os.path.join("/content", fn),
            os.path.join("/root", fn),
            os.path.join("/", fn),
            os.path.join(os.getcwd(), fn)
        ]
        found = False
        for path in candidates:
            if os.path.exists(path):
                args.data_path = path
                found = True
                break
        if not found:
            print(f"❌ Data path not found. Searched candidates: {candidates}. Current dir is {os.getcwd()}, contents: {os.listdir('.') if os.path.exists('.') else []}")
            sys.exit(1)

    print(f"📖 Loading dataset from {args.data_path}...")
    dataset = load_dataset("json", data_files=args.data_path, split="train")
    dataset = dataset.map(format_prompt)
    dataset = dataset.train_test_split(test_size=0.1)

    # 2. 載入 Tokenizer 與設定
    print(f"🤖 Loading tokenizer for {args.model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 3. 載入量化模型 (4-bit QLoRA)
    print("💾 Loading model in 4-bit quantization...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    # 4. 設定 LoRA 參數
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 5. 設定訓練引數
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=2,
        optim="paged_adamw_32bit",
        save_steps=50,
        logging_steps=10,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        fp16=True,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        evaluation_strategy="steps",
        eval_steps=50,
        report_to="none",
    )

    # 6. 使用 SFTTrainer 訓練
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        peft_config=peft_config,
        max_seq_length=512,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("🚀 Starting training...")
    trainer.train()

    # 7. 儲存微調好的 Adapter
    final_output = os.path.join(args.output_dir, "qwen3b_s2t_adapter")
    print(f"🎉 Saving adapter weights to {final_output}...")
    trainer.model.save_pretrained(final_output)
    tokenizer.save_pretrained(final_output)
    print("✅ Done!")

if __name__ == "__main__":
    main()
