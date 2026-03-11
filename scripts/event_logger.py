#!/usr/bin/env python3
# 🛡️ Codex-Verified: Codex-Auth-Lvl13-Final (2026-03-03)
import sys
import json
import time
import os

EVENT_STORE = (
    "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/EVENT_STORE.jsonl"
)


def log_event(event_type, description, metadata=None):
    """
    將事件寫入唯增倉庫。
    event_type: task_completed, block_detected, strategy_shift, etc.
    """
    event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": event_type,
        "description": description,
        "metadata": metadata or {},
    }

    # 確保目錄存在
    os.makedirs(os.path.dirname(EVENT_STORE), exist_ok=True)

    with open(EVENT_STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(f"✅ 事件已存入倉庫: {description}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 event_logger.py <事件類型> <描述>")
    else:
        log_event(sys.argv[1], sys.argv[2])
