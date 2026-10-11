import asyncio

import scripts.engine.nexus_cli as cli_mod


def test_run_async_uses_repo_local_uv_cache_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    log = tmp_path / "out.log"
    cmd = [cli_mod.sys.executable, "-c", "import os; print(os.environ['UV_CACHE_DIR'])"]

    rc, _, _ = asyncio.run(cli_mod.AsyncProcessExecutor().run_async(cmd, log))

    assert rc == 0
    assert log.read_text().strip() == str((cli_mod.REPO_ROOT / ".tmp" / "uv-cache").resolve())


def test_run_async_respects_caller_uv_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    log = tmp_path / "out.log"
    cmd = [cli_mod.sys.executable, "-c", "import os; print(os.environ['UV_CACHE_DIR'])"]

    asyncio.run(cli_mod.AsyncProcessExecutor().run_async(cmd, log))

    assert log.read_text().strip() == str(tmp_path / "cache")


def test_run_async_records_spawn_failure(tmp_path):
    log = tmp_path / "out.log"

    rc, _, _ = asyncio.run(cli_mod.AsyncProcessExecutor().run_async([str(tmp_path / "missing-binary")], log))

    assert rc == 1
    assert "subprocess_spawn_failed: FileNotFoundError" in log.read_text()
