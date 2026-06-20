import os
import sys
import json
import urllib.request
import subprocess
import argparse
from pathlib import Path
from dataclasses import asdict

# Ensure nexus is in path
WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.interface import LocalizedFile

# Monkey-patch Patcher to capture telemetry
original_apply_patch = Patcher.apply_patch
captured_results = []

def patched_apply_patch(self, *args, **kwargs):
    res = original_apply_patch(self, *args, **kwargs)
    captured_results.append(res)
    return res

Patcher.apply_patch = patched_apply_patch

OLLAMA_ENDPOINT = "http://localhost:11434"

def make_ollama_generate(model_name: str):
    def ollama_generate(system_prompt: str, user_prompt: str, timeout: int = 1800) -> str:
        log_file = WORKSPACE_ROOT / "scratch/llm_trace.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- PROMPT TO {model_name} ---\nSYSTEM: {system_prompt}\nUSER: {user_prompt}\n")
            f.write("-" * 40 + "\n")

        print(f"  → Invoking local model: {model_name}...", flush=True)
        
        # 針對 gemma 12B 等本機大模型施加嚴格的 num_ctx 與 timeout 防護以防 OS Hang
        is_large_model = "gemma" in model_name.lower() or "12b" in model_name.lower() or "14b" in model_name.lower()
        ctx_val = 4096 if is_large_model else 32768
        predict_val = 768 if is_large_model else 8192
        timeout_val = 300 if is_large_model else timeout
        
        payload = json.dumps({
            "model": model_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": ctx_val,
                "num_predict": predict_val,
            }
        }).encode()

        try:
            req = urllib.request.Request(
                f"{OLLAMA_ENDPOINT}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_val) as resp:
                data = json.loads(resp.read())
                res = data.get("response", "")
                print(f"  → Response received ({len(res)} chars)", flush=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"RESPONSE:\n{res}\n")
                    f.write("=" * 80 + "\n")
                return res
        except Exception as e:
            print(f"  ❌ Ollama Error: {e}", flush=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"ERROR: {e}\n")
                f.write("=" * 80 + "\n")
            return ""
    return ollama_generate

def run_git(args, cwd):
    print(f"  [git] Running: git {' '.join(args)} in {cwd}")
    res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [git] Warning/Error: {res.stderr.strip()}")
    return res

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, choices=["7b", "14b"], required=True)
    args = parser.parse_args()

    model_map = {
        "7b": "qwen2.5-coder:7b",
        "14b": "gemma4-coder-12b-q4km:latest"
    }
    model_name = model_map[args.model]
    phase_name = "c4_7b" if args.model == "7b" else "c5_gemma4_12b"
    
    print(f"==================================================")
    print(f"🏁 Starting Repair Execution for Model: {model_name} ({phase_name})")
    print(f"==================================================")

    tasks = [
        {
            "task_id": "C_13453",
            "instance_id": "astropy__astropy-13453",
            "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/astropy",
            "base_commit": "19cc804717",
            "target_file": "astropy/io/ascii/html.py",
            "python_executable": "/Users/jameschen/Workspace/nexus/.venv_astropy/bin/python3",
            "problem_statement": (
                "astropy__astropy-13453: Table.write with format='ascii.html' ignores the 'formats' parameter.\n"
                "When writing a table to HTML format using Table.write(..., format='ascii.html', formats={'col': '%.2f'}), "
                "the specified column format is ignored. It should format the column values accordingly inside the HTML table cells."
            ),
            "repro_script": (
                "from astropy.table import Table\n"
                "import sys\n"
                "def test_repro():\n"
                "    t = Table([[1.12345]], names=['a'])\n"
                "    import io\n"
                "    out = io.StringIO()\n"
                "    t.write(out, format='ascii.html', formats={'a': '%.2f'})\n"
                "    html = out.getvalue()\n"
                "    print('HTML Output:')\n"
                "    print(html)\n"
                "    if '<td>1.12</td>' not in html:\n"
                "        raise AssertionError('formats={\"a\": \"%.2f\"} was ignored!')\n"
                "    print('SUCCESS: formats respected.')\n"
                "if __name__ == '__main__':\n"
                "    try:\n"
                "        test_repro()\n"
                "        sys.exit(0)\n"
                "    except Exception as e:\n"
                "        print(f'FAILURE: {e}')\n"
                "        sys.exit(1)\n"
            )
        },
        {
            "task_id": "C_11618",
            "instance_id": "sympy__sympy-11618",
            "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/sympy",
            "base_commit": "d4f8832c21",
            "target_file": "sympy/geometry/point.py",
            "python_executable": "/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3",
            "problem_statement": (
                "Point.distance zips coordinates, and does not check for dimension mismatch.\n"
                "For example, Point(2,0).distance(Point(1,0,2)) returns 1 instead of raising ValueError.\n"
                "It should check for dimension mismatch and raise ValueError."
            ),
            "repro_script": (
                "import sys\n"
                "sys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\n"
                "from sympy import Point\n"
                "def test_repro():\n"
                "    p1 = Point(2, 0)\n"
                "    p2 = Point(1, 0, 2)\n"
                "    try:\n"
                "        dist = p1.distance(p2)\n"
                "        print(f'Calculated distance: {dist}')\n"
                "        if dist == 1:\n"
                "            print('FAILURE: Point.distance zipped coordinates without checking dimensions, returned 1.')\n"
                "            sys.exit(1)\n"
                "        else:\n"
                "            print('SUCCESS: Dimensions mismatch handled or distance correctly calculated in higher dimension.')\n"
                "            sys.exit(0)\n"
                "    except ValueError as e:\n"
                "        print(f'SUCCESS: ValueError raised as expected for dimension mismatch: {e}')\n"
                "        sys.exit(0)\n"
                "    except Exception as e:\n"
                "        print(f'FAILURE: Unexpected exception: {e}')\n"
                "        sys.exit(1)\n"
                "if __name__ == '__main__':\n"
                "    test_repro()\n"
            )
        },
        {
            "task_id": "C_12481",
            "instance_id": "sympy__sympy-12481",
            "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/sympy",
            "base_commit": "c807dfe756",
            "target_file": "sympy/combinatorics/permutations.py",
            "python_executable": "/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3",
            "problem_statement": (
                "Permutation should allow non-disjoint lists in arguments.\n"
                "Currently, Permutation([[0, 1], [0, 2]]) raises a ValueError: 'there were repeated elements'.\n"
                "It should allow repeated elements and multiply them as disjoint cycles (i.e. resolve cycles like Cycle(0, 1)(0, 2) = Permutation(0, 1, 2))."
            ),
            "repro_script": (
                "import sys\n"
                "sys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\n"
                "from sympy.combinatorics import Permutation\n"
                "def test_repro():\n"
                "    try:\n"
                "        p = Permutation([[0, 1], [0, 2]])\n"
                "        print(f'Calculated permutation: {p}')\n"
                "        if p == Permutation(0, 1, 2):\n"
                "            print('SUCCESS: Permutation allowed non-disjoint lists and calculated correctly.')\n"
                "            sys.exit(0)\n"
                "        else:\n"
                "            print('FAILURE: Permutation calculated incorrectly.')\n"
                "            sys.exit(1)\n"
                "    except ValueError as e:\n"
                "        if 'there were repeated elements' in str(e):\n"
                "            print(f'BUG PRESENT: ValueError raised for repeated elements: {e}')\n"
                "            sys.exit(1)\n"
                "        else:\n"
                "            print(f'FAILURE: Unexpected ValueError: {e}')\n"
                "            sys.exit(1)\n"
                "    except Exception as e:\n"
                "        print(f'FAILURE: Unexpected exception: {e}')\n"
                "        sys.exit(1)\n"
                "if __name__ == '__main__':\n"
                "    test_repro()\n"
            )
        }
    ]

    pipeline = HealPipeline(ollama_generate_fn=make_ollama_generate(model_name))

    results_rollup = []

    for t in tasks:
        print(f"\n--------------------------------------------------")
        print(f"👉 Executing task: {t['task_id']} ({t['instance_id']})")
        print(f"--------------------------------------------------")

        # 1. Clean & Checkout workspace
        run_git(["checkout", "--", "."], t["repo_dir"])
        run_git(["clean", "-fd"], t["repo_dir"])
        run_git(["checkout", t["base_commit"]], t["repo_dir"])

        # 2. Inject AST Sliced Context
        sliced_context_file = WORKSPACE_ROOT / f"artifacts/runtime/c3_ast_slicing_metrics_v0/{t['task_id']}/sliced_context.py"
        if sliced_context_file.exists():
            print(f"  → Sliced context found, injecting AST Sliced Context...")
            sliced_content = sliced_context_file.read_text(encoding="utf-8")
        else:
            print(f"  ⚠️ Warning: Sliced context not found! Reading original target file...")
            sliced_content = (t["repo_dir"] / t["target_file"]).read_text(encoding="utf-8")

        # Clear global captured results
        global captured_results
        captured_results = []

        ctx = HealContext(
            instance_id=t["instance_id"],
            repo_dir=t["repo_dir"],
            problem_statement=t["problem_statement"],
            repro_script=t["repro_script"],
            max_tries=3
        )
        ctx.localized_files = [LocalizedFile(path=t["target_file"], content=sliced_content, relevance_score=1.0)]
        ctx.python_executable = t["python_executable"]

        # Run pipeline
        try:
            print(f"  → Running HealPipeline...")
            result_ctx = pipeline.run(ctx)
            success = result_ctx.solve_eligible
        except Exception as e:
            print(f"  ❌ Pipeline Crash: {e}")
            success = False
            result_ctx = ctx

        print(f"  → Solve Eligible: {success}")

        # Save artifacts
        output_dir = WORKSPACE_ROOT / f"artifacts/runtime/{phase_name}_repair_v0/{t['task_id']}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write patch file
        patch_content = result_ctx.final_patch or ""
        (output_dir / "patch.diff").write_text(patch_content, encoding="utf-8")
        
        # Write repro evidence
        repro_evidence = result_ctx.repro_evidence or ""
        (output_dir / "repro_evidence.log").write_text(repro_evidence, encoding="utf-8")

        # Write verification report
        eval_report = result_ctx.evaluation_report or ""
        (output_dir / "verification_report.json").write_text(eval_report, encoding="utf-8")

        # Write receipt
        receipt = {
            "name": "local_heal",
            "task_id": t["task_id"],
            "instance_id": t["instance_id"],
            "model": model_name,
            "gate_passed": success,
            "attempts": result_ctx.attempt - 1 if hasattr(result_ctx, "attempt") else 0,
            "reasoning_mode": result_ctx.reasoning_mode if hasattr(result_ctx, "reasoning_mode") else "INTUITIVE",
            "error_summary": [str(e.message) for e in result_ctx.errors] if hasattr(result_ctx, "errors") else []
        }
        
        if captured_results:
            last_res = captured_results[-1]
            for r in reversed(captured_results):
                if r.success:
                    last_res = r
                    break
            receipt["is_auto_corrected"] = getattr(last_res, "is_auto_corrected", False)
            receipt["similarity"] = getattr(last_res, "similarity", 1.0)
            receipt["resolved_span"] = list(getattr(last_res, "resolved_span", [0, 0]))

        (output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))

        results_rollup.append({
            "task_id": t["task_id"],
            "instance_id": t["instance_id"],
            "model": model_name,
            "success": success,
            "attempts": receipt["attempts"],
            "is_auto_corrected": receipt.get("is_auto_corrected", False)
        })

        # Restore workspace
        run_git(["checkout", "--", "."], t["repo_dir"])
        run_git(["clean", "-fd"], t["repo_dir"])

    # Write rollup metrics JSON
    with open(WORKSPACE_ROOT / f"artifacts/runtime/{phase_name}_repair_v0/repair_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "status": "REPAIR_COMPLETED",
            "phase": phase_name,
            "model": model_name,
            "results": results_rollup
        }, f, indent=2, ensure_ascii=False)

    print(f"\n==================================================")
    print(f"🎉 All repairs finished for model: {model_name}!")
    print(f"Results summary:")
    for r in results_rollup:
        print(f"  * {r['task_id']} ({r['instance_id']}): {'SUCCESS' if r['success'] else 'FAILED'} (Attempts: {r['attempts']})")
    print(f"==================================================")

if __name__ == "__main__":
    main()
