from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.swe_bench_harness import build_predictions


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_build_predictions_reads_local_jsonl_and_writes_both_arms(tmp_path: Path):
    dataset = tmp_path / "swe.jsonl"
    _write_jsonl(
        dataset,
        [
            {
                "repo": "sympy/sympy",
                "instance_id": "sympy__sympy-2",
                "difficulty": "15 min - 1 hour",
                "patch": "diff --git a/x b/x\n",
            },
            {
                "repo": "django/django",
                "instance_id": "django__django-1",
                "difficulty": "<15 min fix",
                "patch": "diff --git a/y b/y\n",
            },
        ],
    )

    payload = build_predictions(dataset_file=dataset, max_tasks=2, arm="both", model="test-model")

    assert payload["schema"] == "nexus_swe_bench_verified_predictions_v1"
    assert payload["arms"] == ["without_nexus", "with_nexus"]
    assert payload["instance_ids"] == ["django__django-1", "sympy__sympy-2"]
    assert payload["predictions"]["without_nexus"][0]["model_name_or_path"] == "test-model"
    assert payload["predictions"]["with_nexus"][0]["model_patch"] == ""


def test_build_predictions_prefers_easy_wiring_subset(tmp_path: Path):
    dataset = tmp_path / "swe.jsonl"
    _write_jsonl(
        dataset,
        [
            {"repo": "a", "instance_id": "hard", "difficulty": "1-4 hours", "patch": ""},
            {"repo": "a", "instance_id": "easy", "difficulty": "<15 min fix", "patch": ""},
        ],
    )

    payload = build_predictions(dataset_file=dataset, max_tasks=1, arm="both")

    assert payload["instance_ids"] == ["easy"]


def test_build_predictions_filters_instance_ids_with_same_denominator(tmp_path: Path):
    dataset = tmp_path / "swe.jsonl"
    _write_jsonl(
        dataset,
        [
            {"repo": "a", "instance_id": "a-1", "difficulty": "<15 min fix", "patch": "a"},
            {"repo": "b", "instance_id": "b-1", "difficulty": "<15 min fix", "patch": "b"},
            {"repo": "c", "instance_id": "c-1", "difficulty": "<15 min fix", "patch": "c"},
        ],
    )

    payload = build_predictions(dataset_file=dataset, max_tasks=3, instance_ids="c-1,a-1", arm="both")

    assert payload["instance_ids"] == ["a-1", "c-1"]
    assert [row["instance_id"] for row in payload["predictions"]["without_nexus"]] == ["a-1", "c-1"]
    assert [row["instance_id"] for row in payload["predictions"]["with_nexus"]] == ["a-1", "c-1"]


def test_gold_patch_fallback_is_explicitly_marked(tmp_path: Path):
    dataset = tmp_path / "swe.jsonl"
    _write_jsonl(
        dataset,
        [{"repo": "a", "instance_id": "a-1", "difficulty": "<15 min fix", "patch": "gold"}],
    )

    payload = build_predictions(dataset_file=dataset, max_tasks=1, arm="without_nexus", gold_patch_fallback=True)
    row = payload["predictions"]["without_nexus"][0]

    assert row["model_patch"] == "gold"
    assert row["gold_patch_fallback"] is True
    assert payload["gold_patch_fallback"] is True
