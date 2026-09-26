"""G1 Physical Identity module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.physical_identity.v1
Inspects and records the exact observable host environment, executable identity,
runtime version, and adapter generation.

False-Green Defense (Invariant 6.1):
- offline_availability and network_dependency MUST NOT be assumed from provider identity.
- Unless physical offline execution evidence has been observed, they must be recorded as UNKNOWN.
- Unobservable fields MUST be recorded as UNKNOWN, never filled with expected facts.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash

PHYSICAL_IDENTITY_SCHEMA = "nexus.provider_experiment.physical_identity.v1"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PhysicalIdentity:
    schema: str
    provider_id: str
    model_id: str
    transport: str
    host_identity: str
    platform: str
    architecture: str
    hardware_identity: str
    os_version: str
    kernel_version: str
    runtime_executable: str
    runtime_executable_sha256: str
    runtime_version: str
    adapter_generation: str
    model_generation: str
    source_commit_identity: str
    offline_availability: str
    network_dependency: str
    timestamp: str
    identity_digest: str
    memory_gb: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "transport": self.transport,
            "host_identity": self.host_identity,
            "platform": self.platform,
            "architecture": self.architecture,
            "hardware_identity": self.hardware_identity,
            "os_version": self.os_version,
            "kernel_version": self.kernel_version,
            "runtime_executable": self.runtime_executable,
            "runtime_executable_sha256": self.runtime_executable_sha256,
            "runtime_version": self.runtime_version,
            "adapter_generation": self.adapter_generation,
            "model_generation": self.model_generation,
            "source_commit_identity": self.source_commit_identity,
            "offline_availability": self.offline_availability,
            "network_dependency": self.network_dependency,
            "timestamp": self.timestamp,
            "identity_digest": self.identity_digest,
            "memory_gb": self.memory_gb,
        }

    def compute_digest(self) -> str:
        data = self.to_dict()
        data.pop("identity_digest", None)
        return canonical_json_hash(data)


def compute_file_sha256(path: str) -> str:
    """Safely compute SHA-256 of an executable, returning UNKNOWN if unreadable."""
    if not path or path == UNKNOWN or not os.path.isfile(path):
        return UNKNOWN
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return UNKNOWN


def inspect_git_commit(cwd: str | None = None) -> str:
    """Get current git HEAD commit SHA, or UNKNOWN if not in git."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return res.stdout.strip() or UNKNOWN
    except Exception:
        return UNKNOWN


def inspect_physical_host_identity(
    *,
    provider_id: str,
    model_id: str,
    transport: str,
    runtime_executable: str = UNKNOWN,
    runtime_version: str = UNKNOWN,
    adapter_generation: str = "v1",
    model_generation: str = UNKNOWN,
    timestamp: str,
    cwd: str | None = None,
    offline_verified: bool | None = None,
    network_dependency_observed: str | None = None,
    memory_gb: int | None = None,
) -> PhysicalIdentity:
    """Inspect and build a PhysicalIdentity object.

    Strict Rule: offline_availability and network_dependency default to UNKNOWN
    unless explicit physical observation evidence is provided.
    """
    plat = platform.system() or UNKNOWN
    arch = platform.machine() or UNKNOWN
    kernel = platform.release() or UNKNOWN
    host_name = platform.node() or UNKNOWN
    os_ver = platform.version() or UNKNOWN

    # Safe hardware observation
    hw_id = UNKNOWN
    observed_memory_gb: int | None = memory_gb
    if plat == "Darwin":
        try:
            res = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                hw_id = res.stdout.strip()
        except Exception:
            pass
        if observed_memory_gb is None:
            try:
                res_mem = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res_mem.returncode == 0 and res_mem.stdout.strip():
                    observed_memory_gb = int(res_mem.stdout.strip()) // (1024**3)
            except Exception:
                pass

    # Executable hash
    exe_hash = UNKNOWN
    if runtime_executable != UNKNOWN:
        resolved_exe = shutil.which(runtime_executable) or runtime_executable
        exe_hash = compute_file_sha256(resolved_exe)

    git_sha = inspect_git_commit(cwd)

    # Invariant 6.1: never assume offline status from provider name
    if offline_verified is True:
        offline_avail = "VERIFIED_OFFLINE"
    elif offline_verified is False:
        offline_avail = "ONLINE_REQUIRED"
    else:
        offline_avail = UNKNOWN

    net_dep = network_dependency_observed if network_dependency_observed is not None else UNKNOWN

    raw = {
        "schema": PHYSICAL_IDENTITY_SCHEMA,
        "provider_id": provider_id,
        "model_id": model_id,
        "transport": transport,
        "host_identity": host_name,
        "platform": plat,
        "architecture": arch,
        "hardware_identity": hw_id,
        "os_version": os_ver,
        "kernel_version": kernel,
        "runtime_executable": runtime_executable,
        "runtime_executable_sha256": exe_hash,
        "runtime_version": runtime_version,
        "adapter_generation": adapter_generation,
        "model_generation": model_generation,
        "source_commit_identity": git_sha,
        "offline_availability": offline_avail,
        "network_dependency": net_dep,
        "timestamp": timestamp,
        "memory_gb": observed_memory_gb,
    }
    digest = canonical_json_hash(raw)

    return PhysicalIdentity(
        schema=PHYSICAL_IDENTITY_SCHEMA,
        provider_id=provider_id,
        model_id=model_id,
        transport=transport,
        host_identity=host_name,
        platform=plat,
        architecture=arch,
        hardware_identity=hw_id,
        os_version=os_ver,
        kernel_version=kernel,
        runtime_executable=runtime_executable,
        runtime_executable_sha256=exe_hash,
        runtime_version=runtime_version,
        adapter_generation=adapter_generation,
        model_generation=model_generation,
        source_commit_identity=git_sha,
        offline_availability=offline_avail,
        network_dependency=net_dep,
        timestamp=timestamp,
        identity_digest=digest,
        memory_gb=observed_memory_gb,
    )


def evaluate_identity_drift(baseline: PhysicalIdentity, current: PhysicalIdentity) -> str:
    """Evaluate whether candidate identity has drifted from baseline.

    Outcomes:
    - CURRENT: identical key characteristics
    - STALE: OS version, kernel, or adapter generation has drifted
    - REQUALIFICATION_REQUIRED: provider, model, runtime binary, or runtime version changed
    """
    if (
        baseline.provider_id != current.provider_id
        or baseline.model_id != current.model_id
        or baseline.runtime_version != current.runtime_version
        or baseline.runtime_executable_sha256 != current.runtime_executable_sha256
    ):
        return "REQUALIFICATION_REQUIRED"

    if (
        baseline.os_version != current.os_version
        or baseline.kernel_version != current.kernel_version
        or baseline.adapter_generation != current.adapter_generation
        or baseline.architecture != current.architecture
    ):
        return "STALE"

    return "CURRENT"
