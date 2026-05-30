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

from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.sandbox import SandboxExecutor
from nexus.services.local_heal.evaluator import PatchTreeEvaluator
from nexus.services.local_heal.validator import validate_syntax
from nexus.services.local_heal.corrector import SelfCorrector

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

from nexus.services.local_heal.localizer import Localizer

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
    parser_tool = SearchReplaceParser()
    localizer = Localizer()

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

            # 2. Localize relevant files
            print("  → Localizing related source files...")
            files = localizer.locate(problem, repo_dir, max_files=3)
            if not files:
                print("  ⚠ No relevant source files found!")
                results.append({"instance_id": iid, "model_patch": "", "model_name_or_path": MODEL_NAME})
                continue
            
            print(f"  ✓ Located: {[f[0] for f in files]}")
            file_ctx = "\n\n".join(f"=== FILE: {fname} ===\n{content}" for fname, content in files)

            # 3. Call Ollama with local_heal spec
            system_prompt = (
                "You are an expert software engineer. "
                "Output exact SEARCH/REPLACE blocks to fix the bug. "
                "Format rules:\n"
                "FILE: path/to/file.py\n"
                "SEARCH:\n"
                "verbatim search content\n"
                "REPLACE:\n"
                "replacement content\n"
                "END\n"
                "Make minimum impact changes. Output ONLY blocks."
            )
            
            user_prompt = f"Bug Report:\n{problem[:1500]}\n\nSource Code:\n{file_ctx}\n\nOutput SEARCH/REPLACE block(s):"
            
            corrector = SelfCorrector()

            # 重試循環最大次數設為 2 次
            max_tries = 2
            current_try = 1
            final_patch = ""

            while current_try <= max_tries:
                print(f"  → Generating patch via Ollama (Attempt {current_try}/{max_tries})...")
                try:
                    response = ollama_generate(system_prompt, user_prompt)
                except Exception as e:
                    print(f"  ✗ Ollama call failed: {e}")
                    break

                # 4. Parse SEARCH/REPLACE blocks
                print(f"  [DEBUG] LLM Response Length: {len(response)} chars")
                blocks = parser_tool.parse_blocks(response)
                if not blocks:
                    print("  ⚠ LLM output no SEARCH/REPLACE blocks.")
                    break

                # 5. Apply blocks and produce clean diff
                print(f"  ✓ Parsed {len(blocks)} blocks. Applying...")
                applied_diffs = []
                has_error = False
                syntax_err_msg = ""

                for b in blocks:
                    # Find matching target path in repo
                    target_path = repo_dir / b["file"]
                    if not target_path.exists():
                        found_files = list(repo_dir.rglob(Path(b["file"]).name))
                        if found_files:
                            target_path = found_files[0]
                        else:
                            print(f"  ✗ Target file not found: {b['file']}")
                            continue
                    
                    print(f"  [DEBUG] Trying to match in file: {target_path}")
                    ok, diff = parser_tool.apply_and_diff(target_path, b["search"], b["replace"])
                    if ok:
                        # 6. 新增：微服務語法檢查器 (AST Static Check)
                        target_code = target_path.read_text(encoding="utf-8", errors="replace")
                        is_valid, err_msg = validate_syntax(target_code)
                        if is_valid:
                            applied_diffs.append(diff)
                            print(f"  ✓ Applied patch to {target_path.relative_to(repo_dir)}")
                        else:
                            has_error = True
                            syntax_err_msg = err_msg
                            print(f"  ✗ Failed AST validator: {err_msg}")
                            # 語法出錯，立即回滾以維持代碼乾淨
                            sh(["git", "checkout", "--", str(target_path)], cwd=repo_dir)
                            break
                    else:
                        has_error = True
                        syntax_err_msg = diff
                        print(f"  ✗ Failed apply on {b['file']}: {diff}")
                        break

                if not has_error:
                    final_patch = "\n".join(applied_diffs).strip()
                    break
                else:
                    # 觸發自我修復循環 (Self-Correction Loop)
                    print(f"  🔄 Triggering Self-Correction Loop due to: {syntax_err_msg}")
                    user_prompt = corrector.build_retry_prompt(user_prompt, syntax_err_msg)
                    current_try += 1

            # Print patch preview
            if final_patch:
                print("  --- Unified Diff ---")
                print("\n".join(final_patch.splitlines()[:15]))
                print("  --------------------")
            else:
                print("  ⚠ No patch was successfully applied.")

            results.append({
                "instance_id": iid,
                "model_patch": final_patch,
                "model_name_or_path": MODEL_NAME
            })

    # Write predictions.jsonl
    with open(out_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\n✅ Finished processing! Predictions saved to: {out_path}")

if __name__ == "__main__":
    main()
