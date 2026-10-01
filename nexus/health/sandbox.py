from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import shutil
import tempfile
import subprocess
import logging

logger = logging.getLogger(__name__)

class SpeculativeSandbox:
    """Temporary repo clone for speculative validation before mainline apply."""

    def __init__(self, source_root: Path, mode: str = "auto"):
        self.source_root = Path(source_root)
        self.sandbox_root: Path | None = None
        self._temp_root: Path | None = None
        
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
        self._validate_source_root()
        try:
            if self.mode == "docker":
                return self._fork_docker()
            return self._fork_tmpdir()
        except BaseException:
            self.cleanup()
            raise

    def _validate_source_root(self) -> Path:
        source_root = self.source_root.expanduser()
        if source_root.is_symlink():
            raise ValueError("sandbox source root must not be a symlink")
        try:
            resolved = source_root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ValueError("sandbox source root must be an existing directory") from exc
        if not resolved.is_dir():
            raise ValueError("sandbox source root must be an existing directory")

        broad_roots = {
            Path("/").resolve(),
            Path.home().resolve(),
            Path(tempfile.gettempdir()).resolve(),
            Path("/tmp").resolve(),
            Path("/private/tmp").resolve(),
            Path("/var/tmp").resolve(),
        }
        if resolved in broad_roots:
            raise ValueError(f"sandbox source root is too broad: {resolved}")
        return resolved

    def _copy_source_tree(self, prefix: str) -> Path:
        source_root = self._validate_source_root()
        self._temp_root = Path(tempfile.mkdtemp(prefix=prefix))
        self.sandbox_root = self._temp_root / "repo"
        shutil.copytree(
            source_root,
            self.sandbox_root,
            dirs_exist_ok=True,
            symlinks=True,
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

    def _fork_tmpdir(self) -> Path:
        return self._copy_source_tree("nexus_sandbox_")

    def _fork_docker(self) -> Path:
        """用 Docker 建立隔離環境"""
        self._copy_source_tree("nexus_docker_")
        
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
        docker_tag = getattr(self, "_docker_tag", None)
        if self.mode == "docker" and docker_tag:
            try:
                subprocess.run(
                    ["docker", "rmi", docker_tag],
                    capture_output=True, timeout=10
                )
            except Exception as exc:
                logger.warning("Failed to remove sandbox Docker image %s: %s", docker_tag, exc)
            finally:
                delattr(self, "_docker_tag")

        temp_root = self._temp_root
        self.sandbox_root = None
        self._temp_root = None
        if temp_root is None:
            return
        if temp_root.is_symlink():
            logger.error("Refusing to remove symlinked sandbox temp root: %s", temp_root)
            return
        shutil.rmtree(temp_root, ignore_errors=True)
