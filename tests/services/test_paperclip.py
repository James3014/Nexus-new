from pathlib import Path

from scripts.ops.paperclip import PaperclipDaemon


def test_scan_once_returns_sorted_deterministic_read_only_snapshot(tmp_path, monkeypatch):
    watch_dir = tmp_path / "heartbeats"
    watch_dir.mkdir()
    (watch_dir / "12.hb").write_text("alive\n", encoding="utf-8")
    (watch_dir / "bad.hb").write_text("invalid\n", encoding="utf-8")
    (watch_dir / "7.hb").write_text("alive\n", encoding="utf-8")

    def fail_kill(*_args):
        raise AssertionError("scan_once must not signal processes")

    def fail_unlink(*_args, **_kwargs):
        raise AssertionError("scan_once must not unlink files")

    monkeypatch.setattr("scripts.ops.paperclip.os.kill", fail_kill)
    monkeypatch.setattr(Path, "unlink", fail_unlink)

    daemon = PaperclipDaemon(watch_dir)
    first = daemon.scan_once()
    second = daemon.scan_once()

    assert first == second
    assert first == {
        "schema": "nexus.paperclip_heartbeat_snapshot.v1",
        "watch_dir": str(watch_dir.resolve()),
        "entries": [
            {"name": "12.hb", "pid": 12, "valid": True},
            {"name": "7.hb", "pid": 7, "valid": True},
            {"name": "bad.hb", "pid": None, "valid": False},
        ],
        "valid_count": 2,
        "invalid_count": 1,
        "status": "INVALID_ENTRIES",
    }
    assert sorted(path.name for path in watch_dir.iterdir()) == ["12.hb", "7.hb", "bad.hb"]
