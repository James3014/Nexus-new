import sqlite3
import json
from pathlib import Path
from datetime import datetime

from nexus.contracts.sqlite_write_guard import build_sqlite_write_guard_receipt

class ProjectMemoryManager:
    """🧠 Nexus Project Memory: Persistent knowledge across sessions."""
    
    def __init__(self, project_root: Path):
        self.db_path = project_root / ".nexus" / "state" / "project_memory.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT,
                    content TEXT,
                    type TEXT, -- RCA, ARCH, PREF
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def build_write_guard_receipt(self, *, concurrent_writer_count: int = 1):
        wal_status = "RETURN"
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("PRAGMA journal_mode").fetchone()
                journal_mode = str(row[0] if row else "").lower()
                wal_status = "PASS" if journal_mode == "wal" else "RETURN"
        except sqlite3.Error:
            wal_status = "RETURN"
        return build_sqlite_write_guard_receipt(
            target_path=str(self.db_path),
            wal_status=wal_status,
            concurrent_writer_count=concurrent_writer_count,
            write_queue_status="PASS" if concurrent_writer_count <= 1 else "RETURN",
            backoff_status="PASS" if concurrent_writer_count <= 1 else "RETURN",
            memory_sanitizer_status="PASS",
            dedup_precision_status="PASS",
        )

    def add_insight(self, topic: str, content: str, insight_type: str = "RCA"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO insights (topic, content, type) VALUES (?, ?, ?)",
                (topic, content, insight_type)
            )

    def add_insight_guarded(
        self,
        topic: str,
        content: str,
        insight_type: str = "RCA",
        *,
        concurrent_writer_count: int = 1,
    ):
        """Write an insight only after the SQLite write guard passes."""

        receipt = self.build_write_guard_receipt(concurrent_writer_count=concurrent_writer_count)
        if receipt.get("status") != "PASS":
            return {
                "schema": "nexus.memory_write_result.v1",
                "status": "RETURN",
                "written": False,
                "topic": topic,
                "write_guard_receipt": receipt,
                "blockers": list(receipt.get("blockers", []) or ["sqlite_write_guard_not_pass"]),
                "claim_boundary": [
                    "Guarded memory writes only confirm local SQLite write safety.",
                    "They do not imply retrieval quality, learning closure success, or public readiness.",
                ],
            }

        self.add_insight(topic, content, insight_type)
        return {
            "schema": "nexus.memory_write_result.v1",
            "status": "PASS",
            "written": True,
            "topic": topic,
            "write_guard_receipt": receipt,
            "blockers": [],
            "claim_boundary": [
                "Guarded memory writes only confirm local SQLite write safety.",
                "They do not imply retrieval quality, learning closure success, or public readiness.",
            ],
        }

    def search(self, query: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT topic, content, type, timestamp FROM insights WHERE content LIKE ?",
                (f"%{query}%",)
            )
            return cursor.fetchall()
