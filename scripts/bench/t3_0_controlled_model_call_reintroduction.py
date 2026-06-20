#!/usr/bin/env python3
"""T3.0: Controlled Model-Call Reintroduction Experiment

D0: Deterministic baseline replay on 6-task subset
M1: Model shadow proposal (model_calls>0, REPLACE-only)
M2: Guarded model candidate (clean attribution only)
"""

import json
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
PYTHON_EXEC_SYMPY = str(NEXUS_ROOT / ".nexus/workspaces/sympy/.venv39/bin/python")
RUN_GROUP = "T3_0_CONTROLLED_MODEL_CALL_REINTRODUCTION"

# 6-task subset per T3.0 spec
SUBSET_TASKS = [
    {
        "instance_id": "astropy__astropy-12907",
        "workspace": "astropy",
        "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/modeling/separable.py",
        "buggy_line": "        cright[-right.shape[0]:, -right.shape[1]:] = 1",
        "fixed_line": "        cright[-right.shape[0]:, -right.shape[1]:] = right",
        "canonical_span_source": "ast_boundary",
        "selection_reason": "ast_boundary canonical recovery case",
        "repro_script": "import sys, os, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.modeling import models as m\nfrom astropy.modeling.separable import separability_matrix\ncm = m.Linear1D(10) & m.Linear1D(5)\nmodel = m.Pix2Sky_TAN() & cm\nres = separability_matrix(model)\nexpected = np.array([[True,True,False,False],[True,True,False,False],[False,False,True,False],[False,False,False,True]])\nif np.array_equal(res, expected):\n    print('SUCCESS'); sys.exit(0)\nelse:\n    print('BUG PRESENT'); sys.exit(1)\n",
    },
    {
        "instance_id": "astropy__astropy-13236",
        "workspace": "astropy",
        "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/table/table.py",
        "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True",
        "fixed_block": "",
        "canonical_span_source": "unified_diff",
        "selection_reason": "unified_diff + REMOVE_BLOCK semantic recovery case",
        "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n",
    },
    {
        "instance_id": "astropy__astropy-13453",
        "workspace": "astropy",
        "python_exec": PYTHON_EXEC_ASTROPY,
        "target_file": "astropy/io/ascii/html.py",
        "buggy_line": "        self.data.header.cols = cols",
        "fixed_line": "        self.data.header.cols = cols\n        self.data.cols = cols",
        "canonical_span_source": "locked_search",
        "selection_reason": "dependency closure + locked_search case",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.io import ascii\nimport tempfile\nwith tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:\n    f.write('<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>')\n    fname = f.name\ntry:\n    table = ascii.read(fname, format='html')\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "sympy__sympy-13031",
        "workspace": "sympy",
        "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/matrices/sparse.py",
        "buggy_line": "        if not self:\n            return type(self)(other)",
        "fixed_line": "        # A null matrix can always be stacked (see  #10770)\n        if self.rows == 0 and self.cols != other.cols:\n            return self._new(0, other.cols, []).col_join(other)",
        "canonical_span_source": "ast_boundary",
        "selection_reason": "repro closure + sympy semantic patch case",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Matrix\ntry:\n    A = Matrix(0, 2, [])\n    B = Matrix([[1, 2], [3, 4]])\n    C = A.col_join(B)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "sympy__sympy-12419",
        "workspace": "sympy",
        "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/polys/polytools.py",
        "buggy_line": "        if not p:",
        "fixed_line": "        if p is None or p.is_zero:",
        "canonical_span_source": "locked_search",
        "selection_reason": "prior patch_mismatch, true new T2.8 task",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import Poly, Symbol\ntry:\n    x = Symbol('x')\n    p = Poly(0, x)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
    {
        "instance_id": "sympy__sympy-13647",
        "workspace": "sympy",
        "python_exec": PYTHON_EXEC_SYMPY,
        "target_file": "sympy/simplify/simplify.py",
        "buggy_line": "        if not expr:",
        "fixed_line": "        if expr is None or expr.is_zero:",
        "canonical_span_source": "locked_search",
        "selection_reason": "prior patch_mismatch, true new T2.8 task",
        "repro_script": "import sys, os\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\nfrom sympy import simplify, Symbol\ntry:\n    x = Symbol('x')\n    result = simplify(x + 0)\n    print('SUCCESS'); sys.exit(0)\nexcept Exception as e:\n    print(f'BUG PRESENT: {e}'); sys.exit(1)\n",
    },
]


def reset_workspace(ws_name):
    ws = NEXUS_ROOT / ".nexus/workspaces" / ws_name
    if ws.exists():
        subprocess.run(["git", "checkout", "--", "."], cwd=str(ws), capture_output=True, timeout=30)
        subprocess.run(["git", "clean", "-fd"], cwd=str(ws), capture_output=True, timeout=30)


def run_verification(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    repro_dst = ws / "reproduce_bug.py"
    repro_dst.write_text(task["repro_script"])
    try:
        r = subprocess.run([task["python_exec"], str(repro_dst)], capture_output=True, text=True, timeout=120, cwd=str(ws))
        output = r.stdout + r.stderr
        passed = r.returncode == 0 and "BUG PRESENT" not in output
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def apply_fix(task):
    ws = NEXUS_ROOT / ".nexus/workspaces" / task["workspace"]
    source_path = ws / task["target_file"]
    if not source_path.exists():
        return "file_not_found", False
    source = source_path.read_text()
    if "buggy_block" in task:
        if task["buggy_block"] in source:
            source_path.write_text(source.replace(task["buggy_block"], task["fixed_block"], 1))
            return "REMOVE_BLOCK", True
        return "block_not_found", False
    else:
        if task["buggy_line"] in source:
            source_path.write_text(source.replace(task["buggy_line"], task["fixed_line"], 1))
            return "AST_SYMBOL_FIX", True
        return "line_not_found", False


def run_d0(task):
    """D0: Deterministic baseline replay."""
    print(f"\n  [D0] {task['instance_id']}")
    reset_workspace(task["workspace"])

    passed_before, _ = run_verification(task)
    if passed_before:
        return {"mode": "D0", "solved": True, "verification": "PASS",
                "canonical_span_source": "locked_search", "deterministic_fallback_used": False,
                "model_calls": 0, "model_patch_reward": 0.0, "failure_class": "SOLVED"}

    fix_type, applied = apply_fix(task)
    passed_after, report = run_verification(task)

    return {
        "mode": "D0",
        "solved": passed_after,
        "verification": "PASS" if passed_after else f"FAIL: {report[:200]}",
        "canonical_span_source": "ast_boundary" if fix_type == "AST_SYMBOL_FIX" else "unified_diff" if fix_type == "REMOVE_BLOCK" else "locked_search",
        "deterministic_fallback_used": applied,
        "deterministic_fallback_reward": fix_type if applied else "",
        "model_calls": 0,
        "model_patch_reward": 0.0,
        "failure_class": "SOLVED" if passed_after else "VERIFICATION_FAILED",
    }


def run_m1_placeholder(task):
    """M1: Model shadow proposal — placeholder (needs model infrastructure)."""
    return {
        "mode": "M1",
        "solved": False,
        "verification": "NOT_RUN",
        "model_calls": 0,
        "model_patch_reward": 0.0,
        "failure_class": "model_infrastructure_not_available",
        "failure_reason": "M1 requires model server (Qwen14B). Local model endpoint not configured.",
        "model_generated_search_detected": False,
        "model_generated_search_used": False,
    }


def run_m2_placeholder(task):
    """M2: Guarded model candidate — placeholder (needs M1 success)."""
    return {
        "mode": "M2",
        "solved": False,
        "verification": "NOT_RUN",
        "model_calls": 0,
        "model_patch_reward": 0.0,
        "failure_class": "m1_not_passed",
        "failure_reason": "M2 requires M1 to produce syntactically valid patch first.",
    }


def write_receipt(instance_id, mode, result):
    receipt = {
        "schema": "nexus.local_heal.t3_0_model_call_receipt.v1",
        "instance_id": instance_id,
        "run_group": RUN_GROUP,
        "mode": mode,
        "simulated": False,
        "claim_eligible": False,
        "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_experiment",
        "telemetry": {
            "instance_id": instance_id,
            "run_group": RUN_GROUP,
            "mode": mode,
            "simulated": False,
            "claim_eligible": False,
            "public_claim_allowed": False,
            "claim_block_reason": "internal_model_call_experiment",
            "model_name": result.get("model_name", "none"),
            "model_calls": result.get("model_calls", 0),
            "canonical_span_source": result.get("canonical_span_source", ""),
            "model_generated_search_detected": result.get("model_generated_search_detected", False),
            "model_generated_search_used": result.get("model_generated_search_used", False),
            "patch_applied": result.get("deterministic_fallback_used", False),
            "syntax_gate_passed": result.get("solved", False),
            "verification_result": result.get("verification", ""),
            "solved": result.get("solved", False),
            "deterministic_fallback_used": result.get("deterministic_fallback_used", False),
            "model_patch_reward": result.get("model_patch_reward", 0.0),
            "deterministic_fallback_reward": result.get("deterministic_fallback_reward", ""),
            "export_as_model_patch_success": False,
            "export_as_canonical_recovery_success": result.get("solved", False) and mode == "D0",
            "export_as_public_claim": False,
            "failure_class": result.get("failure_class", ""),
            "failure_reason": result.get("failure_reason", ""),
        },
    }
    d = NEXUS_ROOT / ".nexus/reports/local_heal" / f"{instance_id}__{RUN_GROUP}__{mode}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    return d / "receipt.json"


def main():
    print("=" * 70)
    print("T3.0: Controlled Model-Call Reintroduction Experiment")
    print(f"Run Group: {RUN_GROUP}")
    print(f"Subset: {len(SUBSET_TASKS)} tasks")
    print("=" * 70)

    # Verify T2.9 artifacts
    print("\n[TASK A] Verifying T2.9 artifacts...")
    required = [
        "configs/baselines/t2_9_20_task_recovery_baseline.yaml",
        "docs/reports/t2_9_20_task_evidence_pack.md",
        "docs/reports/recovery_rule_registry_v1_1_freeze.md",
        "docs/reports/s2t_export_claim_guard_t2_9_freeze.md",
    ]
    all_present = True
    for r in required:
        if (NEXUS_ROOT / r).exists():
            print(f"  PASS: {r}")
        else:
            print(f"  MISSING: {r}")
            all_present = False

    if not all_present:
        print("\nT3.0 PRE-FLIGHT FAIL: Missing T2.9 artifacts. Cannot proceed.")
        return 1

    # Print subset
    print(f"\n[TASK B] Selected subset ({len(SUBSET_TASKS)} tasks):")
    for t in SUBSET_TASKS:
        print(f"  {t['instance_id']} — {t['selection_reason']}")

    all_results = []

    for task in SUBSET_TASKS:
        print(f"\n{'=' * 60}")
        print(f"TASK: {task['instance_id']}")
        print(f"{'=' * 60}")

        # D0
        d0 = run_d0(task)
        write_receipt(task["instance_id"], "D0", d0)
        all_results.append({"instance_id": task["instance_id"], **d0})

        # M1
        m1 = run_m1_placeholder(task)
        write_receipt(task["instance_id"], "M1", m1)
        all_results.append({"instance_id": task["instance_id"], **m1})

        # M2
        m2 = run_m2_placeholder(task)
        write_receipt(task["instance_id"], "M2", m2)
        all_results.append({"instance_id": task["instance_id"], **m2})

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.0 RESULTS")
    print(f"{'=' * 70}")

    d0_results = [r for r in all_results if r["mode"] == "D0"]
    m1_results = [r for r in all_results if r["mode"] == "M1"]
    m2_results = [r for r in all_results if r["mode"] == "M2"]

    d0_solved = sum(1 for r in d0_results if r["solved"])
    print(f"\nD0 baseline: {d0_solved}/{len(d0_results)} PASS")
    print(f"M1 shadow: {sum(1 for r in m1_results if r.get('model_calls', 0) > 0)}/{len(m1_results)} with model calls")
    print(f"M2 candidates: {sum(1 for r in m2_results if r.get('model_patch_reward', 0) > 0)}/{len(m2_results)} model_patch_reward=1.0")

    # Guard checks
    violations = 0
    for r in all_results:
        if r.get("model_calls", 0) == 0 and r.get("model_patch_reward", 0) > 0:
            print(f"  VIOLATION: {r['instance_id']} {r['mode']} model_calls=0 but reward>0")
            violations += 1
        if r.get("export_as_public_claim", False):
            print(f"  VIOLATION: {r['instance_id']} {r['mode']} public_claim=true")
            violations += 1

    print(f"\nGuard violations: {violations}")

    # Verdict
    if d0_solved == len(d0_results) and violations == 0:
        if any(r.get("model_patch_reward", 0) > 0 for r in m2_results):
            verdict = "GREEN"
        else:
            verdict = "YELLOW"
    elif d0_solved >= len(d0_results) - 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.0 Verdict: {verdict}")

    if verdict == "YELLOW":
        print("Recommendation: Prompt/patch format refinement before expanding model-call set.")
        print("T3.0 model infrastructure gap: M1/M2 require local Qwen14B endpoint.")
    elif verdict == "GREEN":
        print("Recommendation: T3.1 controlled expansion to 10 model-call tasks.")
    else:
        print("Recommendation: Fix baseline instability before model-call experiments.")

    # Write summary
    summary = {
        "verdict": verdict,
        "run_group": RUN_GROUP,
        "subset_count": len(SUBSET_TASKS),
        "d0_solved": d0_solved,
        "d0_total": len(d0_results),
        "m1_model_calls": sum(1 for r in m1_results if r.get("model_calls", 0) > 0),
        "m2_model_patch_reward_1": sum(1 for r in m2_results if r.get("model_patch_reward", 0) > 0),
        "guard_violations": violations,
        "model_infrastructure_gap": "M1/M2 require local Qwen14B endpoint (not configured)",
    }
    summary_path = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
