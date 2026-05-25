from __future__ import annotations

import sys
from pathlib import Path
import pytest

from scripts.engine.commands.sandbox_actions import run_sandbox_task
from nexus.engine.sandbox_runner import SandboxRunner


def test_sandbox_runner_builds_elastic_profile_syntax():
    # 測試 build_elastic_profile 是否存在且拼接語法符合 macOS 規範
    runner = SandboxRunner(Path("."))
    if not hasattr(runner, "build_elastic_profile"):
        pytest.fail("SandboxRunner does not expose build_elastic_profile (TDD RED)")

    profile = runner.build_elastic_profile(
        read_literals=["/tmp/allowed_read"],
        write_literals=["/tmp/allowed_write"]
    )

    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "(deny network-outbound)" in profile
    assert '(allow file-read* (literal "/tmp/allowed_read"))' in profile
    assert '(allow file-write* (literal "/tmp/allowed_write"))' in profile


def test_sandbox_runner_elastic_profile_enforces_kernel_isolation(tmp_path: Path):
    if sys.platform != "darwin":
        pytest.skip("Elastic sandbox-exec kernel barrier is only supported on macOS (darwin).")

    runner = SandboxRunner(tmp_path)
    if not hasattr(runner, "build_elastic_profile"):
        pytest.fail("SandboxRunner does not expose build_elastic_profile (TDD RED)")

    # 建立臨時讀寫路徑
    allowed_dir = tmp_path / "allowed"
    forbidden_dir = tmp_path / "forbidden"
    allowed_dir.mkdir()
    forbidden_dir.mkdir()

    # 1. 構建彈性 Profile：僅允許讀寫 allowed_dir，並阻斷網路
    # 由於 sandbox 在 workspace 中執行，我們需要允許 sandbox 系統目錄 (如 /usr/bin/touch, /bin/sh, tmp_path 等讀取)
    # macOS sandbox-exec (allow default) 已經允許了大部分，所以我們用它來做彈性白名單
    # 為了測試，我們手動deny寫入 forbidden_dir。
    # 具體做法：build_elastic_profile 回傳：
    # "(version 1) (allow default) (deny file-write* (subpath \"{forbidden_dir}\"))"
    # 這是一種非常優雅的彈性 profile 設計！
    profile = (
        f'(version 1)\n'
        f'(allow default)\n'
        f'(deny file-write* (subpath "{str(forbidden_dir)}"))\n'
        f'(deny network-outbound)\n'
    )

    # 2. 測試在 sandbox 內寫入 allowed_dir 應成功
    ok_file = allowed_dir / "ok.txt"
    result_ok = runner.run_task(
        "write allowed path",
        command=["touch", str(ok_file)],
        timeout_sec=5,
        elastic_profile=profile
    )
    assert result_ok["success"] is True
    assert ok_file.exists()

    # 3. 測試在 sandbox 內寫入 forbidden_dir 應被 OS 阻斷
    bad_file = forbidden_dir / "bad.txt"
    result_bad = runner.run_task(
        "write forbidden path",
        command=["touch", str(bad_file)],
        timeout_sec=5,
        elastic_profile=profile
    )
    # 被 macOS sandbox-exec 阻斷會導致 exit_code 非 0 (Touch 失敗)
    assert result_bad["success"] is False
    assert not bad_file.exists()
    assert result_bad["exit_code"] != 0
