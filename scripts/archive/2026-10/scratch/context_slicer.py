import sys
from pathlib import Path
import json

# Ensure nexus is in path
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.engine.surgical_slicer import SurgicalSlicer

WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")

def main():
    tasks = [
        {
            "task_id": "C_13453",
            "instance_id": "astropy__astropy-13453",
            "file_path": WORKSPACE_ROOT / ".nexus/workspaces/astropy/astropy/io/ascii/html.py",
            "target_symbol": "HTML",
        },
        {
            "task_id": "C_11618",
            "instance_id": "sympy__sympy-11618",
            "file_path": WORKSPACE_ROOT / ".nexus/workspaces/sympy/sympy/geometry/point.py",
            "target_symbol": "Point",
        },
        {
            "task_id": "C_12481",
            "instance_id": "sympy__sympy-12481",
            "file_path": WORKSPACE_ROOT / ".nexus/workspaces/sympy/sympy/combinatorics/permutations.py",
            "target_symbol": "Permutation",
        }
    ]

    results = []

    for t in tasks:
        fp = t["file_path"]
        sym = t["target_symbol"]
        print(f"Slicing {sym} in {fp}...")
        
        # Read original lines
        orig_content = fp.read_text(encoding="utf-8")
        orig_lines = len(orig_content.splitlines())
        
        slicer = SurgicalSlicer(fp)
        res = slicer.slice_function(sym)
        
        sliced_lines = len(res.code_content.splitlines())
        
        results.append({
            "task_id": t["task_id"],
            "instance_id": t["instance_id"],
            "target_symbol": sym,
            "original_file": str(fp.relative_to(WORKSPACE_ROOT)),
            "original_lines": orig_lines,
            "sliced_lines": sliced_lines,
            "token_estimate": res.token_estimate,
            "dependencies": res.dependencies,
            "scores": res.scores,
        })
        
        # Write the sliced code for reference/inspection
        output_dir = WORKSPACE_ROOT / f"artifacts/runtime/c3_ast_slicing_metrics_v0/{t['task_id']}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "sliced_context.py").write_text(res.code_content, encoding="utf-8")

    # Save metrics JSON
    metrics_dir = WORKSPACE_ROOT / "artifacts/runtime/c3_ast_slicing_metrics_v0"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    with open(metrics_dir / "slicing_metrics.json", "w", encoding="utf-8") as f:
        json.dump({
            "status": "C3_AST_SLICING_READY",
            "track": "Capability-First Post-V6 Execution Track",
            "metrics": results
        }, f, indent=2, ensure_ascii=False)

    # Generate Markdown Report
    md_lines = [
        "# C3 — AST Slicing Metrics Report",
        "",
        "**Status**: C3_AST_SLICING_COMPLETED",
        "**Track**: Capability-First Post-V6 Execution Track",
        "",
        "---",
        "",
        "## 1. Slicing Metrics Summary",
        "",
        "本階段利用 `SurgicalSlicer` 對 3 個重現任務的 target files 進行了 AST 切片，並將龐大的原始檔案縮減為僅包含 target symbol 及其關鍵依賴的精簡 context。這大幅減少了 LLM 處理的 token 數量並提升了 context 精確度。",
        "",
        "| 任務 ID | 實例 ID | 目標 Symbol | 原始檔行數 | 切片檔行數 | Token 估計 | 縮減比例 | 依賴 symbols |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |"
    ]

    for r in results:
        ratio = (1 - r["sliced_lines"] / r["original_lines"]) * 100
        deps = ", ".join(r["dependencies"][:5])
        if len(r["dependencies"]) > 5:
            deps += f" (+{len(r['dependencies'])-5} more)"
        md_lines.append(
            f"| `{r['task_id']}` | `{r['instance_id']}` | `{r['target_symbol']}` | {r['original_lines']} | {r['sliced_lines']} | {r['token_estimate']} | {ratio:.1f}% | {deps} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Detailed Slicing Results",
        ""
    ])

    for r in results:
        md_lines.extend([
            f"### {r['task_id']} ({r['instance_id']})",
            f"*   **原始檔案**: [{r['original_file']}](file://{WORKSPACE_ROOT}/{r['original_file']}) ({r['original_lines']} 行)",
            f"*   **切片檔案**: [sliced_context.py](file://{WORKSPACE_ROOT}/artifacts/runtime/c3_ast_slicing_metrics_v0/{r['task_id']}/sliced_context.py) ({r['sliced_lines']} 行)",
            f"*   **Token 估計**: {r['token_estimate']}",
            f"*   **分析的依賴**: {len(r['dependencies'])} 個",
            "```python",
            "# Sliced Context Reference (First 15 lines):",
            ""
        ])
        
        sliced_path = WORKSPACE_ROOT / f"artifacts/runtime/c3_ast_slicing_metrics_v0/{r['task_id']}/sliced_context.py"
        sliced_code = sliced_path.read_text(encoding="utf-8").splitlines()
        for line in sliced_code[:15]:
            md_lines.append(line)
        if len(sliced_code) > 15:
            md_lines.append("# ... [truncated]")
        md_lines.extend([
            "```",
            ""
        ])

    md_path = WORKSPACE_ROOT / "docs/reports/c3_ast_slicing_metrics_v0.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print("Success! Reports and metrics generated.")

if __name__ == "__main__":
    main()
