"""
SWE-bench Local Heal Runner (V2.14 - Robust Git Enabled)
=======================================================
整合 Localizer / EvaluationGate / SearchReplaceParser 流程。
支援 Pre-flight 環境自動修復與穩健的 Git 操作。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Tuple, Dict, Any

# 確保能 import nexus 模組
sys.path.append(os.getcwd())

from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from nexus.services.local_heal.task_manifest import local_heal_20_task_manifest
from nexus.services.local_heal.env_resolver import (
    EnvResolver,
    apply_env_resolution,
    requirement_for_profile,
)
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.preflight import build_preflight_rows
from nexus.services.local_heal.receipt import build_repair_receipt, write_repair_receipt

NEXUS_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "nexus-local-heal-v17"
OLLAMA_ENDPOINT = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434")
LMSTUDIO_ENDPOINT = os.environ.get("NEXUS_LMSTUDIO_ENDPOINT", "http://localhost:1234/v1")
OLLAMA_MODEL = os.environ.get("NEXUS_OLLAMA_MODEL", "qwen2.5-coder:14b")
DEFAULT_OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("NEXUS_OLLAMA_TIMEOUT_SECONDS", "180"))

def sh(cmd: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        print(f"  ❌ Command failed: {' '.join(cmd)}")
        if res.stdout: print(f"  STDOUT: {res.stdout}")
        if res.stderr: print(f"  STDERR: {res.stderr}")
        raise subprocess.CalledProcessError(res.returncode, cmd, res.stdout, res.stderr)
    return res


def nexus_local_generate(system_prompt: str, user_prompt: str, timeout: int | None = None, model: str | None = None) -> str:
    # 強制鎖定 Ollama 路線，拒絕 LM Studio 污染
    selected_model = model or os.environ.get("NEXUS_OLLAMA_MODEL") or OLLAMA_MODEL
    effective_timeout = timeout or DEFAULT_OLLAMA_TIMEOUT_SECONDS

    print(f"  → Invoking local model: {selected_model} via Ollama...")

    # Ollama Native Interface
    payload = json.dumps({
        "model": selected_model,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 16384,
            "num_predict": 4096,
        }
    }).encode()
    endpoint = f"{OLLAMA_ENDPOINT}/api/generate"

    try:
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as e:
        print(f"  ❌ Ollama Error ({selected_model}): {e}")
        raise


ollama_generate = nexus_local_generate


def build_local_task(
    local_file: Path,
    *,
    root_dir: Path,
    env_profile: str = "python-default",
    manifest_task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "instance_id": f"local_fix_{local_file.name}",
        "manifest_task_id": manifest_task_id,
        "repo_dir": root_dir,
        "local_path": local_file,
        "env_profile": env_profile,
        "problem_statement": (
            f"Fix the bug or race condition in scripts/benchmarks/{local_file.name}. "
            f"Run 'python3 scripts/benchmarks/{local_file.name}' to reproduce."
        ),
        "repro_script": (
            "import sys\n"
            "import os\n"
            "sys.path.append(os.getcwd())\n"
            "import threading\n"
            "import time\n"
            "import random\n"
            f"from scripts.benchmarks.{local_file.name.replace('.py', '')} import test_challenge\n"
            "try:\n"
            "    test_challenge()\n"
            "    print('SUCCESS')\n"
            "except AssertionError as e:\n"
            "    print(f'FAILURE: {e}')\n"
            "    exit(1)"
        ),
        "local_mode": True,
    }


def build_dataset_task(
    item: dict[str, Any],
    *,
    env_profile: str = "python-default",
    manifest_task_id: str | None = None,
    expected_stop_layer: str = "verification",
    probe_goal: str = "general-repair",
) -> dict[str, Any]:
    return {
        "instance_id": item["instance_id"],
        "manifest_task_id": manifest_task_id,
        "repo": item["repo"],
        "commit": item["base_commit"],
        "problem_statement": item["problem_statement"],
        "env_profile": env_profile,
        "expected_stop_layer": expected_stop_layer,
        "probe_goal": probe_goal,
        "local_mode": False,
    }


def build_tasks_from_manifest_specs(
    specs: Any,
    *,
    dataset: Any,
    root_dir: Path = NEXUS_ROOT,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for spec in specs:
        if spec.kind == "swebench":
            if spec.swe_index is None:
                raise ValueError(f"Manifest task {spec.task_id} is missing swe_index")
            if dataset is None:
                raise ValueError(f"Manifest task {spec.task_id} requires a SWE-bench dataset")
            tasks.append(
                build_dataset_task(
                    dataset[spec.swe_index],
                    env_profile=spec.env_profile,
                    manifest_task_id=spec.task_id,
                    expected_stop_layer=spec.expected_stop_layer,
                    probe_goal=spec.probe_goal,
                )
            )
            continue

        if spec.local_path is None:
            raise ValueError(f"Manifest task {spec.task_id} is missing local_path")
        tasks.append(
            build_local_task(
                root_dir / spec.local_path,
                root_dir=root_dir,
                env_profile=spec.env_profile,
                manifest_task_id=spec.task_id,
            )
        )
    return tasks


def build_tasks_from_manifest(
    manifest_name: str,
    dataset: Any,
    *,
    root_dir: Path = NEXUS_ROOT,
) -> list[dict[str, Any]]:
    if manifest_name != "local-heal-20":
        raise ValueError(f"Unknown task manifest: {manifest_name}")
    return build_tasks_from_manifest_specs(
        local_heal_20_task_manifest(),
        dataset=dataset,
        root_dir=root_dir,
    )


def localized_files_for_task(task: dict[str, Any]) -> list[tuple[str, str]]:
    if not task.get("local_mode"):
        return []

    local_path = Path(task["local_path"]).resolve()
    repo_dir = Path(task["repo_dir"]).resolve()
    try:
        relative_path = local_path.relative_to(repo_dir)
    except ValueError:
        relative_path = Path(local_path.name)
    return [(str(relative_path), local_path.read_text(encoding="utf-8", errors="replace"))]


def read_resume_task_ids(path: str | Path | None, *, mode: str) -> set[str]:
    if not path:
        return set()

    resume_path = Path(path)
    if not resume_path.exists():
        return set()

    completed: set[str] = set()
    for line in resume_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = row.get("manifest_task_id")
        if not task_id:
            continue
        if mode == "preflight" and row.get("preflight_ready") is True:
            completed.add(str(task_id))
        elif mode == "repair" and row.get("solve_eligible") is True:
            completed.add(str(task_id))
    return completed


def filter_specs_for_resume(specs: Any, completed_task_ids: set[str]) -> list[Any]:
    return [spec for spec in specs if spec.task_id not in completed_task_ids]


def filter_tasks_for_resume(tasks: list[dict[str, Any]], completed_task_ids: set[str]) -> list[dict[str, Any]]:
    return [task for task in tasks if task.get("manifest_task_id") not in completed_task_ids]


def failure_reason_for_result(res_ctx: Any) -> str:
    explicit = str(getattr(res_ctx, "failure_reason", "") or "").strip()
    if explicit:
        return explicit

    receipt_path = str(getattr(res_ctx, "receipt_path", "") or "")
    if receipt_path and Path(receipt_path).exists():
        try:
            receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
            reason = str(receipt.get("failure_reason") or "").strip()
            if reason:
                return reason
        except (OSError, json.JSONDecodeError):
            pass

    return str(build_repair_receipt(res_ctx).get("failure_reason") or "UNCLASSIFIED")


def build_result_row(task: dict[str, Any], res_ctx: Any) -> dict[str, Any]:
    return {
        "instance_id": task["instance_id"],
        "manifest_task_id": task.get("manifest_task_id"),
        "env_profile": task.get("env_profile", "python-default"),
        "model_patch": getattr(res_ctx, "final_patch", ""),
        "model_name_or_path": MODEL_NAME,
        "solve_eligible": bool(getattr(res_ctx, "solve_eligible", False)),
        "failure_reason": failure_reason_for_result(res_ctx),
        "receipt_path": getattr(res_ctx, "receipt_path", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--instance_id", type=str, help="Specific instance ID to run")
    parser.add_argument("--local_path", type=str, help="Local file path to fix (skips dataset)")
    parser.add_argument("--task_manifest", choices=["local-heal-20"], help="Run a fixed local-heal task manifest")
    parser.add_argument("--preflight_only", action="store_true", help="Write readiness rows without cloning or invoking models")
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument("--output", default=str(NEXUS_ROOT / "benchmarking/swebench_lite/predictions_swe.jsonl"))
    parser.add_argument("--resume_from", type=str, help="JSONL ledger whose completed manifest task IDs should be skipped")
    parser.add_argument("--hidden_verifier", action="store_true", help="Enable hidden verifier check")
    parser.add_argument("--repro_script_file", type=str, help="Manually provided repro script file")

    args = parser.parse_args()
    # 實例化 pipeline
    pipeline = HealPipeline(ollama_generate_fn=nexus_local_generate)
    pipeline.hidden_verifier_required = args.hidden_verifier

    tasks = []
    if args.preflight_only:
        if not args.task_manifest:
            sys.exit("Error: --preflight_only requires --task_manifest")
        manifest_specs = local_heal_20_task_manifest()
        selected_specs = manifest_specs[args.index:min(args.index + args.limit, len(manifest_specs))]
        selected_specs = filter_specs_for_resume(
            selected_specs,
            read_resume_task_ids(args.resume_from, mode="preflight"),
        )
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rows = build_preflight_rows(selected_specs, root_dir=NEXUS_ROOT)
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"\n✅ Preflight rows saved to: {out_path}")
        return

    if args.local_path:
        # 本地模式
        local_file = Path(args.local_path).resolve()
        if not local_file.exists():
            sys.exit(f"Error: Local file {local_file} not found")

        # 強制將 repo_dir 設為專案根目錄
        root_dir = Path("/Users/jameschen/Workspace/nexus").resolve()
        tasks.append(build_local_task(local_file, root_dir=root_dir))
    else:
        # 數據集模式
        if args.task_manifest:
            manifest_specs = local_heal_20_task_manifest()
            selected_specs = manifest_specs[args.index:min(args.index + args.limit, len(manifest_specs))]
            selected_specs = filter_specs_for_resume(
                selected_specs,
                read_resume_task_ids(args.resume_from, mode="repair"),
            )
            ds = None
            if any(spec.kind == "swebench" for spec in selected_specs):
                try:
                    from datasets import load_dataset
                except ImportError:
                    sys.exit("Error: pip install datasets")
                print(f"📦 Loading {args.dataset}...")
                ds = load_dataset(args.dataset, split="test")
            tasks = build_tasks_from_manifest_specs(selected_specs, dataset=ds, root_dir=NEXUS_ROOT)
        elif args.instance_id:
            try:
                from datasets import load_dataset
            except ImportError:
                sys.exit("Error: pip install datasets")
            print(f"📦 Loading {args.dataset}...")
            ds = load_dataset(args.dataset, split="test")
            subset = [item for item in ds if item["instance_id"] == args.instance_id]
            tasks = [build_dataset_task(item) for item in subset]
        else:
            try:
                from datasets import load_dataset
            except ImportError:
                sys.exit("Error: pip install datasets")
            print(f"📦 Loading {args.dataset}...")
            ds = load_dataset(args.dataset, split="test")
            subset = ds.select(range(args.index, min(args.index + args.limit, len(ds))))
            tasks = [build_dataset_task(item) for item in subset]
        tasks = filter_tasks_for_resume(tasks, read_resume_task_ids(args.resume_from, mode="repair"))

    results = []
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_root = Path("/tmp/nexus_swe_debug")
    # 不要每次都清理整個 tmp_root，避免競態
    # if tmp_root.exists():
    #    import shutil
    #    shutil.rmtree(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp = tmp_root

    with open(out_path, "w", encoding="utf-8") as out_file:
        for i, task in enumerate(tasks):
                iid = task["instance_id"]
                profile_name = task.get("env_profile", "python-default")
                print(f"\n{'='*60}")
                print(f"[{i+1}/{len(tasks)}] Processing {iid} (Profile: {profile_name})")

                # 1. 初始環境解析
                req = requirement_for_profile(profile_name)
                env_resolver = EnvResolver()
                env_resolution = env_resolver.resolve(req)

                # 2. 如果失敗且允許自動修復，則啟動修復
                if not env_resolution.ready and req.auto_heal_enabled and any(kw in env_resolution.reason for kw in ["MISSING", "VIOLATION"]):
                    print(f"  🔧 Environment blocked due to {env_resolution.reason}. Attempting auto-heal...")
                    denoiser = EnvDenoiser(repo_dir=NEXUS_ROOT)
                    heal_res = denoiser.heal_requirement(env_resolution, req)
                    if heal_res.healed:
                        print(f"  ✅ Auto-heal succeeded. Re-resolving environment...")
                        env_resolution = env_resolver.resolve(req)
                    else:
                        print(f"  ❌ Auto-heal failed: {heal_res.reason}")

                if not env_resolution.ready:
                    repo_dir = task.get("repo_dir") or tmp / iid.replace("/", "__").replace(".", "_")
                    ctx = HealContext(
                        instance_id=iid,
                        repo_dir=repo_dir,
                        problem_statement=task["problem_statement"],
                        max_tries=2,
                    )
                    ctx.auto_heal_enabled = req.auto_heal_enabled
                    ctx.expected_stop_layer = task.get("expected_stop_layer", "verification")
                    ctx.expected_reason_family = task.get("expected_reason_family", "SOLVED")
                    apply_env_resolution(ctx, env_resolution)
                    ctx.receipt_path = str(write_repair_receipt(ctx))
                    res_ctx = ctx
                    print(f"  ✗ ENV BLOCKED: {res_ctx.failure_reason}")
                elif task["local_mode"]:
                    repo_dir = task["repo_dir"]
                    print("  → Running HealPipeline Orchestrator...")
                    ctx = HealContext(
                        instance_id=iid,
                        repo_dir=repo_dir,
                        problem_statement=task["problem_statement"],
                        max_tries=2,
                    )
                    ctx.auto_heal_enabled = req.auto_heal_enabled
                    ctx.expected_stop_layer = task.get("expected_stop_layer", "verification")
                    ctx.expected_reason_family = task.get("expected_reason_family", "SOLVED")
                    ctx.repro_script = task["repro_script"]
                    ctx.localized_files = localized_files_for_task(task)
                    apply_env_resolution(ctx, env_resolution)
                    res_ctx = pipeline.run(ctx)
                else:
                    repo_dir = tmp / iid.replace("/", "__").replace(".", "_")
                    if repo_dir.exists():
                        import shutil
                        shutil.rmtree(repo_dir)

                    print("  → git clone (shallow, resilient)...")
                    success = False
                    for attempt in range(3):
                        try:
                            if repo_dir.exists():
                                import shutil
                                shutil.rmtree(repo_dir)
                            sh(["git", "clone", "--quiet", "--depth", "1", f"https://github.com/{task['repo']}.git", str(repo_dir)], cwd=tmp)
                            print(f"  ✓ Repository ready (Attempt {attempt+1}).")
                            success = True
                            break
                        except Exception as e:
                            print(f"  ⚠️ Git attempt {attempt+1} failed: {e}")
                            import time
                            time.sleep(5)

                    if not success:
                        print("  ❌ Git operation failed after all retries.")
                        continue

                    print("  → Running HealPipeline Orchestrator...")
                    ctx = HealContext(
                        instance_id=iid,
                        repo_dir=repo_dir,
                        problem_statement=task["problem_statement"],
                        max_tries=2,
                    )
                    ctx.auto_heal_enabled = req.auto_heal_enabled
                    ctx.expected_stop_layer = task.get("expected_stop_layer", "verification")
                    ctx.expected_reason_family = task.get("expected_reason_family", "SOLVED")
                    if args.repro_script_file:
                        ctx.repro_script = Path(args.repro_script_file).read_text(encoding="utf-8")
                    apply_env_resolution(ctx, env_resolution)
                    res_ctx = pipeline.run(ctx)

                if res_ctx.solve_eligible:
                    print("  ✅ SUCCESS: Solve eligible!")
                    if res_ctx.final_patch:
                        print("  --- Patch Preview ---")
                        print("\n".join(res_ctx.final_patch.splitlines()[:5]))
                else:
                    print("  ✗ FAILED: Target remains unsolved.")
                    if res_ctx.evaluation_report:
                        print(f"  --- Evaluation Report ---\n{res_ctx.evaluation_report}")

                row = build_result_row(task, res_ctx)
                results.append(row)
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()
    print(f"\n✅ Predictions saved to: {out_path}")

if __name__ == "__main__":
    main()
