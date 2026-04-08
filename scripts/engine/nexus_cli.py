#!/usr/bin/env python3
import sys
import os
import json
import click
import asyncio
import time
import subprocess
import traceback
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

# 🧪 Nexus v23 Eternal Neural Swarm CLI (Self-Evolve Refactored)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 🔗 Phase 3: 自體演化導入 Service 層 (硬化導入)
from nexus.services.cli_commands_service import CliCommandsService
import asyncio
import os
import concurrent.futures
import time
import uuid

import time
import uuid
import queue
import threading
import atexit

class SingleWriterQueue:
    """🛡️ [v23:IO] FIFO Background Writer to decouple disk IO from decision flow"""
    def __init__(self):
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                path, content, mode = self._queue.get(timeout=0.1)
                from pathlib import Path
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open(mode, encoding="utf-8") as f:
                    f.write(content)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass # Fail silently for async-eligible logs

    def put(self, path, content, mode="a"):
        if not self._stop_event.is_set():
            self._queue.put((path, content, mode))

    def flush(self):
        self._stop_event.set()
        self._queue.join()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

# 🌐 Global Single-Writer Instance
_io_queue = SingleWriterQueue()
atexit.register(_io_queue.flush)

def _log_perf_span(name, start_ts, end_ts, decision_id, metadata=None):
    """🛡️ [v23:PerfMonitor] Async-eligible: Put to queue"""
    try:
        import json
        payload = {
            "span_name": name,
            "decision_id": decision_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_ms": (end_ts - start_ts) * 1000,
            "metadata": metadata or {}
        }
        _io_queue.put("/Users/jameschen/Workspace/nexus/.nexus/metrics/perf_spans.jsonl", json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

@click.group()
@click.pass_context
def nexus(ctx):
    """⚖️ Nexus Singularity OS (v23 Eternal Neural Swarm)"""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NEXUS_SKIP_PROTOCOL_GATE") == "1":
        return
    command_name = ctx.invoked_subcommand or (sys.argv[1] if len(sys.argv) > 1 else "")
    from nexus.services.continuous_learning import run_protocol_startup_gate
    result = run_protocol_startup_gate(REPO_ROOT, command_name=command_name)
    ctx.ensure_object(dict)
    ctx.obj["protocol_gate"] = result
    if not result.ok:
        raise click.ClickException(
            f"Protocol gate failed: {result.protocol_path} | ci({result.ci_mode})={result.ci_summary or result.ci_exit_code}"
        )

def _get_service():
    # Lazy: from nexus.services.cli_commands_service import CliCommandsService
    return CliCommandsService(REPO_ROOT)


def _run_governance_gate(*, dry_run: bool = True, wiki_drift_enforce_level: str = "p0") -> int:
    """Run governance gate with shared defaults for CLI entry commands."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "ops" / "ci_gate.py"),
        "--wiki-drift-enforce-level",
        wiki_drift_enforce_level,
    ]
    if dry_run:
        cmd.append("--dry-run")
    t0 = time.perf_counter()
    res = subprocess.run(cmd)
    t1 = time.perf_counter()
    # Note: decision_id is typically not available here, using global/placeholder
    _log_perf_span("ops.subprocess.gate", t0, t1, "NEXUS_SYSTEM_GATE", {"exit_code": res.returncode})
    return int(getattr(res, "returncode", 1))

# 📦 [Modular CLI] Command Registration
from nexus.cli.commands.core import status, probe, benchmark, learning_sync, closeout
from nexus.cli.commands.memory import memory_group

nexus.add_command(status, name="nexus:status")
nexus.add_command(probe, name="nexus:probe")
nexus.add_command(benchmark, name="nexus:benchmark")
nexus.add_command(learning_sync, name="nexus:learning-sync")
nexus.add_command(closeout, name="nexus:closeout")
nexus.add_command(memory_group, name="nexus:memory")

if __name__ == "__main__":
    nexus()
