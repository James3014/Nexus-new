from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Optional

from packaging import version
from packaging.specifiers import SpecifierSet


WhichFn = Callable[[str], str | None]
VersionProbeFn = Callable[[str], str]
ImportProbeFn = Callable[[str, tuple[str, ...]], tuple[bool, str]]
PackageVersionProbeFn = Callable[[str, str], Optional[str]]
AttributeProbeFn = Callable[[str, dict[str, tuple[str, ...]]], tuple[bool, str]]


@dataclass(frozen=True)
class EnvRequirement:
    profile: str
    python_candidates: tuple[str, ...]
    allowed_python: tuple[tuple[int, int], ...] = ()
    required_imports: tuple[str, ...] = ()
    required_attributes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    package_constraints: dict[str, str] = field(default_factory=dict)
    missing_reason: str = "ENV_VERSION_PARITY_MISSING"
    dependency_missing_reason: str = "ENV_DEPENDENCY_MISSING"
    constraint_violation_reason: str = "ENV_CONSTRAINT_VIOLATION"
    override_env_var: str = ""
    auto_heal_enabled: bool = False

    def with_python_candidates(self, candidates: tuple[str, ...]) -> "EnvRequirement":
        return EnvRequirement(
            profile=self.profile,
            python_candidates=candidates,
            allowed_python=self.allowed_python,
            required_imports=self.required_imports,
            required_attributes=self.required_attributes,
            package_constraints=self.package_constraints,
            missing_reason=self.missing_reason,
            dependency_missing_reason=self.dependency_missing_reason,
            constraint_violation_reason=self.constraint_violation_reason,
            override_env_var=self.override_env_var,
            auto_heal_enabled=self.auto_heal_enabled,
        )


@dataclass(frozen=True)
class EnvResolution:
    profile: str
    ready: bool
    reason: str
    python_executable: str = ""
    probes: tuple[dict[str, str], ...] = ()

    def to_receipt(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "ready": self.ready,
            "reason": self.reason,
            "python_executable": self.python_executable,
            "probes": list(self.probes),
        }


ENV_REQUIREMENTS: dict[str, EnvRequirement] = {
    "python-default": EnvRequirement(
        profile="python-default",
        python_candidates=("python3",),
        missing_reason="PYTHON_DEFAULT_MISSING",
    ),
    "astropy-legacy": EnvRequirement(
        profile="astropy-legacy",
        python_candidates=(
            ".venv_astropy_39/bin/python",
            ".venv_astropy/bin/python",
            "python3.9",
            "python3.10",
        ),
        allowed_python=((3, 9), (3, 10)),
        required_imports=("numpy", "extension_helpers", "setuptools"),
        required_attributes={"importlib.metadata": ("packages_distributions",)},
        package_constraints={"numpy": "<2.0.0"},
        missing_reason="ASTROPY_VERSION_PARITY_MISSING",
        dependency_missing_reason="ASTROPY_DEPENDENCY_MISSING",
        constraint_violation_reason="ASTROPY_NUMPY_VERSION_VIOLATION",
        override_env_var="NEXUS_ASTROPY_LEGACY_PYTHON",
        auto_heal_enabled=True,
    ),
    "astropy-311": EnvRequirement(
        profile="astropy-311",
        python_candidates=(
            ".venv_astropy_311/bin/python",
            "python3.11",
        ),
        allowed_python=((3, 11),),
        required_imports=("numpy", "extension_helpers", "setuptools", "typing.Self"),
        package_constraints={"numpy": "<2.0.0"},
        missing_reason="ASTROPY_311_VERSION_PARITY_MISSING",
        dependency_missing_reason="ASTROPY_311_DEPENDENCY_MISSING",
        constraint_violation_reason="ASTROPY_311_NUMPY_VERSION_VIOLATION",
        override_env_var="NEXUS_ASTROPY_311_PYTHON",
        auto_heal_enabled=False,
    ),
    "astropy-311-modern": EnvRequirement(
        profile="astropy-311-modern",
        python_candidates=(
            ".venv_astropy_311/bin/python",
            "python3.11",
        ),
        allowed_python=((3, 11),),
        required_imports=("numpy", "extension_helpers", "setuptools", "typing.Self"),
        package_constraints={},
        missing_reason="ASTROPY_311_MODERN_VERSION_PARITY_MISSING",
        dependency_missing_reason="ASTROPY_311_MODERN_DEPENDENCY_MISSING",
        constraint_violation_reason="ASTROPY_311_MODERN_NUMPY_VERSION_VIOLATION",
        override_env_var="NEXUS_ASTROPY_311_MODERN_PYTHON",
        auto_heal_enabled=True,
    ),
}


def requirement_for_profile(profile: str) -> EnvRequirement:
    try:
        return ENV_REQUIREMENTS[profile]
    except KeyError as exc:
        raise ValueError(f"Unknown local-heal env profile: {profile}") from exc


def _parse_python_minor(version_text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\.(\d+)", version_text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _probe_python_version(executable: str) -> str:
    result = subprocess.run(
        [
            executable,
            "-c",
            "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return (result.stdout + result.stderr).strip()
    return result.stdout.strip()


def _probe_python_imports(executable: str, imports: tuple[str, ...]) -> tuple[bool, str]:
    if not imports:
        return True, ""
    
    missing = []
    for mod_name in imports:
        # 特別處理 typing.Self 這類需要真實 import 才能確認是否支援的語法
        script = f"try:\n    import {mod_name}\nexcept ImportError:\n    import sys; sys.exit(1)"
        if "." in mod_name:
            # 支援 "typing.Self" 這種 from x import y 的語意檢測
            pkg, name = mod_name.rsplit(".", 1)
            script = f"try:\n    from {pkg} import {name}\nexcept ImportError:\n    import sys; sys.exit(1)"
            
        result = subprocess.run(
            [executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            missing.append(mod_name)
            
    if missing:
        return False, "missing:" + ",".join(missing)
    return True, "ok"


def _probe_package_version(executable: str, package_name: str) -> Optional[str]:
    script = (
        "import importlib.metadata, sys\n"
        "try:\n"
        f"    print(importlib.metadata.version('{package_name}'))\n"
        "except importlib.metadata.PackageNotFoundError:\n"
        "    sys.exit(1)\n"
    )
    result = subprocess.run(
        [executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _probe_python_attributes(
    executable: str,
    required_attributes: dict[str, tuple[str, ...]],
) -> tuple[bool, str]:
    if not required_attributes:
        return True, "ok"
    script = (
        "import importlib, sys\n"
        f"required = {required_attributes!r}\n"
        "missing = []\n"
        "for module_name, attrs in required.items():\n"
        "    try:\n"
        "        module = importlib.import_module(module_name)\n"
        "    except Exception:\n"
        "        missing.append(module_name)\n"
        "        continue\n"
        "    for attr in attrs:\n"
        "        if not hasattr(module, attr):\n"
        "            missing.append(f'{module_name}.{attr}')\n"
        "print('missing_attr:' + ','.join(missing) if missing else 'ok')\n"
        "sys.exit(1 if missing else 0)\n"
    )
    result = subprocess.run(
        [executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=5,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def _candidate_version(candidate: str) -> str:
    return candidate.removeprefix("python")


def _uv_python_find(candidate: str) -> str | None:
    version = _candidate_version(candidate)
    if not version:
        return None
    try:
        result = subprocess.run(
            ["uv", "python", "find", version],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


class EnvResolver:
    def __init__(
        self,
        *,
        which: WhichFn | None = None,
        version_probe: VersionProbeFn | None = None,
        import_probe: ImportProbeFn | None = None,
        package_version_probe: PackageVersionProbeFn | None = None,
        attribute_probe: AttributeProbeFn | None = None,
        uv_find: WhichFn | None = None,
    ):
        self.which = which or shutil.which
        self.version_probe = version_probe or _probe_python_version
        self.import_probe = import_probe or _probe_python_imports
        self.package_version_probe = package_version_probe or _probe_package_version
        self.attribute_probe = attribute_probe or _probe_python_attributes
        self.uv_find = uv_find or _uv_python_find

    def resolve(self, requirement: EnvRequirement) -> EnvResolution:
        probes: list[dict[str, str]] = []
        candidates = list(requirement.python_candidates)
        if requirement.override_env_var and os.environ.get(requirement.override_env_var):
            candidates.insert(0, requirement.override_env_var)

        for candidate in candidates:
            if candidate == requirement.override_env_var:
                path = os.environ.get(candidate, "")
            else:
                path = self.which(candidate) or self.uv_find(candidate)
            if not path:
                probes.append({"candidate": candidate, "path": "", "version": "", "status": "missing"})
                continue

            version_text = self.version_probe(path)
            minor = _parse_python_minor(version_text)
            if requirement.allowed_python and minor not in requirement.allowed_python:
                probes.append(
                    {
                        "candidate": candidate,
                        "path": path,
                        "version": version_text,
                        "status": "unsupported_version",
                    }
                )
                continue

            imports_ready, import_status = self.import_probe(path, requirement.required_imports)
            if not imports_ready:
                probes.append(
                    {
                        "candidate": candidate,
                        "path": path,
                        "version": version_text,
                        "status": "missing_imports",
                        "import_status": import_status,
                    }
                )
                continue

            attributes_ready, attribute_status = self.attribute_probe(path, requirement.required_attributes)
            if not attributes_ready:
                probes.append(
                    {
                        "candidate": candidate,
                        "path": path,
                        "version": version_text,
                        "status": "missing_imports",
                        "import_status": attribute_status,
                    }
                )
                continue

            # 檢查套件版本約束
            constraints_ok = True
            constraint_failures = []
            for pkg, spec in requirement.package_constraints.items():
                current_version = self.package_version_probe(path, pkg)
                if not current_version:
                    constraints_ok = False
                    constraint_failures.append(f"missing:{pkg}")
                    continue
                
                try:
                    if not SpecifierSet(spec).contains(current_version):
                        constraints_ok = False
                        constraint_failures.append(f"{pkg}:{current_version} not in {spec}")
                except Exception:
                    constraints_ok = False
                    constraint_failures.append(f"{pkg}:invalid_spec:{spec}")

            if not constraints_ok:
                probes.append(
                    {
                        "candidate": candidate,
                        "path": path,
                        "version": version_text,
                        "status": "constraint_violation",
                        "violations": ",".join(constraint_failures),
                    }
                )
                continue

            probes.append(
                {
                    "candidate": candidate,
                    "path": path,
                    "version": version_text,
                    "status": "accepted",
                    "import_status": import_status or "ok",
                }
            )
            return EnvResolution(
                profile=requirement.profile,
                ready=True,
                reason="READY",
                python_executable=path,
                probes=tuple(probes),
            )

        # 決定最能反映環境現狀的失敗原因 (優先級排序)
        if not probes:
            return EnvResolution(
                profile=requirement.profile,
                ready=False,
                reason=requirement.missing_reason,
                probes=tuple(probes),
            )

        # 搜尋優先級最高的失敗狀態
        status_priority = ["constraint_violation", "missing_imports", "unsupported_version", "missing"]
        best_status = "missing"
        
        for p_status in status_priority:
            if any(p["status"] == p_status for p in probes):
                best_status = p_status
                break

        if best_status == "constraint_violation":
            last_reason = requirement.constraint_violation_reason
        elif best_status == "missing_imports":
            last_reason = requirement.dependency_missing_reason
        else:
            last_reason = requirement.missing_reason

        return EnvResolution(
            profile=requirement.profile,
            ready=False,
            reason=last_reason,
            probes=tuple(probes),
        )


def apply_env_resolution(ctx: Any, resolution: EnvResolution) -> bool:
    ctx.env_resolution = resolution.to_receipt()
    if resolution.ready:
        # 轉換為絕對路徑，防止 TemporaryDirectory 導致相對路徑失效
        ctx.python_executable = os.path.abspath(resolution.python_executable)
        return True

    ctx.runner_completed = True
    ctx.solve_eligible = False
    ctx.reproduced = False
    ctx.failure_reason = resolution.reason
    return False
