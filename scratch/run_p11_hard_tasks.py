"""
P11: Rerun Hard Tasks After P9/P10
===================================
Uses improved infrastructure:
- P9: Anchor provenance (after_base_checkout) + strict replacement parser
- P10: Semantic anchor selection for multiple candidates

Tasks:
- C_11618 / sympy__sympy-11618
- C_12481 / sympy__sympy-12481
- C_13453 / astropy__astropy-13453
"""
import os
import sys
import json
import hashlib
import urllib.request
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# ── env setup ────────────────────────────────────────────────────────────────
os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"

WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.semantic_anchor_selection import select_semantic_anchor

# ── config ───────────────────────────────────────────────────────────────────
OLLAMA_ENDPOINT = "http://localhost:11434"
MODEL_NAME = "gemma4-coder-12b-q4km:latest"
NUM_CTX    = 4096
NUM_PREDICT= 768
TIMEOUT_S  = 300
N_CANDIDATES = 3
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/p11_hard_tasks_after_anchor_parser_fix_v0"

# ── tasks with anchor intent (for semantic selection) ─────────────────────────
TASKS = [
    {
        "task_id": "C_13453",
        "instance_id": "astropy__astropy-13453",
        "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/astropy",
        "base_commit": "19cc804717",
        "target_file": "astropy/io/ascii/html.py",
        "python_executable": "/Users/jameschen/Workspace/nexus/.venv_astropy/bin/python3",
        "problem_statement": (
            "astropy__astropy-13453: Table.write with format='ascii.html' ignores the 'formats' parameter.\n"
            "When writing a table to HTML format using Table.write(..., format='ascii.html', formats={'col': '%.2f'}), "
            "the specified column format is ignored. It should format the column values accordingly inside the HTML table cells."
        ),
        "repro_script": (
            "from astropy.table import Table\n"
            "import sys\n"
            "def test_repro():\n"
            "    t = Table([[1.12345]], names=['a'])\n"
            "    import io\n"
            "    out = io.StringIO()\n"
            "    t.write(out, format='ascii.html', formats={'a': '%.2f'})\n"
            "    html = out.getvalue()\n"
            "    print('HTML Output:')\n"
            "    print(html)\n"
            "    if '<td>1.12</td>' not in html:\n"
            "        raise AssertionError('formats={\"a\": \"%.2f\"} was ignored!')\n"
            "    print('SUCCESS: formats respected.')\n"
            "if __name__ == '__main__':\n"
            "    try:\n"
            "        test_repro()\n"
            "        sys.exit(0)\n"
            "    except Exception as e:\n"
            "        print(f'FAILURE: {e}')\n"
            "        sys.exit(1)\n"
        ),
        "anchor_text": (
            "                            else:\n\n"
            "                                col_iter_str_vals = self.fill_values(col, col.info.iter_str_vals())\n"
            "                                col_str_iters.append(col_iter_str_vals)\n\n"
            "                                new_cols_escaped.append(col_escaped)"
        ),
        "symbol_name": "HTML.write",
        "anchor_intent": "HTML.write() calls col.info.iter_str_vals() but ignores self.data.formats; need to apply column format before iter_str_vals.",
        "issue_keywords": ["format", "html", "table", "write", "formats"],
    },
    {
        "task_id": "C_11618",
        "instance_id": "sympy__sympy-11618",
        "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/sympy",
        "base_commit": "d4f8832c21",
        "target_file": "sympy/geometry/point.py",
        "python_executable": "/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3",
        "problem_statement": (
            "Point.distance zips coordinates, and does not check for dimension mismatch.\n"
            "For example, Point(2,0).distance(Point(1,0,2)) returns 1 instead of raising ValueError.\n"
            "It should check for dimension mismatch and raise ValueError."
        ),
        "repro_script": (
            "import sys\n"
            "sys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\n"
            "from sympy import Point\n"
            "def test_repro():\n"
            "    p1 = Point(2, 0)\n"
            "    p2 = Point(1, 0, 2)\n"
            "    try:\n"
            "        dist = p1.distance(p2)\n"
            "        print(f'Calculated distance: {dist}')\n"
            "        if dist == 1:\n"
            "            print('FAILURE: Point.distance zipped without checking dimensions, returned 1.')\n"
            "            sys.exit(1)\n"
            "        else:\n"
            "            print('SUCCESS: distance handled dimension mismatch.')\n"
            "            sys.exit(0)\n"
            "    except ValueError as e:\n"
            "        print(f'SUCCESS: ValueError raised: {e}')\n"
            "        sys.exit(0)\n"
            "    except Exception as e:\n"
            "        print(f'FAILURE: Unexpected exception: {e}')\n"
            "        sys.exit(1)\n"
            "if __name__ == '__main__':\n"
            "    test_repro()\n"
        ),
        "anchor_text": (
            "        s, p = Point._normalize_dimension(self, Point(p))\n"
            "        return sqrt(Add(*((a - b)**2 for a, b in zip(s, p))))"
        ),
        "symbol_name": "Point.distance",
        "anchor_intent": "Point.distance normalizes dimensions before zipping, but _normalize_dimension silently pads shorter point. Need to raise ValueError if dimensions differ.",
        "issue_keywords": ["distance", "dimension", "mismatch", "valueerror", "zip"],
    },
    {
        "task_id": "C_12481",
        "instance_id": "sympy__sympy-12481",
        "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/sympy",
        "base_commit": "c807dfe756",
        "target_file": "sympy/combinatorics/permutations.py",
        "python_executable": "/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3",
        "problem_statement": (
            "Permutation should allow non-disjoint lists in arguments.\n"
            "Currently, Permutation([[0, 1], [0, 2]]) raises a ValueError: 'there were repeated elements'.\n"
            "It should allow repeated elements and multiply them as disjoint cycles (i.e. resolve cycles like Cycle(0, 1)(0, 2) = Permutation(0, 1, 2))."
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
        "symbol_name": "Permutation.__new__",
        "anchor_intent": "Permutation.__new__ raises ValueError for repeated elements in cyclic form. Need to allow non-disjoint cycles by converting to Cycle composition.",
        "issue_keywords": ["permutation", "disjoint", "cycles", "repeated", "elements"],
    },
]


def ollama_generate(system_prompt: str, user_prompt: str, variant_id: str = "v1") -> str:
    payload = json.dumps({
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        }
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


def build_repair_prompt(problem: str, anchor_text: str, anchor_intent: str, symbol: str,
                        source_context: str, variant: int) -> tuple[str, str]:
    system = (
        "You are an expert Python engineer fixing a specific bug. "
        "The exact source code anchor to replace is provided. "
        "Output ONLY the replacement Python code — no explanation, no markdown, no file paths. "
        "The output will directly replace the anchor text in the file."
    )
    variants = [
        f"Fix the bug in `{symbol}`.\n\nProblem:\n{problem}\n\nHint: {anchor_intent}\n\nCode to replace:\n```python\n{anchor_text}\n```\n\nOutput ONLY the fixed replacement code:",
        f"BUG: {problem[:300]}\n\nThe following code in `{symbol}` must be fixed:\n```python\n{anchor_text}\n```\n\nFix intent: {anchor_intent}\n\nWrite ONLY the fixed code (same indentation):",
        f"Source context:\n```python\n{source_context[:1200]}\n```\n\nAnchor to replace in `{symbol}`:\n```python\n{anchor_text}\n```\n\nBug: {problem[:200]}\nFix: {anchor_intent}\n\nOutput replacement only:",
    ]
    user = variants[variant % len(variants)]
    return system, user


def run_git(args, cwd):
    res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    return res


def run_repro(repro_script: str, python_exe: str, repo_dir: Path) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(repro_script)
        script_path = f.name
    try:
        res = subprocess.run(
            [python_exe, script_path],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=60
        )
        log = res.stdout + "\n" + res.stderr
        return res.returncode == 0, log.strip()
    except Exception as e:
        return False, f"REPRO_ERROR: {e}"
    finally:
        Path(script_path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print(f"🏁 P11: Hard Tasks After P9/P10")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Protocol: NEXUS_PROTOCOL_MODE={os.environ['NEXUS_PROTOCOL_MODE']}")
    print(f"   P9: Anchor provenance + strict parser")
    print(f"   P10: Semantic anchor selection")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    patch_applier = PatchApplier(parser, patcher)

    results_rollup = []

    for t in TASKS:
        print(f"\n{'─'*60}")
        print(f"👉 Task: {t['task_id']} ({t['instance_id']})")
        print(f"   Symbol: {t['symbol_name']}")

        task_out = OUTPUT_DIR / t["task_id"]
        task_out.mkdir(parents=True, exist_ok=True)

        repo = t["repo_dir"]
        python_exe = t["python_executable"]

        # 1. Checkout to base commit (P9: must happen BEFORE anchor extraction)
        run_git(["checkout", "--", "."], repo)
        run_git(["clean", "-fd"], repo)
        run_git(["checkout", t["base_commit"]], repo)

        # 2. Read source text AFTER checkout
        source_text = (repo / t["target_file"]).read_text(encoding="utf-8")
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]

        # 3. P10: Semantic anchor selection (generates candidates, scores, selects best)
        print("   → Running semantic anchor selection...")
        selection_result = select_semantic_anchor(
            file_path=t["target_file"],
            source_text=source_text,
            target_symbol=t["symbol_name"],
            issue_keywords=t.get("issue_keywords", []),
        )

        if selection_result.selected:
            anchor = selection_result.selected.source_text
            print(f"   → Selected anchor: {selection_result.selected.symbol_name} "
                  f"(score={selection_result.selected.score:.2f}, "
                  f"type={selection_result.selected.candidate_type})")
            print(f"   → Anchor span: L{selection_result.selected.span_start}-L{selection_result.selected.span_end}")
        else:
            # Fallback to hardcoded anchor
            anchor = t["anchor_text"]
            print("   → Semantic selection failed, using hardcoded anchor")

        # 4. P9: Verify anchor provenance
        anchor_hash = hashlib.sha256(anchor.encode()).hexdigest()[:16]
        anchor_count = source_text.count(anchor)
        print(f"   → Anchor ({len(anchor)} chars) found {anchor_count}x in source.")

        if anchor_count == 0:
            print("   ❌ Anchor NOT found in source! Skipping.")
            results_rollup.append({
                "task_id": t["task_id"],
                "status": "P11_ANCHOR_NOT_IN_SOURCE",
                "anchor_preview": anchor[:100],
            })
            continue
        if anchor_count > 1:
            print("   ❌ Anchor ambiguous (found multiple times). Skipping.")
            results_rollup.append({
                "task_id": t["task_id"],
                "status": "P11_ANCHOR_AMBIGUOUS",
                "anchor_count": anchor_count,
            })
            continue

        # 5. Verify repro fails at baseline
        print("   → Running baseline repro to confirm bug is present...")
        baseline_ok, baseline_log = run_repro(t["repro_script"], python_exe, repo)
        print(f"   → Baseline repro: {'PASS (bug not reproducible)' if baseline_ok else 'FAIL (bug confirmed)'}")
        (task_out / "baseline_repro.log").write_text(baseline_log)

        if baseline_ok:
            print("   ⚠️  Bug not reproducible at base commit. Noting but proceeding...")

        # 6. Get source context for prompts
        sliced_path = WORKSPACE_ROOT / f"artifacts/runtime/c3_ast_slicing_metrics_v0/{t['task_id']}/sliced_context.py"
        if sliced_path.exists():
            source_context = sliced_path.read_text(encoding="utf-8")
            print(f"   → Using AST-sliced context ({len(source_context)} chars).")
        else:
            source_context = source_text[:3000]
            print(f"   → Using raw source context ({len(source_context)} chars).")

        # 7. Generate N candidates
        print(f"   → Generating {N_CANDIDATES} model candidates...")
        raw_outputs = []
        for i in range(N_CANDIDATES):
            variant_id = f"v{i+1}"
            sys_prompt, usr_prompt = build_repair_prompt(
                problem=t["problem_statement"],
                anchor_text=anchor,
                anchor_intent=t["anchor_intent"],
                symbol=t["symbol_name"],
                source_context=source_context,
                variant=i,
            )
            response = ollama_generate(sys_prompt, usr_prompt, variant_id)
            raw_outputs.append((response, variant_id, f"call_{i+1}"))

        # 8. Parse and apply candidates (P9: strict parser)
        print("   → Parsing and applying candidates...")
        source_text_fresh = (repo / t["target_file"]).read_text(encoding="utf-8")
        loc_files = [LocalizedFile(path=t["target_file"], content=source_text_fresh)]

        selected_candidate = None
        all_candidates = []

        for idx, (raw_out, variant, call_id) in enumerate(raw_outputs):
            if not raw_out:
                all_candidates.append({"candidate_id": f"cand_{idx+1}", "failure_stage": "empty_response"})
                continue

            # P9: Parse with strict anchored_edit mode
            intents_or_err = parser.parse(raw_out, anchor_text=anchor)
            if hasattr(intents_or_err, "kind"):
                all_candidates.append({
                    "candidate_id": f"cand_{idx+1}",
                    "failure_stage": f"parser_rejected:{intents_or_err.kind.name}",
                    "error_message": intents_or_err.message,
                })
                continue

            intent = intents_or_err[0]
            rep_hash = hashlib.sha256(intent.replace.strip().encode()).hexdigest()[:16]
            already_seen = any(c.get("rep_hash") == rep_hash for c in all_candidates)
            if already_seen:
                print(f"    → [cand_{idx+1}] Duplicate replacement, skipping.")
                continue

            # Apply to source
            full_path = repo / t["target_file"]
            try:
                patched = source_text_fresh.replace(anchor, intent.replace, 1)
                if patched == source_text_fresh:
                    all_candidates.append({
                        "candidate_id": f"cand_{idx+1}",
                        "failure_stage": "anchor_not_replaced",
                        "rep_hash": rep_hash,
                    })
                    continue
                full_path.write_text(patched, encoding="utf-8")
                print(f"    → [cand_{idx+1}] Patch applied ({len(intent.replace)} chars replacement).")
            except Exception as e:
                all_candidates.append({
                    "candidate_id": f"cand_{idx+1}",
                    "failure_stage": f"apply_error:{e}",
                    "rep_hash": rep_hash,
                })
                continue

            # Run repro
            repro_ok, repro_log = run_repro(t["repro_script"], python_exe, repo)
            (task_out / f"cand_{idx+1}_repro.log").write_text(repro_log)
            print(f"    → [cand_{idx+1}] Repro: {'SUCCESS ✅' if repro_ok else 'FAILED ❌'}")

            cand_info = {
                "candidate_id": f"cand_{idx+1}",
                "variant": variant,
                "rep_hash": rep_hash,
                "replacement_preview": intent.replace[:200],
                "repro_passed": repro_ok,
                "failure_stage": "none" if repro_ok else "repro_fail",
                "selected": repro_ok,
            }
            all_candidates.append(cand_info)

            if repro_ok:
                selected_candidate = cand_info
                diff_res = subprocess.run(
                    ["git", "diff", t["target_file"]],
                    cwd=str(repo),
                    capture_output=True, text=True
                )
                (task_out / "patch.diff").write_text(diff_res.stdout)
                print(f"   ✅ Selected candidate {idx+1}! Patch saved.")
                break
            else:
                full_path.write_text(source_text_fresh, encoding="utf-8")

        # Restore workspace
        run_git(["checkout", "--", "."], repo)
        run_git(["clean", "-fd"], repo)

        # Determine status
        task_success = selected_candidate is not None
        if task_success:
            status = "P11_VERIFIER_PASS_INTERNAL_ONLY"
        elif any(c.get("failure_stage", "").startswith("parser_rejected:") for c in all_candidates):
            status = "P11_PARSER_REJECTED_BAD_OUTPUT"
        elif any(c.get("failure_stage") == "anchor_not_replaced" for c in all_candidates):
            status = "P11_PATCH_APPLY_FAILED"
        else:
            status = "P11_SEMANTIC_FAILURE_AFTER_VALID_PATCH"

        receipt = {
            "task_id": t["task_id"],
            "instance_id": t["instance_id"],
            "model": MODEL_NAME,
            "protocol_mode": "anchored_edit",
            "base_commit": t["base_commit"],
            "checked_out_commit": t["base_commit"],
            "anchor_char_len": len(anchor),
            "anchor_found_count": anchor_count,
            "anchor_text_hash": anchor_hash,
            "source_hash": source_hash,
            "anchor_extraction_stage": "after_base_checkout",
            "semantic_selection": {
                "selected_candidate": selection_result.selected.anchor_id if selection_result.selected else None,
                "selection_reason": selection_result.selection_reason,
                "total_candidates": selection_result.total_candidates,
            },
            "baseline_bug_confirmed": not baseline_ok,
            "n_candidates_generated": len(raw_outputs),
            "n_candidates_evaluated": len(all_candidates),
            "status": status,
            "gate_passed": task_success,
            "selected_candidate": selected_candidate,
            "all_candidates_summary": all_candidates,
        }
        (task_out / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))

        results_rollup.append({
            "task_id": t["task_id"],
            "instance_id": t["instance_id"],
            "success": task_success,
            "status": status,
            "protocol_mode": "anchored_edit",
            "candidates_tried": len(all_candidates),
            "parser_rejections": sum(1 for c in all_candidates if c.get("failure_stage", "").startswith("parser_rejected:")),
        })

        status_str = "SUCCESS ✅" if task_success else f"FAILED ❌ ({status})"
        print(f"\n   Task {t['task_id']}: {status_str}")

    # Rollup
    n_success = sum(1 for r in results_rollup if r.get("success"))
    rollup = {
        "status": "P11_COMPLETE",
        "model": MODEL_NAME,
        "protocol_mode": "anchored_edit",
        "p9_anchor_provenance": "enforced",
        "p9_strict_parser": "enforced",
        "p10_semantic_selection": "enforced",
        "tasks_total": len(results_rollup),
        "tasks_success": n_success,
        "tasks_failed": len(results_rollup) - n_success,
        "results": results_rollup,
    }
    (OUTPUT_DIR / "repair_results.json").write_text(json.dumps(rollup, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print(f"🎉 P11 Complete: {n_success}/{len(results_rollup)} tasks succeeded")
    for r in results_rollup:
        mark = "✅" if r.get("success") else "❌"
        print(f"   {mark} {r['task_id']} — {r.get('status', '')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
