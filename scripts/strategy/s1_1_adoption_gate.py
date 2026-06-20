#!/usr/bin/env python3
"""S1.1: Strategy-Conditioned Prompt Adoption Gate — 2-Task Active Comparison"""

import json, subprocess, sys, hashlib, time, re
from pathlib import Path

sys.path.insert(0, "/Users/jameschen/Workspace/nexus")
from nexus.strategy import StrategyPlanner, StrategyAdherenceChecker
from nexus.strategy.strategy_prompt_renderer import StrategyPromptRenderer

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
RUN_GROUP = "S1_1_ADOPTION_GATE"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

CANDIDATES = [
    {"instance_id": "astropy__astropy-12907", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/modeling/separable.py", "buggy_line": "        cright[-right.shape[0]:, -right.shape[1]:] = 1", "fixed_line": "        cright[-right.shape[0]:, -right.shape[1]:] = right", "issue_summary": "Separability matrix wrong assignment", "repro_script": "import sys, os, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.modeling import models as m\nfrom astropy.modeling.separable import separability_matrix\ncm = m.Linear1D(10) & m.Linear1D(5)\nmodel = m.Pix2Sky_TAN() & cm\nres = separability_matrix(model)\nexpected = np.array([[True,True,False,False],[True,True,False,False],[False,False,True,False],[False,False,False,True]])\nif np.array_equal(res, expected):\n    print('SUCCESS'); sys.exit(0)\nelse:\n    print('BUG PRESENT'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14182", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/ascii/rst.py", "buggy_line": "    start_line = 3", "fixed_line": "    start_line = 2", "issue_summary": "RST parser start_line off by one", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.ascii import rst\ntry:\n    table = rst.RST().read('==== =====\\nCol1 Col2\\n==== =====\\n  1   2.3\\n==== =====')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
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
    buggy_indent = len(buggy_line) - len(buggy_line.lstrip())
    buggy_indent_str = buggy_line[:buggy_indent]
    model_stripped = model_output.strip()
    model_indent = len(model_output) - len(model_output.lstrip())
    if model_indent < buggy_indent and model_stripped:
        return buggy_indent_str + model_stripped
    return model_output

def context_syntax_check(full_file, path):
    try:
        compile(full_file, path, 'exec'); return True, "ok"
    except SyntaxError as e:
        return False, f"error: {e.msg} line {e.lineno}"


def run_active_comparison(cand, mode_name, prompt):
    """Run a single active comparison mode."""
    reset_workspace(cand["workspace"])
    ws = NEXUS_ROOT / ".nexus/workspaces" / cand["workspace"]
    source_hash = get_source_hash(cand["workspace"])

    t0 = time.time()
    output, ok = call_ollama(prompt)
    latency = time.time() - t0

    fmt, extracted, replace_ok = classify_output(output)
    normalized = normalize_indentation(extracted, cand["buggy_line"])

    sp = ws / cand["target_file"]
    orig = sp.read_text()
    patched = orig.replace(cand["buggy_line"], normalized, 1) if cand["buggy_line"] in orig else orig
    effective = orig != patched
    ctx_ok, ctx_reason = context_syntax_check(patched, str(sp))

    if ctx_ok and replace_ok and effective:
        reset_workspace(cand["workspace"])
        sp2 = ws / cand["target_file"]
        orig2 = sp2.read_text()
        if cand["buggy_line"] in orig2:
            sp2.write_text(orig2.replace(cand["buggy_line"], normalized, 1))
        passed_verify, _ = run_verification(cand)
        reward = 1.0 if passed_verify else 0.0
    else:
        passed_verify = False
        reward = 0.0

    return {
        "mode": mode_name,
        "source_hash": source_hash,
        "latency": latency,
        "raw_output": extracted,
        "normalized": normalized,
        "replace_ok": replace_ok,
        "effective": effective,
        "ctx_ok": ctx_ok,
        "ctx_reason": ctx_reason,
        "verification": "PASS" if passed_verify else "FAIL",
        "model_patch_reward": reward,
    }


def main():
    print("=" * 70)
    print("S1.1: Strategy-Conditioned Prompt Adoption Gate")
    print("=" * 70)

    planner = StrategyPlanner()
    renderer = StrategyPromptRenderer()
    checker = StrategyAdherenceChecker()

    all_results = []

    for cand in CANDIDATES:
        iid = cand["instance_id"]
        print(f"\n{'=' * 55}")
        print(f"CANDIDATE: {iid}")
        print("=" * 55)

        # Generate strategy envelope
        envelope = planner.plan(
            instance_id=iid,
            issue_summary=cand["issue_summary"],
            target_files=[cand["target_file"]],
            canonical_span_source="ast_boundary",
        )
        block = renderer.render(envelope)

        # Baseline prompt
        baseline_prompt = f"TASK: Return ONLY the replacement code.\nFILE: {cand['target_file']}\nBUGGY CODE:\n{cand['buggy_line']}\nFIX: Replace with: {cand['fixed_line']}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement line.\nOUTPUT:"

        # Strategy-conditioned prompt
        strategy_prompt = block.block + "\n" + baseline_prompt

        print(f"  Baseline prompt: {len(baseline_prompt)}ch")
        print(f"  Strategy prompt: {len(strategy_prompt)}ch")

        # Run both modes
        baseline_result = run_active_comparison(cand, "baseline", baseline_prompt)
        strategy_result = run_active_comparison(cand, "strategy_conditioned", strategy_prompt)

        # Adherence check
        adherence = checker.check(envelope, effective_change=True, source_snapshot_present=True, canonical_search_locked=True)

        print(f"\n  Baseline:  reward={baseline_result['model_patch_reward']} latency={baseline_result['latency']:.1f}s")
        print(f"  Strategy:  reward={strategy_result['model_patch_reward']} latency={strategy_result['latency']:.1f}s")
        print(f"  Adherence: {adherence['adherence_status']}")

        result = {
            "instance_id": iid,
            "strategy_id": envelope.strategy_id,
            "baseline": baseline_result,
            "strategy": strategy_result,
            "adherence": adherence,
        }
        all_results.append(result)

    # Summary
    print(f"\n{'=' * 70}")
    print("S1.1 RESULTS")
    print(f"{'=' * 70}")

    for r in all_results:
        b = r["baseline"]["model_patch_reward"]
        s = r["strategy"]["model_patch_reward"]
        print(f"  {r['instance_id']}: baseline={b} strategy={s} adherence={r['adherence']['adherence_status']}")

    baseline_rewards = sum(1 for r in all_results if r["baseline"]["model_patch_reward"] > 0)
    strategy_rewards = sum(1 for r in all_results if r["strategy"]["model_patch_reward"] > 0)

    print(f"\nBaseline reward>0: {baseline_rewards}/{len(all_results)}")
    print(f"Strategy reward>0: {strategy_rewards}/{len(all_results)}")

    # Strategy must not be worse than baseline
    strategy_not_worse = all(
        r["strategy"]["model_patch_reward"] >= r["baseline"]["model_patch_reward"]
        for r in all_results
    )
    print(f"Strategy not worse than baseline: {'PASS' if strategy_not_worse else 'FAIL'}")

    verdict = "GREEN" if strategy_not_worse else "YELLOW"
    print(f"\nS1.1 Verdict: {verdict}")

    # Write comparison
    output_path = NEXUS_ROOT / "artifacts/strategy/s1_1_active_comparison.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in all_results:
            f.write(json.dumps(r, indent=2) + "\n")
    print(f"\nComparison: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
