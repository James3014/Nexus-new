from __future__ import annotations

import json
from pathlib import Path

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
