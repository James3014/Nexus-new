from __future__ import annotations

import json
import stat
from pathlib import Path

from nexus.services import external_intelligence


def test_atomic_json_fsyncs_file_and_parent_directory(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "state" / "attempt.json"
    fsync_kinds: list[str] = []
    real_fsync = external_intelligence.os.fsync

    def tracking_fsync(fd: int) -> None:
        mode = external_intelligence.os.fstat(fd).st_mode
        fsync_kinds.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(fd)

    monkeypatch.setattr(external_intelligence.os, "fsync", tracking_fsync)

    external_intelligence._atomic_json(target, {"state": "DISPATCHING"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "DISPATCHING"}
    assert "file" in fsync_kinds
    assert "directory" in fsync_kinds
