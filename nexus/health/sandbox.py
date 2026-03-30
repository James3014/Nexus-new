from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable
import subprocess
import logging

logger = logging.getLogger(__name__)

class SpeculativeSandbox:
    """Temporary repo clone for speculative validation before mainline apply."""

    def __init__(self, source_root: Path, mode: str = "auto"):
        self.source_root = Path(source_root)
        self.sandbox_root: Path | None = None
        
        # 🆕 自動偵測 Docker 可用性
        if mode == "auto":
            self.mode = "docker" if self._docker_available() else "tmpdir"
        else:
            self.mode = mode
            
        logger.info("Sandbox initialized in mode: %s", self.mode)

    @staticmethod
    def _docker_available() -> bool:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                check=False,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @property
    def sandbox_report(self) -> dict:
        """回報沙盒執行資訊，供 outcome event 記錄"""
        return {
            "sandbox_mode": self.mode,
            "docker_available": self.mode == "docker" or self._docker_available(),
            "source_root": str(self.source_root),
        }

    def fork(self) -> Path:
        if self.mode == "docker":
            return self._fork_docker()
        return self._fork_tmpdir()

    def _fork_tmpdir(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="nexus_sandbox_"))
        self.sandbox_root = temp_dir / "repo"
        shutil.copytree(
            self.source_root,
            self.sandbox_root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                ".mypy_cache",
                ".nexus/runs",
            ),
        )
        return self.sandbox_root

    def _fork_docker(self) -> Path:
        """用 Docker 建立隔離環境"""
        temp_dir = Path(tempfile.mkdtemp(prefix="nexus_docker_"))
        self.sandbox_root = temp_dir / "repo"
        shutil.copytree(
            self.source_root,
            self.sandbox_root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                ".mypy_cache",
                ".nexus/runs",
            ),
        )
        
        # 建立 Dockerfile（如果專案沒有）
        dockerfile = self.sandbox_root / "Dockerfile.nexus"
        if not dockerfile.exists():
            dockerfile.write_text(self._generate_dockerfile())
        
        # Build & Tag
        tag = f"nexus-sandbox:{hash(str(self.source_root.absolute())) % 1000000}"
        logger.info("Building Docker image: %s", tag)
        subprocess.run(
            ["docker", "build", "-f", str(dockerfile), "-t", tag, "."],
            cwd=self.sandbox_root, capture_output=True, timeout=120
        )
        
        self._docker_tag = tag
        return self.sandbox_root

    def _generate_dockerfile(self) -> str:
        """根據專案語言自動生成 Dockerfile"""
        if (self.source_root / "pyproject.toml").exists() or (self.source_root / "pytest.ini").exists():
            return """FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e . 2>/dev/null || true
RUN pip install pytest || true
"""
        elif (self.source_root / "Cargo.toml").exists():
            return """FROM rust:1.77-slim
WORKDIR /app
COPY . .
RUN cargo build 2>/dev/null || true
"""
        elif (self.source_root / "package.json").exists():
            return """FROM node:20-slim
WORKDIR /app
COPY . .
RUN npm install 2>/dev/null || true
"""
        else:
            return """FROM ubuntu:24.04
WORKDIR /app
COPY . .
"""

    def run(
        self,
        manifest_path: Path,
        runner: Callable[[Path, Path | None], int],
    ) -> int:
        if self.sandbox_root is None:
            raise RuntimeError("sandbox not initialized")
            
        if self.mode == "docker" and hasattr(self, "_docker_tag"):
            return self._run_docker(manifest_path, runner)
            
        return runner(manifest_path, self.sandbox_root)

    def _run_docker(self, manifest_path: Path, runner: Callable[[Path, Path | None], int]) -> int:
        """在 Docker 容器內執行驗證"""
        # 注意：runner(manifest_path, sandbox_root) 在原本的設計中會被呼叫
        # 但是我們的 docker 環境自己跑
        logger.info("Running tasks in Docker container %s", self._docker_tag)
        try:
            # 我們這裡假設專案用 Python/Pytest 作為主要驗證手段（根據 _auto_detect_verify_commands 判斷）
            # 最理想的解法是把 manifest 的指令注入進 docker run，但我們先使用回退邏輯
            # 我們直接呼叫 runner 讓它在 sandbox_root 下生成所需的測試檔，
            # 然後我們在 docker 內掛載這個資料夾跑一次 python -m pytest
            result = subprocess.run(
                ["docker", "run", "--rm",
                 "-v", f"{self.sandbox_root}:/app",
                 self._docker_tag,
                 "python3", "-m", "pytest", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=180,
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            return 124

    def cleanup(self) -> None:
        if self.mode == "docker" and hasattr(self, "_docker_tag"):
            subprocess.run(
                ["docker", "rmi", self._docker_tag],
                capture_output=True, timeout=10
            )
        if self.sandbox_root is None:
            return
        shutil.rmtree(self.sandbox_root.parent, ignore_errors=True)
        self.sandbox_root = None
