"""Local inference runtime adapters for M5.

Supports:
- llama.cpp CLI runner (Metal accelerated on Apple Silicon)
- MLX inference runner
- Mock/test runner for deterministic verification and negative matrices

Preserves the core invariant:
- Requested runtime != observed runtime
- Requested model != observed model
- Fail-closed on missing/malformed/timed-out execution
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .contracts import (
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_TIMEOUT,
)
from .host_inventory import inspect_models


@dataclass(frozen=True)
class RuntimeExecutionResult:
    """Observed result from a local model invocation."""

    requested_runtime: str
    observed_runtime: str
    requested_model: str
    observed_model: str
    output_text: str
    stdout: str
    stderr: str
    exit_code: Optional[int]
    elapsed_ms: int
    rss_bytes: int
    physical_model_path: str = ""
    physical_model_size_bytes: int = 0
    runtime_command: tuple[str, ...] = field(default_factory=tuple)
    runtime_version: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    context_limit: int = 0
    timed_out: bool = False
    cancelled: bool = False
    error: Optional[str] = None
    escalation_reason: Optional[str] = None


class LocalInferenceRuntime(ABC):
    """Abstract interface for local inference engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if runtime executable / environment is physically available."""

    @abstractmethod
    def run_inference(
        self,
        *,
        model_id: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        context_limit: Optional[int] = None,
    ) -> RuntimeExecutionResult:
        """Execute inference against a local model."""


class LlamaCppRuntime(LocalInferenceRuntime):
    """llama.cpp CLI runner on M5."""

    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = (
            executable_path or shutil.which("llama-cli") or "/opt/homebrew/bin/llama-cli"
        )

    def is_available(self) -> bool:
        """Check if llama-cli executable exists and is executable."""
        return bool(
            self.executable_path
            and os.path.isfile(self.executable_path)
            and os.access(self.executable_path, os.X_OK)
        )

    def _get_version(self) -> str:
        try:
            res = subprocess.run(
                [self.executable_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            out = res.stdout.strip() or res.stderr.strip()
            return out.splitlines()[0] if out else "unknown"
        except Exception:
            return "unknown"

    def run_inference(
        self,
        *,
        model_id: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        context_limit: Optional[int] = None,
    ) -> RuntimeExecutionResult:
        start_time = time.monotonic()
        observed_runtime = "llama.cpp"

        if not self.is_available():
            return RuntimeExecutionResult(
                requested_runtime="llama.cpp",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model="UNKNOWN",
                output_text="",
                stdout="",
                stderr="llama-cli executable not found or not executable",
                exit_code=-1,
                elapsed_ms=0,
                rss_bytes=0,
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                error="Runtime binary unavailable",
            )

        models = inspect_models()
        if model_id not in models or not Path(models[model_id].file_path).is_file():
            return RuntimeExecutionResult(
                requested_runtime="llama.cpp",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model="UNKNOWN",
                output_text="",
                stdout="",
                stderr=f"Model {model_id} file not found on disk",
                exit_code=-1,
                elapsed_ms=0,
                rss_bytes=0,
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                error=f"Model file missing for {model_id}",
            )

        item = models[model_id]
        physical_file_name = Path(item.file_path).name
        observed_model = f"{physical_file_name}:{item.size_bytes}B"
        ctx = context_limit or item.context_limit or 4096
        version = self._get_version()

        cmd = [
            self.executable_path,
            "-m",
            item.file_path,
            "-p",
            prompt,
            "-n",
            str(max_tokens),
            "-c",
            str(ctx),
            "--temp",
            str(temperature),
            "-ngl",
            "99",
            "--no-warmup",
            "--simple-io",
            "--single-turn",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            stdout = proc.stdout
            stderr = proc.stderr

            if proc.returncode != 0:
                return RuntimeExecutionResult(
                    requested_runtime="llama.cpp",
                    observed_runtime=observed_runtime,
                    requested_model=model_id,
                    observed_model=observed_model,
                    physical_model_path=item.file_path,
                    physical_model_size_bytes=item.size_bytes,
                    runtime_command=tuple(cmd),
                    runtime_version=version,
                    output_text="",
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode,
                    elapsed_ms=elapsed_ms,
                    rss_bytes=0,
                    error=f"llama-cli process failed with returncode {proc.returncode}",
                )

            return RuntimeExecutionResult(
                requested_runtime="llama.cpp",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model=observed_model,
                physical_model_path=item.file_path,
                physical_model_size_bytes=item.size_bytes,
                runtime_command=tuple(cmd),
                runtime_version=version,
                output_text=stdout.strip(),
                stdout=stdout,
                stderr=stderr,
                exit_code=0,
                elapsed_ms=elapsed_ms,
                rss_bytes=0,
                context_limit=ctx,
            )

        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return RuntimeExecutionResult(
                requested_runtime="llama.cpp",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model=observed_model,
                physical_model_path=item.file_path,
                physical_model_size_bytes=item.size_bytes,
                runtime_command=tuple(cmd),
                runtime_version=version,
                output_text="",
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr or "" if isinstance(exc.stderr, str) else "",
                exit_code=None,
                elapsed_ms=elapsed_ms,
                rss_bytes=0,
                timed_out=True,
                escalation_reason=LOCAL_TIMEOUT,
                error=f"Execution timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return RuntimeExecutionResult(
                requested_runtime="llama.cpp",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model=observed_model,
                physical_model_path=item.file_path,
                physical_model_size_bytes=item.size_bytes,
                runtime_command=tuple(cmd),
                runtime_version=version,
                output_text="",
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                elapsed_ms=elapsed_ms,
                rss_bytes=0,
                error=str(exc),
            )


class MlxRuntime(LocalInferenceRuntime):
    """MLX runtime using Apple Silicon MLX framework."""

    def __init__(self, python_path: Optional[str] = None):
        self.python_path = python_path or "/Users/james/.omlx/bin/omlx-cluster-python"

    def is_available(self) -> bool:
        """Check if MLX python executable exists and is executable."""
        return bool(
            self.python_path
            and os.path.isfile(self.python_path)
            and os.access(self.python_path, os.X_OK)
        )

    def run_inference(
        self,
        *,
        model_id: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        context_limit: Optional[int] = None,
    ) -> RuntimeExecutionResult:
        start_time = time.monotonic()
        observed_runtime = "mlx"

        if not self.is_available():
            return RuntimeExecutionResult(
                requested_runtime="mlx",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model="UNKNOWN",
                output_text="",
                stdout="",
                stderr="MLX python executable not found",
                exit_code=-1,
                elapsed_ms=0,
                rss_bytes=0,
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                error="MLX environment unavailable",
            )

        # MLX verification: verify environment is present and importable,
        # but truthfully report that model inference is not bound (no physical directory weights bound).
        code = """
import sys
try:
    import mlx.core as mx
    import mlx_lm
    print('MLX_READY')
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
"""
        try:
            proc = subprocess.run(
                [self.python_path, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            if proc.returncode != 0:
                return RuntimeExecutionResult(
                    requested_runtime="mlx",
                    observed_runtime=observed_runtime,
                    requested_model=model_id,
                    observed_model="UNKNOWN",
                    output_text="",
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    exit_code=proc.returncode,
                    elapsed_ms=elapsed_ms,
                    rss_bytes=0,
                    escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                    error=proc.stderr or "MLX execution failed",
                )
            # MLX runtime is available on host, but physical model inference is not bound
            return RuntimeExecutionResult(
                requested_runtime="mlx",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model="UNKNOWN",
                output_text="",
                stdout=proc.stdout,
                stderr="MLX runtime is installed and import-ready, but model inference is not bound (no physical MLX model weights bound on host)",
                exit_code=0,
                elapsed_ms=elapsed_ms,
                rss_bytes=0,
                escalation_reason=LOCAL_RUNTIME_UNAVAILABLE,
                error="MLX model inference is not bound on this host",
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return RuntimeExecutionResult(
                requested_runtime="mlx",
                observed_runtime=observed_runtime,
                requested_model=model_id,
                observed_model="UNKNOWN",
                output_text="",
                stdout="",
                stderr="MLX process timed out",
                exit_code=None,
                elapsed_ms=elapsed_ms,
                rss_bytes=0,
                timed_out=True,
                escalation_reason=LOCAL_TIMEOUT,
                error="Timed out",
            )


class MockLocalRuntime(LocalInferenceRuntime):
    """Deterministic mock runtime for fast unit tests and negative matrices."""

    def __init__(
        self,
        *,
        output_text: str = "Mock local assist findings",
        observed_runtime: str = "mock-runtime-v1",
        observed_model: Optional[str] = None,
        simulate_timeout: bool = False,
        simulate_error: Optional[str] = None,
        simulate_cancel: bool = False,
        simulate_exit_code: int = 0,
        simulate_memory_bytes: int = 1024 * 1024 * 100,
        simulate_swap_bytes: int = 0,
        simulate_model_mismatch: bool = False,
    ):
        self.output_text = output_text
        self.observed_runtime = observed_runtime
        self._configured_model = observed_model
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.simulate_cancel = simulate_cancel
        self.simulate_exit_code = simulate_exit_code
        self.simulate_memory_bytes = simulate_memory_bytes
        self.simulate_swap_bytes = simulate_swap_bytes
        self.simulate_model_mismatch = simulate_model_mismatch

    def is_available(self) -> bool:
        """Check if runtime executable / environment is physically available."""
        return True

    def run_inference(
        self,
        *,
        model_id: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        context_limit: Optional[int] = None,
    ) -> RuntimeExecutionResult:
        actual_model = self._configured_model or model_id
        if self.simulate_model_mismatch:
            actual_model = "mismatch-model-detected"

        if self.simulate_timeout:
            return RuntimeExecutionResult(
                requested_runtime="mock",
                observed_runtime=self.observed_runtime,
                requested_model=model_id,
                observed_model=actual_model,
                output_text="",
                stdout="",
                stderr="Simulated timeout expired",
                exit_code=None,
                elapsed_ms=int(timeout_seconds * 1000),
                rss_bytes=self.simulate_memory_bytes,
                timed_out=True,
                escalation_reason=LOCAL_TIMEOUT,
                error="Operation timed out",
            )

        if self.simulate_cancel:
            return RuntimeExecutionResult(
                requested_runtime="mock",
                observed_runtime=self.observed_runtime,
                requested_model=model_id,
                observed_model=actual_model,
                output_text="",
                stdout="",
                stderr="Simulated cancellation",
                exit_code=-15,
                elapsed_ms=50,
                rss_bytes=self.simulate_memory_bytes,
                cancelled=True,
                error="Operation cancelled by coordinator",
            )

        if self.simulate_error:
            return RuntimeExecutionResult(
                requested_runtime="mock",
                observed_runtime=self.observed_runtime,
                requested_model=model_id,
                observed_model=actual_model,
                output_text="",
                stdout="",
                stderr=self.simulate_error,
                exit_code=self.simulate_exit_code or 1,
                elapsed_ms=50,
                rss_bytes=self.simulate_memory_bytes,
                error=self.simulate_error,
            )

        return RuntimeExecutionResult(
            requested_runtime="mock",
            observed_runtime=self.observed_runtime,
            requested_model=model_id,
            observed_model=actual_model,
            output_text=self.output_text,
            stdout=self.output_text,
            stderr="",
            exit_code=self.simulate_exit_code,
            elapsed_ms=45,
            rss_bytes=self.simulate_memory_bytes,
            input_tokens=len(prompt.split()),
            output_tokens=len(self.output_text.split()),
            context_limit=context_limit or 4096,
        )
