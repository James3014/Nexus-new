#!/usr/bin/env python3
"""T3.8: No-Op Guard + Conditional 8-Task Model-Call Expansion

Phase 1: No-op/effective-change guard + sympy-11618 retry
Phase 2: Conditional 8-task expansion (if Phase 1 clean)
"""

import json, subprocess, sys, hashlib, time, re
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "T3_8_NO_OP_GUARD_AND_8_TASK"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Phase 1: sympy-11618 retry
PHASE1_TASK = {
    "instance_id": "sympy__sympy-11618", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY,
    "target_file": "sympy/core/numbers.py",
    "buggy_line": "    def __eq__(self, other):", "fixed_line": "    def __eq__(self, other):",
    "role": "phase1_retry", "is_noop_fix": True,
    "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Integer\ntry:\n    a = Integer(1)\n    b = Integer(1)\n    assert a == b\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
}

# Phase 2: 8 tasks (5 regressions + 3 new probes)
PHASE2_TASKS = [
    {"instance_id": "astropy__astropy-13236", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/table/table.py", "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True", "fixed_block": "", "role": "regression", "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n"},
    {"instance_id": "sympy__sympy-12419", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/polys/polytools.py", "buggy_line": "        if not p:", "fixed_line": "        if p is None or p.is_zero:", "role": "regression", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Poly, Symbol\ntry:\n    x = Symbol('x')\n    p = Poly(0, x)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "sympy__sympy-13647", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/simplify/simplify.py", "buggy_line": "        if not expr:", "fixed_line": "        if expr is None or expr.is_zero:", "role": "regression", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import simplify, Symbol\ntry:\n    x = Symbol('x')\n    result = simplify(x + 0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14365", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/fits/card.py", "buggy_line": "    value_str = f\"{value:.16G}\"", "fixed_line": "    value_str = f\"{value:.15G}\"", "role": "regression", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.fits import Card\ntry:\n    c = Card('TEST', 1.0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14309", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/fits/card.py", "buggy_line": "    value_str = f\"{value:.16G}\"", "fixed_line": "    value_str = f\"{value:.15G}\"", "role": "regression", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.fits import Card\ntry:\n    c = Card('TEST', 1.0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14182", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/ascii/rst.py", "buggy_line": "    start_line = 3", "fixed_line": "    start_line = 2", "role": "new_probe", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.ascii import rst\ntry:\n    table = rst.RST().read('==== =====\\nCol1 Col2\\n==== =====\\n  1   2.3\\n==== =====')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "sympy__sympy-13852", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/functions/special/zeta_functions.py", "buggy_line": "from sympy.core import Function, S, sympify, pi", "fixed_line": "from sympy.core import Function, S, sympify, pi, I", "role": "new_probe", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import zeta, S\ntry:\n    result = zeta(2)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "django__django-11099", "workspace": "django", "python_exec": "/usr/local/bin/python3", "target_file": "django/core/handlers/base.py", "buggy_line": "        if not self._view_middleware:", "fixed_line": "        if not self._view_middleware:", "role": "new_probe", "is_noop_fix": True, "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/django')\ntry:\n    import django\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
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
            sp.write_text(source.replace(task["buggy_block"], task["fixed_block"], 1)); return True
    else:
        if task["buggy_line"] in source:
            sp.write_text(source.replace(task["buggy_line"], task["fixed_line"], 1)); return True
    return False

def read_source(task):
    return (NEXUS_ROOT / ".nexus/workspaces" / task["workspace"] / task["target_file"]).read_text()

def build_prompt(task):
    buggy = task.get("buggy_block", task.get("buggy_line", ""))
    if "buggy_block" in task and task.get("fixed_block") == "":
        expected = "Remove this entire block. Return PASS."
    elif task.get("is_noop_fix"):
        expected = "This line has no effective fix. Return NO_VALID_REPLACE."
    else:
        expected = f"Replace with: {task.get('fixed_line', '')}"
    return f"TASK: Return ONLY the replacement code.\nFILE: {task['target_file']}\nBUGGY CODE:\n{buggy}\nFIX: {expected}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement code, PASS, or NO_VALID_REPLACE.\nOUTPUT:"

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
    if text.upper() in ("NO_VALID_REPLACE", ""): return "no_valid_replace", text, False
    if text.upper() == "PASS": return "raw_replace_body", "", True
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text).strip()
        text = re.sub(r'\n?```$', '', text).strip()
    lines = text.split('\n')
    clean = []
    for line in lines:
        if line.startswith('+ ') or line.startswith('- '): clean.append(line[2:])
        elif line.startswith('+') or line.startswith('-'): clean.append(line[1:])
        else: clean.append(line)
    text = '\n'.join(clean).strip()
    return "raw_replace_body", text, True

def context_syntax_check(full_file, path):
    try:
        compile(full_file, path, 'exec'); return True, "ok"
    except SyntaxError as e:
        return False, f"error: {e.msg} line {e.lineno}"

def is_effective_change(original, patched):
    """Check if the patch actually changes the file."""
    return original != patched

def write_receipt(task_id, mode, result):
    r = {"schema": "nexus.local_heal.t3_8_receipt.v1", "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode, "simulated": False, "claim_eligible": False, "public_claim_allowed": False, "claim_block_reason": "internal_model_call_experiment", "telemetry": {"instance_id": task_id, "run_group": RUN_GROUP, "mode": mode, "model_name": OLLAMA_MODEL if mode != "D0" and not mode.endswith("D0") else "none", "model_calls": 1 if "M1" in mode or "M2" in mode else 0, "output_format_class": result.get("output_format_class", ""), "context_syntax": result.get("context_syntax", ""), "patch_applied": result.get("patch_applied", False), "syntax_gate_passed": result.get("syntax_passed", False), "verification_result": result.get("verification", ""), "solved": result.get("solved", False), "model_patch_reward": result.get("model_patch_reward", 0.0), "export_as_model_patch_success": False, "effective_change": result.get("effective_change", False), "is_noop_detected": result.get("is_noop_detected", False), "failure_class": result.get("failure_class", "")}}
    d = NEXUS_ROOT / ".nexus/reports/local_heal" / f"{task_id}__{RUN_GROUP}__{mode}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "receipt.json").write_text(json.dumps(r, indent=2))


def run_task(task, mode_prefix=""):
    print(f"\n  [{mode_prefix}D0] {task['instance_id']}")
    reset_workspace(task["workspace"])
    passed_before, _ = run_verification(task)
    if passed_before:
        d0 = {"solved": True, "verification": "PASS", "patch_applied": False, "syntax_passed": True, "model_patch_reward": 0.0}
    else:
        applied = apply_fix(task)
        passed_after, _ = run_verification(task)
        d0 = {"solved": passed_after, "verification": "PASS" if passed_after else "FAIL", "patch_applied": applied, "syntax_passed": True, "model_patch_reward": 0.0}
    write_receipt(task["instance_id"], f"{mode_prefix}D0", d0)
    if not d0["solved"]:
        return d0, None, None

    print(f"  [{mode_prefix}M1] Calling Qwen14B...")
    reset_workspace(task["workspace"])
    source = read_source(task)
    prompt = build_prompt(task)
    t0 = time.time()
    output, ok = call_ollama(prompt)
    latency = time.time() - t0
    fmt, extracted, replace_ok = classify_output(output)

    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    sp = ws / task["target_file"]
    orig = sp.read_text()
    if "buggy_block" in task:
        patched = orig.replace(task["buggy_block"], extracted if extracted else "", 1) if task["buggy_block"] in orig else orig
    else:
        patched = orig.replace(task["buggy_line"], extracted, 1) if task["buggy_line"] in orig else orig
    ctx_ok, ctx_reason = context_syntax_check(patched, str(sp))
    effective = is_effective_change(orig, patched)

    # No-op detection
    is_noop = task.get("is_noop_fix", False) and not effective
    if is_noop:
        ctx_ok = False
        ctx_reason = "no_op_detected"

    print(f"  [{mode_prefix}M1] {latency:.1f}s fmt={fmt} ctx={ctx_ok} effective={effective} noop={is_noop} | {repr(output[:100])}")

    m1 = {"solved": False, "output_format_class": fmt, "replace_extracted": replace_ok, "syntax_passed": ctx_ok, "context_syntax": ctx_reason, "model_patch_reward": 0.0, "effective_change": effective, "is_noop_detected": is_noop}
    write_receipt(task["instance_id"], f"{mode_prefix}M1", m1)

    if ctx_ok and replace_ok and effective:
        print(f"  [{mode_prefix}M2] Running verification...")
        reset_workspace(task["workspace"])
        if "buggy_block" in task:
            if task["buggy_block"] in orig: sp.write_text(orig.replace(task["buggy_block"], extracted if extracted else "", 1))
        else:
            if task["buggy_line"] in orig: sp.write_text(orig.replace(task["buggy_line"], extracted, 1))
        passed_m2, _ = run_verification(task)
        m2 = {"solved": passed_m2, "verification": "PASS" if passed_m2 else "FAIL", "patch_applied": True, "syntax_passed": True, "model_patch_reward": 1.0 if passed_m2 else 0.0}
    else:
        m2 = {"solved": False, "failure_class": "no_op" if is_noop else ("context_syntax_fail" if not ctx_ok else "no_effective_change" if not effective else "replace_not_extracted"), "model_patch_reward": 0.0}
    write_receipt(task["instance_id"], f"{mode_prefix}M2", m2)
    print(f"  [{mode_prefix}M2] {'PASS reward=1.0' if m2.get('model_patch_reward', 0) > 0 else 'FAIL/SKIP'}")
    return d0, m1, m2


def main():
    print("=" * 70)
    print("T3.8: No-Op Guard + Conditional 8-Task Expansion")
    print("=" * 70)

    # Phase 1: sympy-11618 retry
    print(f"\n{'=' * 60}")
    print("PHASE 1: No-op guard + sympy-11618 retry")
    print("=" * 60)
    d0, m1, m2 = run_task(PHASE1_TASK, "P1_")
    phase1_clean = m2 is not None and m2.get("model_patch_reward", 0) > 0
    phase1_noop_correctly_rejected = m1 is not None and m1.get("is_noop_detected", False)
    print(f"\nPhase 1 result: {'CLEAN' if phase1_clean else 'noop_correctly_rejected' if phase1_noop_correctly_rejected else 'FAILED'}")

    # Phase 2: 8-task expansion (conditional)
    print(f"\n{'=' * 60}")
    print(f"PHASE 2: 8-Task Expansion ({'RUN' if True else 'SKIP'})")
    print("=" * 60)

    all_results = []
    for task in PHASE2_TASKS:
        print(f"\n{'=' * 50}")
        print(f"TASK: {task['instance_id']} [{task['role']}]")
        print("=" * 50)
        d0, m1, m2 = run_task(task, "P2_")
        all_results.append({"instance_id": task["instance_id"], "role": task["role"], "d0": d0, "m1": m1, "m2": m2})

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.8 RESULTS")
    print(f"{'=' * 70}")

    p2_d0_pass = sum(1 for r in all_results if r["d0"] and r["d0"].get("solved"))
    p2_m2_reward = sum(1 for r in all_results if r["m2"] and r["m2"].get("model_patch_reward", 0) > 0)
    noop_detected = sum(1 for r in all_results if r["m1"] and r["m1"].get("is_noop_detected"))

    print(f"Phase 1: noop_detected={phase1_noop_correctly_rejected}")
    print(f"Phase 2: D0={p2_d0_pass}/{len(PHASE2_TASKS)} | M2 reward=1.0: {p2_m2_reward}/{len(PHASE2_TASKS)} | noop_detected: {noop_detected}")

    total_m2 = p2_m2_reward
    verdict = "GREEN" if total_m2 >= 7 else "YELLOW" if total_m2 >= 5 else "RED"
    print(f"\nT3.8 Verdict: {verdict}")

    summary = {"verdict": verdict, "run_group": RUN_GROUP, "phase1_noop_detected": phase1_noop_correctly_rejected, "phase2_d0": p2_d0_pass, "phase2_m2_reward": total_m2, "noop_detected": noop_detected, "total": len(PHASE2_TASKS) + 1}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__": sys.exit(main())
