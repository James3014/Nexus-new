import sqlite3
import json
from pathlib import Path
from datetime import datetime

class ProjectMemoryManager:
    """🧠 Nexus Project Memory: Persistent knowledge across sessions."""
    
    def __init__(self, project_root: Path):
        self.db_path = project_root / ".nexus" / "state" / "project_memory.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT,
                    content TEXT,
                    type TEXT, -- RCA, ARCH, PREF
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def add_insight(self, topic: str, content: str, insight_type: str = "RCA"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO insights (topic, content, type) VALUES (?, ?, ?)",
                (topic, content, insight_type)
            )

    def search(self, query: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT topic, content, type, timestamp FROM insights WHERE content LIKE ?",
                (f"%{query}%",)
            )
            return cursor.fetchall()
