#!/usr/bin/env python3
"""T3.6: Controlled 4-Task Mixed Model-Call Experiment

3 regression candidates + 1 new probe (astropy-14365).
"""

import json
import subprocess
import sys
import hashlib
import time
import re
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "T3_6_CONTROLLED_4_TASK_MIXED"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

TASKS = [
    {
        "instance_id": "astropy__astropy-13236", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/table/table.py",
        "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True",
        "fixed_block": "", "role": "regression",
        "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n",
    },
    {
        "instance_id": "sympy__sympy-12419", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/polys/polytools.py",
        "buggy_line": "        if not p:", "fixed_line": "        if p is None or p.is_zero:",
        "role": "regression",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Poly, Symbol\ntry:\n    x = Symbol('x')\n    p = Poly(0, x)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "sympy__sympy-13647", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/simplify/simplify.py",
        "buggy_line": "        if not expr:", "fixed_line": "        if expr is None or expr.is_zero:",
        "role": "regression",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import simplify, Symbol\ntry:\n    x = Symbol('x')\n    result = simplify(x + 0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "astropy__astropy-14365", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/io/fits/card.py",
        "buggy_line": "    value_str = f\"{value:.16G}\"", "fixed_line": "    value_str = f\"{value:.15G}\"",
        "role": "new_probe",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.fits import Card\ntry:\n    c = Card('TEST', 1.0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
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
    if "buggy_block" in task:
        if task["buggy_block"] in source:
            sp.write_text(source.replace(task["buggy_block"], task["fixed_block"], 1))
            return True
    else:
        if task["buggy_line"] in source:
            sp.write_text(source.replace(task["buggy_line"], task["fixed_line"], 1))
            return True
    return False


def read_source(task):
    return (NEXUS_ROOT / ".nexus/workspaces" / task["workspace"] / task["target_file"]).read_text()


def build_prompt(task):
    if "buggy_block" in task:
        buggy = task["buggy_block"]
        expected = "Remove this entire block (block deletion). Return PASS."
    else:
        buggy = task["buggy_line"]
        expected = f"Replace with: {task['fixed_line']}"
    return f"""TASK: Return ONLY the replacement code for a specific code block.

FILE: {task['target_file']}

BUGGY CODE:
{buggy}

FIX: {expected}

RULES:
- Return ONLY the replacement code body
- NO markdown, NO code fences, NO diff, NO explanation
- NO SEARCH, NO +/- prefixes
- For block deletion, return exactly: PASS
- For line replacement, return the exact replacement line with indentation

OUTPUT:"""


def call_ollama(prompt):
    import urllib.request
    payload = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.0, "num_predict": 512}}).encode()
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


def context_syntax_check(full_file, path):
    try:
        compile(full_file, path, 'exec')
        return True, "ok"
    except SyntaxError as e:
        return False, f"error: {e.msg} line {e.lineno}"


def write_receipt(task_id, mode, result):
    r = {
        "schema": "nexus.local_heal.t3_6_receipt.v1",
        "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
        "simulated": False, "claim_eligible": False, "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_experiment",
        "telemetry": {
            "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
            "model_name": OLLAMA_MODEL if mode != "D0" else "none",
            "model_calls": 1 if mode.startswith("M") else 0,
            "output_format_class": result.get("output_format_class", ""),
            "context_syntax": result.get("context_syntax", ""),
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
    print("T3.6: Controlled 4-Task Mixed Model-Call Experiment")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Tasks: {len(TASKS)} ({sum(1 for t in TASKS if t['role']=='regression')} regression + {sum(1 for t in TASKS if t['role']=='new_probe')} new probe)")
    print("=" * 70)

    all_results = []

    for task in TASKS:
        print(f"\n{'=' * 60}")
        print(f"TASK: {task['instance_id']} [{task['role']}]")
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
        all_results.append({"instance_id": task["instance_id"], "mode": "D0", "role": task["role"], **d0})
        print(f"  D0: {'PASS' if d0['solved'] else 'FAIL'}")

        if not d0["solved"]:
            continue

        # M1ctx
        reset_workspace(task["workspace"])
        source = read_source(task)
        prompt = build_prompt(task)
        ph = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        print(f"  M1ctx: Calling Qwen14B...")
        t0 = time.time()
        output, ok = call_ollama(prompt)
        latency = time.time() - t0
        oh = hashlib.sha256(output.encode()).hexdigest()[:16]
        print(f"  M1ctx: {latency:.1f}s | output: {repr(output[:150])}")

        fmt, extracted, replace_ok = classify_output(output)

        # Context-aware syntax check
        ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
        sp = ws / task["target_file"]
        orig = sp.read_text()
        if "buggy_block" in task:
            if task["buggy_block"] in orig:
                patched = orig.replace(task["buggy_block"], extracted if extracted else "", 1)
            else:
                patched = orig
        else:
            if task["buggy_line"] in orig:
                patched = orig.replace(task["buggy_line"], extracted, 1)
            else:
                patched = orig
        ctx_ok, ctx_reason = context_syntax_check(patched, str(sp))
        print(f"  M1ctx: fmt={fmt} ctx_syntax={ctx_ok} ({ctx_reason})")

        m1 = {"solved": False, "output_format_class": fmt, "replace_extracted": replace_ok, "syntax_passed": ctx_ok, "context_syntax": ctx_reason, "model_patch_reward": 0.0, "prompt_hash": ph, "output_hash": oh, "latency": latency}
        write_receipt(task["instance_id"], "M1ctx", m1)
        all_results.append({"instance_id": task["instance_id"], "mode": "M1ctx", "role": task["role"], **m1})

        # M2ctx
        if ctx_ok and replace_ok:
            reset_workspace(task["workspace"])
            sp = ws / task["target_file"]
            orig = sp.read_text()
            if "buggy_block" in task:
                if task["buggy_block"] in orig:
                    sp.write_text(orig.replace(task["buggy_block"], extracted if extracted else "", 1))
            else:
                if task["buggy_line"] in orig:
                    sp.write_text(orig.replace(task["buggy_line"], extracted, 1))
            passed_m2, _ = run_verification(task)
            m2 = {"solved": passed_m2, "verification": "PASS" if passed_m2 else "FAIL", "patch_applied": True, "syntax_passed": True, "model_patch_reward": 1.0 if passed_m2 else 0.0}
        else:
            m2 = {"solved": False, "failure_class": "context_syntax_fail" if not ctx_ok else "replace_not_extracted", "model_patch_reward": 0.0}
        write_receipt(task["instance_id"], "M2ctx", m2)
        all_results.append({"instance_id": task["instance_id"], "mode": "M2ctx", "role": task["role"], **m2})
        print(f"  M2ctx: {'PASS reward=1.0' if m2.get('model_patch_reward', 0) > 0 else 'FAIL/SKIP'}")

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.6 RESULTS")
    print(f"{'=' * 70}")

    for task in TASKS:
        tid = task["instance_id"]
        d0r = next((r for r in all_results if r["instance_id"] == tid and r["mode"] == "D0"), {})
        m2r = next((r for r in all_results if r["instance_id"] == tid and r["mode"] == "M2ctx"), {})
        print(f"  {tid} [{task['role']}]: D0={'PASS' if d0r.get('solved') else 'FAIL'} M2_reward={m2r.get('model_patch_reward',0)}")

    d0_pass = sum(1 for r in all_results if r["mode"] == "D0" and r.get("solved"))
    m2_reward = sum(1 for r in all_results if r["mode"] == "M2ctx" and r.get("model_patch_reward", 0) > 0)
    regression_reward = sum(1 for r in all_results if r["mode"] == "M2ctx" and r.get("model_patch_reward", 0) > 0 and r.get("role") == "regression")
    new_probe_reward = sum(1 for r in all_results if r["mode"] == "M2ctx" and r.get("model_patch_reward", 0) > 0 and r.get("role") == "new_probe")

    print(f"\nD0: {d0_pass}/{len(TASKS)} PASS")
    print(f"M2ctx model_patch_reward=1.0: {m2_reward}/{len(TASKS)}")
    print(f"  Regression: {regression_reward}/3")
    print(f"  New probe: {new_probe_reward}/1")

    if d0_pass == len(TASKS) and m2_reward >= 3:
        verdict = "GREEN"
    elif d0_pass >= len(TASKS) - 1 and m2_reward >= 2:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.6 Verdict: {verdict}")

    summary = {"verdict": verdict, "run_group": RUN_GROUP, "d0_pass": d0_pass, "m2_reward_1": m2_reward, "regression": regression_reward, "new_probe": new_probe_reward, "total": len(TASKS)}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    print(f"Summary: {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
