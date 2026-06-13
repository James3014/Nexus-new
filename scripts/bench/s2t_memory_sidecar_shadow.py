#!/usr/bin/env python3
"""
scripts/bench/s2t_memory_sidecar_shadow.py

Runner for the 3B Memory Sidecar in shadow mode.
Takes task artifacts and produces a schema-valid checkpoint.
"""
import argparse
import json
import sys
import hashlib
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for local imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.s2t_strict import S2T3BAdvisor, robust_json_parse

def load_json_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def read_text_file(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

class MemorySidecarAdvisor(S2T3BAdvisor):
    """Extension of S2T3BAdvisor for Memory Sidecar tasks."""
    
    def generate_checkpoint(self, task_id: str, artifacts: Dict[str, str]) -> Dict[str, Any]:
        self._lazy_load()
        
        prompt_template = read_text_file("prompts/s2t_memory_sidecar_v1.md")
        if not prompt_template:
            return {"abstain_reason": "prompt_template_missing"}

        # Inject artifacts into template
        prompt = prompt_template
        for key, value in artifacts.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", value if value else "Not provided")
        prompt = prompt.replace("{{task_id}}", task_id)

        if self._use_simulation:
            # Mock successful checkpoint for testing infrastructure
            return {
                "schema": "nexus.s2t_memory_sidecar_checkpoint.v1",
                "task_id": task_id,
                "mode": "optimization",
                "summary": "Simulation mode: Checkpoint generated.",
                "completed_steps": ["infra_setup"],
                "open_blockers": [],
                "failure_family": None,
                "evidence_refs": [],
                "modified_files": [],
                "test_commands": [],
                "test_results": [],
                "next_action": "continue_task",
                "claim_boundary": "observation_only",
                "do_not_repeat": [],
                "confidence": "medium",
                "abstain_reason": None
            }

        if not self._is_loaded or self.model is None or self.tokenizer is None:
            return {"abstain_reason": f"model_not_loaded: {self._load_error}"}

        try:
            # System part of the prompt is already in the file, but we split for chat template if needed
            # For simplicity, we treat the whole prompt as the instruction
            messages = [
                {"role": "user", "content": prompt}
            ]
            text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
            
            import torch
            with torch.no_grad():
                generated_ids = self.model.generate(**model_inputs, max_new_tokens=512)
            
            generated_ids = [
                output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            
            # Clean markdown blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            return robust_json_parse(response)
        except Exception as e:
            return {"abstain_reason": f"inference_failed: {str(e)}"}

def main():
    parser = argparse.ArgumentParser(description="Nexus S2T Memory Sidecar Shadow Runner")
    parser.add_argument("--task-id", required=True, help="Task Identifier")
    parser.add_argument("--receipt", help="Path to task receipt JSON")
    parser.add_argument("--log", help="Path to execution log")
    parser.add_argument("--git-diff-stat", help="Path to git diff stat")
    parser.add_argument("--test-output", help="Path to test output log")
    parser.add_argument("--plan", help="Path to implementation plan")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--adapter-dir", default="training/adapters/qwen3b_s2t_adapter_v2")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--mock", action="store_true", help="Run with simulation mode")

    args = parser.parse_args()

    # Load Inputs
    artifacts = {
        "receipt": json.dumps(load_json_file(args.receipt), indent=2) if args.receipt else "",
        "log": read_text_file(args.log),
        "diff_stat": read_text_file(args.git_diff_stat),
        "test_output": read_text_file(args.test_output),
        "plan": read_text_file(args.plan)
    }

    # Initialize Advisor
    advisor = MemorySidecarAdvisor(
        adapter_path=args.adapter_dir,
        force_simulation=args.mock
    )
    
    # Generate Checkpoint
    checkpoint = advisor.generate_checkpoint(args.task_id, artifacts)

    # Write Output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    row = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task_id": args.task_id,
        "checkpoint": checkpoint,
        "input_hashes": {
            "receipt": hashlib.sha256(artifacts["receipt"].encode()).hexdigest() if artifacts["receipt"] else None,
            "log": hashlib.sha256(artifacts["log"].encode()).hexdigest() if artifacts["log"] else None,
            "diff_stat": hashlib.sha256(artifacts["diff_stat"].encode()).hexdigest() if artifacts["diff_stat"] else None,
            "test_output": hashlib.sha256(artifacts["test_output"].encode()).hexdigest() if artifacts["test_output"] else None,
            "plan": hashlib.sha256(artifacts["plan"].encode()).hexdigest() if artifacts["plan"] else None
        },
        "metadata": {
            "adapter": args.adapter_dir,
            "mock": args.mock
        }
    }

    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    print(f"Checkpoint written to {args.output}")

if __name__ == "__main__":
    main()
