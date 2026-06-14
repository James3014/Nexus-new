import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.engine.canonical_task_seam import execute_single_task_via_service

# Set environment variables for Ollama (7B/14B & 3B Advisor)
os.environ["NEXUS_OAUTH_PROVIDER"] = "auto"
os.environ["NEXUS_S2T_3B_ADVISOR_ENABLED"] = "1"
os.environ["NEXUS_S2T_3B_USE_OLLAMA"] = "1"
os.environ["NEXUS_S2T_3B_ASSISTED_MODE"] = "low_risk"
os.environ["NEXUS_S2T_3B_ALLOWED_RISK"] = "low"
os.environ["NEXUS_S2T_3B_ADVISOR_FORCE"] = "1"
os.environ["NEXUS_USE_SURGICAL_REPAIR"] = "1"

# Reset easy-001 target file
project_root = Path("/Users/jameschen/Workspace/nexus/.nexus/bench_cases/easy-001")
target_file = project_root / "target.py"
buggy_content = """def normalize_flag(text: str) -> str:
    # intentionally buggy for benchmark
    return text
"""
target_file.write_text(buggy_content, encoding="utf-8")

# Clean cache to force re-execution
research_file = project_root / "researchpack.json"
if research_file.exists():
    research_file.unlink()

print("==============================================")
print("🚀 Running easy-001 in Pure Ollama Mode...")
print("==============================================")

t0 = time.monotonic()
success = execute_single_task_via_service(
    task_text="Fix off-by-one or casing in normalize_flag to output lowercase stripped value.",
    project_root=project_root
)
duration = time.monotonic() - t0

print("\n==============================================")
print("📊 Task Finished!")
print("==============================================")
print(f"Success Status: {success}")
print(f"Execution Duration: {duration:.2f}s")
