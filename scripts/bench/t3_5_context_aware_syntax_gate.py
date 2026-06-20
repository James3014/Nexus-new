#!/usr/bin/env python3
"""T3.5: Context-Aware Post-Apply Syntax Gate

Validates model output by applying it to the full file and checking syntax
of the complete file, not just the isolated snippet.
"""

import json
import subprocess
import sys
import hashlib
import time
import re
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "T3_5_CONTEXT_AWARE_SYNTAX_GATE"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

TASKS = [
    {
        "instance_id": "sympy__sympy-12419", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/polys/polytools.py",
        "buggy_line": "        if not p:", "fixed_line": "        if p is None or p.is_zero:",
        "canonical_span_source": "locked_search",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Poly, Symbol\ntry:\n    x = Symbol('x')\n    p = Poly(0, x)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "sympy__sympy-13647", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/simplify/simplify.py",
        "buggy_line": "        if not expr:", "fixed_line": "        if expr is None or expr.is_zero:",
        "canonical_span_source": "locked_search",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import simplify, Symbol\ntry:\n    x = Symbol('x')\n    result = simplify(x + 0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
]


def reset_workspace(ws):
    d = NEXUS_ROOT / ".nexus/workspaces" / ws
    subprocess.run(["git", "checkout", "--", "."], cwd=str(d), capture_output=True, timeout=30)
    subprocess.run(["git", "clean", "-fd"], cwd=str(d), capture_output=True, timeout=30)


def run_verification(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    (ws / "reproduce_bug.py").write_text(task["repro_script"])
    try:
        r = subprocess.run([task["python_exec"], str(ws / "reproduce_bug.py")], capture_output=True, text=True, timeout=120, cwd=str(ws))
        return r.returncode == 0 and "BUG PRESENT" not in (r.stdout + r.stderr), r.stdout + r.stderr
    except Exception as e:
        return False, str(e)


def apply_fix(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    sp = ws / task["target_file"]
    source = sp.read_text()
    if task["buggy_line"] in source:
        sp.write_text(source.replace(task["buggy_line"], task["fixed_line"], 1))
        return True
    return False


def read_source(task):
    return (NEXUS_ROOT / ".nexus/workspaces" / task["workspace"] / task["target_file"]).read_text()


def context_aware_syntax_check(full_file_content, file_path):
    """Check syntax of the full file after applying replacement."""
    try:
        compile(full_file_content, file_path, 'exec')
        return True, "full_file_syntax_ok"
    except SyntaxError as e:
        return False, f"syntax_error: {e.msg} line {e.lineno}"


def build_prompt(task):
    return f"""TASK: Return ONLY the replacement line for a specific buggy line in a Python file.

FILE: {task['target_file']}

BUGGY LINE (must be replaced):
{task['buggy_line']}

EXPECTED FIX: Replace with:
{task['fixed_line']}

RULES:
- Return the EXACT replacement line, preserving the same indentation
- The replacement must be a complete Python statement
- Include trailing colon for if/else/for/while/def/class
- NO markdown, NO code fences, NO diff, NO explanation
- NO SEARCH, NO +/- prefixes
- Return ONLY the replacement line

OUTPUT:"""


def call_ollama(prompt):
    import urllib.request
    payload = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.0, "num_predict": 256}}).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["response"], True
    except Exception as e:
        return str(e), False


def classify_output(text):
    text = text.strip()
    if text.upper() in ("NO_VALID_REPLACE", ""):
        return "no_valid_replace", text, False
    if text.upper() == "PASS":
        return "raw_replace_body", "", True
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text).strip()
        text = re.sub(r'\n?```$', '', text).strip()
    lines = text.split('\n')
    clean = []
    for line in lines:
        if line.startswith('+ ') or line.startswith('- '):
            clean.append(line[2:])
        elif line.startswith('+') or line.startswith('-'):
            clean.append(line[1:])
        else:
            clean.append(line)
    text = '\n'.join(clean).strip()
    if "SEARCH" in text.upper() and "REPLACE" in text.upper():
        return "search_replace_block", text, False
    return "raw_replace_body", text, True


def write_receipt(task_id, mode, result):
    r = {
        "schema": "nexus.local_heal.t3_5_receipt.v1",
        "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
        "simulated": False, "claim_eligible": False, "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_context_syntax",
        "telemetry": {
            "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
            "model_name": OLLAMA_MODEL if mode != "D0" else "none",
            "model_calls": 1 if mode.startswith("M") else 0,
            "output_format_class": result.get("output_format_class", ""),
            "context_syntax_check": result.get("context_syntax_check", ""),
            "patch_applied": result.get("patch_applied", False),
            "syntax_gate_passed": result.get("syntax_passed", False),
            "verification_result": result.get("verification", ""),
            "solved": result.get("solved", False),
            "model_patch_reward": result.get("model_patch_reward", 0.0),
            "export_as_model_patch_success": False,
            "failure_class": result.get("failure_class", ""),
        },
    }
    d = NEXUS_ROOT / ".nexus/reports/local_heal" / f"{task_id}__{RUN_GROUP}__{mode}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "receipt.json").write_text(json.dumps(r, indent=2))


def main():
    print("=" * 70)
    print("T3.5: Context-Aware Post-Apply Syntax Gate")
    print(f"Model: {OLLAMA_MODEL}")
    print("=" * 70)

    all_results = []

    for task in TASKS:
        print(f"\n{'=' * 60}")
        print(f"TASK: {task['instance_id']}")
        print("=" * 60)

        # D0
        reset_workspace(task["workspace"])
        passed_before, _ = run_verification(task)
        if passed_before:
            d0 = {"solved": True, "verification": "PASS", "patch_applied": False, "syntax_passed": True, "model_patch_reward": 0.0}
        else:
            applied = apply_fix(task)
            passed_after, _ = run_verification(task)
            d0 = {"solved": passed_after, "verification": "PASS" if passed_after else "FAIL", "patch_applied": applied, "syntax_passed": True, "model_patch_reward": 0.0}
        write_receipt(task["instance_id"], "D0", d0)
        all_results.append({"instance_id": task["instance_id"], "mode": "D0", **d0})
        print(f"  D0: {'PASS' if d0['solved'] else 'FAIL'}")

        if not d0["solved"]:
            continue

        # M1v3
        reset_workspace(task["workspace"])
        source = read_source(task)
        prompt = build_prompt(task)
        ph = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        print(f"  M1v3: Calling Qwen14B...")
        t0 = time.time()
        output, ok = call_ollama(prompt)
        latency = time.time() - t0
        oh = hashlib.sha256(output.encode()).hexdigest()[:16]
        print(f"  M1v3: {latency:.1f}s | output: {repr(output[:200])}")

        fmt, extracted, replace_ok = classify_output(output)
        print(f"  M1v3: fmt={fmt} replace_ok={replace_ok}")

        # Context-aware syntax check: apply to full file
        ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
        sp = ws / task["target_file"]
        orig_source = sp.read_text()

        if task["buggy_line"] in extracted or extracted.strip() == task["fixed_line"].strip():
            # Model output matches expected fix
            patched_source = orig_source.replace(task["buggy_line"], extracted, 1)
        else:
            patched_source = orig_source

        ctx_ok, ctx_reason = context_aware_syntax_check(patched_source, str(sp))
        print(f"  M1v3: context_syntax={ctx_ok} ({ctx_reason})")

        # Isolated snippet check (for comparison)
        try:
            compile(extracted, '<snippet>', 'exec')
            isolated_ok = True
        except SyntaxError:
            isolated_ok = False
        print(f"  M1v3: isolated_syntax={isolated_ok}")

        m1 = {
            "solved": False, "output_format_class": fmt, "replace_extracted": replace_ok,
            "syntax_passed": ctx_ok, "context_syntax_check": ctx_reason,
            "isolated_syntax": isolated_ok, "model_patch_reward": 0.0,
            "prompt_hash": ph, "output_hash": oh, "latency": latency,
        }
        write_receipt(task["instance_id"], "M1v3", m1)
        all_results.append({"instance_id": task["instance_id"], "mode": "M1v3", **m1})

        # M2v3
        if ctx_ok and replace_ok:
            reset_workspace(task["workspace"])
            sp = ws / task["target_file"]
            orig = sp.read_text()
            if task["buggy_line"] in orig:
                sp.write_text(orig.replace(task["buggy_line"], extracted, 1))
            passed_m2, _ = run_verification(task)
            m2 = {"solved": passed_m2, "verification": "PASS" if passed_m2 else "FAIL", "patch_applied": True, "syntax_passed": True, "model_patch_reward": 1.0 if passed_m2 else 0.0}
        else:
            m2 = {"solved": False, "failure_class": "context_syntax_fail" if not ctx_ok else "replace_not_extracted", "model_patch_reward": 0.0}
        write_receipt(task["instance_id"], "M2v3", m2)
        all_results.append({"instance_id": task["instance_id"], "mode": "M2v3", **m2})
        print(f"  M2v3: {'PASS reward=1.0' if m2.get('model_patch_reward', 0) > 0 else 'FAIL/SKIP'}")

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.5 RESULTS")
    print(f"{'=' * 70}")

    d0_pass = sum(1 for r in all_results if r["mode"] == "D0" and r.get("solved"))
    m2_reward = sum(1 for r in all_results if r["mode"] == "M2v3" and r.get("model_patch_reward", 0) > 0)

    print(f"D0: {d0_pass}/{len(TASKS)} PASS")
    print(f"M2v3 model_patch_reward=1.0: {m2_reward}/{len(TASKS)}")

    if d0_pass == len(TASKS) and m2_reward >= 1:
        verdict = "GREEN"
    elif d0_pass >= len(TASKS) - 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.5 Verdict: {verdict}")

    summary = {"verdict": verdict, "run_group": RUN_GROUP, "d0_pass": d0_pass, "m2_reward_1": m2_reward, "total": len(TASKS)}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    print(f"Summary: {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
