from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import shutil
import sysconfig
from typing import Any, Callable, Sequence


CommandRunner = Callable[[list[str], Path, int], tuple[int, str]]


@dataclass
class EnvDenoiseResult:
    attempted: bool = False
    succeeded: bool = False
    healed: bool = False
    reason: str = "UNSUPPORTED"
    commands: list[str] = field(default_factory=list)
    output: str = ""
    python_executable: str = "python3"

    def to_receipt(self) -> dict[str, object]:
        return {
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "healed": self.healed,
            "reason": self.reason,
            "commands": self.commands,
            "python_executable": self.python_executable,
            "output_tail": self.output[-1200:] if self.output else "",
        }


def _default_run_command(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    # 強制清理 PYTHONPATH 與 PYTHONHOME，防止跨版本污染
    # 並注入 CFLAGS 繞過現代編譯器的嚴格檢查 (如 macOS clang)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    # 防止 uv 或其他工具自動注入環境
    env.pop("VIRTUAL_ENV", None)
    env["CFLAGS"] = "-Wno-error=incompatible-function-pointer-types"
    
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.returncode, result.stdout + result.stderr


class EnvDenoiser:
    def __init__(
        self,
        repo_dir: Path,
        *,
        run_command: CommandRunner | None = None,
        timeout_seconds: int = 180,
        python_executable: str = "python3",
        compat_python_executable: str | None = None,
        support_site_packages: str | None = None,
    ):
        self.repo_dir = repo_dir
        self.run_command = run_command or _default_run_command
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable
        self.compat_python_executable = compat_python_executable or self._find_compat_python()
        self.support_site_packages = (
            support_site_packages
            or self._find_support_site_packages()
            or sysconfig.get_paths().get("purelib", "")
        )

    def heal_requirement(self, resolution: Any, requirement: Any) -> EnvDenoiseResult:
        """
        嘗試修復環境中的依賴衝突或缺失。
        """
        if resolution.ready:
            return EnvDenoiseResult(succeeded=True, reason="ALREADY_READY")

        # 找出有衝突或缺失的探針
        violations = []
        target_python = ""

        for probe in resolution.probes:
            probe_violations = []
            if probe.get("status") in ["constraint_violation", "missing_imports"]:
                probe_python = probe.get("path")
                # 解析違規項目
                if probe.get("status") == "constraint_violation":
                    # violations 格式如 "numpy:2.0.0 not in <2.0.0"
                    v_text = probe.get("violations", "")
                    for v in v_text.split(","):
                        pkg_name = v.split(":")[0]
                        if pkg_name in requirement.package_constraints:
                            probe_violations.append(f"{pkg_name}{requirement.package_constraints[pkg_name]}")
                elif probe.get("status") == "missing_imports":
                    # import_status 格式如 "missing:numpy,setuptools"
                    imp_status = probe.get("import_status", "")
                    if imp_status.startswith("missing:"):
                        missing_pkgs = imp_status.removeprefix("missing:").split(",")
                        probe_violations.extend(missing_pkgs)

                if probe_python and probe_violations:
                    target_python = probe_python
                    violations = probe_violations
                    break

        if not target_python or not violations:
            return EnvDenoiseResult(attempted=True, succeeded=False, reason="NO_HEALABLE_VIOLATIONS")

        # 執行安裝
        # 優先使用 uv pip (如果環境中有 uv)
        has_uv = bool(shutil.which("uv"))
        if has_uv:
            command = ["uv", "pip", "install"] + violations + ["--python", target_python]
        else:
            command = [target_python, "-m", "pip", "install"] + violations
        
        command_label = " ".join(command)

        try:
            return_code, output = self.run_command(command, self.repo_dir, self.timeout_seconds)
            succeeded = (return_code == 0)
            return EnvDenoiseResult(
                attempted=True,
                succeeded=succeeded,
                healed=succeeded,
                reason="DEPENDENCY_HEALED" if succeeded else "DEPENDENCY_HEAL_FAILED",
                commands=[command_label],
                output=output,
                python_executable=target_python,
            )
        except Exception as exc:
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="DEPENDENCY_HEAL_EXCEPTION",
                commands=[command_label],
                output=str(exc),
                python_executable=target_python,
            )

    def prepare_from_evidence(self, evidence: str) -> EnvDenoiseResult:
        # 1. 處理 Astropy 特有的 Source Checkout 失敗 (優先級最高)
        if self._looks_like_astropy_source_checkout_failure(evidence):
            return self._prepare_astropy_build(evidence)

        # 2. 處理通用的 ModuleNotFoundError
        missing_pkg = self._extract_missing_module(evidence)
        if missing_pkg:
            # 禁止安裝正在修復的目標包
            if missing_pkg == "astropy":
                return self._prepare_astropy_build(evidence)

            # 對於某些套件，其安裝名稱與導入名稱不同
            install_map = {
                "erfa": "pyerfa",
            }
            install_name = install_map.get(missing_pkg, missing_pkg)
            
            has_uv = bool(shutil.which("uv"))
            if has_uv:
                command = ["uv", "pip", "install", install_name, "--python", self.python_executable]
            else:
                command = [self.python_executable, "-m", "pip", "install", install_name]
            
            command_label = " ".join(command)
            try:
                return_code, output = self.run_command(command, self.repo_dir, self.timeout_seconds)
                succeeded = (return_code == 0)
                return EnvDenoiseResult(
                    attempted=True,
                    succeeded=succeeded,
                    healed=succeeded,
                    reason=f"MODULE_HEALED_{install_name}" if succeeded else f"MODULE_HEAL_FAILED_{install_name}",
                    commands=[command_label],
                    output=output,
                    python_executable=self.python_executable,
                )
            except Exception as exc:
                return EnvDenoiseResult(
                    attempted=True,
                    succeeded=False,
                    reason=f"MODULE_HEAL_EXCEPTION_{install_name}",
                    commands=[command_label],
                    output=str(exc),
                    python_executable=self.python_executable,
                )

        return EnvDenoiseResult()

    def _prepare_astropy_build(self, evidence: str) -> EnvDenoiseResult:
        if not (self.repo_dir / "setup.py").exists():
            return EnvDenoiseResult(
                attempted=False,
                succeeded=False,
                reason="ASTROPY_SETUP_PY_MISSING",
            )

        command = [self.python_executable, "setup.py", "build_ext", "--inplace"]
        command_label = f"{self.python_executable} setup.py build_ext --inplace"
        try:
            return_code, output = self.run_command(command, self.repo_dir, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_BUILD_EXT_TIMEOUT",
                commands=[command_label],
                output=str(output),
                python_executable=self.python_executable,
            )
        except Exception as exc:
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_BUILD_EXT_EXCEPTION",
                commands=[command_label],
                output=str(exc),
                python_executable=self.python_executable,
            )

        result = EnvDenoiseResult(
            attempted=True,
            succeeded=return_code == 0,
            healed=return_code == 0,
            reason="ASTROPY_BUILD_EXT_INPLACE" if return_code == 0 else "ASTROPY_BUILD_EXT_FAILED",
            commands=[command_label],
            output=output,
            python_executable=self.python_executable,
        )
        if return_code == 0:
            return result
        if "setuptools.dep_util" in output:
            return self._retry_with_setuptools_dep_util_shim(command_label, output)
        if self._looks_like_python_abi_failure(output):
            return self._retry_with_compat_python(result.commands, result.output)
        return result

    @staticmethod
    def _extract_missing_module(evidence: str) -> str | None:
        # 尋找 ModuleNotFoundError: No module named 'xxx'
        match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", evidence)
        if match:
            return match.group(1).split(".")[0] # 只取頂層包名
        # 尋找 ImportError: No module named 'xxx'
        match = re.search(r"ImportError: No module named ([^ ]+)", evidence)
        if match:
            return match.group(1).split(".")[0]
        return None

    def _retry_with_setuptools_dep_util_shim(self, previous_command: str, previous_output: str) -> EnvDenoiseResult:
        shim_code = (
            "import runpy, sys, types, os\n"
            # 隔離模式下的路徑注入
            "try:\n"
            "    from setuptools._distutils.dep_util import newer_group\n"
            "except Exception:\n"
            "    from distutils.dep_util import newer_group\n"
            "module = types.ModuleType('setuptools.dep_util')\n"
            "module.newer_group = newer_group\n"
            "sys.modules['setuptools.dep_util'] = module\n"
            "sys.argv = ['setup.py', 'build_ext', '--inplace']\n"
            "runpy.run_path('setup.py', run_name='__main__')\n"
        )
        command = [self.python_executable, "-c", shim_code]
        command_label = f"{self.python_executable} -c <setuptools.dep_util shim> setup.py build_ext --inplace"
        try:
            return_code, output = self.run_command(command, self.repo_dir, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_BUILD_EXT_SHIM_TIMEOUT",
                commands=[previous_command, command_label],
                output=previous_output + "\n" + str(output),
                python_executable=self.python_executable,
            )
        except Exception as exc:
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_BUILD_EXT_SHIM_EXCEPTION",
                commands=[previous_command, command_label],
                output=previous_output + "\n" + str(exc),
                python_executable=self.python_executable,
            )

        result = EnvDenoiseResult(
            attempted=True,
            succeeded=return_code == 0,
            reason="ASTROPY_BUILD_EXT_WITH_SETUPTOOLS_DEP_UTIL_SHIM",
            commands=[previous_command, command_label],
            output=previous_output + "\n" + output,
            python_executable=self.python_executable,
        )
        if return_code == 0:
            return result
        if self._looks_like_python_abi_failure(output):
            return self._retry_with_compat_python(result.commands, result.output)
        return result

    def _retry_with_compat_python(self, previous_commands: list[str], previous_output: str) -> EnvDenoiseResult:
        if not self.compat_python_executable:
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_COMPAT_PYTHON_MISSING",
                commands=previous_commands,
                output=previous_output,
                python_executable=self.python_executable,
            )

        shim_code = self._build_setup_shim_code()
        command = [self.compat_python_executable, "-c", shim_code]
        command_label = f"{self.compat_python_executable} -c <compat astropy build shim> setup.py build_ext --inplace"
        try:
            return_code, output = self.run_command(command, self.repo_dir, self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_COMPAT_BUILD_TIMEOUT",
                commands=previous_commands + [command_label],
                output=previous_output + "\n" + str(output),
                python_executable=self.compat_python_executable,
            )
        except Exception as exc:
            return EnvDenoiseResult(
                attempted=True,
                succeeded=False,
                reason="ASTROPY_COMPAT_BUILD_EXCEPTION",
                commands=previous_commands + [command_label],
                output=previous_output + "\n" + str(exc),
                python_executable=self.compat_python_executable,
            )

        reason = "ASTROPY_BUILD_EXT_WITH_COMPAT_PYTHON"
        if return_code != 0 and self._looks_like_python_abi_failure(output):
            reason = "ASTROPY_COMPAT_BUILD_ABI_FAILURE"

        return EnvDenoiseResult(
            attempted=True,
            succeeded=return_code == 0,
            reason=reason,
            commands=previous_commands + [command_label],
            output=previous_output + "\n" + output,
            python_executable=self.compat_python_executable,
        )

    def _build_setup_shim_code(self) -> str:
        support_path = repr(self.support_site_packages)
        return (
            "import runpy, sys, types\n"
            f"support_path = {support_path}\n"
            "if support_path and support_path not in sys.path:\n"
            "    sys.path.append(support_path)\n"
            "try:\n"
            "    from setuptools._distutils.dep_util import newer_group\n"
            "except Exception:\n"
            "    from distutils.dep_util import newer_group\n"
            "module = types.ModuleType('setuptools.dep_util')\n"
            "module.newer_group = newer_group\n"
            "sys.modules['setuptools.dep_util'] = module\n"
            "sys.argv = ['setup.py', 'build_ext', '--inplace']\n"
            "runpy.run_path('setup.py', run_name='__main__')\n"
        )

    @staticmethod
    def _looks_like_python_abi_failure(output: str) -> bool:
        lowered = output.lower()
        # 加入 'incompatible function pointer types' 與 'tp_traverse' 作為 ABI/構建不相容的訊號
        return (
            "incompatible function pointer types" in lowered 
            or "pywtbarr_traverse" in lowered
            or "tp_traverse" in lowered
            or "tp_clear" in lowered
        )

    @staticmethod
    def _find_compat_python() -> str | None:
        # 增加 3.9 作為舊版 Astropy 的救命稻草
        for candidate in ("python3.9", "python3.12", "python3.11", "python3.10"):
            resolved = shutil.which(candidate)
            if not resolved:
                # 嘗試使用 uv 查找
                try:
                    res = subprocess.run(["uv", "python", "find", candidate], capture_output=True, text=True, timeout=2)
                    if res.returncode == 0:
                        resolved = res.stdout.strip()
                except Exception:
                    pass
            if resolved:
                return resolved
        return None

    @staticmethod
    def _find_support_site_packages() -> str:
        spec = importlib.util.find_spec("extension_helpers")
        if not spec:
            return ""

        locations = getattr(spec, "submodule_search_locations", None)
        if locations:
            first_location = next(iter(locations), "")
            return str(Path(first_location).parent) if first_location else ""

        origin = getattr(spec, "origin", None)
        if not origin:
            return ""

        origin_path = Path(origin)
        if origin_path.name == "__init__.py":
            return str(origin_path.parent.parent)
        return str(origin_path.parent)

    @staticmethod
    def _looks_like_astropy_source_checkout_failure(evidence: str) -> bool:
        lowered = evidence.lower()
        markers: Sequence[str] = (
            "trying to import astropy from within a source checkout",
            "extension modules are built",
            "build_ext --inplace",
            "cannot import name '_compiler' from 'astropy.utils'",
            "partially initialized module 'astropy",
            "circular import",
        )
        return any(marker in lowered for marker in markers)
