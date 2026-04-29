from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.commercial_lane_tasks import build_lane_tasks
from scripts.bench.capability_ab_runner import load_tasks


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
