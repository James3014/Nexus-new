"""
SWE-bench Local Harness (Ollama-Direct)
========================================
流程：
  1. 從 HuggingFace 讀取 SWE-bench_Verified 第 N 題
  2. git clone target repo @ base_commit
  3. 讀取相關檔案 (top-level relevant files via heuristic)
  4. 直接呼叫 Ollama 生成 unified diff patch
  5. git apply & git diff 驗證
  6. 寫入 predictions.jsonl

Usage:
  uv run --with datasets benchmarking/swebench_lite/swe_harness.py --limit 1
  uv run --with datasets benchmarking/swebench_lite/swe_harness.py --limit 1 --index 5
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

NEXUS_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "nexus-v16-ollama"
OLLAMA_ENDPOINT = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")


# ── utilities ─────────────────────────────────────────────────────────────────

def sh(cmd: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def ollama_generate(system_prompt: str, user_prompt: str, timeout: int = 180) -> str:
    """Call Ollama /api/generate and return the response text."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.05,
            "num_ctx": 8192,
            "num_predict": 2048,
        }
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    import socket
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except socket.timeout as e:
        raise RuntimeError(f"Ollama request timed out after {timeout}s") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e


def collect_relevant_files(repo_dir: Path, problem: str, max_files: int = 5) -> list[tuple[str, str]]:
    """
    Heuristic: 找出跟 problem statement 最相關的 Python 檔案。
    1. 從 problem text 抓 module/file 名稱關鍵字
    2. 找到匹配的 .py 文件
    3. 讀取內容（截斷至 2000 chars）
    """
    import re

    # Extract potential module names from problem
    tokens = set(re.findall(r'\b([a-z][a-z_0-9]{2,})\b', problem.lower()))
    # Score files
    scored = []
    for pyfile in repo_dir.rglob("*.py"):
        rel = pyfile.relative_to(repo_dir)
        rel_str = str(rel).lower()
        if any(p in rel_str for p in ("test", "__pycache__", ".tox", "build", "dist")):
            continue
        score = sum(1 for tok in tokens if tok in rel_str)
        if score > 0:
            scored.append((score, pyfile, rel))

    scored.sort(key=lambda x: -x[0])
    result = []
    for _, pyfile, rel in scored[:max_files]:
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            # Truncate to 2000 chars to keep prompt within 8192 context
            if len(content) > 2000:
                content = content[:2000] + "\n... [truncated]"
            result.append((str(rel), content))
        except Exception:
            pass
    return result


def clean_patch(patch: str) -> str:
    """
    Clean up LLM-generated patches:
    - Remove fake 'index XXXXXXX..YYYYYYY' lines
    - Remove 'diff --git' lines (convert to standard unified diff)
    - Strip trailing whitespace issues
    """
    import re
    lines = patch.splitlines()
    cleaned = []
    for line in lines:
        # Skip fake index lines (e.g., 'index 1234567..89abcde 100644')
        if re.match(r'^index [0-9a-f.]{6,}', line):
            continue
        # Skip 'diff --git a/...' header lines
        if line.startswith('diff --git '):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def extract_patch(llm_output: str) -> str:
    """Extract unified diff from LLM output."""
    import re
    # Look for ```diff or ``` blocks first
    patterns = [
        r"```diff\n(.*?)```",
        r"```patch\n(.*?)```",
        r"```\n((?:diff --git|--- a/).*?)```",
    ]
    for pattern in patterns:
        m = re.search(pattern, llm_output, re.DOTALL)
        if m:
            return clean_patch(m.group(1).strip())
    # Raw diff in output
    for marker in ("--- a/", "diff --git "):
        idx = llm_output.find(marker)
        if idx != -1:
            return clean_patch(llm_output[idx:].strip())
    return ""


def parse_search_replace(llm_output: str, files: list[tuple[str, str]], repo_dir: Path) -> str:
    """
    Parse SEARCH/REPLACE blocks from LLM output and generate a proper unified diff.
    Reads the FULL file from repo_dir (not truncated) for accurate replacement.
    """
    import re
    import difflib

    # Build filename → short path map for lookup
    fname_set = {fname for fname, _ in files}

    # Find all SEARCH/REPLACE blocks
    pattern = re.compile(
        r'FILE:\s*([^\n]+)\s*\n'
        r'SEARCH:\s*\n(.*?)\nREPLACE:\s*\n(.*?)\nEND',
        re.DOTALL
    )
    matches = list(pattern.finditer(llm_output))
    if not matches:
        return ""

    all_diffs = []
    for m in matches:
        raw_fname = m.group(1).strip().lstrip('a/').lstrip('b/')
        search_text = m.group(2)
        replace_text = m.group(3)

        # Resolve to actual file path in repo
        candidate = repo_dir / raw_fname
        if not candidate.exists():
            # Try to find by suffix match
            found = None
            for pyfile in repo_dir.rglob("*.py"):
                if str(pyfile).endswith(raw_fname):
                    found = pyfile
                    break
            if found is None:
                print(f"  ⚠ FILE not found in repo: {raw_fname}")
                continue
            candidate = found

        rel_path = str(candidate.relative_to(repo_dir))
        orig_content = candidate.read_text(encoding="utf-8", errors="replace")

        # Apply the replacement
        new_content = orig_content.replace(search_text, replace_text, 1)
        if new_content == orig_content:
            print(f"  ⚠ SEARCH text not found in {rel_path} (whitespace mismatch?)")
            # Try normalizing whitespace
            import textwrap
            dedented = textwrap.dedent(search_text).strip()
            for line in orig_content.split('\n'):
                pass
            continue

        # Generate unified diff using difflib (always correct line counts)
        orig_lines = orig_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm='\n',
        ))
        if diff_lines:
            all_diffs.append(''.join(diff_lines))
            print(f"  ✓ SEARCH/REPLACE matched in {rel_path}")

    return '\n'.join(all_diffs).strip()


def generate_patch(problem: str, repo_dir: Path) -> str:
    """Use Ollama to generate a patch via SEARCH/REPLACE blocks (fallback: raw diff)."""
    files = collect_relevant_files(repo_dir, problem)

    if not files:
        print("  ⚠ No relevant files found, using top-level scan...")
        for pyfile in list(repo_dir.rglob("*.py"))[:5]:
            rel = str(pyfile.relative_to(repo_dir))
            content = pyfile.read_text(encoding="utf-8", errors="replace")[:2000]
            files.append((rel, content))

    file_ctx = "\n\n".join(
        f"=== FILE: {fname} ===\n{content}" for fname, content in files
    )

    system_prompt = (
        "You are an expert Python bug fixer. "
        "Given a bug report and source files, output SEARCH/REPLACE blocks to fix the bug. "
        "Each block must follow this EXACT format:\n"
        "FILE: path/to/file.py\n"
        "SEARCH:\n"
        "exact original lines (copy verbatim)\n"
        "REPLACE:\n"
        "fixed lines\n"
        "END\n"
        "Output ONLY these blocks, no explanation."
    )

    user_prompt = f"""Bug Report:
{problem[:1200]}

Source Files:
{file_ctx}

Output SEARCH/REPLACE blocks to fix the bug.
Example:
FILE: astropy/modeling/separable.py
SEARCH:
    if isinstance(transform, CompoundModel):
        left = _separable(transform.left)
REPLACE:
    if isinstance(transform, CompoundModel):
        left = _separable(transform.left)  # fixed
END"""

    total_prompt_chars = len(system_prompt) + len(user_prompt)
    print(f"  → Calling Ollama ({OLLAMA_MODEL}), prompt={total_prompt_chars} chars...")
    response = ollama_generate(system_prompt, user_prompt, timeout=600)
    print(f"  ← Response: {len(response)} chars")

    # Strategy 1: Parse SEARCH/REPLACE
    patch = parse_search_replace(response, files)
    if patch:
        print(f"  ✓ patch via SEARCH/REPLACE ({len(patch)} chars)")
        return patch

    # Strategy 2: Fallback - extract raw diff
    print("  ~ falling back to raw diff extraction")
    raw = extract_patch(response)
    return raw


def apply_and_verify_patch(patch: str, repo_dir: Path) -> tuple[bool, str]:
    """Try to apply patch; return (success, final_diff)."""
    if not patch:
        return False, ""

    # Write patch to temp file
    patch_file = repo_dir / "_nexus_candidate.patch"
    patch_file.write_text(patch, encoding="utf-8")

    # Try apply --check
    r_check = sh(["git", "apply", "--check", str(patch_file)], cwd=repo_dir)
    if r_check.returncode != 0:
        print(f"  ✗ patch check failed: {r_check.stderr[:200]}")
        # Try --3way as fallback
        r3 = sh(["git", "apply", "--3way", str(patch_file)], cwd=repo_dir)
        if r3.returncode != 0:
            print(f"  ✗ --3way also failed: {r3.stderr[:150]}")
            patch_file.unlink(missing_ok=True)
            return False, ""
        print("  ~ applied via --3way")
    else:
        sh(["git", "apply", str(patch_file)], cwd=repo_dir)

    patch_file.unlink(missing_ok=True)

    # Get final diff
    diff_r = sh(["git", "diff"], cwd=repo_dir)
    final = diff_r.stdout.strip()
    if not final:
        # Nothing changed — patch was no-op
        print("  ⚠ patch applied but no diff (no-op)")
        return False, ""
    return True, final


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--index", type=int, default=0, help="Start index in dataset")
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument("--output", default=str(
        NEXUS_ROOT / "benchmarking/swebench_lite/predictions_swe.jsonl"))
    parser.add_argument("--skip-clone", action="store_true",
                        help="Skip cloning (use existing /tmp/swe_* dirs)")
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Error: pip install datasets")

    print(f"📦 Loading {args.dataset}...")
    ds = load_dataset(args.dataset, split="test")
    subset = ds.select(range(args.index, min(args.index + args.limit, len(ds))))
    print(f"   {len(subset)} instance(s) to process (start={args.index})")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with tempfile.TemporaryDirectory(prefix="swe_nexus_") as tmp_root:
        tmp = Path(tmp_root)

        for i, item in enumerate(subset):
            iid = item["instance_id"]
            repo = item["repo"]
            commit = item["base_commit"]
            problem = item["problem_statement"]

            print(f"\n{'='*60}")
            print(f"[{i+1}/{args.limit}] {iid}")
            print(f"  repo={repo}  commit={commit[:10]}")

            repo_dir = tmp / iid.replace("/", "__").replace(".", "_")

            # 1. Clone
            if not args.skip_clone:
                print("  → cloning...")
                r1 = sh(["git", "clone", "--quiet", f"https://github.com/{repo}.git",
                         str(repo_dir)], cwd=tmp, timeout=120)
                if r1.returncode != 0:
                    print(f"  ✗ clone failed: {r1.stderr[:300]}")
                    results.append({"instance_id": iid, "model_patch": "",
                                    "model_name_or_path": MODEL_NAME, "error": "clone_failed"})
                    continue

                r2 = sh(["git", "checkout", commit], cwd=repo_dir, timeout=30)
                if r2.returncode != 0:
                    print(f"  ✗ checkout failed: {r2.stderr[:200]}")
                    results.append({"instance_id": iid, "model_patch": "",
                                    "model_name_or_path": MODEL_NAME, "error": "checkout_failed"})
                    continue
                print(f"  ✓ cloned @ {commit[:10]}")

            # 2. Generate patch via Ollama
            try:
                raw_patch = generate_patch(problem, repo_dir)
            except Exception as e:
                print(f"  ✗ LLM error: {e}")
                results.append({"instance_id": iid, "model_patch": "",
                                "model_name_or_path": MODEL_NAME, "error": str(e)})
                continue

            print(f"  raw patch ({len(raw_patch)} chars):")
            if raw_patch:
                print("  " + "\n  ".join(raw_patch[:400].split("\n")))

            # 3. Apply & verify
            ok, final_diff = apply_and_verify_patch(raw_patch, repo_dir)
            if ok:
                print(f"  ✓ patch applied — final diff: {len(final_diff)} chars")
                model_patch = final_diff
            else:
                # Use raw patch even if apply check failed (for submission)
                model_patch = raw_patch
                print(f"  ⚠ using raw patch (apply failed)")

            results.append({
                "instance_id": iid,
                "model_patch": model_patch,
                "model_name_or_path": MODEL_NAME,
            })

    # Write JSONL
    with open(out_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    patched = sum(1 for r in results if r.get("model_patch"))
    print(f"\n{'='*60}")
    print(f"✅ Done: {patched}/{len(results)} patched → {out_path}")


if __name__ == "__main__":
    main()
