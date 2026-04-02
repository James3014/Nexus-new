from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import time
import sqlite3
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class NodeRecord:
    node_id: str
    host: str
    port: int
    status: str
    last_heartbeat: float
    load: float
    capabilities: List[str]
    tls_fingerprint: str = ""

class NodeRegistry:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_heartbeat REAL NOT NULL,
                    load REAL NOT NULL,
                    capabilities TEXT NOT NULL,
                    tls_fingerprint TEXT NOT NULL
                )
            ''')
            conn.commit()

    def register(self, node: NodeRecord) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                INSERT INTO nodes (node_id, host, port, status, last_heartbeat, load, capabilities, tls_fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET 
                    host=excluded.host,
                    port=excluded.port,
                    status=excluded.status,
                    last_heartbeat=excluded.last_heartbeat,
                    load=excluded.load,
                    capabilities=excluded.capabilities,
                    tls_fingerprint=excluded.tls_fingerprint
            ''', (
                node.node_id, node.host, node.port, node.status, 
                node.last_heartbeat, node.load, json.dumps(node.capabilities), node.tls_fingerprint
            ))
            conn.commit()

    def deregister(self, node_id: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
            conn.commit()

    def discover(self) -> List[NodeRecord]:
        self._prune_stale_nodes()
        records = []
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM nodes WHERE status = 'ONLINE' OR status = 'DEGRADED'")
            for row in cursor:
                try:
                    caps = json.loads(row["capabilities"])
                except Exception:
                    caps = []
                records.append(NodeRecord(
                    node_id=row["node_id"],
                    host=row["host"],
                    port=row["port"],
                    status=row["status"],
                    last_heartbeat=row["last_heartbeat"],
                    load=row["load"],
                    capabilities=caps,
                    tls_fingerprint=row["tls_fingerprint"]
                ))
        return records

    def heartbeat(self, node_id: str, load: float = 0.0, capabilities: Optional[List[str]] = None) -> None:
        now = time.time()
        with sqlite3.connect(str(self.db_path)) as conn:
            if capabilities is not None:
                caps_json = json.dumps(capabilities)
                conn.execute('''
                    UPDATE nodes 
                    SET last_heartbeat = ?, status = 'ONLINE', load = ?, capabilities = ?
                    WHERE node_id = ?
                ''', (now, load, caps_json, node_id))
            else:
                conn.execute('''
                    UPDATE nodes 
                    SET last_heartbeat = ?, status = 'ONLINE', load = ?
                    WHERE node_id = ?
                ''', (now, load, node_id))
            conn.commit()

    def _prune_stale_nodes(self) -> None:
        now = time.time()
        with sqlite3.connect(str(self.db_path)) as conn:
            # > 60s -> DEGRADED
            conn.execute("UPDATE nodes SET status = 'DEGRADED' WHERE status = 'ONLINE' AND last_heartbeat < ?", (now - 60,))
            # > 300s -> OFFLINE
            conn.execute("UPDATE nodes SET status = 'OFFLINE' WHERE status IN ('ONLINE', 'DEGRADED') AND last_heartbeat < ?", (now - 300,))
            conn.commit()

    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        self._prune_stale_nodes()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
            if row:
                try:
                    caps = json.loads(row["capabilities"])
                except Exception:
                    caps = []
                return NodeRecord(
                    node_id=row["node_id"],
                    host=row["host"],
                    port=row["port"],
                    status=row["status"],
                    last_heartbeat=row["last_heartbeat"],
                    load=row["load"],
                    capabilities=caps,
                    tls_fingerprint=row["tls_fingerprint"]
                )
        return None
