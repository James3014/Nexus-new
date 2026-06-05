import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Tuple

import datasets
from benchmarking.swebench_lite.swe_local_heal import nexus_local_generate
from nexus.services.local_heal.task_manifest import (
    local_heal_113_task_manifest,
    LocalHealTaskSpec,
)
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.env_denoiser import EnvDenoiser

NEXUS_ROOT = Path(__file__).resolve().parents[2]
EXPERT_REPRO_ROOT = NEXUS_ROOT / ".nexus" / "expert_repro"


def get_task_manifest_specs() -> Tuple[LocalHealTaskSpec, ...]:
    return local_heal_113_task_manifest()


def build_task_from_spec(spec: LocalHealTaskSpec, dataset: Any) -> dict:
    instance = next((row for row in dataset if row["instance_id"] == spec.instance_id), None)
    if not instance:
        raise ValueError(f"Task {spec.task_id} not found in dataset")
    return {
        "instance_id": instance["instance_id"],
        "manifest_task_id": spec.task_id,
        "repo_dir": NEXUS_ROOT,  # SWE-bench local target uses root
        "problem_statement": instance["problem_statement"],
        "env_profile": spec.env_profile,
    }


def call_generator_for_repro(problem: str, previous_error: str = "") -> str:
    system_prompt = "You write minimal Python bug reproduction scripts."
    
    user_prompt = (
        "Write a single Python script that reproduces the issue below.\n"
        "Output only Python code, no markdown fences, no explanation.\n"
        "CRITICAL: The script must use explicit 'assert' statements, raise exceptions, "
        "or perform check-failed verifications so that it guarantees exiting with a "
        "non-zero status when the bug is present.\n\n"
        f"Issue:\n{problem}"
    )
    
    if previous_error:
        user_prompt += (
            "\n\n⚠️ [HUD WARNING: PREVIOUS ATTEMPT FAILED TO REPRODUCE]\n"
            f"Your previous script exited with status 0 (no crash/no failure), but the bug was not caught.\n"
            f"Console Output/Error:\n{previous_error}\n\n"
            "Please fix the script. You MUST use 'assert' to explicitly verify the wrong behavior "
            "so it triggers a non-zero exit status when the bug is present."
        )

    # Use Qwen 7b for reproduction script generation
    response = nexus_local_generate(
        system_prompt,
        user_prompt,
        model="qwen2.5-coder:7b",
        timeout=180,
    )
    
    # Strip markdown code blocks
    script = response.strip()
    fenced = re.search(r"```(?:python|py)?\s*\n(.*?)\n\s*```", script, re.DOTALL | re.IGNORECASE)
    if fenced:
        script = fenced.group(1)
    script = re.sub(r"^\s*```(?:python|py)?\s*\n?", "", script, flags=re.IGNORECASE)
    script = re.sub(r"\n?\s*```\s*$", "", script)
    return script.strip()


def run_and_verify_repro(task_dir: Path, script_code: str, python_exe: str = "python3") -> Tuple[bool, str]:
    repro_path = task_dir / "reproduce_bug.py"
    try:
        # Inject paths
        benchmarks_dir = str(task_dir / "scripts/benchmarks")
        path_injection = (
            "import sys, os\n"
            f"sys.path.insert(0, {str(task_dir)!r})\n"
            f"sys.path.insert(1, {benchmarks_dir!r})\n"
        )
        repro_path.write_text(path_injection + script_code, encoding="utf-8")

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.pop("VIRTUAL_ENV", None)

        res = subprocess.run(
            [python_exe, "-I", "reproduce_bug.py"],
            cwd=str(task_dir),
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )

        output = res.stdout + res.stderr
        # If exit status is non-zero, it successfully reproduced! (excluding env failures)
        if res.returncode != 0:
            if ReproductionRunner.is_environment_failure(output):
                return False, f"[ENV_FAILURE] {output}"
            return True, output
        return False, f"[EXIT_ZERO] {output}"
    except Exception as e:
        return False, str(e)
    finally:
        if repro_path.exists():
            try:
                os.remove(repro_path)
            except:
                pass


def main():
    print("📦 Loading princeton-nlp/SWE-bench_Verified...")
    dataset = datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    specs = get_task_manifest_specs()
    tasks = [build_task_from_spec(spec, dataset) for spec in specs]
    
    print(f"🚀 Starting Expert Repro Preparation Loop for {len(tasks)} tasks...")
    EXPERT_REPRO_ROOT.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    skipped_count = 0
    failed_count = 0
    
    for i, task in enumerate(tasks):
        instance_id = task["instance_id"]
        expert_dir = EXPERT_REPRO_ROOT / instance_id
        expert_file = expert_dir / "reproduce_bug.py"
        
        # Check if already prepared
        if expert_file.exists():
            print(f"[{i+1}/{len(tasks)}] ⏭️  Skipping {instance_id} (Already prepared)")
            skipped_count += 1
            continue
            
        print(f"\n{'-'*60}")
        print(f"[{i+1}/{len(tasks)}] Preparing environment and repro for {instance_id}...")
        
        # Setup env denoiser python path
        repo_dir = Path(task["repo_dir"])
        env_denoiser = EnvDenoiser(repo_dir)
        python_exe = "python3"
        # Dummy dry-run to trigger environment resolution
        try:
            denoise_res = env_denoiser.prepare_from_evidence("modulenotfounderror: no module named 'numpy'")
            if denoise_res.succeeded and getattr(denoise_res, "python_executable", ""):
                python_exe = denoise_res.python_executable
        except Exception:
            pass

        # Try to generate and verify with retry loop (max 3 tries)
        previous_err = ""
        repro_success = False
        final_script = ""
        
        for attempt in range(1, 4):
            print(f"  📝 Generating repro script (Attempt {attempt}/3)...")
            script = call_generator_for_repro(task["problem_statement"], previous_err)
            if not script:
                previous_err = "Model returned empty response."
                continue
                
            print("  🧪 Verifying repro script (checking if it exits with non-zero)...")
            ok, output = run_and_verify_repro(repo_dir, script, python_exe)
            if ok:
                repro_success = True
                final_script = script
                print("  ✅ SUCCESS: Bug successfully reproduced (Non-zero exit status achieved)!")
                break
            else:
                previous_err = output
                print(f"  ❌ FAILED: {output[:200]}...")
                
        if repro_success and final_script:
            expert_dir.mkdir(parents=True, exist_ok=True)
            expert_file.write_text(final_script, encoding="utf-8")
            print(f"  💾 Saved expert repro to: {expert_file.relative_to(NEXUS_ROOT)}")
            success_count += 1
        else:
            print(f"  ⚠️ GAVE UP: Could not auto-generate a valid repro script for {instance_id}")
            failed_count += 1
            
    print(f"\n{'='*60}")
    print("🏁 Expert Repro Preparation Complete!")
    print(f"  👉 Successfully Prepared: {success_count}")
    print(f"  👉 Skipped (Already Exist): {skipped_count}")
    print(f"  👉 Failed to Auto-Prepare: {failed_count}")


if __name__ == "__main__":
    main()
