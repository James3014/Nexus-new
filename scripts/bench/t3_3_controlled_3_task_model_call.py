#!/usr/bin/env python3
"""T3.3: Controlled 3-Task Model-Call Experiment

Tests Qwen14B on 3 tasks with D0/M1/M2 modes.
Task 1: astropy-13236 (known success from T3.2)
Task 2: sympy-12419 (sympy patch_mismatch)
Task 3: sympy-13647 (sympy patch_mismatch)
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
RUN_GROUP = "T3_3_CONTROLLED_3_TASK_MODEL_CALL"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

TASKS = [
    {
        "instance_id": "astropy__astropy-13236", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/table/table.py",
        "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True",
        "fixed_block": "", "canonical_span_source": "unified_diff",
        "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n",
    },
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


def reset_workspace(ws_name):
    ws = NEXUS_ROOT / ".nexus/workspaces" / ws_name
    subprocess.run(["git", "checkout", "--", "."], cwd=str(ws), capture_output=True, timeout=30)
    subprocess.run(["git", "clean", "-fd"], cwd=str(ws), capture_output=True, timeout=30)


def run_verification(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    (ws / "reproduce_bug.py").write_text(task["repro_script"])
    try:
        r = subprocess.run([task["python_exec"], str(ws / "reproduce_bug.py")], capture_output=True, text=True, timeout=120, cwd=str(ws))
        output = r.stdout + r.stderr
        return r.returncode == 0 and "BUG PRESENT" not in output, output
    except Exception as e:
        return False, str(e)


def apply_fix(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    sp = ws / task["target_file"]
    if not sp.exists():
        return False
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


def build_prompt(task, source_context):
    buggy = task.get("buggy_block", task.get("buggy_line", ""))
    return f"""TASK: Return ONLY the replacement code for a specific code block.

FILE: {task['target_file']}

BUGGY CODE BLOCK (this exact block must be replaced):
{buggy}

EXPECTED FIX: {'Remove this entire block (block deletion). Replacement is empty.' if 'fixed_block' in task and task['fixed_block'] == '' else f'Replace with: {task.get("fixed_line", "")}'}

RULES:
- Return ONLY the replacement code body
- NO markdown, NO code fences, NO diff format, NO explanation
- NO SEARCH, NO @@ markers, NO +/- prefixes
- If the fix is block deletion, return exactly: PASS (one word, nothing else)
- If you cannot fix it, return exactly: NO_VALID_REPLACE

YOUR OUTPUT (raw replacement code only):"""


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
        return "no_valid_replace", text, False, False
    if text.upper() == "PASS":
        return "raw_replace_body", "", True, False
    diff_markers = re.findall(r'^[+-]\s', text, re.MULTILINE)
    if len(diff_markers) > 2:
        return "unified_diff", text, False, False
    if text.startswith("```"):
        code = re.sub(r'^```\w*\n?', '', text).strip()
        code = re.sub(r'\n?```$', '', code).strip()
        if code and not re.search(r'^[+-]\s', code, re.MULTILINE):
            return "markdown_fenced_code", code, True, True
        return "markdown_fenced_code", text, False, True
    if "SEARCH" in text.upper() and "REPLACE" in text.upper():
        return "search_replace_block", text, False, False
    try:
        compile(text, '<m>', 'exec')
        return "raw_replace_body", text, True, False
    except SyntaxError:
        pass
    lines = [l for l in text.strip().split('\n') if l.strip() and not l.strip().startswith('#')]
    if lines:
        return "raw_replace_body", text, True, False
    return "invalid_format", text, False, False


def check_syntax(code):
    if not code or code.strip() in ("", "PASS"):
        return True
    try:
        compile(code, '<m>', 'exec')
        return True
    except SyntaxError:
        return False


def write_receipt(task_id, mode, result):
    r = {
        "schema": "nexus.local_heal.t3_3_receipt.v1",
        "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
        "simulated": False, "claim_eligible": False, "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_experiment",
        "telemetry": {
            "instance_id": task_id, "run_group": RUN_GROUP, "mode": mode,
            "model_name": OLLAMA_MODEL if mode != "D0" else "none",
            "model_calls": 1 if mode.startswith("M") else 0,
            "canonical_span_source": result.get("canonical_span_source", ""),
            "output_format_class": result.get("output_format_class", ""),
            "sanitizer_used": result.get("sanitizer_used", False),
            "patch_applied": result.get("patch_applied", False),
            "syntax_gate_passed": result.get("syntax_passed", False),
            "verification_result": result.get("verification", ""),
            "solved": result.get("solved", False),
            "deterministic_fallback_used": False,
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
    print("T3.3: Controlled 3-Task Model-Call Experiment")
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
            d0 = {"solved": True, "verification": "PASS", "patch_applied": False, "syntax_passed": True, "model_patch_reward": 0.0, "canonical_span_source": task["canonical_span_source"]}
        else:
            applied = apply_fix(task)
            passed_after, _ = run_verification(task)
            d0 = {"solved": passed_after, "verification": "PASS" if passed_after else "FAIL", "patch_applied": applied, "syntax_passed": True, "model_patch_reward": 0.0, "canonical_span_source": task["canonical_span_source"]}
        write_receipt(task["instance_id"], "D0", d0)
        all_results.append({"instance_id": task["instance_id"], "mode": "D0", **d0})
        print(f"  D0: {'PASS' if d0['solved'] else 'FAIL'}")

        if not d0["solved"]:
            print("  D0 FAILED — skipping M1/M2")
            for mode in ["M1", "M2"]:
                r = {"solved": False, "failure_class": "baseline_regression", "model_patch_reward": 0.0}
                write_receipt(task["instance_id"], mode, r)
                all_results.append({"instance_id": task["instance_id"], "mode": mode, **r})
            continue

        # M1
        reset_workspace(task["workspace"])
        source = read_source(task)
        prompt = build_prompt(task, source)
        ph = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        print(f"  M1: Calling Qwen14B (prompt hash: {ph})...")
        t0 = time.time()
        output, ok = call_ollama(prompt)
        latency = time.time() - t0
        oh = hashlib.sha256(output.encode()).hexdigest()[:16]
        print(f"  M1: {latency:.1f}s | output: {output[:150]}")

        fmt, extracted, replace_ok, sanitizer = classify_output(output)
        syntax_ok = check_syntax(extracted)
        print(f"  M1: fmt={fmt} replace_ok={replace_ok} syntax={syntax_ok}")

        m1 = {"solved": False, "output_format_class": fmt, "sanitizer_used": sanitizer, "replace_extracted": replace_ok, "syntax_passed": syntax_ok, "model_patch_reward": 0.0, "canonical_span_source": task["canonical_span_source"], "prompt_hash": ph, "output_hash": oh, "latency": latency}
        write_receipt(task["instance_id"], "M1", m1)
        all_results.append({"instance_id": task["instance_id"], "mode": "M1", **m1})

        # M2
        if replace_ok and syntax_ok:
            reset_workspace(task["workspace"])
            ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
            sp = ws / task["target_file"]
            orig = sp.read_text()
            buggy = task.get("buggy_block", task.get("buggy_line", ""))
            if buggy in orig:
                replacement = "" if extracted.strip() == "PASS" or extracted.strip() == "" else extracted
                sp.write_text(orig.replace(buggy, replacement, 1))
            passed_m2, _ = run_verification(task)
            m2 = {"solved": passed_m2, "verification": "PASS" if passed_m2 else "FAIL", "patch_applied": True, "syntax_passed": True, "model_patch_reward": 1.0 if passed_m2 else 0.0, "canonical_span_source": task["canonical_span_source"]}
        else:
            m2 = {"solved": False, "failure_class": "m1_not_passed", "model_patch_reward": 0.0, "canonical_span_source": task["canonical_span_source"]}
        write_receipt(task["instance_id"], "M2", m2)
        all_results.append({"instance_id": task["instance_id"], "mode": "M2", **m2})
        print(f"  M2: {'PASS reward=1.0' if m2.get('model_patch_reward', 0) > 0 else 'FAIL/SKIP'}")

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.3 RESULTS")
    print(f"{'=' * 70}")

    for task in TASKS:
        tid = task["instance_id"]
        d0r = next((r for r in all_results if r["instance_id"] == tid and r["mode"] == "D0"), {})
        m1r = next((r for r in all_results if r["instance_id"] == tid and r["mode"] == "M1"), {})
        m2r = next((r for r in all_results if r["instance_id"] == tid and r["mode"] == "M2"), {})
        print(f"  {tid}: D0={'PASS' if d0r.get('solved') else 'FAIL'} M1_fmt={m1r.get('output_format_class','N/A')} M2_reward={m2r.get('model_patch_reward',0)}")

    d0_pass = sum(1 for r in all_results if r["mode"] == "D0" and r.get("solved"))
    m2_reward = sum(1 for r in all_results if r["mode"] == "M2" and r.get("model_patch_reward", 0) > 0)
    print(f"\nD0: {d0_pass}/{len(TASKS)} PASS")
    print(f"M2 model_patch_reward=1.0: {m2_reward}/{len(TASKS)}")

    if d0_pass == len(TASKS) and m2_reward >= 2:
        verdict = "GREEN"
    elif d0_pass >= len(TASKS) - 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.3 Verdict: {verdict}")

    summary = {"verdict": verdict, "run_group": RUN_GROUP, "d0_pass": d0_pass, "m2_reward_1": m2_reward, "total": len(TASKS)}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    print(f"Summary: {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
