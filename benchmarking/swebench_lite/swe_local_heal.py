import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import datasets
from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from nexus.services.local_heal.task_manifest import (
    LocalHealTaskSpec,
    local_heal_20_task_manifest,
    local_heal_40_task_manifest,
    local_heal_113_task_manifest,
)

NEXUS_ROOT = Path(__file__).parent.parent.parent.resolve()
LOCAL_HEAL_ROOT = Path(os.environ.get("NEXUS_LOCAL_HEAL_ROOT_DIR", str(NEXUS_ROOT))).resolve()
OLLAMA_MODEL = "qwen2.5-coder:14b"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 420
DEFAULT_OLLAMA_NUM_CTX = 4096
DEFAULT_OLLAMA_NUM_PREDICT = 768


from nexus.services.local_heal.client import OllamaClient
from nexus.services.local_heal.telemetry import TelemetryCollector

telemetry_store = TelemetryCollector()


def nexus_local_generate(
    system_prompt: str,
    user_prompt: str,
    timeout: int | None = None,
    model: str | None = None,
    options: dict[str, Any] | None = None,
    api_type: str = "generate",
) -> str:
    selected_model = model or os.environ.get("NEXUS_OLLAMA_MODEL") or OLLAMA_MODEL
    effective_timeout = timeout or DEFAULT_OLLAMA_TIMEOUT_SECONDS
    endpoint = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")

    resolved_options = options
    if resolved_options is None:
        resolved_options = {
            "temperature": 0.0,
            "num_ctx": int(os.environ.get("NEXUS_OLLAMA_NUM_CTX", DEFAULT_OLLAMA_NUM_CTX)),
            "num_predict": int(os.environ.get("NEXUS_OLLAMA_NUM_PREDICT", DEFAULT_OLLAMA_NUM_PREDICT)),
        }

    client = OllamaClient(
        model=selected_model,
        endpoint=endpoint,
        log_path="/Users/jameschen/Workspace/nexus/ollama_calls.log",
        telemetry_collector=telemetry_store
    )

    if api_type == "chat":
        return client.chat(system_prompt, user_prompt, effective_timeout, resolved_options)
    return client.generate(system_prompt, user_prompt, effective_timeout, resolved_options)


ollama_generate = nexus_local_generate


def build_result_row(task: dict[str, Any], res_ctx: HealContext) -> dict[str, Any]:
    receipt_path_str = str(getattr(res_ctx, "receipt_path", "") or "")
    receipt_path = Path(receipt_path_str)

    receipt_data = {}
    if receipt_path.exists():
        try:
            receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    solve_eligible = receipt_data.get("solve_eligible", getattr(res_ctx, "solve_eligible", False))
    failure_reason = receipt_data.get("failure_reason", "")
    model_decisions = receipt_data.get("model_decisions", getattr(res_ctx, "model_decisions", []))
    token_telemetry_status = receipt_data.get("token_telemetry_status", getattr(res_ctx, "token_telemetry_status", "unknown"))
    token_total_estimated = receipt_data.get("token_total_estimated", getattr(res_ctx, "token_total_estimated", 0))

    if not failure_reason:
        # Fallback to older failure inference only if receipt is missing or empty
        failure_reason = failure_reason_for_result(res_ctx)

    return {
        "instance_id": task["instance_id"],
        "manifest_task_id": task.get("manifest_task_id", ""),
        "env_profile": task.get("env_profile", "python-default"),
        "model_patch": getattr(res_ctx, "final_patch", ""),
        "model_name_or_path": "nexus-local-heal-v17",
        "solve_eligible": solve_eligible,
        "failure_reason": failure_reason,
        "receipt_path": receipt_path_str,
        "wall_time_sec_measured": getattr(res_ctx, "wall_time_sec", 0.0),
        "token_telemetry_status": token_telemetry_status,
        "token_total_estimated": token_total_estimated,
        "model_decisions": model_decisions,
    }


def build_task_from_spec(
    spec: LocalHealTaskSpec,
    dataset: Any,
    *,
    root_dir: Path,
) -> dict[str, Any]:
    from nexus.services.local_heal.env_resolver import EnvResolver, requirement_for_profile
    resolver = EnvResolver()
    env_profile = spec.env_profile
    if env_profile == "python-default" and spec.instance_id:
        if "astropy" in spec.instance_id:
            env_profile = "astropy-legacy"
        elif "django" in spec.instance_id:
            env_profile = "django-legacy"
    resolution = resolver.resolve(requirement_for_profile(env_profile))
    python_exe = os.path.abspath(resolution.python_executable) if resolution.ready else ""

    if spec.kind == "swebench":
        instance = None
        if spec.swe_index is not None and spec.swe_index < len(dataset):
            instance = dataset[spec.swe_index]
        elif spec.instance_id:
            instance = next((row for row in dataset if row["instance_id"] == spec.instance_id), None)

        if not instance:
            raise ValueError(f"Task {spec.task_id} not found in dataset")

        return {
            "instance_id": instance["instance_id"],
            "manifest_task_id": spec.task_id,
            "kind": spec.kind,
            "family": spec.family,
            "repo_dir": root_dir,
            "problem_statement": instance["problem_statement"],
            "env_profile": env_profile,
            "swe_index": spec.swe_index,
            "domain_id": spec.domain_id,
            "lane": spec.lane,
            "expected_stop_layer": spec.expected_stop_layer,
            "expected_reason_family": spec.expected_reason_family,
            "probe_goal": spec.probe_goal,
            "local_mode": False,
            "python_executable": python_exe,
        }

    local_file = root_dir / spec.local_path
    return {
        "instance_id": f"local_fix_{local_file.name}",
        "manifest_task_id": spec.task_id,
        "kind": spec.kind,
        "family": spec.family,
        "repo_dir": root_dir,
        "local_path": local_file,
        "env_profile": env_profile,
        "swe_index": spec.swe_index,
        "domain_id": spec.domain_id,
        "lane": spec.lane,
        "problem_statement": f"Fix race condition in {local_file.name}",
        "expected_stop_layer": spec.expected_stop_layer,
        "expected_reason_family": spec.expected_reason_family,
        "probe_goal": spec.probe_goal,
        "local_mode": True,
        "python_executable": python_exe,
    }


def build_tasks_from_manifest_specs(
    specs: tuple[LocalHealTaskSpec, ...],
    dataset: Any,
    *,
    root_dir: Path,
) -> list[dict[str, Any]]:
    tasks = []
    for spec in specs:
        tasks.append(
            build_task_from_spec(
                spec,
                dataset,
                root_dir=root_dir,
            )
        )
    return tasks


def build_tasks_from_manifest(
    manifest_name: str,
    dataset: Any,
    *,
    root_dir: Path = LOCAL_HEAL_ROOT,
) -> list[dict[str, Any]]:
    from nexus.services.local_heal.task_manifest import (
        local_heal_20_task_manifest,
        local_heal_40_task_manifest,
        local_heal_60_task_manifest,
        local_heal_100_task_manifest,
        local_heal_113_task_manifest,
        local_heal_batch1_task_manifest,
    )
    if manifest_name == "local-heal-20":
        specs = local_heal_20_task_manifest()
    elif manifest_name == "local-heal-40":
        specs = local_heal_40_task_manifest()
    elif manifest_name == "local-heal-60":
        specs = local_heal_60_task_manifest()
    elif manifest_name == "local-heal-100":
        specs = local_heal_100_task_manifest()
    elif manifest_name == "local-heal-113":
        specs = local_heal_113_task_manifest()
    elif manifest_name == "local-heal-batch1":
        specs = local_heal_batch1_task_manifest()
    else:
        raise ValueError(f"Unknown task manifest: {manifest_name}")

    return build_tasks_from_manifest_specs(
        specs,
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
    return [
        (
            str(relative_path),
            local_path.read_text(encoding="utf-8", errors="replace"),
        )
    ]


def read_resume_task_ids(path: str | Path | None, *, mode: str) -> set[str]:
    if not path:
        return set()

    resume_path = Path(path)
    if not resume_path.exists():
        return set()

    completed = set()
    with open(resume_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            tid = row.get("manifest_task_id")
            if not tid:
                continue

            if mode == "repair" and row.get("solve_eligible"):
                completed.add(tid)
            elif mode == "preflight" and row.get("preflight_ready"):
                completed.add(tid)
    return completed


def filter_tasks_for_resume(
    tasks: list[dict[str, Any]], completed_task_ids: set[str]
) -> list[dict[str, Any]]:
    return [
        task for task in tasks if task.get("manifest_task_id") not in completed_task_ids
    ]


def filter_specs_for_resume(
    specs: tuple[LocalHealTaskSpec, ...], completed_task_ids: set[str]
) -> tuple[LocalHealTaskSpec, ...]:
    return tuple(spec for spec in specs if spec.task_id not in completed_task_ids)


def failure_reason_for_result(res_ctx: Any) -> str:
    explicit = str(getattr(res_ctx, "failure_reason", "") or "").strip()
    if explicit:
        return explicit

    receipt_path = Path(str(getattr(res_ctx, "receipt_path", "") or ""))
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt_reason = str(receipt.get("failure_reason") or "").strip()
            if receipt_reason:
                return receipt_reason
        except (OSError, json.JSONDecodeError):
            pass

    if not getattr(res_ctx, "reproduced", True):
        return "REPRO_NOT_REPRODUCED"

    if not getattr(res_ctx, "solve_eligible", False):
        return "NO_PATCH"

    return "UNKNOWN_FAILURE"


def ensure_workspace_state(task: dict[str, Any]) -> None:
    """確保 Workspace 處於正確的 Commit 且 C 擴展已編譯"""
    repo_dir = Path(task["repo_dir"]).resolve()
    base_commit = task.get("base_commit")
    python_exe = task.get("python_executable", "python3")
    import subprocess

    if not task.get("local_mode"):
        nexus_workspaces_dir = (NEXUS_ROOT / ".nexus" / "workspaces").resolve()
        if not str(repo_dir).startswith(str(nexus_workspaces_dir)):
            raise RuntimeError(f"WORKSPACE_SAFETY_VIOLATION: Cannot run destructive git commands outside of {nexus_workspaces_dir}. Attempted on: {repo_dir}")

    if not (repo_dir / ".git").exists():
        if task.get("local_mode"):
            return # Do not clone in local_mode

        # 自動 Clone
        repo_map = {
            "astropy": "https://github.com/astropy/astropy.git",
            "django": "https://github.com/django/django.git",
            "requests": "https://github.com/psf/requests.git",
            "flask": "https://github.com/pallets/flask.git",
            "sympy": "https://github.com/sympy/sympy.git",
            "pytest": "https://github.com/pytest-dev/pytest.git",
        }
        repo_key = next((k for k in repo_map if k in task["instance_id"]), None)
        if repo_key:
            print(f"  📥 Workspace missing. Cloning {repo_key}...")
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(["git", "clone", repo_map[repo_key], str(repo_dir)], capture_output=True)
            if res.returncode != 0:
                raise RuntimeError(f"WORKSPACE_CLONE_FAILURE: {res.stderr.decode('utf-8')[:200]}")

    if base_commit and (repo_dir / ".git").exists():
        print(f"  ⚓ Switching to base commit: {base_commit}")
        # 1. Checkout
        res = subprocess.run(["git", "checkout", "-f", base_commit], cwd=str(repo_dir), capture_output=True)
        if res.returncode != 0:
            raise RuntimeError(f"WORKSPACE_CHECKOUT_FAILURE: {res.stderr.decode('utf-8')[:200]}")

        res = subprocess.run(["git", "clean", "-fd"], cwd=str(repo_dir), capture_output=True)
        if res.returncode != 0:
            raise RuntimeError(f"WORKSPACE_CLEAN_FAILURE: {res.stderr.decode('utf-8')[:200]}")

        # 2. Compile (如果是 Astropy)
        if "astropy" in task["instance_id"] and os.environ.get("NEXUS_NO_COMPILE") != "1":
            print("  ⚙️ Compiling Astropy C extensions (build_ext --inplace)...")
            build_cmd = [python_exe, "setup.py", "build_ext", "--inplace"]
            res = subprocess.run(build_cmd, cwd=str(repo_dir), capture_output=True, text=True)
            if res.returncode != 0:
                print(f"  ⚠️ Compilation warning (RC={res.returncode}): {res.stderr[:200]}...")

        # 3. Apply SymPy compatibility patches for Python 3.10+
        if "sympy" in str(repo_dir):
            patch_marker = repo_dir / ".nexus_patched_310"
            if not patch_marker.exists():
                print("  🩹 Applying SymPy compatibility patches (combined)...")
                # P0-4: 擴大搜尋範圍至 'collections' 以涵蓋 MutableSet 等直接引用
                combined_patch = (
                    f"grep -rIl 'collections' {repo_dir}/sympy | "
                    f"xargs -I {{}} sed -i '' "
                    f"-e 's/from collections import Mapping, defaultdict/from collections import defaultdict; from collections.abc import Mapping/g' "
                    f"-e 's/from collections import Mapping/from collections.abc import Mapping/g' "
                    f"-e 's/from collections import Callable/from collections.abc import Callable/g' "
                    f"-e 's/from collections import MutableSet/from collections.abc import MutableSet/g' "
                    f"-e 's/from collections import MutableMapping/from collections.abc import MutableMapping/g' "
                    f"-e 's/collections.MutableSet/collections.abc.MutableSet/g' "
                    f"-e 's/collections.Mapping/collections.abc.Mapping/g' "
                    f"-e 's/collections.Callable/collections.abc.Callable/g' "
                    f"-e 's/collections.Iterable/collections.abc.Iterable/g' "
                    f"-e 's/from collections import Container/from collections.abc import Container/g' "
                    f"-e 's/from collections import Iterable/from collections.abc import Iterable/g' "
                    f"{{}} 2>/dev/null || true"
                )
                subprocess.run(combined_patch, shell=True)
                patch_marker.touch()
            else:
                print("  ✅ SymPy compatibility patches already applied.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--no-compile", action="store_true", help="Skip compilation")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--instance_id", type=str, help="Specific instance ID to run")
    parser.add_argument(
        "--local_path", type=str, help="Local file path to fix (skips dataset)"
    )
    parser.add_argument(
        "--task_manifest",
        choices=["local-heal-20", "local-heal-40", "local-heal-60", "local-heal-100", "local-heal-113", "local-heal-batch1"],
        help="Run a fixed local-heal task manifest",
    )
    parser.add_argument(
        "--preflight_only",
        action="store_true",
        help="Write readiness rows without cloning or invoking models",
    )
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument(
        "--output",
        default=str(NEXUS_ROOT / "benchmarking/swebench_lite/predictions_swe.jsonl"),
    )
    parser.add_argument(
        "--resume_from",
        type=str,
        help="JSONL ledger whose completed manifest task IDs should be skipped",
    )
    parser.add_argument(
        "--hidden_verifier", action="store_true", help="Enable hidden verifier check"
    )
    parser.add_argument(
        "--repro_script_file",
        type=str,
        help="Optional existing repro script to use instead of generating one",
    )

    args = parser.parse_args()

    dataset = None
    if not args.local_path:
        print(f"📦 Loading {args.dataset}...")
        dataset = datasets.load_dataset(args.dataset, split="test")

    tasks = []
    if args.local_path:
        tasks = [
            {
                "instance_id": f"local_fix_{Path(args.local_path).name}",
                "repo_dir": LOCAL_HEAL_ROOT,
                "local_path": args.local_path,
                "env_profile": "python-default",
                "problem_statement": f"Fix issues in {args.local_path}",
                "local_mode": True,
            }
        ]
    elif args.instance_id:
        instance = next(
            (row for row in dataset if row["instance_id"] == args.instance_id), None
        )
        if not instance:
            print(f"❌ Error: Instance {args.instance_id} not found in dataset")
            return

        env_profile = "python-default"
        try:
            from nexus.services.local_heal.task_manifest import local_heal_113_task_manifest
            specs = local_heal_113_task_manifest()
            matched_spec = next((s for s in specs if s.instance_id == args.instance_id), None)
            if matched_spec:
                env_profile = matched_spec.env_profile
        except Exception:
            pass

        if env_profile == "python-default":
            if "astropy" in args.instance_id:
                env_profile = "astropy-legacy"
            elif "django" in args.instance_id:
                env_profile = "django-legacy"
            elif "sympy" in args.instance_id:
                env_profile = "sympy-default"

        from nexus.services.local_heal.env_resolver import EnvResolver, requirement_for_profile
        resolver = EnvResolver()
        resolution = resolver.resolve(requirement_for_profile(env_profile))
        python_exe = os.path.abspath(resolution.python_executable) if resolution.ready else ""

        repo_name = "astropy" if "astropy" in args.instance_id else "django" if "django" in args.instance_id else "sympy" if "sympy" in args.instance_id else "requests" if "requests" in args.instance_id else "flask" if "flask" in args.instance_id else ""
        task_repo_dir = LOCAL_HEAL_ROOT
        if repo_name:
            task_repo_dir = LOCAL_HEAL_ROOT / ".nexus" / "workspaces" / repo_name
        else:
            # Fallback to instance_id prefix if recognized structure
            parts = args.instance_id.split("__")
            if len(parts) == 2:
                task_repo_dir = LOCAL_HEAL_ROOT / ".nexus" / "workspaces" / parts[0].replace("psf", "requests").replace("pallets", "flask")

        tasks = [
            {
                "instance_id": instance["instance_id"],
                "base_commit": instance.get("base_commit"),
                "repo_dir": task_repo_dir,
                "problem_statement": instance["problem_statement"],
                "env_profile": env_profile,
                "local_mode": False,
                "python_executable": python_exe,
            }
        ]
    elif args.task_manifest:
        tasks = build_tasks_from_manifest(
            args.task_manifest, dataset, root_dir=LOCAL_HEAL_ROOT
        )
        for t in tasks:
            inst_id = t["instance_id"]
            repo_name = "astropy" if "astropy" in inst_id else "django" if "django" in inst_id else "sympy" if "sympy" in inst_id else "requests" if "requests" in inst_id else "flask" if "flask" in inst_id else ""
            if repo_name:
                t["repo_dir"] = str(LOCAL_HEAL_ROOT / ".nexus" / "workspaces" / repo_name)
            else:
                parts = inst_id.split("__")
                if len(parts) == 2:
                    t["repo_dir"] = str(LOCAL_HEAL_ROOT / ".nexus" / "workspaces" / parts[0].replace("psf", "requests").replace("pallets", "flask"))
        if args.resume_from:
            completed = read_resume_task_ids(
                args.resume_from, mode="preflight" if args.preflight_only else "repair"
            )
            tasks = filter_tasks_for_resume(tasks, completed)
        tasks = tasks[args.index : args.index + args.limit]
    else:
        tasks = [
            {
                "instance_id": row["instance_id"],
                "repo_dir": LOCAL_HEAL_ROOT,
                "problem_statement": row["problem_statement"],
                "env_profile": "python-default",
                "local_mode": False,
            }
            for row in list(dataset)[args.index : args.index + args.limit]
        ]

    if not tasks:
        print("ℹ️ No tasks to process.")
        return

    pipeline = HealPipeline(
        ollama_generate_fn=ollama_generate, hidden_verifier=args.hidden_verifier
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mode_label = "PREFLIGHT" if args.preflight_only else "REPAIR"
    print(f"\n🚀 Starting {mode_label} Loop for {len(tasks)} tasks...")

    with open(out_path, "a") as out_file:
        for i, task in enumerate(tasks):
            print(f"\n{'='*60}")
            print(
                f"[{i+1}/{len(tasks)}] Processing {task['instance_id']} (Profile: {task.get('env_profile')})"
            )

            try:
                ensure_workspace_state(task)
            except Exception as e:
                print(f"  💥 WORKSPACE ERROR: {e}")
                row = {
                    "instance_id": task["instance_id"],
                    "manifest_task_id": task.get("manifest_task_id", ""),
                    "solve_eligible": False,
                    "failure_reason": str(e).split(":")[0], # E.g., WORKSPACE_SAFETY_VIOLATION
                }
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()
                continue

            start_wall = time.time()
            ctx = HealContext(
                instance_id=task["instance_id"],
                repo_dir=Path(task["repo_dir"]),
                problem_statement=task["problem_statement"],
                expected_stop_layer=task.get("expected_stop_layer", "verification"),
                expected_reason_family=task.get("expected_reason_family", "SOLVED"),
            )
            ctx.auto_heal_enabled = True
            ctx.skip_reproduction = os.environ.get("NEXUS_SKIP_REPRODUCTION") == "1" or os.environ.get("NEXUS_SKIP_REPRODUCTION", "").lower() == "true"
            ctx.python_executable = task.get("python_executable", "")
            ctx.local_mode = task.get("local_mode", False)
            if ctx.local_mode:
                ctx.local_path = Path(task["local_path"])
                ctx.localized_files = localized_files_for_task(task)

            if args.preflight_only:
                from nexus.services.local_heal.preflight import run_preflight_for_spec
                spec = LocalHealTaskSpec(
                    task_id=task.get("manifest_task_id", "manual"),
                    kind=task.get("kind", "local_concurrency" if task.get("local_mode") else "swebench"),
                    family=task.get("family", "concurrency" if task.get("local_mode") else "swebench"),
                    env_profile=task.get("env_profile", "python-default"),
                    swe_index=task.get("swe_index"),
                    instance_id=task.get("instance_id"),
                    local_path=str(task.get("local_path", "")) if task.get("local_mode") else None,
                    domain_id=task.get("domain_id", "legacy"),
                    lane=task.get("lane", "baseline"),
                )
                preflight_row = run_preflight_for_spec(spec, Path(task["repo_dir"]))
                out_file.write(json.dumps(preflight_row) + "\n")
                out_file.flush()
                continue

            if args.repro_script_file:
                repro_path = Path(args.repro_script_file)
                if repro_path.exists():
                    ctx.repro_script = repro_path.read_text()

            # 優先加載 Antigravity 準備的專家級重現腳本，確保重現環境 100% 成功
            expert_repro_path = NEXUS_ROOT / ".nexus" / "expert_repro" / task["instance_id"] / "reproduce_bug.py"
            if expert_repro_path.exists():
                print(f"  🧠 Loaded expert repro script for {task['instance_id']}")
                ctx.repro_script = expert_repro_path.read_text(encoding="utf-8")

            try:
                telemetry_store.records = []
                res_ctx = pipeline.run(ctx)
                res_ctx.wall_time_sec = time.time() - start_wall

                # Merge Ollama telemetry details into the context
                if telemetry_store.records:
                    total_tokens = sum(r.get("prompt_eval_count", 0) + r.get("eval_count", 0) for r in telemetry_store.records)
                    res_ctx.token_total_estimated = total_tokens
                    res_ctx.token_telemetry_status = "success"

                    for idx, record in enumerate(telemetry_store.records):
                        if idx < len(res_ctx.model_decisions):
                            res_ctx.model_decisions[idx]["telemetry"] = record
                else:
                    res_ctx.token_telemetry_status = "estimated"

                if res_ctx.solve_eligible:
                    print("  ✅ SUCCESS: Solve eligible!")
                else:
                    is_np_error = "name 'np' is not defined" in str(
                        res_ctx.evaluation_report
                    ) or "name 'np' is not defined" in str(res_ctx.repro_evidence)
                    if (
                        res_ctx.failure_reason == "REPRO_ENVIRONMENT_FAILURE"
                        or not res_ctx.reproduced
                    ) and is_np_error:
                        print("  🔧 Auto-fixing repro script...")
                        res_ctx.repro_script = "import numpy as np\n" + res_ctx.repro_script
                        res_ctx = pipeline.run(res_ctx)

                row = build_result_row(task, res_ctx)
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()
            except Exception as e:
                print(f"  💥 CRITICAL EXCEPTION: {e}")
                row = {
                    "instance_id": task["instance_id"],
                    "manifest_task_id": task.get("manifest_task_id", ""),
                    "solve_eligible": False,
                    "failure_reason": f"CRITICAL_EXCEPTION:{type(e).__name__}:{str(e)}",
                }
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()

    print(f"\n✅ Predictions saved to: {out_path}")


if __name__ == "__main__":
    main()
