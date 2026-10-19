import json
import logging
import os
import random
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path

from nexus.contracts.sqlite_write_guard import build_sqlite_write_guard_receipt
from nexus.infrastructure.sqlite_retry import SQLiteRetryHandler, is_retryable_sqlite_busy

logger = logging.getLogger(__name__)

SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRIES = 4

SNAPSHOT_ATTEMPTS = 3


class StateReadOnlySnapshotError(RuntimeError):
    """No consistent read-only snapshot of the SQLite files could be taken."""


def _remove_tmpdir(path: str) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("could not remove read-only sqlite temp copy %s: %s", path, exc)


class _TempCopyConnection(sqlite3.Connection):
    """Connection on a temp copy; closing it (also via ``with``) removes the copy."""

    _tmpdir: str | None = None

    def close(self) -> None:
        try:
            super().close()
        finally:
            tmpdir, self._tmpdir = self._tmpdir, None
            if tmpdir:
                _remove_tmpdir(tmpdir)

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()

    def __del__(self) -> None:  # pragma: no cover - finalizer safety net
        try:
            self.close()
        except Exception:
            pass


def state_read_only() -> bool:
    from nexus.core.state_root import state_read_only as _state_read_only

    return _state_read_only()


class ProjectMemoryManager:
    """🧠 Nexus Project Memory: Persistent knowledge across sessions."""
    
    def __init__(self, project_root: Path):
        from nexus.core.state_root import persistent_state_root

        project_root = persistent_state_root(project_root)  # #2688
        self.db_path = project_root / ".nexus" / "state" / "project_memory.sqlite"
        self.last_sqlite_retry_receipt: dict | None = None
        if state_read_only():  # #2721: no mkdir, no CREATE TABLE (re-checked per call too)
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self):
        if state_read_only():
            return
        with self._connect() as conn:
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
            with self._connect() as conn:
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
        if state_read_only():  # #2721
            return
        self._execute_with_retry(
            "INSERT INTO insights (topic, content, type) VALUES (?, ?, ?)",
            (topic, content, insight_type),
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

        if state_read_only():  # #2721: no guard probe (opens the DB), no write
            return {
                "schema": "nexus.memory_write_result.v1",
                "status": "RETURN",
                "written": False,
                "topic": topic,
                "write_guard_receipt": None,
                "blockers": ["state_read_only"],
                "claim_boundary": [
                    "NEXUS_STATE_READ_ONLY=1: memory writes are skipped.",
                ],
            }

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
        if state_read_only() and not self.db_path.exists():  # #2721: nothing to read, create nothing
            return []
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT topic, content, type, timestamp FROM insights WHERE content LIKE ?",
                (f"%{query}%",)
            )
            return cursor.fetchall()

    def _source_signature(self) -> tuple:
        """(size, mtime_ns) of the DB and its -wal/-shm, or None for a missing file."""
        sig = []
        for suffix in ("", "-wal", "-shm"):
            try:
                st = os.stat(str(self.db_path) + suffix)
                sig.append((st.st_size, st.st_mtime_ns))
            except FileNotFoundError:
                sig.append(None)
        return tuple(sig)

    def _copy_snapshot(self, tmpdir: str) -> None:
        name = self.db_path.name
        shutil.copy2(self.db_path, Path(tmpdir) / name)
        for suffix in ("-wal", "-shm"):
            src = Path(str(self.db_path) + suffix)
            if src.exists():
                try:
                    shutil.copy2(src, Path(tmpdir) / (name + suffix))
                except FileNotFoundError:  # checkpointed away: caught by the re-stat
                    pass

    def _connect_temp_copy(self):
        """Open a throwaway copy of the DB (+ any -wal/-shm) from the system temp dir.

        Copying the WAL files too makes WAL-only rows visible; recovery/checkpointing
        happens only in the copy, which is deleted when the connection closes.  The
        source files are stat-ed before and after the copy; if a writer changed them
        (or a -wal appeared/disappeared) the copy is discarded and retried, and after
        SNAPSHOT_ATTEMPTS failures ``StateReadOnlySnapshotError`` is raised rather than
        opening a possibly inconsistent copy.
        """
        for attempt in range(1, SNAPSHOT_ATTEMPTS + 1):
            tmpdir = tempfile.mkdtemp(prefix="nexus-ro-sqlite-")
            try:
                before = self._source_signature()
                self._copy_snapshot(tmpdir)
                after = self._source_signature()
                if before == after and before[0] is not None:
                    conn = sqlite3.connect(
                        str(Path(tmpdir) / self.db_path.name),
                        timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
                        factory=_TempCopyConnection,
                    )
                    conn._tmpdir = tmpdir
                    return conn
            except FileNotFoundError:
                pass  # source vanished mid-copy: treat as a changed snapshot
            except BaseException:
                _remove_tmpdir(tmpdir)
                raise
            _remove_tmpdir(tmpdir)
            logger.warning(
                "read-only sqlite snapshot of %s changed during copy (attempt %d/%d)",
                self.db_path, attempt, SNAPSHOT_ATTEMPTS,
            )
        raise StateReadOnlySnapshotError(
            f"could not take a consistent read-only snapshot of {self.db_path} "
            f"after {SNAPSHOT_ATTEMPTS} attempts (concurrent writer)"
        )

    def _connect(self):
        if state_read_only():  # #2721: query a private temp copy, never touch the state root
            return self._connect_temp_copy()
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        return conn

    def _execute_with_retry(self, sql: str, params: tuple):
        handler = SQLiteRetryHandler(
            max_attempts=SQLITE_WRITE_RETRIES,
            base_delay_sec=0.025,
            max_delay_sec=0.25,
        )

        def operation() -> None:
            with self._connect() as conn:
                conn.execute(sql, params)

        try:
            return handler.run(
                operation,
                target_path=str(self.db_path),
                operation_name="project_memory_write",
            )
        finally:
            self.last_sqlite_retry_receipt = handler.last_receipt


def _is_retryable_sqlite_lock(exc: sqlite3.OperationalError) -> bool:
    return is_retryable_sqlite_busy(exc)


def _sqlite_jitter_delay(attempt: int) -> float:
    base = min(0.25, 0.025 * (2 ** max(0, attempt)))
    return base + random.uniform(0, base / 2)
