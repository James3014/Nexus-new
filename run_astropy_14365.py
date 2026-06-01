import os
import sys
from pathlib import Path
from typing import Any

# 確保能 import nexus 模組
sys.path.append(os.getcwd())

from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from benchmarking.swebench_lite.swe_local_heal import ollama_generate

def main():
    # 注意：需要確保 scratch/ 下有對應的 repo，或是使用正式路徑
    # 這裡假設 repo 已存在或我們指向 astropy 主 repo
    repo_dir = Path("/Users/jameschen/Workspace/nexus/scratch/tmp_astropy_14182").resolve()
    instance_id = "astropy__astropy-14365"
    
    problem_statement = """
ascii.qdp Table format assumes QDP commands are upper case
### Description
ascii.qdp assumes that commands in a QDP file are upper case, for example, for errors they must be "READ SERR 1 2" whereas QDP itself is not case sensitive and case use "read serr 1 2". 

As many QDP files are created by hand, the expectation that all commands be all-caps should be removed.

### How to Reproduce
Create a QDP file with lowercase commands and try to read it with Table.read(..., format='ascii.qdp').
    """.strip()

    repro_script = """
from astropy.table import Table
import tempfile
import os

def test_repro():
    qdp_content = "read serr 1 2 \\n1 0.5 1 0.5"
    with tempfile.NamedTemporaryFile(suffix=".qdp", mode="w", delete=False) as f:
        f.write(qdp_content)
        temp_name = f.name
    
    try:
        print(f"Reading QDP file with lowercase commands: {temp_name}")
        t = Table.read(temp_name, format='ascii.qdp')
        print("SUCCESS: Read successfully.")
    except Exception as e:
        print(f"FAILURE: {e}")
        raise AssertionError(f"Failed to read lowercase QDP: {e}")
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)

if __name__ == "__main__":
    test_repro()
    """.strip()

    ctx = HealContext(
        instance_id=instance_id,
        repo_dir=repo_dir,
        problem_statement=problem_statement,
        repro_script=repro_script,
        max_tries=3
    )

    # 預定位關鍵檔案
    target_file = "astropy/io/ascii/qdp.py"
    target_path = repo_dir / target_file
    if target_path.exists():
        ctx.localized_files = [(target_file, target_path.read_text(errors="replace"))]

    pipeline = HealPipeline(ollama_generate_fn=ollama_generate)

    print(f"🚀 Starting LocalHeal for {instance_id}...")
    final_ctx = pipeline.run(ctx)

    print("\n" + "="*40)
    print(f"🏁 Task Completed. Solve Eligible: {final_ctx.solve_eligible}")
    print(f"Reasoning Mode: {final_ctx.reasoning_mode}")
    
    # 產出治理產物
    print(f"Final Patch:\n{final_ctx.final_patch}")

if __name__ == "__main__":
    main()
