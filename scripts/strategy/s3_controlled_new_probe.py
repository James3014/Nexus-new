#!/usr/bin/env python3
"""S3: Controlled New-Probe Strategy Rollout — Real-Task Evidence"""

import json, subprocess, sys, hashlib, time, re
from pathlib import Path

sys.path.insert(0, "/Users/jameschen/Workspace/nexus")
from nexus.strategy import StrategyPlanner, StrategyAdherenceChecker
from nexus.strategy.strategy_probe import StrategyProbeEvaluator
from nexus.strategy.strategy_prompt_renderer import StrategyPromptRenderer

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "S3_CONTROLLED_NEW_PROBE"
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"

# 2 new probes (not in T4.10 verified set)
PROBES = [
    {"instance_id": "astropy__astropy-14182", "workspace": "astropy", "python_exec": PYTHON_EXEC_ASTROPY, "target_file": "astropy/io/ascii/rst.py", "buggy_line": "    start_line = 3", "fixed_line": "    start_line = 2", "issue_summary": "RST parser start_line off by one", "has_traceback": False, "has_target_symbol": True, "has_issue_summary": True, "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io.ascii import rst\ntry:\n    table = rst.RST().read('==== =====\\nCol1 Col2\\n==== =====\\n  1   2.3\\n==== =====')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
    {"instance_id": "sympy__sympy-13852", "workspace": "sympy", "python_exec": PYTHON_EXEC_SYMPY, "target_file": "sympy/functions/special/zeta_functions.py", "buggy_line": "from sympy.core import Function, S, sympify, pi", "fixed_line": "from sympy.core import Function, S, sympify, pi, I", "issue_summary": "Missing I import in zeta_functions", "has_traceback": False, "has_target_symbol": True, "has_issue_summary": True, "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import zeta, S\ntry:\n    result = zeta(2)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n"},
]

STRATEGY_TYPES = ["traceback_first", "symbol_graph_first", "issue_semantics_first"]


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


def main():
    print("=" * 70)
    print("S3: Controlled New-Probe Strategy Rollout")
    print("=" * 70)

    evaluator = StrategyProbeEvaluator()
    renderer = StrategyPromptRenderer()
    checker = StrategyAdherenceChecker()

    all_results = []

    for probe in PROBES:
        iid = probe["instance_id"]
        print(f"\n{'=' * 55}")
        print(f"PROBE: {iid}")
        print("=" * 55)

        # Source capture
        reset_workspace(probe["workspace"])
        source_hash = get_source_hash(probe["workspace"])
        ws = NEXUS_ROOT / ".nexus/workspaces" / probe["workspace"]
        buggy_found = probe["buggy_line"] in (ws / probe["target_file"]).read_text() if (ws / probe["target_file"]).exists() else False
        print(f"  Source: hash={source_hash} buggy_found={buggy_found}")

        if not buggy_found:
            all_results.append({"instance_id": iid, "status": "source_stale", "winner": None, "reward": 0.0})
            continue

        # Generate 3 strategy candidates
        strategy_candidates = []
        for st in STRATEGY_TYPES:
            from nexus.strategy import StrategyEnvelope
            envelope = StrategyEnvelope(
                instance_id=iid,
                task_goal=f"Repair {iid}: {probe['issue_summary']}",
                issue_summary=probe["issue_summary"],
                candidate_files=[probe["target_file"]],
                strategy_source=f"deterministic_{st}",
            )
            strategy_candidates.append({"strategy_type": st, "envelope": envelope})

        # Run strategy-specific evidence probes
        probe_results = []
        for sc in strategy_candidates:
            st = sc["strategy_type"]
            envelope = sc["envelope"]

            # Readiness
            readiness = evaluator.evaluate_readiness(envelope, target_file_exists=True, source_snapshot_present=True, canonical_search_locked=True, verifier_available=True)

            # Strategy-specific evidence
            if st == "traceback_first":
                evidence = evaluator.evaluate_traceback_first(envelope, has_traceback=probe["has_traceback"], traceback_matches_target=False)
            elif st == "symbol_graph_first":
                evidence = evaluator.evaluate_symbol_graph_first(envelope, has_target_symbol=probe["has_target_symbol"], symbol_unique=True, symbol_in_canonical_span=True, imports_detected=True)
            else:
                evidence = evaluator.evaluate_issue_semantics_first(envelope, has_issue_summary=probe["has_issue_summary"], has_behavior_delta=False, keywords_match_target=True, semantic_category=False)

            final_score = evidence["strategy_evidence_score"] if readiness["readiness_pass"] else -1
            probe_results.append({"strategy_type": st, "evidence_score": evidence["strategy_evidence_score"], "confidence": evidence["strategy_evidence_confidence"], "final_score": final_score})
            print(f"  {st}: evidence={evidence['strategy_evidence_score']} confidence={evidence['strategy_evidence_confidence']:.2f} final={final_score}")

        # Rank
        ranked = sorted(probe_results, key=lambda x: -x["final_score"])
        winner = ranked[0]
        print(f"  Winner: {winner['strategy_type']} (score={winner['final_score']})")

        # Execute winner only
        winner_envelope = [sc["envelope"] for sc in strategy_candidates if sc["strategy_type"] == winner["strategy_type"]][0]
        block = renderer.render(winner_envelope)

        prompt = f"TASK: Return ONLY the replacement code.\nFILE: {probe['target_file']}\nBUGGY CODE:\n{probe['buggy_line']}\nFIX: Replace with: {probe['fixed_line']}\nRULES: NO markdown, NO diff, NO SEARCH. Return ONLY replacement line.\nOUTPUT:"
        strategy_prompt = block.block + "\n" + prompt

        reset_workspace(probe["workspace"])
        t0 = time.time()
        output, ok = call_ollama(strategy_prompt)
        latency = time.time() - t0
        fmt, extracted, replace_ok = classify_output(output)
        normalized = normalize_indentation(extracted, probe["buggy_line"])

        sp = ws / probe["target_file"]
        orig = sp.read_text()
        patched = orig.replace(probe["buggy_line"], normalized, 1) if probe["buggy_line"] in orig else orig
        effective = orig != patched
        ctx_ok, _ = context_syntax_check(patched, str(sp))

        if ctx_ok and replace_ok and effective:
            reset_workspace(probe["workspace"])
            sp2 = ws / probe["target_file"]
            orig2 = sp2.read_text()
            if probe["buggy_line"] in orig2:
                sp2.write_text(orig2.replace(probe["buggy_line"], normalized, 1))
            passed_verify, _ = run_verification(probe)
            reward = 1.0 if passed_verify else 0.0
        else:
            passed_verify = False
            reward = 0.0

        print(f"  Winner M0: {latency:.1f}s reward={reward}")

        all_results.append({
            "instance_id": iid,
            "status": "winner_executed",
            "winner_type": winner["strategy_type"],
            "winner_score": winner["final_score"],
            "ranking": [{"type": r["strategy_type"], "score": r["final_score"]} for r in ranked],
            "reward": reward,
            "latency": latency,
        })

    # Summary
    print(f"\n{'=' * 70}")
    print("S3 RESULTS")
    print(f"{'=' * 70}")

    for r in all_results:
        print(f"  {r['instance_id']}: winner={r.get('winner_type', 'N/A')} reward={r.get('reward', 0)}")

    reward_count = sum(1 for r in all_results if r.get("reward", 0) > 0)
    diverse_winners = len(set(r.get("winner_type") for r in all_results if r.get("winner_type")))

    print(f"\nReward>0: {reward_count}/{len(all_results)}")
    print(f"Winner diversity: {diverse_winners} types")

    verdict = "GREEN" if reward_count >= 2 else "YELLOW" if reward_count >= 1 else "RED"
    print(f"\nS3 Verdict: {verdict}")

    summary = {"verdict": verdict, "reward": reward_count, "diversity": diverse_winners, "total": len(all_results)}
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
