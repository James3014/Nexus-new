from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.export_benchmark_learning_ledgers import build_learning_ledgers, render_markdown


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_build_learning_ledgers_splits_model_training_and_cost_avoidance(tmp_path: Path) -> None:
    model_path = tmp_path / "model.jsonl"
    local_path = tmp_path / "local.jsonl"
    _write_jsonl(
        model_path,
        [
            {
                "mode": "with_nexus",
                "task_id": "model-uplift",
                "task_type": "public_docs_code_sync",
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
                "route_decision_selected_count": 5,
            }
        ],
    )
    _write_jsonl(
        local_path,
        [
            {
                "mode": "with_nexus",
                "task_id": "local-win",
                "task_type": "public_test_repair",
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "local_hidden_shadow",
            }
        ],
    )
    aggregate = {
        "schema_version": "aggregate",
        "rows": [
            {
                "task_id": "model-uplift",
                "with_status": "SUCCESS",
                "with_semantic": "VERIFIED",
                "with_eligible": True,
                "without_status": "FAILED",
                "without_semantic": "UNVERIFIED",
                "with_file": str(model_path),
            },
            {
                "task_id": "local-win",
                "with_status": "SUCCESS",
                "with_semantic": "VERIFIED",
                "with_eligible": True,
                "without_status": "FAILED",
                "without_semantic": "UNVERIFIED",
                "with_file": str(local_path),
            },
            {
                "task_id": "failed",
                "with_status": "FAILED",
                "with_semantic": "UNVERIFIED",
                "with_eligible": True,
            },
        ],
    }

    payload = build_learning_ledgers(aggregate, project_root=tmp_path)

    assert payload["summary"] == {
        "nexus_policy_count": 2,
        "model_training_count": 1,
        "model_uplift_training_count": 1,
        "cost_avoidance_count": 1,
        "rejected_count": 1,
    }
    assert payload["model_training_episodes"][0]["task_id"] == "model-uplift"
    assert payload["cost_avoidance_episodes"][0]["reason"] == "local_or_shadow_success"
    assert "Model Training Episodes" in render_markdown(payload)


def test_build_learning_ledgers_rejects_model_training_without_provider_token_source(tmp_path: Path) -> None:
    detail_path = tmp_path / "estimated.jsonl"
    _write_jsonl(
        detail_path,
        [
            {
                "mode": "with_nexus",
                "task_id": "estimated-win",
                "task_type": "public_test_repair",
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "missing",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    aggregate = {
        "schema_version": "aggregate",
        "rows": [
            {
                "task_id": "estimated-win",
                "with_status": "SUCCESS",
                "with_semantic": "VERIFIED",
                "with_eligible": True,
                "without_status": "FAILED",
                "without_semantic": "UNVERIFIED",
                "with_file": str(detail_path),
            }
        ],
    }

    payload = build_learning_ledgers(aggregate, project_root=tmp_path)

    assert payload["summary"]["model_training_count"] == 0
    assert payload["summary"]["cost_avoidance_count"] == 1
    assert payload["cost_avoidance_episodes"][0]["reason"] == "provider_tokens_not_measured"
