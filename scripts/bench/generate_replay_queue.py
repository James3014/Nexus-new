#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


def load_manifest_tasks(manifest_path: Path | str) -> list[str]:
    """
    載入 manifest 中的 task IDs，用以查詢 index 物理位址。
    """
    path = Path(manifest_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [t.get("id", "") for t in data.get("tasks", [])]
    except Exception as e:
        print(f"⚠️ 載入 manifest 失敗: {e}")
        return []


def generate_queue(
    policy_path: Path | str = ".nexus/policy/combine_blockers_rca.json",
    manifest_path: Path | str = "scripts/bench/public_benchmark_nexus_value_execution_safe_v1.json"
) -> tuple[list[dict[str, Any]], str]:
    """
    自 RCA policy 中過濾並排序出最小續跑的 replay queue，並比對 manifest 計算物理 index。
    """
    policy = Path(policy_path)
    if not policy.exists():
        print(f"❌ 找不到 Policy RCA JSON: {policy}")
        return [], ""

    try:
        with open(policy, "r", encoding="utf-8") as f:
            data = json.load(f)
        blockers = data.get("blockers", [])
    except Exception as e:
        print(f"❌ 讀取 Policy RCA JSON 失敗: {e}")
        return [], ""

    # 1. 載入 manifest 用於比對 task ID 取出 index
    manifest_task_ids = load_manifest_tasks(manifest_path)
    
    # 2. 過濾 action == "replayable" 的項目，並排除 non-refillable 的 blocker
    replayable_blockers = [b for b in blockers if b.get("action") == "replayable"]
    non_refillable_blockers = [b for b in blockers if b.get("action") == "non-refillable"]

    # 3. 定義優先權比重 (權重越低越優先)
    # tokenless_timeout_fallback 優先於 stats_outlier_token
    category_weights = {
        "tokenless_timeout_fallback": 0,
        "stats_outlier_token": 1
    }

    def sort_key(b: dict[str, Any]) -> int:
        cat = b.get("rca_category", "")
        return category_weights.get(cat, 99)

    sorted_blockers = sorted(replayable_blockers, key=sort_key)

    # 4. 比對 manifest，計算物理 index 尋址
    queue_items = []
    index_list = []
    
    print("\n=== [Replay Queue 計算] ===")
    for b in sorted_blockers:
        task_id = b.get("task_id", "")
        if not task_id:
            continue
            
        # 比對 manifest 取物理 index
        try:
            physical_idx = manifest_task_ids.index(task_id)
            b["manifest_index"] = physical_idx
            index_list.append(str(physical_idx))
            print(f"  - 尋址成功: Task ID '{task_id}' -> Manifest Index [{physical_idx}] (RCA: {b.get('rca_category')})")
        except ValueError:
            # 若 manifest 中無此 ID，但我們需要提供 mock 支持或是報警告
            b["manifest_index"] = -1
            print(f"  - ⚠️ 尋址警告: Task ID '{task_id}' 未存在於當前 manifest 中。")
            
        queue_items.append(b)

    # 安全隔離檢查
    print("\n=== [安全隔離檢查] ===")
    for nb in non_refillable_blockers:
        task_id = nb.get("task_id")
        print(f"  - [EXCLUDED] Blocker '{task_id}' 屬於 non-refillable，已安全隔離排除。")

    # 合成 index filter
    index_filter_str = ",".join(index_list)
    print(f"\n✓ 成功生成最小續跑佇列！")
    print(f"  - 最小精準 replay index 參數: --manifest-index-filter \"{index_filter_str}\"")
    
    return queue_items, index_filter_str


def main() -> None:
    parser = argparse.ArgumentParser(description="7R Replay Queue Generator from RCA policy")
    parser.add_argument(
        "--policy",
        type=str,
        default=".nexus/policy/combine_blockers_rca.json",
        help="Path to combine blockers RCA policy"
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default="scripts/bench/public_benchmark_nexus_value_execution_safe_v1.json",
        help="Path to manifest JSON"
    )
    args = parser.parse_args()

    _, index_filter = generate_queue(
        policy_path=args.policy,
        manifest_path=args.manifest
    )
    
    # 輸出給 shell 使用
    print(index_filter)


if __name__ == "__main__":
    main()
