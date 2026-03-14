import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from core.state_contracts import NexusIssue

class QueueManager:
    """
    🗄️ Nexus Queue Manager
    使用 SQLite 實現持久化隊列，支援平行 Worker 與優先級調度。
    """
    def __init__(self, db_path: str = "logs/nexus_queue.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    priority INTEGER,
                    status TEXT, -- PENDING, RUNNING, COMPLETED, FAILED, MELTED
                    payload TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.commit()

    def enqueue(self, issue: NexusIssue):
        """加入隊列。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO queue (id, batch_id, priority, status, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (issue.task_id, issue.batch_id, issue.priority, "PENDING", issue.model_dump_json(), datetime.now(), datetime.now())
            )
            conn.commit()

    def pop_next(self) -> Optional[NexusIssue]:
        """提取下一個最高優先級的 PENDING 任務。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM queue WHERE status = 'PENDING' ORDER BY priority ASC, created_at ASC LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # 標記為運行中
            conn.execute("UPDATE queue SET status = 'RUNNING', updated_at = ? WHERE id = ?", (datetime.now(), row['id']))
            conn.commit()
            return NexusIssue.model_validate_json(row['payload'])

    def update_status(self, task_id: str, status: str):
        """更新任務狀態。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE queue SET status = ?, updated_at = ? WHERE id = ?", (status, datetime.now(), task_id))
            conn.commit()

    def get_stats(self) -> dict:
        """獲取隊列統計數據。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT status, COUNT(*) as count FROM queue GROUP BY status")
            return {row[0]: row[1] for row in cursor.fetchall()}

if __name__ == "__main__":
    qm = QueueManager()
    print(f"📊 Initial Stats: {qm.get_stats()}")
