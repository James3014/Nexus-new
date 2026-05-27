import pytest
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.engine.nexus_cli import AsyncProcessExecutor

@pytest.mark.anyio
async def test_uv_cache_env_isolation():
    """
    TDD Phase (RED): Verify that AsyncProcessExecutor injects the isolated
    UV_CACHE_DIR environment variable to safeguard against global permission blocks.
    """
    executor = AsyncProcessExecutor()
    
    # We patch asyncio.create_subprocess_exec to inspect the injected env
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_p = MagicMock()
        mock_p.stdout = MagicMock()
        mock_p.stderr = MagicMock()
        async def mock_read(*args, **kwargs):
            return b""
        mock_p.stdout.read.side_effect = mock_read
        mock_p.stderr.read.side_effect = mock_read
        
        mock_p.wait = MagicMock()
        async def mock_wait():
            return 0
        mock_p.wait.side_effect = mock_wait
        mock_exec.return_value = mock_p
        
        # Run run_async
        with tempfile.NamedTemporaryFile(delete=False) as log_file:
            log_path = Path(log_file.name)
            try:
                await executor.run_async([sys.executable, "-c", "print('hello')"], log_path)
            finally:
                if log_path.exists():
                    log_path.unlink()
                    
        # Verify that create_subprocess_exec was called and had env with UV_CACHE_DIR
        mock_exec.assert_called_once()
        called_kwargs = mock_exec.call_args[1]
        assert "env" in called_kwargs
        assert "UV_CACHE_DIR" in called_kwargs["env"]
        assert called_kwargs["env"]["UV_CACHE_DIR"].endswith(".tmp/uv-cache")

@pytest.mark.anyio
async def test_async_executor_permission_error_self_healing():
    """
    TDD Phase (RED): Verify that AsyncProcessExecutor gracefully handles and
    heals from PermissionError on log directories without crashing.
    """
    executor = AsyncProcessExecutor()
    
    # We use a forbidden/unwritable log path to trigger PermissionError or OSError
    unwritable_path = Path("/sys/class/unwritable_test_log.json")
    
    # Run run_async on unwritable path
    # Expected to not raise PermissionError, but return non-zero returncode or handle gracefully
    returncode, stdout_len, stderr_len = await executor.run_async(
        [sys.executable, "-c", "print('hello')"],
        unwritable_path
    )
    
    # It must handle gracefully and default to safe fallback (e.g. log to stdout or return safe envelope)
    assert returncode == 0 or returncode == 1
