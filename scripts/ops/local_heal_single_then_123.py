from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from benchmarking.swebench_lite.swe_local_heal import nexus_local_generate
from nexus.engine.local_model_policy import LocalModelPolicy
from nexus.services.local_heal.pipeline import HealContext, HealPipeline


NEXUS_ROOT = Path(__file__).resolve().parents[2]
PROBE_ROOT = Path("/private/tmp/nexus_local_heal_one_task")


BUGGY_COUNTER = """import threading
import time


class InventoryCounter:
    def __init__(self):
        self.count = 0

    def increment(self):
        current = self.count
        time.sleep(0.001)
        self.count = current + 1


def test_challenge():
    counter = InventoryCounter()
    threads = [threading.Thread(target=counter.increment) for _ in range(100)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert counter.count == 100, f"Counter race detected: {counter.count} != 100"


if __name__ == "__main__":
    test_challenge()
"""

REPRO_SCRIPT = """import counter_bug


counter_bug.test_challenge()
"""


def write_probe_fixture() -> tuple[Path, Path]:
    PROBE_ROOT.mkdir(parents=True, exist_ok=True)
    target = PROBE_ROOT / "counter_bug.py"
    repro = PROBE_ROOT / "repro_counter_bug.py"
    target.write_text(BUGGY_COUNTER, encoding="utf-8")
    repro.write_text(REPRO_SCRIPT, encoding="utf-8")
    return target, repro


def run_repro(repro: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repro)],
        cwd=str(PROBE_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def duplicate_top_level_defs(source: str) -> list[str]:
    tree = ast.parse(source)
    seen: set[tuple[type[ast.AST], str]] = set()
    duplicates: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        key = (type(node), node.name)
        if key in seen:
            duplicates.append(node.name)
        seen.add(key)
    return duplicates


def run_single_probe() -> dict[str, object]:
    target, repro = write_probe_fixture()
    before = run_repro(repro)
    if before.returncode == 0:
        raise RuntimeError("Probe fixture is not red before repair; refusing to claim success.")

    os.environ.setdefault("NEXUS_PATCH_TIMEOUT_SECONDS", "500")
    os.environ.setdefault("NEXUS_OLLAMA_NUM_CTX", "4096")
    os.environ.setdefault("NEXUS_OLLAMA_NUM_PREDICT", "768")
    LocalModelPolicy.PATCH_TIMEOUT_SECONDS = int(os.environ["NEXUS_PATCH_TIMEOUT_SECONDS"])

    ctx = HealContext(
        instance_id="local_counter_bug_probe_clean_gate",
        repo_dir=PROBE_ROOT,
        problem_statement=(
            "Fix the race condition in counter_bug.py. InventoryCounter.increment "
            "performs a non-atomic read/sleep/write update, so concurrent increments "
            "lose updates. Modify the existing InventoryCounter class in place; do not "
            "create or redefine another InventoryCounter class. Preserve test_challenge "
            "and make the counter reach 100."
        ),
    )
    ctx.auto_heal_enabled = True
    ctx.python_executable = str(NEXUS_ROOT / ".venv/bin/python")
    ctx.repro_script = repro.read_text(encoding="utf-8")
    ctx.localized_files = [("counter_bug.py", target.read_text(encoding="utf-8"))]

    started = time.time()
    result = HealPipeline(ollama_generate_fn=nexus_local_generate).run(ctx)
    after = run_repro(repro)
    patched_source = target.read_text(encoding="utf-8")
    duplicates = duplicate_top_level_defs(patched_source)

    payload: dict[str, object] = {
        "probe_root": str(PROBE_ROOT),
        "target": str(target),
        "receipt_path": result.receipt_path,
        "solve_eligible": result.solve_eligible,
        "failure_reason": result.failure_reason,
        "reproduced": result.reproduced,
        "visible_after_returncode": after.returncode,
        "duplicate_top_level_defs": duplicates,
        "final_patch_len": len(result.final_patch or ""),
        "wall_time_sec": round(time.time() - started, 3),
        "model_decisions": result.model_decisions,
        "evaluation_report": result.evaluation_report,
    }

    if not result.solve_eligible or after.returncode != 0 or duplicates:
        payload["status"] = "FAILED"
        return payload
    payload["status"] = "CLEAN_SINGLE_SUCCESS"
    return payload


def run_manifest_123(output: Path) -> int:
    cmd = [
        sys.executable,
        "-m",
        "benchmarking.swebench_lite.swe_local_heal",
        "--task_manifest",
        "local-heal-113",
        "--limit",
        "123",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=str(NEXUS_ROOT))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-123",
        action="store_true",
        help="After clean single-task success, launch the full local-heal-113 repair run.",
    )
    parser.add_argument(
        "--output",
        default=str(NEXUS_ROOT / "benchmarking/swebench_lite/predictions_local_heal_123.jsonl"),
        help="Output JSONL path for the optional 123-task run.",
    )
    args = parser.parse_args()

    payload = run_single_probe()
    print(json.dumps(payload, indent=2))
    if payload.get("status") != "CLEAN_SINGLE_SUCCESS":
        return 2

    if not args.run_123:
        return 0

    return run_manifest_123(Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
