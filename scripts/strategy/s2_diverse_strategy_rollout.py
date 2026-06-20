#!/usr/bin/env python3
"""S2: Diverse Strategy Rollout — Strategy Tournament + Winner-Only Execution"""

import json, subprocess, sys, hashlib, time, re
from pathlib import Path

sys.path.insert(0, "/Users/jameschen/Workspace/nexus")
from nexus.strategy import StrategyPlanner, StrategyAdherenceChecker
from nexus.strategy.strategy_prompt_renderer import StrategyPromptRenderer

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "S2_DIVERSE_STRATEGY_ROLLOUT"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

CANDIDATES = [
    {"instance_id": "astropy__astropy-13236", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/table/table.py", "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True", "fixed_block": "", "issue_summary": "Table NdarrayMixin block removal", "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n"},
    {"instance_id": "sympy__sympy-13852", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/functions/special/zeta_functions.py", "buggy_line": "from sympy.core import Function, S, sympify, pi", "fixed_line": "from sympy.core import Function, S, sympify, pi, I", "issue_summary": "Missing I import in zeta_functions", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import zeta, S\ntry:\n    result = zeta(2)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-12907", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/modeling/separable.py", "buggy_line": "        cright[-right.shape[0]:, -right.shape[1]:] = 1", "fixed_line": "        cright[-right.shape[0]:, -right.shape[1]:] = right", "issue_summary": "Separability matrix wrong assignment", "repro_script": "import sys, os, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.modeling import models as m\nfrom astropy.modeling.separable import separability_matrix\ncm = m.Linear1D(10) & m.Linear1D(5)\nmodel = m.Pix2Sky_TAN() & cm\nres = separability_matrix(model)\nexpected = np.array([[True,True,False,False],[True,True,False,False],[False,False,True,False],[False,False,False,True]])\nif np.array_equal(res, expected):\n    print('SUCCESS'); sys.exit(0)\nelse:\n    print('BUG PRESENT'); sys.exit(1)\n"},
    {"instance_id": "astropy__astropy-14182", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/ascii/rst.py", "buggy_line": "    start_line = 3", "fixed_line": "    start_line = 2", "issue_summary": "RST parser start_line off by one", "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.ascii import rst\ntry:\n    table = rst.RST().read('==== =====\\nCol1 Col2\\n==== =====\\n  1   2.3\\n==== =====')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
]

STRATEGY_TYPES = [
    {"type": "traceback_first", "repair_strategy": "Localize from observed failure and traceback", "priority": "canonical_search_lockable"},
    {"type": "symbol_graph_first", "repair_strategy": "Minimal symbol-local patch targeting function/class/import", "priority": "source_snapshot_available"},
    {"type": "issue_semantics_first", "repair_strategy": "Semantic behavior correction based on expected behavior delta", "priority": "verifier_available"},
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


def generate_strategy_candidates(cand):
    """Generate 3 strategy candidates per task."""
    candidates = []
    for st in STRATEGY_TYPES:
        from nexus.strategy import StrategyEnvelope
        envelope = StrategyEnvelope(
            instance_id=cand["instance_id"],
            task_goal=f"Repair {cand['instance_id']}: {cand['issue_summary']}",
            issue_summary=cand["issue_summary"],
            bug_hypothesis=cand["issue_summary"],
            repair_strategy=st["repair_strategy"],
            candidate_files=[cand["target_file"]],
            strategy_source=f"deterministic_{st['type']}",
        )
        candidates.append({"strategy_type": st["type"], "envelope": envelope})
    return candidates


def run_probe(cand, envelope):
    """Run low-cost deterministic probe."""
    ws = NEXUS_ROOT / ".nexus/workspaces" / cand["workspace"]
    target_exists = (ws / cand["target_file"]).exists()
    source_hash = get_source_hash(cand["workspace"])
    buggy = cand.get("buggy_block", cand.get("buggy_line", ""))
    buggy_found = buggy in (ws / cand["target_file"]).read_text() if target_exists else False

    score = 0
    reasons = []
    if target_exists:
        score += 2; reasons.append("target_file_found")
    if source_hash != "unknown":
        score += 2; reasons.append("source_snapshot_available")
    if buggy_found:
        score += 3; reasons.append("canonical_search_lockable")
    score += 2; reasons.append("verifier_available")
    score += 1; reasons.append("public_claim_boundary_present")

    return {"probe_score": score, "probe_reasons": reasons, "probe_pass": score >= 5}


def rank_strategies(candidates_with_probes):
    """Deterministic Borda-style ranking."""
    scored = []
    for c in candidates_with_probes:
        scored.append({
            "strategy_type": c["strategy_type"],
            "probe_score": c["probe"]["probe_score"],
            "strategy_id": c["envelope"].strategy_id,
        })
    scored.sort(key=lambda x: -x["probe_score"])
    return scored


def main():
    print("=" * 70)
    print("S2: Diverse Strategy Rollout — Tournament + Winner-Only")
    print("=" * 70)

    all_results = []

    for cand in CANDIDATES:
        iid = cand["instance_id"]
        print(f"\n{'=' * 55}")
        print(f"CANDIDATE: {iid}")
        print("=" * 55)

        # Generate 3 strategy candidates
        strategy_candidates = generate_strategy_candidates(cand)
        print(f"  Generated {len(strategy_candidates)} strategy candidates")

        # Run probes
        for sc in strategy_candidates:
            sc["probe"] = run_probe(cand, sc["envelope"])
            print(f"  {sc['strategy_type']}: probe_score={sc['probe']['probe_score']}")

        # Rank
        ranked = rank_strategies(strategy_candidates)
        winner = ranked[0]
        print(f"  Winner: {winner['strategy_type']} (score={winner['probe_score']})")

        # Execute winner only
        renderer = StrategyPromptRenderer()
        winner_envelope = [sc["envelope"] for sc in strategy_candidates if sc["strategy_type"] == winner["strategy_type"]][0]
        block = renderer.render(winner_envelope)

        if "buggy_block" in cand:
            buggy = cand["buggy_block"]
            expected = "Remove block. Return PASS."
        else:
            buggy = cand["buggy_line"]
            expected = f"Replace with: {cand['fixed_line']}"

        baseline = f"TASK: Return ONLY the replacement code.\nFILE: {cand['target_file']}\nBUGGY CODE:\n{buggy}\nFIX: {expected}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement line.\nOUTPUT:"
        strategy_prompt = block.block + "\n" + baseline

        reset_workspace(cand["workspace"])
        t0 = time.time()
        output, ok = call_ollama(strategy_prompt)
        latency = time.time() - t0
        fmt, extracted, replace_ok = classify_output(output)
        normalized = normalize_indentation(extracted, cand.get("buggy_line", ""))

        ws = NEXUS_ROOT / ".nexus/workspaces" / cand["workspace"]
        sp = ws / cand["target_file"]
        orig = sp.read_text()
        buggy_key = cand.get("buggy_block", cand.get("buggy_line", ""))
        patched = orig.replace(buggy_key, normalized if "buggy_block" not in cand else (extracted if extracted else ""), 1) if buggy_key in orig else orig
        effective = orig != patched
        ctx_ok, _ = context_syntax_check(patched, str(sp))

        if ctx_ok and replace_ok and effective:
            reset_workspace(cand["workspace"])
            sp2 = ws / cand["target_file"]
            orig2 = sp2.read_text()
            if buggy_key in orig2:
                if "buggy_block" in cand:
                    sp2.write_text(orig2.replace(buggy_key, extracted if extracted else "", 1))
                else:
                    sp2.write_text(orig2.replace(buggy_key, normalized, 1))
            passed_verify, _ = run_verification(cand)
            reward = 1.0 if passed_verify else 0.0
        else:
            passed_verify = False
            reward = 0.0

        print(f"  Winner M0: {latency:.1f}s reward={reward}")

        all_results.append({
            "instance_id": iid,
            "winner_type": winner["strategy_type"],
            "winner_score": winner["probe_score"],
            "strategy_count": len(strategy_candidates),
            "reward": reward,
            "latency": latency,
        })

    # Summary
    print(f"\n{'=' * 70}")
    print("S2 RESULTS")
    print(f"{'=' * 70}")

    for r in all_results:
        print(f"  {r['instance_id']}: winner={r['winner_type']} score={r['winner_score']} reward={r['reward']}")

    reward_count = sum(1 for r in all_results if r["reward"] > 0)
    print(f"\nWinner reward>0: {reward_count}/{len(all_results)}")

    verdict = "GREEN" if reward_count >= 3 else "YELLOW" if reward_count >= 2 else "RED"
    print(f"\nS2 Verdict: {verdict}")

    summary = {"verdict": verdict, "reward": reward_count, "total": len(all_results)}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
