import os
import sys
import click
import json
import subprocess
import time
import queue
import threading
import atexit
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]

def _get_service():
    from nexus.services.cli_commands_service import CliCommandsService
    return CliCommandsService(REPO_ROOT)

class SingleWriterQueue:
    def __init__(self):
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
    def _run(self):
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.1)
                path, content, mode = item
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open(mode, encoding="utf-8") as f:
                    f.write(content)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass
    def put(self, path, content, mode="a"):
        if not self._stop_event.is_set():
            self._queue.put((path, content, mode))
    def flush(self):
        self._stop_event.set()
        self._queue.join()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

from nexus.core.telemetry import FileTelemetryProvider

_io_queue = SingleWriterQueue()
atexit.register(_io_queue.flush)

# 🌐 Global Telemetry Instance
_telemetry = FileTelemetryProvider(
    REPO_ROOT / ".nexus" / "metrics" / "perf_spans.jsonl",
    _io_queue
)

def _log_perf_span(name, start_ts, end_ts, decision_id, metadata=None):
    _telemetry.log_span(name, start_ts, end_ts, decision_id, metadata)

