"""
SWE-bench Local Heal Runner
===========================
整合 Localizer / SandboxExecutor / PatchTreeEvaluator / SearchReplaceParser 流程。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Tuple, Dict, Any

from nexus.services.local_heal.pipeline import HealPipeline, HealContext

NEXUS_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "nexus-local-heal-v17"
OLLAMA_ENDPOINT = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")

def sh(cmd: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)

def ollama_generate(system_prompt: str, user_prompt: str, timeout: int = 1200) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 4096,
        }
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
        return data.get("response", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument("--output", default=str(NEXUS_ROOT / "benchmarking/swebench_lite/predictions_swe.jsonl"))
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Error: pip install datasets")

    print(f"📦 Loading {args.dataset}...")
    ds = load_dataset(args.dataset, split="test")
    subset = ds.select(range(args.index, min(args.index + args.limit, len(ds))))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    # 實例化 pipeline，傳入 LLM 呼叫函數
    pipeline = HealPipeline(ollama_generate_fn=ollama_generate)

    with tempfile.TemporaryDirectory(prefix="swe_heal_") as tmp_root:
        tmp = Path(tmp_root)

        for i, item in enumerate(subset):
            iid = item["instance_id"]
            repo = item["repo"]
            commit = item["base_commit"]
            problem = item["problem_statement"]

            print(f"\n{'='*60}")
            print(f"[{i+1}/{args.limit}] Processing {iid}")
            
            repo_dir = tmp / iid.replace("/", "__").replace(".", "_")

            # 1. Clone & Checkout
            print("  → git clone...")
            sh(["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(repo_dir)], cwd=tmp)
            sh(["git", "checkout", "--quiet", commit], cwd=repo_dir)
            print(f"  ✓ Checked out @ {commit[:10]}")

            # 2. 執行 HealPipeline 管線 (固定五階段處理)
            print("  → Running HealPipeline Orchestrator...")
            ctx = HealContext(
                instance_id=iid,
                repo_dir=repo_dir,
                problem_statement=problem,
                max_tries=3
            )
            
            ctx = pipeline.run(ctx)

            # Print patch preview
            if ctx.final_patch:
                print("  --- Unified Diff ---")
                print("\n".join(ctx.final_patch.splitlines()[:15]))
                print("  --------------------")
            else:
                print("  ⚠ No patch was successfully applied.")
                if ctx.errors:
                    print(f"  ✗ Pipeline error trace: {[e.message for e in ctx.errors]}")

            results.append({
                "instance_id": iid,
                "model_patch": ctx.final_patch,
                "model_name_or_path": MODEL_NAME
            })

    # Write predictions.jsonl
    with open(out_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\n✅ Finished processing! Predictions saved to: {out_path}")

if __name__ == "__main__":
    main()
