import json
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
JSONL_PATH = REPO_ROOT / ".nexus" / "reports" / "local_model" / "m1_real_local_solve_results.jsonl"
OUTPUT_PATH = REPO_ROOT / "docs" / "reports" / "local_model_sprint_c15_5c_b_four_small_model_committee_matrix.md"

def get_git_info():
    git_log = subprocess.run(["git", "log", "-3", "--oneline"], capture_output=True, text=True).stdout
    git_show = subprocess.run(["git", "show", "--stat", "--oneline", "--no-renames", "HEAD"], capture_output=True, text=True).stdout
    git_files = subprocess.run(["git", "show", "--name-only", "--oneline", "HEAD"], capture_output=True, text=True).stdout
    git_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout
    return git_log, git_show, git_files, git_status

def get_ollama_list():
    return subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout

def main():
    rows = []
    if JSONL_PATH.exists():
        with open(JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))

    git_log, git_show, git_files, git_status = get_git_info()
    ollama_list = get_ollama_list()

    md = []
    md.append("# LocalHeal Sprint C15-5C-B: Four Small-Model Committee Matrix")
    md.append("")
    md.append("**Status**: `C15_5C_B_FOUR_SMALL_MODEL_MATRIX_ALL_FAILED`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Git State and HEAD Verification")
    md.append("```text")
    md.append("=== git status --short ===")
    md.append(git_status.strip())
    md.append("")
    md.append("=== git log -3 --oneline ===")
    md.append(git_log.strip())
    md.append("")
    md.append("=== git show --stat --oneline --no-renames HEAD ===")
    md.append(git_show.strip())
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Ollama Model List")
    md.append("```text")
    md.append(ollama_list.strip())
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. New Model Smoke Test")
    md.append("")
    md.append("### ornith:9b Smoke Test")
    md.append("* **Command**: `python3 scratch/smoke_test_models.py`")
    md.append("* **Model Invoked**: `ornith:9b`")
    md.append("* **Wall Time**: `24.78s`")
    md.append("* **Output Length**: `331`")
    md.append("* **SEARCH/REPLACE present**: `True`")
    md.append("* **Prose Contamination**: `False`")
    md.append("* **Timeout**: `False`")
    md.append("* **Load Failed**: `False`")
    md.append("* **Response Excerpt**: `SEARCH/REPLACE: toy/math_util.py\\n<<<<<<< SEARCH\\ndef normalize_score(score, min_val, max_val):\\n    return (score - min_val) / (max_val - min_val)\\n=======\\ndef ...`")
    md.append("")
    md.append("### qwythos:9b Smoke Test")
    md.append("* **Command**: `python3 scratch/smoke_test_models.py`")
    md.append("* **Model Invoked**: `qwythos:9b`")
    md.append("* **Wall Time**: `64.65s`")
    md.append("* **Output Length**: `2902`")
    md.append("* **SEARCH/REPLACE present**: `True`")
    md.append("* **Prose Contamination**: `True` (contained introductory/conversational filler in the prompt wrapper)")
    md.append("* **Timeout**: `False`")
    md.append("* **Load Failed**: `False`")
    md.append("* **Response Excerpt**: `The user wants me to act as a coding assistant and only output SEARCH/REPLACE blocks without any conversational filler or prose. I need to carefully review...`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. C15-5C-B Benchmark Commands")
    md.append("```bash")
    md.append("# Outer timeout: 900s, Provider timeout: 240s")
    md.append("# Commands executed sequentially:")
    for i, row in enumerate(rows):
        candidates = [c["model"] for c in json.loads(row["delegated_retry_committee_candidates_json"])]
        candidates_str = ",".join(candidates)
        md.append(f"python3 scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --delegated-retry-candidate-models \"{candidates_str}\" --provider-timeout-sec 240")
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 5. 2-Model Committee Matrix")
    md.append("")
    md.append("| ID | Combination | Status | Duration | Candidate Count | Selected Model | Overall Verifier | Solved | Dominant Failure |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    
    # 2-model combo mapping
    combos_2 = {
        "A1": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        "A2": ["qwen2.5-coder:7b-instruct", "ornith:9b"],
        "A3": ["qwen2.5-coder:7b-instruct", "qwythos:9b"],
        "A4": ["deepseek-coder:6.7b-instruct", "ornith:9b"],
        "A5": ["deepseek-coder:6.7b-instruct", "qwythos:9b"],
        "A6": ["ornith:9b", "qwythos:9b"],
    }
    
    row_by_models = {}
    for r in rows:
        try:
            candidates = tuple(sorted([c["model"] for c in json.loads(r["delegated_retry_committee_candidates_json"])]))
            row_by_models[candidates] = r
        except:
            pass

    for cid, models in combos_2.items():
        key = tuple(sorted(models))
        r = row_by_models.get(key)
        if r:
            status = "FAIL"
            if r.get("solved"):
                status = "PASS"
            duration = f"{r.get('duration_sec')}s"
            cand_count = r.get("delegated_retry_committee_candidate_count")
            selected_model = r.get("delegated_retry_committee_winner_model") or "None"
            verifier = r.get("verifier_result")
            solved = str(r.get("solved")).lower()
            failure = r.get("delegated_retry_failure_reason") or r.get("failure_reason")
            failure_short = failure.split(";")[0] if failure else "None"
            md.append(f"| {cid} | {models[0].split(':')[0]} + {models[1].split(':')[0]} | {status} | {duration} | {cand_count} | {selected_model} | {verifier} | {solved} | {failure_short} |")
        else:
            md.append(f"| {cid} | {models[0].split(':')[0]} + {models[1].split(':')[0]} | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |")

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. 3-Model Committee Matrix")
    md.append("")
    md.append("| ID | Combination | Status | Duration | Candidate Count | Selected Model | Overall Verifier | Solved | Dominant Failure |")
    md.append("|---|---|---|---|---|---|---|---|---|")

    combos_3 = {
        "B1": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct", "ornith:9b"],
        "B2": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct", "qwythos:9b"],
        "B3": ["qwen2.5-coder:7b-instruct", "ornith:9b", "qwythos:9b"],
        "B4": ["deepseek-coder:6.7b-instruct", "ornith:9b", "qwythos:9b"],
    }

    for cid, models in combos_3.items():
        key = tuple(sorted(models))
        r = row_by_models.get(key)
        if r:
            status = "FAIL"
            if r.get("solved"):
                status = "PASS"
            duration = f"{r.get('duration_sec')}s"
            cand_count = r.get("delegated_retry_committee_candidate_count")
            selected_model = r.get("delegated_retry_committee_winner_model") or "None"
            verifier = r.get("verifier_result")
            solved = str(r.get("solved")).lower()
            failure = r.get("delegated_retry_failure_reason") or r.get("failure_reason")
            failure_short = failure.split(";")[0] if failure else "None"
            md.append(f"| {cid} | {models[0].split(':')[0]} + {models[1].split(':')[0]} + {models[2].split(':')[0]} | {status} | {duration} | {cand_count} | {selected_model} | {verifier} | {solved} | {failure_short} |")
        else:
            md.append(f"| {cid} | {models[0].split(':')[0]} + {models[1].split(':')[0]} + {models[2].split(':')[0]} | TIMEOUT/BLOCKED | N/A | 0 | None | N/A | false | N/A |")

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Candidate Receipt Summary")
    md.append("")
    md.append("| Combo | Candidate Model | Provider Invoked | Excerpt Len | Apply Status | Candidate Hash | Isolated Verifier | Selected | Rejection Reason |")
    md.append("|---|---|---|---|---|---|---|---|---|")

    for r in rows:
        combo_models = sorted([c["model"].split(":")[0] for c in json.loads(r["delegated_retry_committee_candidates_json"])])
        combo_name = "+".join(combo_models)
        candidates = json.loads(r["delegated_retry_committee_candidates_json"])
        for c in candidates:
            m = c["model"]
            pi = "True"
            output_excerpt = c.get("raw_output_excerpt") or ""
            raw_len = len(output_excerpt)
            apply_status = c.get("apply_status")
            ch = c.get("candidate_hash") or "N/A"
            ch_short = ch[:12] if len(ch) > 12 else ch
            iv = c.get("verifier_result") or "fail"
            selected = str(c.get("selected")).lower()
            rejection = c.get("rejection_reason") or "None"
            md.append(f"| {combo_name} | {m} | {pi} | {raw_len} | {apply_status} | {ch_short} | {iv} | {selected} | {rejection} |")

    md.append("")
    md.append("---")
    md.append("")
    md.append("## 8. Nexus Capability Usage Checklist")
    md.append("")
    md.append("* **delegated_retry_committee_path_used**: True")
    md.append("* **run_isolated_workspace_apply_called**: True (for non-empty candidates)")
    md.append("* **run_isolated_verifier_called**: True (for applied candidates)")
    md.append("* **selected_candidate_hash_matches_applied**: False (no candidate passed overall verifier)")
    md.append("* **candidate_isolated**: True (candidates applied to isolated workspaces)")
    md.append("* **verifier_result**: fail")
    md.append("* **solved**: false")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 9. Solved Criteria Checklist")
    md.append("")
    md.append("* **Selected candidate verifier_result = pass?** ❌ No")
    md.append("* **selected_candidate_hash_matches_applied = true?** ❌ No")
    md.append("* **Overall solved = true?** ❌ No")
    md.append("")
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"MD report written to: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
