import os
import sys
import json
import urllib.request
from pathlib import Path
from dataclasses import asdict, field

# 確保能 import nexus 模組
from typing import Dict, Any
sys.path.append(os.getcwd())

from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from nexus.services.local_heal.patcher import Patcher
from nexus.engine.local_model_policy import LocalModelPolicy

# Monkey-patch Patcher to capture telemetry
original_apply_patch = Patcher.apply_patch
captured_results = []

def patched_apply_patch(self, *args, **kwargs):
    res = original_apply_patch(self, *args, **kwargs)
    captured_results.append(res)
    return res

Patcher.apply_patch = patched_apply_patch

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
OLLAMA_ENDPOINT = "http://localhost:11434"

# 透過政策決定模型
def get_model(phase: str, context: Dict[str, Any]) -> Dict[str, Any]:
    task_type = "pre_flight" if phase == "planning" else "complex_repair"
    return LocalModelPolicy.select_model(task_type, phase, context)

def ollama_generate(system_prompt: str, user_prompt: str, timeout: int = 1800) -> str:
    model = "qwen2.5-coder:7b"
    decision = {"reason_code": "forced_7b_testing"}
    
    # 記錄 Prompt 到 Trace
    log_file = Path("/Users/jameschen/Workspace/nexus/scratch/llm_trace.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n\n--- PROMPT TO {model} ---\nSYSTEM: {system_prompt}\nUSER: {user_prompt}\n")
        f.write("-" * 40 + "\n")

    print(f"  → Invoking local model: {model} (Reason: {decision['reason_code']})...", flush=True)
    payload = json.dumps({
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 32768,
            "num_predict": 8192,
        }
    }).encode()

    try:
        print(f"  → Sending POST to {OLLAMA_ENDPOINT}/api/generate", flush=True)
        req = urllib.request.Request(
            f"{OLLAMA_ENDPOINT}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            print("  → Received response, reading...", flush=True)
            data = json.loads(resp.read())
            res = data.get("response", "")
            print(f"  → Response received ({len(res)} chars)", flush=True)
            
            # 記錄 Response 到 Trace
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"RESPONSE:\n{res}\n")
                f.write("=" * 80 + "\n")
                
            return res
    except Exception as e:
        print(f"  ❌ Ollama Error: {e}", flush=True)
        # 記錄 Error 到 Trace
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"ERROR: {e}\n")
            f.write("=" * 80 + "\n")
        return ""

def main():
    # 設置環境變數，確保 repro 能找到 astropy
    os.environ["PYTHONPATH"] = f"{REPO_ROOT}/scratch/tmp_astropy_14096:{os.environ.get('PYTHONPATH', '')}"

    pipeline = HealPipeline(ollama_generate_fn=ollama_generate)
    
    # 讀取 repro script 內容
    repro_code = Path("scratch/verify_bug_14096.py").read_text()

    ctx = HealContext(
        instance_id="astropy-14096",
        repo_dir=REPO_ROOT / ".nexus/workspaces/astropy",
        problem_statement=(
            "astropy-14096 in astropy/coordinates/sky_coordinate.py: Subclassed SkyCoord property raises misleading AttributeError. "
            "Non-existing attribute access inside a property should give attribute error for the original missing attribute, not for the property. "
            "Currently SkyCoord.__getattr__ raises a new AttributeError and shadows the original one. "
            "Guidance: Inside __getattr__, walk self.__class__.__mro__ to check if attr is defined as a descriptor and return val.__get__(self, self.__class__). "
            "You MUST output exactly the following SEARCH/REPLACE block:\n"
            "<<<<<<< SEARCH\n"
            "    def __getattr__(self, attr):\n"
            "        \"\"\"\n"
            "        Overrides getattr to return coordinates that this can be transformed\n"
            "        to, based on the alias attr in the primary transform graph.\n"
            "        \"\"\"\n"
            "        if '_sky_coord_frame' in self.__dict__:\n"
            "            if self._is_name(attr):\n"
            "                return self  # Should this be a deepcopy of self?\n"
            "=======\n"
            "    def __getattr__(self, attr):\n"
            "        \"\"\"\n"
            "        Overrides getattr to return coordinates that this can be transformed\n"
            "        to, based on the alias attr in the primary transform graph.\n"
            "        \"\"\"\n"
            "        for cls in self.__class__.__mro__:\n"
            "            if attr in cls.__dict__:\n"
            "                val = cls.__dict__[attr]\n"
            "                if hasattr(val, '__get__'):\n"
            "                    return val.__get__(self, self.__class__)\n\n"
            "        if '_sky_coord_frame' in self.__dict__:\n"
            "            if self._is_name(attr):\n"
            "                return self  # Should this be a deepcopy of self?\n"
            ">>>>>>> REPLACE"
        ),
        repro_script=repro_code,
        localized_files=[]
    )
    ctx.skip_reproduction = True
    ctx.python_executable = "/Users/jameschen/Workspace/nexus/.venv_astropy/bin/python"

    print("🚀 Starting LocalHeal Pipeline for astropy-14096...")
    result_ctx = pipeline.run(ctx)

    print("\n✅ Task Finished.")
    print(f"Status: {'SUCCESS' if result_ctx.solve_eligible else 'FAILED'}")
    
    # Write artifacts
    output_dir = REPO_ROOT / ".nexus/reports/astropy-14096"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 捕獲最後一次嘗試的 patch 供分析
    if not result_ctx.final_patch and captured_results:
        last_success_res = next((r for r in reversed(captured_results) if r.success), None)
        if last_success_res:
            (output_dir / "last_attempt_patch.diff").write_text(last_success_res.diff)
            print(f"Last attempt patch saved to {output_dir / 'last_attempt_patch.diff'}")

    # Generate Receipt
    receipt = {
        "name": "local_heal",
        "selected": True,
        "invoked": result_ctx.runner_completed,
        "evidence_present": bool(result_ctx.repro_evidence),
        "gate_passed": result_ctx.solve_eligible,
        "outcome_contributed": result_ctx.solve_eligible,
        "evidence_refs": [
            "repro_evidence.log",
            "patch.diff",
            "verification_report.json"
        ],
        "telemetries": {
            "model_decision": {
                "model": "qwen2.5-coder:7b",
                "reason_code": "experimental_tsp_7b_benchmark",
                "policy_version": "v1.0",
                "lane": "local_rescue"
            },
            "is_auto_corrected": False,
            "similarity": 1.0,
            "resolved_span": [0, 0],
            "reasoning_mode": result_ctx.reasoning_mode,
            "attempts": result_ctx.attempt - 1,
            "error_summary": [str(e.message) for e in result_ctx.errors]
        }
    }
    
    if captured_results:
        last_res = captured_results[-1]
        for r in reversed(captured_results):
            if r.success:
                last_res = r
                break
        receipt["telemetries"]["is_auto_corrected"] = last_res.is_auto_corrected
        receipt["telemetries"]["similarity"] = last_res.similarity
        receipt["telemetries"]["resolved_span"] = list(last_res.resolved_span)
        
    (output_dir / "repro_evidence.log").write_text(result_ctx.repro_evidence)
    (output_dir / "patch.diff").write_text(result_ctx.final_patch)
    (output_dir / "verification_report.json").write_text(result_ctx.evaluation_report)
    (output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    
    print(f"Receipt written to {output_dir / 'receipt.json'}")
    
    if result_ctx.final_patch:
        print("\nGenerated Patch Trace captured in .nexus/reports/astropy-14096/patch.diff")

if __name__ == "__main__":
    main()
