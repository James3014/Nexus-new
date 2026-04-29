from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.commercial_lane_tasks import build_lane_tasks
from scripts.bench.capability_ab_runner import load_tasks

PUBLIC_CAPABILITY_TARGETS = {
    "codeintel",
    "research",
    "hyper",
    "nightshift",
    "swarm",
    "drone",
    "ultra_review",
    "autoreason",
    "ddtree",
}


def test_commercial_lanes_reference_existing_public_tasks():
    manifest = json.loads(Path("scripts/bench/public_benchmark_commercial_lanes_v1.json").read_text(encoding="utf-8"))

    assert manifest["rules"]["same_model_bare_vs_nexus"] is True
    assert manifest["rules"]["hidden_verifier_required"] is True
    assert {lane["id"] for lane in manifest["lanes"]} == {
        "capability_lift",
        "governed_delivery",
        "cost_efficiency",
    }

    tasks_by_manifest = {
        path: {task.id for task in load_tasks(path)}
        for path in {
            ref["manifest"]
            for lane in manifest["lanes"]
            for ref in lane["task_refs"]
        }
    }
    missing = [
        ref
        for lane in manifest["lanes"]
        for ref in lane["task_refs"]
        if ref["task_id"] not in tasks_by_manifest[ref["manifest"]]
    ]

    assert not missing


def test_commercial_lane_compiler_outputs_runner_tasks_file():
    payload = build_lane_tasks(lane="governed_delivery")

    assert payload["benchmark_id"].endswith(":governed_delivery")
    assert payload["frozen"] is True
    assert payload["tasks"]
    assert {task["commercial_lane"] for task in payload["tasks"]} == {"governed_delivery"}
    assert {task["id"] for task in payload["tasks"]} >= {
        "nexus-value-gov-001",
        "rlm-harder-v2-governance-001",
    }


def test_commercial_lanes_cover_public_capability_targets_without_running_models():
    manifest = json.loads(Path("scripts/bench/public_benchmark_commercial_lanes_v1.json").read_text(encoding="utf-8"))
    task_expected: dict[str, set[str]] = {}
    for path in {ref["manifest"] for lane in manifest["lanes"] for ref in lane["task_refs"]}:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for task in payload["tasks"]:
            task_expected[str(task["id"])] = set(task.get("expected_capabilities", []))

    covered: set[str] = set()
    for lane in manifest["lanes"]:
        for ref in lane["task_refs"]:
            covered.update(task_expected[ref["task_id"]])

    missing = PUBLIC_CAPABILITY_TARGETS - covered

    assert missing == {"research", "nightshift", "swarm", "drone", "ultra_review", "autoreason", "ddtree"}
