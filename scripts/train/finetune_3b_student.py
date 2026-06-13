#!/usr/bin/env python3
"""
🚀 Nexus Phase 4.5: S2T 3B Student Model Fine-tuning Script (QLoRA)
用於在本地或 Colab T4 GPU 實例上微調 Qwen2.5-3B-Instruct。
"""

import os
import sys
import subprocess

# 自動在遠端 Fresh 環境安裝依賴套件
try:
    import trl
except ImportError:
    print("📦 Installing dependencies on fresh Colab VM...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "torch", "transformers", "datasets", "peft", "trl", "accelerate"])

import torch
import argparse
from pathlib import Path
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTConfig, SFTTrainer

# 系統 Prompt，引導 3B 學生模型模仿 Nexus 的結構化決策
SYSTEM_PROMPT = (
    "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
    "and provide selection reason codes and required verifiers based on the route features "
    "and candidate summaries.\n"
    "You must strictly output a valid JSON object. Do NOT wrap output in markdown blocks (e.g. ```json). "
    "Do NOT use single quotes for JSON keys or string values (do NOT output Python dict format). "
    "Every output MUST strictly contain all 4 required keys: 'selected_candidate_id', 'selection_reason_codes', "
    "'required_verifier', 'abstain_reason'. The 'required_verifier' field MUST be null or one of the following "
    "allowed verifiers: ['pytest', 'claim_gate', 'delivery_gate', 'hidden_verifier']."
)

ALLOWED_VERIFIERS = ["pytest", "claim_gate", "delivery_gate", "hidden_verifier"]

def format_prompt(sample):
    """將 SFT 資料格式化為對話範本格式 (ChatML)"""
    target_data = sample.get('correct_target') if 'correct_target' in sample else sample.get('target')
    reminder = sample.get('contract_reminder', '')
    
    system_content = SYSTEM_PROMPT
    if reminder:
        system_content = f"{SYSTEM_PROMPT}\n{reminder}"
        
    input_str = f"Route Features: {sample['input']['route_features']}\nCandidates: {sample['input']['candidate_summaries']}"
    target_str = str(target_data)
    
    messages = [
        {"role": "system", "content": system_content},
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
    import json
    from datasets import Dataset, load_dataset

    if os.path.exists(args.data_path):
        print(f"📖 Loading real dataset from {args.data_path}...")
        dataset = load_dataset("json", data_files=args.data_path, split="train")
        
        # 🛡️ Label Validator: 訓練前掃描所有 target，不合格直接 fail closed
        print("🛡️ Running pre-training Label Validator contract check...")
        for idx, sample in enumerate(dataset):
            target_data = sample.get('correct_target') if 'correct_target' in sample else sample.get('target')
            if not target_data:
                raise ValueError(f"Label Validator Gate Fail: Missing target data in sample {idx}")
            
            # 1. 驗證 4 個 required keys
            for key in ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]:
                if key not in target_data:
                    raise ValueError(f"Label Validator Gate Fail: Missing key '{key}' in sample {idx} target")
            
            # 2. 驗證 required_verifier enum
            v = target_data["required_verifier"]
            if v is not None and v not in ALLOWED_VERIFIERS:
                raise ValueError(f"Label Validator Gate Fail: Invalid verifier '{v}' in sample {idx} target. Must be one of {ALLOWED_VERIFIERS} or null")
        print("✅ Pre-training Label Validator contract check PASSED.")
        
        use_embedded = False
    else:
        print(f"⚠️ Data path '{args.data_path}' not found. Loading embedded synthetic dataset as smoke fixture...")
        use_embedded = True
        embedded_data_json = """[
  {
    "task_id": "sim-task-0",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-0",
          "cost": null
        },
        {
          "id": "cand-pass-0",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-0",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-1",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-1",
          "cost": null
        },
        {
          "id": "cand-pass-1",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-1",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-2",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-2",
          "cost": null
        },
        {
          "id": "cand-pass-2",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-2",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-3",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-3",
          "cost": null
        },
        {
          "id": "cand-pass-3",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-3",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-4",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-4",
          "cost": null
        },
        {
          "id": "cand-pass-4",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-4",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-5",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-5",
          "cost": null
        },
        {
          "id": "cand-pass-5",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-5",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-6",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-6",
          "cost": null
        },
        {
          "id": "cand-pass-6",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-6",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-7",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-7",
          "cost": null
        },
        {
          "id": "cand-pass-7",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-7",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-8",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-8",
          "cost": null
        },
        {
          "id": "cand-pass-8",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-8",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-9",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-9",
          "cost": null
        },
        {
          "id": "cand-pass-9",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-9",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-10",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-10",
          "cost": null
        },
        {
          "id": "cand-pass-10",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-10",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-11",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-11",
          "cost": null
        },
        {
          "id": "cand-pass-11",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-11",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-12",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-12",
          "cost": null
        },
        {
          "id": "cand-pass-12",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-12",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-13",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-13",
          "cost": null
        },
        {
          "id": "cand-pass-13",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-13",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-14",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-14",
          "cost": null
        },
        {
          "id": "cand-pass-14",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-14",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-15",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-15",
          "cost": null
        },
        {
          "id": "cand-pass-15",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-15",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-16",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-16",
          "cost": null
        },
        {
          "id": "cand-pass-16",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-16",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-17",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-17",
          "cost": null
        },
        {
          "id": "cand-pass-17",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-17",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-18",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-18",
          "cost": null
        },
        {
          "id": "cand-pass-18",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-18",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-19",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-19",
          "cost": null
        },
        {
          "id": "cand-pass-19",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-19",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-20",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-20",
          "cost": null
        },
        {
          "id": "cand-pass-20",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-20",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-21",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-21",
          "cost": null
        },
        {
          "id": "cand-pass-21",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-21",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-22",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-22",
          "cost": null
        },
        {
          "id": "cand-pass-22",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-22",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-23",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-23",
          "cost": null
        },
        {
          "id": "cand-pass-23",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-23",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-24",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-24",
          "cost": null
        },
        {
          "id": "cand-pass-24",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-24",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-25",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-25",
          "cost": null
        },
        {
          "id": "cand-pass-25",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-25",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-26",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-26",
          "cost": null
        },
        {
          "id": "cand-pass-26",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-26",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-27",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-27",
          "cost": null
        },
        {
          "id": "cand-pass-27",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-27",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-28",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-28",
          "cost": null
        },
        {
          "id": "cand-pass-28",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-28",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-29",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-29",
          "cost": null
        },
        {
          "id": "cand-pass-29",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-29",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-30",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-30",
          "cost": null
        },
        {
          "id": "cand-pass-30",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-30",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-31",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-31",
          "cost": null
        },
        {
          "id": "cand-pass-31",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-31",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-32",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-32",
          "cost": null
        },
        {
          "id": "cand-pass-32",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-32",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-33",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-33",
          "cost": null
        },
        {
          "id": "cand-pass-33",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-33",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-34",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-34",
          "cost": null
        },
        {
          "id": "cand-pass-34",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-34",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-0",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-0",
          "cost": null
        },
        {
          "id": "cand-pass-0",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-0",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-1",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-1",
          "cost": null
        },
        {
          "id": "cand-pass-1",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-1",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-2",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-2",
          "cost": null
        },
        {
          "id": "cand-pass-2",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-2",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-3",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-3",
          "cost": null
        },
        {
          "id": "cand-pass-3",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-3",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-4",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-4",
          "cost": null
        },
        {
          "id": "cand-pass-4",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-4",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-5",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-5",
          "cost": null
        },
        {
          "id": "cand-pass-5",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-5",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-6",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-6",
          "cost": null
        },
        {
          "id": "cand-pass-6",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-6",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-7",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-7",
          "cost": null
        },
        {
          "id": "cand-pass-7",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-7",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-8",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-8",
          "cost": null
        },
        {
          "id": "cand-pass-8",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-8",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-9",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-9",
          "cost": null
        },
        {
          "id": "cand-pass-9",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-9",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-10",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-10",
          "cost": null
        },
        {
          "id": "cand-pass-10",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-10",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-11",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-11",
          "cost": null
        },
        {
          "id": "cand-pass-11",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-11",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-12",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-12",
          "cost": null
        },
        {
          "id": "cand-pass-12",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-12",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-13",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-13",
          "cost": null
        },
        {
          "id": "cand-pass-13",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-13",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-14",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-14",
          "cost": null
        },
        {
          "id": "cand-pass-14",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-14",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-15",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-15",
          "cost": null
        },
        {
          "id": "cand-pass-15",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-15",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-16",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-16",
          "cost": null
        },
        {
          "id": "cand-pass-16",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-16",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-17",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-17",
          "cost": null
        },
        {
          "id": "cand-pass-17",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-17",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-18",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-18",
          "cost": null
        },
        {
          "id": "cand-pass-18",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-18",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-19",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-19",
          "cost": null
        },
        {
          "id": "cand-pass-19",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-19",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-20",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-20",
          "cost": null
        },
        {
          "id": "cand-pass-20",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-20",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-21",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-21",
          "cost": null
        },
        {
          "id": "cand-pass-21",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-21",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-22",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-22",
          "cost": null
        },
        {
          "id": "cand-pass-22",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-22",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-23",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-23",
          "cost": null
        },
        {
          "id": "cand-pass-23",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-23",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-24",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-24",
          "cost": null
        },
        {
          "id": "cand-pass-24",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-24",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-25",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-25",
          "cost": null
        },
        {
          "id": "cand-pass-25",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-25",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-26",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-26",
          "cost": null
        },
        {
          "id": "cand-pass-26",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-26",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-27",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-27",
          "cost": null
        },
        {
          "id": "cand-pass-27",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-27",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-28",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-28",
          "cost": null
        },
        {
          "id": "cand-pass-28",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-28",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-29",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-29",
          "cost": null
        },
        {
          "id": "cand-pass-29",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-29",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-30",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-30",
          "cost": null
        },
        {
          "id": "cand-pass-30",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-30",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-31",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-31",
          "cost": null
        },
        {
          "id": "cand-pass-31",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-31",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-32",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-32",
          "cost": null
        },
        {
          "id": "cand-pass-32",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-32",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-33",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-33",
          "cost": null
        },
        {
          "id": "cand-pass-33",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-33",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  },
  {
    "task_id": "sim-task-34",
    "model": "gemini-3-flash-preview",
    "input": {
      "risk_tier": "medium",
      "route_features": {},
      "candidate_summaries": [
        {
          "id": "cand-fail-34",
          "cost": null
        },
        {
          "id": "cand-pass-34",
          "cost": null
        }
      ],
      "budget": {}
    },
    "target": {
      "selected_candidate_id": "cand-pass-34",
      "selection_reason_codes": [
        "verifier_failed_candidate_excluded",
        "has_empirical_test_evidence",
        "lower_claim_risk"
      ],
      "required_verifier": "pytest",
      "abstain_reason": null
    }
  }
]"""
        dataset = Dataset.from_list(json.loads(embedded_data_json))
    dataset = dataset.map(format_prompt)
    dataset = dataset.train_test_split(test_size=0.1)

    # 2. 載入 Tokenizer 與設定
    print(f"🤖 Loading tokenizer for {args.model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 3. 載入模型 (根據 CUDA 是否可用決定是否使用 4-bit 量化與 QLoRA)
    use_cuda = torch.cuda.is_available()
    if use_cuda:
        print("💾 Loading model in 4-bit quantization (CUDA GPU)...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)
    else:
        print("💾 CUDA not available. Loading model in float32 (CPU)...")
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            device_map={"": "cpu"},
            torch_dtype=torch.float32,
            trust_remote_code=True,
        )

    # 4. 設定 LoRA 參數
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    # 5. 設定訓練引數 (自適應優化器與精確度)
    training_args = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=2,
        optim="paged_adamw_32bit" if use_cuda else "adamw_torch",
        save_steps=50,
        logging_steps=10,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        bf16=use_cuda,
        use_cpu=not use_cuda,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        eval_strategy="steps",
        eval_steps=50,
        report_to="none",
        max_length=512,
    )

    # 6. 使用 SFTTrainer 訓練
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        peft_config=peft_config,
        processing_class=tokenizer,
        args=training_args,
    )
    trainer.model.print_trainable_parameters()

    print("🚀 Starting training...")
    trainer.train()

    # 7. 儲存微調好的 Adapter
    if args.output_dir.endswith("qwen3b_s2t_adapter") or args.output_dir.endswith("qwen3b_s2t_adapter_v2"):
        final_output = args.output_dir
    else:
        final_output = os.path.join(args.output_dir, "qwen3b_s2t_adapter")
    print(f"🎉 Saving adapter weights to {final_output}...")
    trainer.model.save_pretrained(final_output)
    tokenizer.save_pretrained(final_output)
    print("✅ Done!")

    # 8. 自動打包，解決 VM 自動回收
    try:
        import shutil
        print("📦 Packaging adapter weights...")
        archive_path = shutil.make_archive("/content/qwen3b_s2t_adapter", "gztar", final_output)
        print(f"📦 Archive created at {archive_path}.")
    except Exception as e:
        print("❌ Error packaging adapter:", e)

if __name__ == "__main__":
    main()
