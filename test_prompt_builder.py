import sys
from pathlib import Path
from nexus.services.local_heal.prompt_builder import PromptBuilder

repo_dir = Path(".nexus/workspaces/astropy")
plan = {
  "search_symbols": ["SkyCoord", "__getattr__"],
  "repair_strategy": "Override the `__getattr__` method to handle custom properties correctly.",
  "violated_invariants": []
}
surgical_files = [("astropy/coordinates/sky_coordinate.py", "MOCK CONTENT")]

try:
    print("Building system prompt...")
    sys_prompt = PromptBuilder.build_patch_system_prompt("qwen2.5-coder:7b", interleaved=True)
    print("Building user prompt...")
    user_prompt = PromptBuilder.build_patch_user_prompt(
        "MOCK PROBLEM", "MOCK EVIDENCE", plan, surgical_files,
        reasoning_mode="INTUITIVE", failure_reason="", attempt=1, project_root=repo_dir
    )
    print("Done. User prompt length:", len(user_prompt))
except Exception as e:
    print(f"Error: {e}")
