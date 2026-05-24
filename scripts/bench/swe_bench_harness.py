#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_DATASET_FILE = Path("scripts/bench/swe-bench-verified.json")
DIFFICULTY_ORDER = {
    "<15 min fix": 0,
    "15 min - 1 hour": 1,
    "1-4 hours": 2,
    ">4 hours": 3,
}


def _read_local_dataset(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _select_rows(rows: list[dict[str, Any]], *, max_tasks: int, instance_ids: str = "") -> list[dict[str, Any]]:
    if instance_ids and instance_ids != "all":
        wanted = {item.strip() for item in instance_ids.split(",") if item.strip()}
        rows = [row for row in rows if str(row.get("instance_id")) in wanted]
    rows = sorted(
        rows,
        key=lambda row: (
            DIFFICULTY_ORDER.get(str(row.get("difficulty", "")), 999),
            str(row.get("repo", "")),
            str(row.get("instance_id", "")),
        ),
    )
    return rows[: max(0, int(max_tasks))]


def _latest_nexus_patch(repo_root: Path) -> str:
    runs_dir = repo_root / ".nexus" / "runs"
    if not runs_dir.exists():
        return ""
    task_dirs = sorted([item for item in runs_dir.glob("task-*") if item.is_dir()], key=os.path.getmtime)
    if not task_dirs:
        return ""
    latest_run = task_dirs[-1]
    patch_file = latest_run / "patch.diff"
    if patch_file.exists():
        return patch_file.read_text(encoding="utf-8", errors="replace")
    patches = sorted(latest_run.glob("*.patch"))
    return patches[0].read_text(encoding="utf-8", errors="replace") if patches else ""


def _prediction_for_row(
    row: dict[str, Any],
    *,
    arm: str,
    model: str,
    repo_root: Path,
    invoke_nexus: bool,
    gold_patch_fallback: bool,
) -> dict[str, Any]:
    patch = ""
    error = ""
    if invoke_nexus and arm == "with_nexus":
        cmd = [
            "uv",
            "run",
            "scripts/engine/nexus_cli.py",
            "nexus",
            "run",
            str(row.get("problem_statement") or ""),
            "--output-file",
            ".nexus/reports/swe_bench_wiring/run_output.json",
        ]
        env = os.environ.copy()
        env["NEXUS_BENCHMARK_MODE"] = "1"
        res = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True, timeout=600)
        if res.returncode == 0:
            patch = _latest_nexus_patch(repo_root)
        else:
            error = (res.stderr or res.stdout or "nexus_runner_failed")[-1000:]
    elif gold_patch_fallback:
        patch = str(row.get("patch") or "")

    return {
        "instance_id": str(row.get("instance_id") or ""),
        "model_patch": patch,
        "model_name_or_path": model,
        "arm": arm,
        "repo": str(row.get("repo") or ""),
        "difficulty": str(row.get("difficulty") or ""),
        "wiring_only": not invoke_nexus,
        "gold_patch_fallback": bool(gold_patch_fallback and patch),
        "error": error,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _run_official_harness(*, repo_root: Path, predictions_path: Path, run_id: str, dataset_name: str = "princeton-nlp/SWE-bench_Verified", split: str = "test") -> int:
    cmd = [
        "uv",
        "run",
        "--with",
        "swebench",
        "python3",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--predictions_path",
        str(predictions_path),
        "--max_workers",
        "8",
        "--run_id",
        run_id,
        "--split",
        split,
    ]
    return subprocess.run(cmd, cwd=repo_root).returncode


def build_predictions(
    *,
    dataset_file: str | Path = DEFAULT_DATASET_FILE,
    max_tasks: int = 5,
    instance_ids: str = "",
    arm: str = "both",
    model: str = "nexus-swe-bench-wiring",
    invoke_nexus: bool = False,
    gold_patch_fallback: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    selected = _select_rows(_read_local_dataset(dataset_file), max_tasks=max_tasks, instance_ids=instance_ids)
    arms = ["without_nexus", "with_nexus"] if arm == "both" else [arm]
    predictions: dict[str, list[dict[str, Any]]] = {}
    for arm_name in arms:
        predictions[arm_name] = [
            _prediction_for_row(
                row,
                arm=arm_name,
                model=model,
                repo_root=repo_root,
                invoke_nexus=invoke_nexus,
                gold_patch_fallback=gold_patch_fallback,
            )
            for row in selected
        ]
    return {
        "schema": "nexus_swe_bench_verified_predictions_v1",
        "dataset_file": str(dataset_file),
        "max_tasks": max_tasks,
        "instance_ids": [str(row.get("instance_id") or "") for row in selected],
        "arms": list(predictions),
        "invoke_nexus": bool(invoke_nexus),
        "gold_patch_fallback": bool(gold_patch_fallback),
        "predictions": predictions,
    }


def main(argv: list[str] | None = None) -> int:
    import os
    os.environ["NEXUS_GEMINI_MODEL_NAME"] = "gemini-3-flash-preview"
    parser = argparse.ArgumentParser(description="SWE-bench Verified wiring harness for Nexus public credibility runs.")
    parser.add_argument("--dataset-file", default=str(DEFAULT_DATASET_FILE))
    parser.add_argument("--mode", default="verified")
    parser.add_argument("--limit", "--max-tasks", dest="max_tasks", type=int, default=5)
    parser.add_argument("--instance-ids", default="")
    parser.add_argument("--model", default="nexus-swe-bench-wiring")
    parser.add_argument("--arm", choices=["without_nexus", "with_nexus", "both"], default="both")
    parser.add_argument("--output-dir", default=".nexus/reports/swe_bench_wiring")
    parser.add_argument("--jsonl-output", default="")
    parser.add_argument("--metadata-output", default="")
    parser.add_argument("--invoke-nexus", action="store_true")
    parser.add_argument("--gold-patch-fallback", action="store_true")
    parser.add_argument("--run-official-harness", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    payload = build_predictions(
        dataset_file=args.dataset_file,
        max_tasks=int(args.max_tasks),
        instance_ids=str(args.instance_ids),
        arm=str(args.arm),
        model=str(args.model),
        invoke_nexus=bool(args.invoke_nexus),
        gold_patch_fallback=bool(args.gold_patch_fallback),
        repo_root=repo_root,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    for arm_name, rows in payload["predictions"].items():
        if args.jsonl_output and len(payload["predictions"]) == 1:
            path = Path(args.jsonl_output)
        else:
            path = output_dir / f"{arm_name}_predictions.jsonl"
        _write_jsonl(path, rows)
        written[arm_name] = str(path)

    metadata_path = Path(args.metadata_output) if args.metadata_output else output_dir / "swe_bench_metadata.json"
    metadata = {key: value for key, value in payload.items() if key != "predictions"}
    metadata["prediction_files"] = written
    metadata["official_harness"] = {
        "requested": bool(args.run_official_harness),
        "status": "not_run",
        "returncode": None,
        "run_id": "",
    }
    if args.run_official_harness:
        run_id = f"nexus-swe-bench-{int(time.time())}"
        target = Path(next(iter(written.values())))
        dataset_name = "ScaleAI/SWE-bench_Pro" if "pro" in str(args.dataset_file).lower() else "princeton-nlp/SWE-bench_Verified"
        split = "test"
        code = _run_official_harness(
            repo_root=repo_root,
            predictions_path=target,
            run_id=run_id,
            dataset_name=dataset_name,
            split=split
        )
        metadata["official_harness"] = {
            "requested": True,
            "status": "PASS" if code == 0 else "FAIL",
            "returncode": code,
            "run_id": run_id,
        }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(metadata_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
