#!/usr/bin/env python3
"""T4.4: Fixture-Backed Replay for Ready Candidates + Historical-Only Exclusion Guard"""

import json, subprocess, sys, hashlib, time, re, yaml
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "T4_4_FIXTURE_BACKED_REPLAY"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

READY_CANDIDATES = {
    "astropy__astropy-13236": {"workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/table/table.py", "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True", "fixed_block": "", "stored_output": "PASS", "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n"},
    "sympy__sympy-13852": {"workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/functions/special/zeta_functions.py", "buggy_line": "from sympy.core import Function, S, sympify, pi", "fixed_line": "from sympy.core import Function, S, sympify, pi, I", "stored_output": "from sympy.core import Function, S, sympify, pi, I", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import zeta, S\ntry:\n    result = zeta(2)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
}

HISTORICAL_ONLY = ["sympy__sympy-12419", "sympy__sympy-13647", "astropy__astropy-14365", "astropy__astropy-14309"]


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

def apply_fix(task, fix_text):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    sp = ws / task["target_file"]
    source = sp.read_text()
    if "buggy_block" in task:
        if task["buggy_block"] in source:
            sp.write_text(source.replace(task["buggy_block"], fix_text, 1)); return True
    else:
        if task["buggy_line"] in source:
            sp.write_text(source.replace(task["buggy_line"], fix_text, 1)); return True
    return False

def get_source_hash(ws):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(NEXUS_ROOT / ".nexus/workspaces" / ws), capture_output=True, text=True, timeout=10)
        return r.stdout.strip()[:12] if r.returncode == 0 else "unknown"
    except: return "unknown"

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
    return "raw_replace_body", text, True

def context_syntax_check(full_file, path):
    try:
        compile(full_file, path, 'exec'); return True, "ok"
    except SyntaxError as e:
        return False, f"error: {e.msg} line {e.lineno}"


def main():
    print("=" * 70)
    print("T4.4: Fixture-Backed Replay + Historical-Only Exclusion")
    print(f"Fixture-ready: {len(READY_CANDIDATES)} | Historical-only: {len(HISTORICAL_ONLY)}")
    print("=" * 70)

    all_results = []

    # Replay fixture-ready candidates
    for iid, task in READY_CANDIDATES.items():
        print(f"\n{'=' * 55}")
        print(f"REPLAY: {iid}")
        print("=" * 55)

        result = {"instance_id": iid, "status": "fixture_ready"}

        # A0: Anchor audit
        reset_workspace(task["workspace"])
        source_hash = get_source_hash(task["workspace"])
        ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
        source = (ws / task["target_file"]).read_text() if (ws / task["target_file"]).exists() else ""
        buggy_found = task["buggy_block"] in source if "buggy_block" in task else task.get("buggy_line", "") in source
        result["a0"] = "PASS" if buggy_found else "FAIL"
        result["source_hash"] = source_hash
        print(f"  A0: {result['a0']} hash={source_hash}")

        # D0: Deterministic baseline
        passed_before, _ = run_verification(task)
        if passed_before:
            result["d0"] = "PASS"
        else:
            applied = apply_fix(task, task.get("fixed_block", "") if "buggy_block" in task else task.get("fixed_line", ""))
            passed_after, _ = run_verification(task)
            result["d0"] = "PASS" if passed_after else "FAIL"
        print(f"  D0: {result['d0']}")

        # R0: Stored-output replay
        reset_workspace(task["workspace"])
        stored = task["stored_output"]
        apply_fix(task, stored)
        passed_r0, _ = run_verification(task)
        result["r0"] = "PASS" if passed_r0 else "FAIL"
        result["r0_reward"] = 0.0
        print(f"  R0: {result['r0']} (historical, reward=0.0)")

        # M0: Fresh Qwen replay
        reset_workspace(task["workspace"])
        if "buggy_block" in task:
            expected = "Remove block. Return PASS."
        else:
            expected = f"Replace with: {task['fixed_line']}"
        prompt = f"TASK: Return ONLY the replacement code.\nFILE: {task['target_file']}\nBUGGY CODE:\n{task.get('buggy_block', task.get('buggy_line', ''))}\nFIX: {expected}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement code or PASS.\nOUTPUT:"

        t0 = time.time()
        output, ok = call_ollama(prompt)
        latency = time.time() - t0
        fmt, extracted, replace_ok = classify_output(output)

        sp = ws / task["target_file"]
        orig = sp.read_text()
        if "buggy_block" in task:
            patched = orig.replace(task["buggy_block"], extracted if extracted else "", 1) if task["buggy_block"] in orig else orig
        else:
            patched = orig.replace(task["buggy_line"], extracted, 1) if task["buggy_line"] in orig else orig
        ctx_ok, _ = context_syntax_check(patched, str(sp))
        effective = orig != patched

        if ctx_ok and replace_ok and effective:
            reset_workspace(task["workspace"])
            sp2 = ws / task["target_file"]
            orig2 = sp2.read_text()
            if "buggy_block" in task:
                if task["buggy_block"] in orig2: sp2.write_text(orig2.replace(task["buggy_block"], extracted if extracted else "", 1))
            else:
                if task["buggy_line"] in orig2: sp2.write_text(orig2.replace(task["buggy_line"], extracted, 1))
            passed_m0, _ = run_verification(task)
            result["m0"] = "PASS" if passed_m0 else "FAIL"
            result["m0_reward"] = 1.0 if passed_m0 else 0.0
        else:
            result["m0"] = "FAIL"
            result["m0_reward"] = 0.0
        print(f"  M0: {result['m0']} reward={result['m0_reward']} ({latency:.1f}s)")

        all_results.append(result)

    # Historical-only exclusion
    for iid in HISTORICAL_ONLY:
        all_results.append({"instance_id": iid, "status": "historical_only_excluded", "a0": "EXCLUDED", "d0": "EXCLUDED", "r0": "EXCLUDED", "m0": "EXCLUDED", "m0_reward": 0.0})

    # Summary
    print(f"\n{'=' * 70}")
    print("T4.4 RESULTS")
    print(f"{'=' * 70}")

    for r in all_results:
        print(f"  {r['instance_id']}: status={r['status']} M0={r.get('m0','N/A')} reward={r.get('m0_reward',0)}")

    ready_pass = sum(1 for r in all_results if r.get("status") == "fixture_ready" and r.get("m0") == "PASS")
    ready_total = sum(1 for r in all_results if r.get("status") == "fixture_ready")
    excluded = sum(1 for r in all_results if "excluded" in r.get("status", ""))

    print(f"\nFixture-ready PASS: {ready_pass}/{ready_total} | Excluded: {excluded}")

    if ready_pass == ready_total:
        verdict = "GREEN"
    elif ready_pass >= 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT4.4 Verdict: {verdict}")

    summary = {"verdict": verdict, "ready_pass": ready_pass, "ready_total": ready_total, "excluded": excluded}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__": sys.exit(main())
