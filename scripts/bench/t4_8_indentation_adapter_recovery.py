#!/usr/bin/env python3
"""T4.8: Indentation-Normalized Replacement Adapter + Two-Probe Recovery"""

import json, subprocess, sys, hashlib, time, re
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
RUN_GROUP = "T4_8_INDENTATION_ADAPTER_RECOVERY"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

PROBES = [
    {"instance_id": "astropy__astropy-12907", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/modeling/separable.py", "buggy_line": "        cright[-right.shape[0]:, -right.shape[1]:] = 1", "fixed_line": "        cright[-right.shape[0]:, -right.shape[1]:] = right", "repro_script": "import sys, os, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.modeling import models as m\nfrom astropy.modeling.separable import separability_matrix\ncm = m.Linear1D(10) & m.Linear1D(5)\nmodel = m.Pix2Sky_TAN() & cm\nres = separability_matrix(model)\nexpected = np.array([[True,True,False,False],[True,True,False,False],[False,False,True,False],[False,False,False,True]])\nif np.array_equal(res, expected):\n    print('SUCCESS'); sys.exit(0)\nelse:\n    print('BUG PRESENT'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14182", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/ascii/rst.py", "buggy_line": "    start_line = 3", "fixed_line": "    start_line = 2", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.ascii import rst\ntry:\n    table = rst.RST().read('==== =====\\nCol1 Col2\\n==== =====\\n  1   2.3\\n==== =====')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
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

def normalize_indentation(model_output, buggy_line):
    """Project model output into the indentation context of the buggy line."""
    # Get indentation of buggy line
    buggy_indent = len(buggy_line) - len(buggy_line.lstrip())
    buggy_indent_str = buggy_line[:buggy_indent]
    
    # Get indentation of model output
    model_stripped = model_output.strip()
    model_indent = len(model_output) - len(model_output.lstrip())
    
    # If model output has less indentation than buggy line, project it
    if model_indent < buggy_indent and model_stripped:
        return buggy_indent_str + model_stripped
    return model_output

def context_syntax_check(full_file, path):
    try:
        compile(full_file, path, 'exec'); return True, "ok"
    except SyntaxError as e:
        return False, f"error: {e.msg} line {e.lineno}"


def main():
    print("=" * 70)
    print("T4.8: Indentation-Normalized Adapter + 2-Probe Recovery")
    print("=" * 70)

    all_results = []

    for probe in PROBES:
        iid = probe["instance_id"]
        print(f"\n{'=' * 55}")
        print(f"PROBE: {iid}")
        print("=" * 55)

        result = {"instance_id": iid}

        # Source capture
        reset_workspace(probe["workspace"])
        source_hash = get_source_hash(probe["workspace"])
        ws = NEXUS_ROOT / ".nexus/workspaces" / probe["workspace"]
        source = (ws / probe["target_file"]).read_text()
        buggy_found = probe["buggy_line"] in source
        result["source_hash"] = source_hash
        result["buggy_found"] = buggy_found
        print(f"  Source: hash={source_hash} buggy_found={buggy_found}")

        if not buggy_found:
            result["m0"] = "SKIP"
            result["m0_reward"] = 0.0
            all_results.append(result)
            continue

        # D0
        passed_before, _ = run_verification(probe)
        if passed_before:
            result["d0"] = "PASS (already fixed)"
        else:
            result["d0"] = "PASS (needs fix)"
        print(f"  D0: {result['d0']}")

        # M0 with indentation normalization
        reset_workspace(probe["workspace"])
        prompt = f"TASK: Return ONLY the replacement code.\nFILE: {probe['target_file']}\nBUGGY CODE:\n{probe['buggy_line']}\nFIX: Replace with: {probe['fixed_line']}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement line with correct indentation.\nOUTPUT:"

        t0 = time.time()
        output, ok = call_ollama(prompt)
        latency = time.time() - t0
        fmt, extracted, replace_ok = classify_output(output)
        print(f"  Raw output: {repr(extracted[:100])}")

        # Apply indentation normalization
        normalized = normalize_indentation(extracted, probe["buggy_line"])
        print(f"  Normalized: {repr(normalized[:100])}")

        # Apply to source
        sp = ws / probe["target_file"]
        orig = sp.read_text()
        patched = orig.replace(probe["buggy_line"], normalized, 1) if probe["buggy_line"] in orig else orig
        effective = orig != patched
        ctx_ok, ctx_reason = context_syntax_check(patched, str(sp))
        print(f"  effective={effective} ctx_ok={ctx_ok} ({ctx_reason})")

        if ctx_ok and replace_ok and effective:
            reset_workspace(probe["workspace"])
            sp2 = ws / probe["target_file"]
            orig2 = sp2.read_text()
            if probe["buggy_line"] in orig2:
                sp2.write_text(orig2.replace(probe["buggy_line"], normalized, 1))
            passed_m0, _ = run_verification(probe)
            result["m0"] = "PASS" if passed_m0 else "FAIL"
            result["m0_reward"] = 1.0 if passed_m0 else 0.0
        else:
            result["m0"] = "FAIL"
            result["m0_reward"] = 0.0
        print(f"  M0: {result['m0']} reward={result['m0_reward']} ({latency:.1f}s)")

        all_results.append(result)

    # Summary
    print(f"\n{'=' * 70}")
    print("T4.8 RESULTS")
    print(f"{'=' * 70}")

    for r in all_results:
        print(f"  {r['instance_id']}: M0={r.get('m0','N/A')} reward={r.get('m0_reward',0)}")

    m0_pass = sum(1 for r in all_results if r.get("m0") == "PASS")
    m0_reward = sum(1 for r in all_results if r.get("m0_reward", 0) > 0)

    verdict = "GREEN" if m0_reward >= 2 else "YELLOW" if m0_reward >= 1 else "RED"
    print(f"\nT4.8 Verdict: {verdict}")

    summary = {"verdict": verdict, "m0_pass": m0_pass, "m0_reward": m0_reward}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__": sys.exit(main())
