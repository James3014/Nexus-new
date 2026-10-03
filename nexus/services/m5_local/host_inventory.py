"""Physical M5 host hardware, runtime, and model inventory inspection.

Provides fresh, un-cached inspection of:
- CPU / unified memory / swap pressure
- Local inference runtimes (llama-cli, llama-server, MLX)
- Local model weights on disk with sizes and supported context
- Classification (AVAILABLE_EXACT, PARTIAL, NOT_INSTALLED, UNKNOWN)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .contracts import (
    HOST_CLASSIFICATION_AVAILABLE_EXACT,
    HOST_CLASSIFICATION_NOT_INSTALLED,
    HOST_CLASSIFICATION_PARTIAL,
    M5_LOCAL_HOST_INVENTORY_SCHEMA,
    QUALIFICATION_NOT_QUALIFIED,
    ROLE_BOUNDED_CODE_PATCH,
    ROLE_READ_ONLY_ASSIST,
    ROLE_REPO_RANKING,
    ROLE_TYPED_DECISION,
    utc_now,
)


@dataclass(frozen=True)
class ModelInventoryItem:
    """An exact model file observed on the local filesystem."""

    model_id: str
    file_path: str
    size_bytes: int
    format: str  # GGUF, MLX, etc.
    context_limit: int
    classification: str  # AVAILABLE_EXACT, PARTIAL, etc.
    runtime_runnable: bool
    role_qualifications: dict[str, str]  # role -> QUALIFICATION_*


@dataclass(frozen=True)
class RuntimeInventoryItem:
    """A local inference executable observed on the system."""

    runtime_id: str
    executable_path: str
    version: str
    classification: str
    is_available: bool


@dataclass(frozen=True)
class HostMemoryInfo:
    """Current host memory and swap stats."""

    total_ram_bytes: int
    active_pages: int
    inactive_pages: int
    free_pages: int
    swap_total_mb: float
    swap_used_mb: float
    swap_free_mb: float


@dataclass(frozen=True)
class M5HostInventory:
    """Complete host hardware and local inference asset inventory."""

    schema: str = M5_LOCAL_HOST_INVENTORY_SCHEMA
    cpu_brand: str = ""
    memory: Optional[HostMemoryInfo] = None
    runtimes: dict[str, RuntimeInventoryItem] = field(default_factory=dict)
    models: dict[str, ModelInventoryItem] = field(default_factory=dict)
    inspected_at: str = field(default_factory=utc_now)


def _exec_command(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
        out = res.stdout.strip()
        if not out and res.stderr:
            out = res.stderr.strip()
        return out
    except Exception:
        return ""


def get_host_memory_info() -> HostMemoryInfo:
    """Read physical RAM size and current virtual memory / swap stats on Darwin hosts."""
    if sys.platform != "darwin":
        return HostMemoryInfo(
            total_ram_bytes=0,
            active_pages=0,
            inactive_pages=0,
            free_pages=0,
            swap_total_mb=0.0,
            swap_used_mb=0.0,
            swap_free_mb=0.0,
        )

    total_ram = 0
    raw_ram = _exec_command(["sysctl", "-n", "hw.memsize"])
    if raw_ram.isdigit():
        total_ram = int(raw_ram)

    vm_stats = _exec_command(["vm_stat"])
    active_pages = 0
    inactive_pages = 0
    free_pages = 0
    for line in vm_stats.splitlines():
        if "Pages active:" in line:
            active_pages = int(line.split(":")[1].strip().rstrip("."))
        elif "Pages inactive:" in line:
            inactive_pages = int(line.split(":")[1].strip().rstrip("."))
        elif "Pages free:" in line:
            free_pages = int(line.split(":")[1].strip().rstrip("."))

    swap_usage = _exec_command(["sysctl", "-n", "vm.swapusage"])
    swap_total = 0.0
    swap_used = 0.0
    swap_free = 0.0
    # format: total = 6144.00M  used = 5206.06M  free = 937.94M
    for part in swap_usage.split():
        if part.startswith("total="):
            val = part.split("=")[1].rstrip("M")
            try:
                swap_total = float(val)
            except ValueError:
                pass
        elif part.startswith("used="):
            val = part.split("=")[1].rstrip("M")
            try:
                swap_used = float(val)
            except ValueError:
                pass
        elif part.startswith("free="):
            val = part.split("=")[1].rstrip("M")
            try:
                swap_free = float(val)
            except ValueError:
                pass

    return HostMemoryInfo(
        total_ram_bytes=total_ram,
        active_pages=active_pages,
        inactive_pages=inactive_pages,
        free_pages=free_pages,
        swap_total_mb=swap_total,
        swap_used_mb=swap_used,
        swap_free_mb=swap_free,
    )


def inspect_runtimes() -> dict[str, RuntimeInventoryItem]:
    """Inspect local inference runtime binaries."""
    runtimes: dict[str, RuntimeInventoryItem] = {}

    # 1. llama-cli
    llama_cli_path = shutil.which("llama-cli") or "/opt/homebrew/bin/llama-cli"
    if os.path.isfile(llama_cli_path) and os.access(llama_cli_path, os.X_OK):
        ver_output = _exec_command([llama_cli_path, "--version"])
        ver = ver_output.splitlines()[0] if ver_output else "unknown"
        runtimes["llama.cpp"] = RuntimeInventoryItem(
            runtime_id="llama.cpp",
            executable_path=llama_cli_path,
            version=ver,
            classification=HOST_CLASSIFICATION_AVAILABLE_EXACT,
            is_available=True,
        )
    else:
        runtimes["llama.cpp"] = RuntimeInventoryItem(
            runtime_id="llama.cpp",
            executable_path=llama_cli_path,
            version="",
            classification=HOST_CLASSIFICATION_NOT_INSTALLED,
            is_available=False,
        )

    # 2. MLX (via omlx cluster python or global python)
    omlx_py = Path("/Users/james/.omlx/bin/omlx-cluster-python").expanduser()
    if omlx_py.is_file() and os.access(omlx_py, os.X_OK):
        mlx_check = _exec_command([
            str(omlx_py),
            "-c",
            "import mlx.core as mx; import mlx_lm; print(mx.__version__, mlx_lm.__version__)",
        ])
        if mlx_check:
            runtimes["mlx"] = RuntimeInventoryItem(
                runtime_id="mlx",
                executable_path=str(omlx_py),
                version=mlx_check,
                classification=HOST_CLASSIFICATION_AVAILABLE_EXACT,
                is_available=True,
            )
        else:
            runtimes["mlx"] = RuntimeInventoryItem(
                runtime_id="mlx",
                executable_path=str(omlx_py),
                version="",
                classification=HOST_CLASSIFICATION_PARTIAL,
                is_available=False,
            )
    else:
        runtimes["mlx"] = RuntimeInventoryItem(
            runtime_id="mlx",
            executable_path=str(omlx_py),
            version="",
            classification=HOST_CLASSIFICATION_NOT_INSTALLED,
            is_available=False,
        )

    return runtimes


def inspect_models() -> dict[str, ModelInventoryItem]:
    """Inspect physical GGUF and MLX model weights on M5 disk."""
    models: dict[str, ModelInventoryItem] = {}

    known_model_paths = [
        (
            "qwen36-35b-q4",
            "/Users/james/workspace/local-llm/models/official-longhorizon-ab/qwen36-q4/Qwen3.6-35B-A3B-Q4_K_M.gguf",
            32768,
            "GGUF",
        ),
        (
            "occamy-1.0-q4",
            "/Users/james/workspace/local-llm/models/official-longhorizon-ab/occamy-q4/occamy-1.0-Q4_K_M.gguf",
            32768,
            "GGUF",
        ),
        (
            "occamy-1.0-q8",
            "/Users/james/workspace/local-llm/models/official-longhorizon-ab/occamy-q8/occamy-1.0-Q8_0.gguf",
            32768,
            "GGUF",
        ),
        (
            "occamy-1.0-fit-q5",
            "/Users/james/workspace/local-llm/models/occamy/sc117-fit-reference/occamy-1.0-abliterated-FIT-REFERENCE-24G-Q5_K_M.gguf",
            32768,
            "GGUF",
        ),
    ]

    for model_id, raw_path, ctx_limit, fmt in known_model_paths:
        p = Path(raw_path).expanduser()
        if p.is_file():
            size = p.stat().st_size
            # Invariant: Separates execution support (RUNNABLE) from role qualification (QUALIFIED).
            # Model existence or novelty does NOT grant qualification.
            # Without physical Nexus Learning qualification receipts, all roles remain NOT_QUALIFIED.
            models[model_id] = ModelInventoryItem(
                model_id=model_id,
                file_path=str(p),
                size_bytes=size,
                format=fmt,
                context_limit=ctx_limit,
                classification=HOST_CLASSIFICATION_AVAILABLE_EXACT,
                runtime_runnable=True,
                role_qualifications={
                    ROLE_REPO_RANKING: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_TYPED_DECISION: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_READ_ONLY_ASSIST: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_BOUNDED_CODE_PATCH: QUALIFICATION_NOT_QUALIFIED,
                },
            )
        else:
            models[model_id] = ModelInventoryItem(
                model_id=model_id,
                file_path=str(p),
                size_bytes=0,
                format=fmt,
                context_limit=ctx_limit,
                classification=HOST_CLASSIFICATION_NOT_INSTALLED,
                runtime_runnable=False,
                role_qualifications={
                    ROLE_REPO_RANKING: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_TYPED_DECISION: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_READ_ONLY_ASSIST: QUALIFICATION_NOT_QUALIFIED,
                    ROLE_BOUNDED_CODE_PATCH: QUALIFICATION_NOT_QUALIFIED,
                },
            )

    return models


def inspect_m5_host() -> M5HostInventory:
    """Produce fresh physical host inventory for M5."""
    if sys.platform == "darwin":
        cpu_brand = _exec_command(["sysctl", "-n", "machdep.cpu.brand_string"]) or "UNKNOWN"
    else:
        cpu_brand = "UNKNOWN"
    mem_info = get_host_memory_info()
    runtimes = inspect_runtimes()
    models = inspect_models()

    return M5HostInventory(
        cpu_brand=cpu_brand,
        memory=mem_info,
        runtimes=runtimes,
        models=models,
    )


@dataclass(frozen=True)
class ModelIdentityVerificationResult:
    """Result of physical model identity attestation check."""

    is_valid: bool
    status: str  # "MATCH", "MISMATCH", "UNKNOWN"
    reason: Optional[str] = None
    requested_model: str = ""
    observed_model: str = ""
    expected_path: str = ""
    observed_path: str = ""
    expected_size_bytes: int = 0
    observed_size_bytes: int = 0


def verify_model_identity(
    requested_model: str,
    result: Any,
    models: Optional[dict[str, ModelInventoryItem]] = None,
) -> ModelIdentityVerificationResult:
    """Shared physical model identity verifier per Section 4 & 5.

    Verifies the binding:
        requested logical model
                ↓
        fresh physical inventory binding
                ↓
        runtime result physical_model_path
        runtime result physical_model_size_bytes
        runtime result observed_model
                ↓
        MATCH / MISMATCH / UNKNOWN

    Requirements:
    1. requested alias exists in current inspect_models() result (or supplied inventory);
    2. expected model file exists on disk;
    3. res.physical_model_path matches expected physical path;
    4. res.physical_model_size_bytes matches expected physical byte count;
    5. res.observed_model is not UNKNOWN / empty;
    6. observed physical descriptor corresponds to that physical file/size;
    7. successful runtime result is bound to the same execution (requested_model matches).

    Deterministic mock contract (Section 5):
    If the result is a pure mock (no physical path/size specified and runtime is mock),
    the mock contract requested_model == observed_model is verified.
    """
    observed_model = getattr(result, "observed_model", "")
    observed_path = getattr(result, "physical_model_path", "")
    observed_size = getattr(result, "physical_model_size_bytes", 0)
    res_requested = getattr(result, "requested_model", "")
    observed_runtime = getattr(result, "observed_runtime", "")
    req_runtime = getattr(result, "requested_runtime", "")

    # Condition 5: Observed model cannot be UNKNOWN or empty
    if not observed_model or observed_model == "UNKNOWN":
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="UNKNOWN",
            reason=f"Model identity is UNKNOWN for requested model {requested_model!r}",
            requested_model=requested_model,
            observed_model=observed_model or "UNKNOWN",
            observed_path=observed_path,
            observed_size_bytes=observed_size,
        )

    # Condition 7: Runtime result must be bound to the same requested execution
    if res_requested and res_requested != requested_model:
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="MISMATCH",
            reason=f"Runtime result requested model mismatch: expected {requested_model!r}, observed {res_requested!r}",
            requested_model=requested_model,
            observed_model=observed_model,
            observed_path=observed_path,
            observed_size_bytes=observed_size,
        )

    inv = models if models is not None else inspect_models()
    item = inv.get(requested_model)

    # Determine if this is a pure mock contract check
    is_pure_mock = (
        (req_runtime == "mock" or observed_runtime.startswith("mock"))
        and not observed_path
        and observed_size == 0
    )

    if is_pure_mock:
        if observed_model == requested_model:
            return ModelIdentityVerificationResult(
                is_valid=True,
                status="MATCH",
                requested_model=requested_model,
                observed_model=observed_model,
            )
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="MISMATCH",
            reason=f"Mock model identity mismatch: requested {requested_model!r}, observed {observed_model!r}",
            requested_model=requested_model,
            observed_model=observed_model,
        )

    # Physical verification:
    # Condition 1: requested alias exists in current model inventory
    if item is None:
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="UNKNOWN",
            reason=f"Requested model {requested_model!r} not found in model inventory",
            requested_model=requested_model,
            observed_model=observed_model,
            observed_path=observed_path,
            observed_size_bytes=observed_size,
        )

    expected_path = item.file_path
    expected_size = item.size_bytes
    expected_file = Path(expected_path)

    # Condition 2: expected model file exists on disk
    if not expected_file.is_file():
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="UNKNOWN",
            reason=f"Physical model file {expected_path} for {requested_model!r} does not exist on disk",
            requested_model=requested_model,
            observed_model=observed_model,
            expected_path=expected_path,
            observed_path=observed_path,
            expected_size_bytes=expected_size,
            observed_size_bytes=observed_size,
        )

    # Condition 3: res.physical_model_path matches expected physical path
    if observed_path != expected_path:
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="MISMATCH",
            reason=f"Model physical path mismatch: expected {expected_path}, observed {observed_path}",
            requested_model=requested_model,
            observed_model=observed_model,
            expected_path=expected_path,
            observed_path=observed_path,
            expected_size_bytes=expected_size,
            observed_size_bytes=observed_size,
        )

    # Condition 4: res.physical_model_size_bytes matches expected physical byte count
    if observed_size != expected_size:
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="MISMATCH",
            reason=f"Model physical size mismatch: expected {expected_size}B, observed {observed_size}B",
            requested_model=requested_model,
            observed_model=observed_model,
            expected_path=expected_path,
            observed_path=observed_path,
            expected_size_bytes=expected_size,
            observed_size_bytes=observed_size,
        )

    # Condition 6: observed physical descriptor corresponds to that physical file/size
    expected_descriptor = f"{expected_file.name}:{expected_size}B"
    if observed_model != expected_descriptor:
        return ModelIdentityVerificationResult(
            is_valid=False,
            status="MISMATCH",
            reason=f"Observed model descriptor mismatch: expected {expected_descriptor}, observed {observed_model}",
            requested_model=requested_model,
            observed_model=observed_model,
            expected_path=expected_path,
            observed_path=observed_path,
            expected_size_bytes=expected_size,
            observed_size_bytes=observed_size,
        )

    # All 7 conditions verified
    return ModelIdentityVerificationResult(
        is_valid=True,
        status="MATCH",
        requested_model=requested_model,
        observed_model=observed_model,
        expected_path=expected_path,
        observed_path=observed_path,
        expected_size_bytes=expected_size,
        observed_size_bytes=observed_size,
    )
