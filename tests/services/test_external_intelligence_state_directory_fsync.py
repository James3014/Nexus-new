"""Regression coverage for crash-durable External Intelligence state publication."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from nexus.services import external_intelligence


def test_atomic_json_fsyncs_file_and_parent_directory(tmp_path: Path, monkeypatch) -> None:
    observed: list[str] = []
    original_fsync = os.fsync
    original_fstat = os.fstat

    def recording_fsync(fd: int) -> None:
        mode = original_fstat(fd).st_mode
        observed.append("directory" if stat.S_ISDIR(mode) else "file")
        original_fsync(fd)

    monkeypatch.setattr(external_intelligence.os, "fsync", recording_fsync)

    target = tmp_path / "attempts" / "request.json"
    external_intelligence._atomic_json(target, {"state": "DISPATCHING", "retry_safe": False})

    assert target.exists()
    assert "file" in observed
    assert "directory" in observed
