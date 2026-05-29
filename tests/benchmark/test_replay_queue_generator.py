from __future__ import annotations

import tempfile
import json
from pathlib import Path
from scripts.bench.generate_replay_queue import generate_queue


def test_replay_queue_generator_success():
    """
    測試 Replay Queue 生成器：
    1. 正確過濾 action: "replayable"。
    2. 優先順序: tokenless_timeout_fallback > stats_outlier_token。
    3. 安全隔離排除 non-refillable blocker。
    """
    # 模擬 RCA blockers policy JSON
    mock_policy = {
        "blockers": [
            {
                "task_id": "task-non-refillable-001",
                "rca_category": "non_refillable_model_required",
                "action": "non-refillable",
                "reasons": "hard blocker"
            },
            {
                "task_id": "task-timeout-002",
                "rca_category": "tokenless_timeout_fallback",
                "action": "replayable",
                "reasons": "timeout fallback"
            },
            {
                "task_id": "task-outlier-003",
                "rca_category": "stats_outlier_token",
                "action": "replayable",
                "reasons": "outlier stats"
            }
        ]
    }

    # 模擬 manifest JSON 用以比對物理 index
    mock_manifest = {
        "tasks": [
            {"id": "task-other-000"},
            {"id": "task-timeout-002"}, # index 1
            {"id": "task-outlier-003"}, # index 2
        ]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "blockers.json"
        manifest_path = Path(tmpdir) / "manifest.json"

        with open(policy_path, "w") as f:
            json.dump(mock_policy, f)
        with open(manifest_path, "w") as f:
            json.dump(mock_manifest, f)

        # 執行生成
        queue_items, index_filter = generate_queue(
            policy_path=policy_path,
            manifest_path=manifest_path
        )

        # 驗算結果
        # 1. 隔離排除: 只有 2 個 replayable 被提取，non-refillable 應被排除
        assert len(queue_items) == 2
        
        # 2. 優先順序: timeout 優先於 outlier
        assert queue_items[0]["task_id"] == "task-timeout-002"
        assert queue_items[1]["task_id"] == "task-outlier-003"
        
        # 3. 尋址成功:
        assert queue_items[0]["manifest_index"] == 1
        assert queue_items[1]["manifest_index"] == 2
        
        # 4. 生成的 index_filter 正確對齊
        assert index_filter == "1,2"
