import os

from scripts.ops import gemini_nexus_invoke


def test_gemini_invoker_strips_nexus_runner_and_sandbox_env(monkeypatch):
    monkeypatch.setenv("NEXUS_RUNNER", "Gemini")
    monkeypatch.setenv("GEMINI_SANDBOX", "true")
    monkeypatch.setenv("NEXUS_KEEP_ME", "yes")

    env = gemini_nexus_invoke._gemini_subprocess_env()

    assert "NEXUS_RUNNER" not in env
    assert "GEMINI_SANDBOX" not in env
    assert env["NEXUS_KEEP_ME"] == "yes"
    assert os.environ["GEMINI_SANDBOX"] == "true"


def test_lock_file_left_by_a_killed_run_does_not_block_the_next_run(tmp_path):
    """#3203: a lock file whose holder died (no live lock on it) is taken over."""
    lock = tmp_path / "gemini.lock"
    lock.write_text("999999999", encoding="utf-8")

    assert gemini_nexus_invoke._acquire_lock(lock) is True
    try:
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
    finally:
        gemini_nexus_invoke._release_lock(lock)
    assert not lock.exists()


def test_lock_held_by_a_live_holder_still_blocks(tmp_path):
    """#3203: single flight still holds while another descriptor owns the lock."""
    import fcntl

    lock = tmp_path / "gemini.lock"
    holder = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert gemini_nexus_invoke._acquire_lock(lock) is False
        assert lock.exists()
    finally:
        os.close(holder)

    assert gemini_nexus_invoke._acquire_lock(lock) is True
    gemini_nexus_invoke._release_lock(lock)


def test_lock_released_by_holder_is_reacquired_on_the_new_file(tmp_path, monkeypatch):
    """#3203: when the holder unlinks the file while we lock it, retry on the current path."""
    lock = tmp_path / "gemini.lock"
    real_flock = gemini_nexus_invoke.fcntl.flock
    calls: list[int] = []

    def flock_after_holder_released(fd, operation):
        calls.append(fd)
        if len(calls) == 1:
            # The previous holder releases between our open() and flock(): it unlinks the
            # file we opened, and a third run creates a fresh one at the same path.
            lock.unlink()
            lock.write_text("third run", encoding="utf-8")
        return real_flock(fd, operation)

    monkeypatch.setattr(gemini_nexus_invoke.fcntl, "flock", flock_after_holder_released)
    assert gemini_nexus_invoke._acquire_lock(lock) is True
    try:
        assert len(calls) == 2
        assert os.path.samestat(os.fstat(gemini_nexus_invoke._LOCK_FDS[lock]), os.stat(lock))
    finally:
        gemini_nexus_invoke._release_lock(lock)
    gemini_nexus_invoke._release_lock(lock)
    assert not lock.exists()
