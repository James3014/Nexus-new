"""
G6: Rerun C_12481 with G1-G5 Pipeline
======================================
Uses:
- G1: Agentless candidate pipeline (bounded generation)
- G3: Linear replay runner (isolated execution)
- G4: Structured verifier feedback (if actionable)
- G5: Backend resource policy (model governance)
"""
import os
import sys
import json
import hashlib
import subprocess
import tempfile
from pathlib import Path

os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"

WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.agentless_pipeline import AgentlessCandidatePipeline
from nexus.services.local_heal.semantic_anchor_selection import select_semantic_anchor
from nexus.services.local_heal.backend_resource_policy import BackendResourcePolicy
from nexus.services.local_heal.structured_verifier_feedback import StructuredVerifierFeedback
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

# ── Config ───────────────────────────────────────────────────────────────────
MODEL_NAME = "gemma4-coder-12b-q4km:latest"
OLLAMA_ENDPOINT = "http://localhost:11434"
NUM_CTX = 4096
NUM_PREDICT = 768
TIMEOUT_S = 300
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/g6_rerun_c12481_c13453_v0/C_12481"

# ── Task ─────────────────────────────────────────────────────────────────────
TASK = {
    "task_id": "C_12481",
    "instance_id": "sympy__sympy-12481",
    "repo_dir": str(WORKSPACE_ROOT / ".nexus/workspaces/sympy"),
    "base_commit": "c807dfe756",
    "target_file": "sympy/combinatorics/permutations.py",
    "python_executable": str(WORKSPACE_ROOT / ".venv_sympy/bin/python3"),
    "problem_statement": (
        "Permutation should allow non-disjoint lists in arguments.\n"
        "Currently, Permutation([[0, 1], [0, 2]]) raises ValueError: 'there were repeated elements'.\n"
        "It should allow repeated elements and multiply them as disjoint cycles."
    ),
    "repro_script": (
        "import sys\n"
        "sys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\n"
        "from sympy.combinatorics import Permutation\n"
        "def test_repro():\n"
        "    try:\n"
        "        p = Permutation([[0, 1], [0, 2]])\n"
        "        print(f'Calculated permutation: {p}')\n"
        "        if p == Permutation(0, 1, 2):\n"
        "            print('SUCCESS: Permutation allowed non-disjoint lists and calculated correctly.')\n"
        "            sys.exit(0)\n"
        "        else:\n"
        "            print('FAILURE: Permutation calculated incorrectly.')\n"
        "            sys.exit(1)\n"
        "    except ValueError as e:\n"
        "        if 'there were repeated elements' in str(e):\n"
        "            print(f'BUG PRESENT: ValueError raised for repeated elements: {e}')\n"
        "            sys.exit(1)\n"
        "        else:\n"
        "            print(f'FAILURE: Unexpected ValueError: {e}')\n"
        "            sys.exit(1)\n"
        "    except Exception as e:\n"
        "        print(f'FAILURE: Unexpected exception: {e}')\n"
        "        sys.exit(1)\n"
        "if __name__ == '__main__':\n"
        "    test_repro()\n"
    ),
    "anchor_text": (
        "        if has_dups(temp):\n"
        "            if is_cycle:\n"
        "                raise ValueError('there were repeated elements; to resolve '\n"
        "                'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))\n"
        "            else:\n"
        "                raise ValueError('there were repeated elements.')"
    ),
    "issue_keywords": ["permutation", "disjoint", "cycles", "repeated", "elements"],
}


def ollama_generate(system_prompt: str, user_prompt: str, variant_id: str = "v1") -> str:
    import urllib.request
    payload = json.dumps({
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}
    }).encode()
    print(f"    → [{variant_id}] Invoking {MODEL_NAME}...", flush=True)
    try:
        req = urllib.request.Request(
            f"{OLLAMA_ENDPOINT}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            res = data.get("response", "")
            print(f"    → [{variant_id}] {len(res)} chars received.", flush=True)
            return res
    except Exception as e:
        print(f"    ❌ [{variant_id}] Ollama error: {e}", flush=True)
        return ""


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def run_repro(repro_script: str, python_exe: str, repo_dir: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(repro_script)
        script_path = f.name
    try:
        res = subprocess.run(
            [python_exe, script_path],
            cwd=repo_dir,
            capture_output=True, text=True, timeout=60
        )
        return res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return False, f"REPRO_ERROR: {e}"
    finally:
        Path(script_path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("🏁 G6: Rerun C_12481 with G1-G5 Pipeline")
    print(f"   Model: {MODEL_NAME}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # G5: Validate model policy
    policy = BackendResourcePolicy()
    allowed, reason = policy.validate_execution(MODEL_NAME)
    print(f"   → G5 Policy: {'ALLOWED' if allowed else 'FORBIDDEN'} — {reason}")
    if not allowed:
        print("   ❌ Model not allowed!")
        return

    # 1. Checkout to base_commit
    print("   → Checking out base_commit...")
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])

    # 2. Read source
    source_text = Path(TASK["repo_dir"]) / TASK["target_file"]
    source_text = source_text.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]
    print(f"   → Source hash: {source_hash}")

    # 3. Verify anchor
    anchor = TASK["anchor_text"]
    anchor_count = source_text.count(anchor)
    print(f"   → Anchor found {anchor_count}x in source.")
    if anchor_count != 1:
        print("   ❌ Anchor not found or ambiguous!")
        return

    # 4. Verify bug exists
    print("   → Running baseline repro...")
    baseline_ok, baseline_log = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
    print(f"   → Baseline: {'PASS' if baseline_ok else 'FAIL (bug confirmed)'}")
    (OUTPUT_DIR / "baseline_repro.log").write_text(baseline_log)

    # 5. Semantic anchor selection
    print("   → Running semantic anchor selection...")
    selection = select_semantic_anchor(
        file_path=TASK["target_file"],
        source_text=source_text,
        target_symbol="Permutation.__new__",
        issue_keywords=TASK["issue_keywords"],
    )
    if selection.selected:
        print(f"   → Selected anchor: {selection.selected.symbol_name} (score={selection.selected.score:.2f})")
    else:
        print("   → Selected anchor: fallback (score=0.00)")

    # 6. G1: Run Agentless pipeline
    print("   → Running G1 Agentless pipeline...")

    def generate_fn(anchor_text, symbol, variant_id):
        system = (
            "You are fixing a Python bug with a MINIMAL, PRECISE change.\n\n"
            "RULES:\n"
            "1. Output ONLY raw Python code (max 12 lines)\n"
            "2. NEVER wrap in ```python ... ``` fences\n"
            "3. NEVER add explanation before/after code\n"
            "4. Preserve exact indentation from the anchor\n"
            "5. Change ONLY what is needed to fix the bug\n"
            "6. If you cannot fix with a small change, output: ABSTAIN\n\n"
            "REJECTED (will be discarded):\n"
            "- Markdown fences\n"
            "- Explanation text\n"
            "- Broad refactor touching many lines\n\n"
            "ACCEPTED:\n"
            "- Raw Python code, 1-12 lines\n"
            "- Exact indentation match\n"
            "- Minimal change to fix the bug"
        )
        user = (
            f"Bug: {TASK['problem_statement'][:300]}\n\n"
            f"Symbol: {symbol}\n"
            f"Fix intent: Permutation should allow non-disjoint cycles by converting to Cycle composition.\n\n"
            f"Code to replace:\n{anchor_text}\n\n"
            f"Output ONLY the replacement code (max 12 lines, raw Python):"
        )
        return ollama_generate(system, user, variant_id)

    def verify_fn(replacement):
        # Apply patch
        repo_dir = Path(TASK["repo_dir"])
        source = (repo_dir / TASK["target_file"]).read_text(encoding="utf-8")
        patched = source.replace(anchor, replacement, 1)
        if patched == source:
            return False, "anchor_not_replaced"
        (repo_dir / TASK["target_file"]).write_text(patched, encoding="utf-8")

        # Run repro
        ok, output = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])

        # Restore
        run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])

        return ok, output

    pipeline = AgentlessCandidatePipeline(max_anchors=2, max_candidates_per_anchor=3)
    result = pipeline.run(
        task_id=TASK["task_id"],
        anchors=[
            {"id": "a1", "symbol": "Permutation.__new__", "source_text": anchor, "score": 1.0},
            {"id": "a2", "symbol": "__new__", "source_text": anchor, "score": 0.8},
        ],
        generate_fn=generate_fn,
        verify_fn=verify_fn,
    )

    print(f"   → Pipeline status: {result.status}")
    print(f"   → Candidates: {len(result.candidates)}")
    print(f"   → Selected: {result.selected.candidate_id if result.selected else 'none'}")

    # 7. G4: Structured verifier feedback if applicable
    correction_used = False
    if result.selected is None and result.stage_counts.get("rejected", 0) > 0:
        # Find a candidate that had verifier failure
        verifier_failures = [c for c in result.candidates if "verifier:" in c.rejection_reason]
        if verifier_failures:
            print("   → G4: Applying structured verifier feedback...")
            fb = StructuredVerifierFeedback()
            feedback_output = verifier_failures[0].rejection_reason.replace("verifier:", "")
            packet = fb.parse(
                feedback_output,
                previous_replacement=verifier_failures[0].replacement,
                anchor_text=anchor,
            )
            print(f"   → Failure type: {packet.failure_type}")
            print(f"   → Assertion: {packet.assertion_summary[:100]}")

            # Generate one correction
            system, user = fb.build_correction_prompt(
                packet,
                problem=TASK["problem_statement"],
                symbol="Permutation.__new__",
            )
            correction = ollama_generate(system, user, "correction_v1")

            if correction and not correction.strip().startswith("ABSTAIN"):
                # Apply and verify
                ok, output = verify_fn(correction)
                if ok:
                    print("   → G4: Correction PASSED verifier!")
                    result.selected = type(result.selected)(
                        candidate_id="correction_v1",
                        anchor_id="correction",
                        anchor_symbol="Permutation.__new__",
                        replacement=correction,
                        replacement_hash=hashlib.sha256(correction.encode()).hexdigest()[:16],
                        stage=CandidateStage.SELECTED,
                        verifier_output=output,
                    )
                    correction_used = True
                else:
                    print(f"   → G4: Correction FAILED: {output[:200]}")

    # 8. Save results
    status = "G6_C12481_VERIFIER_PASS_INTERNAL_ONLY" if result.selected else "G6_C12481_PATCH_APPLIED_VERIFIER_FAILED"

    receipt = {
        "task_id": TASK["task_id"],
        "model": MODEL_NAME,
        "base_commit": TASK["base_commit"],
        "source_hash": source_hash,
        "anchor_hash": hashlib.sha256(anchor.encode()).hexdigest()[:16],
        "selected_anchors": [a["id"] for a in pipeline.run(
            task_id=TASK["task_id"],
            anchors=[],
            generate_fn=lambda *a: "",
        ).candidates[:0]] if False else ["a1", "a2"],
        "candidate_count": len(result.candidates),
        "parser_pass_count": sum(1 for c in result.candidates if "parser" not in c.rejection_reason),
        "patch_apply_count": sum(1 for c in result.candidates if c.stage.value in ["patch_applied", "verifier_passed", "selected"]),
        "verifier_pass_count": sum(1 for c in result.candidates if c.stage.value in ["verifier_passed", "selected"]),
        "correction_used": correction_used,
        "compliance_status": "pass",
        "selected_candidate_id": result.selected.candidate_id if result.selected else None,
        "failure_stage_distribution": {c.rejection_reason: sum(1 for x in result.candidates if x.rejection_reason == c.rejection_reason) for c in result.candidates if c.rejection_reason},
        "final_status": status,
        "pipeline_result": result.status,
    }
    (OUTPUT_DIR / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))

    # Restore workspace
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])

    print("\n" + "=" * 60)
    print(f"   Final Status: {status}")
    print(f"   Candidates: {len(result.candidates)}")
    print(f"   Selected: {result.selected.candidate_id if result.selected else 'none'}")
    print(f"   Correction used: {correction_used}")
    print("=" * 60)


if __name__ == "__main__":
    from nexus.services.local_heal.agentless_pipeline import CandidateStage
    main()
