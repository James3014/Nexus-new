#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from types import SimpleNamespace

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.engine import nexus_cli as engine_cli
from scripts.engine.nexus_cli import nexus as main
from nexus.services.cli_commands_service import CliCommandsService
from nexus.app.command_service import NexusCommandService, TaskRequest

class NexusCLI(CliCommandsService):
    """⚔️ Legacy Compatibility Shim for NexusCLI (AOS 145+)"""
    def __init__(self, *args, **kwargs):
        # 兼容舊版 tests/test_v9_regression_p1.py 的 project_root 傳參內容
        root = kwargs.pop("project_root", None) or (args[0] if args else None)
        self.output_dir = Path(kwargs.pop("output_dir", Path(root or REPO_ROOT) / "runs"))
        super().__init__(repo_root=root)
        self.project_root = Path(root or REPO_ROOT)
        self.profile_path = self.project_root / ".nexus" / "runtime_profile.json"
        self.runtime_profile = {"name": "standard"}
        self._service = NexusCommandService(
            SimpleNamespace(project_root=self.project_root, run_dir=self.output_dir)
        )

    @property
    def service(self):
        return self._service

    def _print_delivery_summary(self) -> None:
        if getattr(self.service, "last_effective_verify_commands", None):
            print("Verification Commands:")
            for cmd in self.service.last_effective_verify_commands:
                print(cmd)
        report_paths = getattr(self.service, "last_completion_report_paths", None)
        if isinstance(report_paths, (list, tuple)) and report_paths:
            print("Delivery Reports:")
            for path in report_paths:
                print(str(path))

    def run_bug(self, task: str, delivery_mode: str = "standard", verify_commands=None):
        verify_commands = list(verify_commands or [])
        if self.runtime_profile.get("name") == "prod":
            if self.run_release_ready() != 0:
                self.service.last_completion_error = "release_ready_gate_failed"
                return False

        req = TaskRequest(
            task=task,
            delivery_mode=delivery_mode,
            verify_commands=verify_commands,
        )
        ok = bool(self.service.execute_bug(req))
        self._print_delivery_summary()
        return ok

    def run_feature(
        self,
        task: str,
        domain: str | None = None,
        plan_only: bool = False,
        skill: str | None = None,
        delivery_mode: str = "standard",
        verify_commands=None,
        artifact_paths=None,
    ):
        req = TaskRequest(
            task=task,
            domain=domain,
            plan_only=plan_only,
            skill=skill,
            delivery_mode=delivery_mode,
            verify_commands=list(verify_commands or []),
            artifact_paths=artifact_paths,
        )
        ok = bool(self.service.execute_feature(req))
        self._print_delivery_summary()
        return ok

    def run_check(self, level: str = "standard"):
        return self.service.execute_self_check(level=level)

    def run_self_heal(self, mode: str = "standard"):
        return self.service.execute_self_heal(mode=mode)

    def run_health_explain(self, output: str = "text"):
        return self.service.execute_health_explain()

    def run_phase6_research(self, workspace: str, rounds: int, proof_ratio_min: float, output_prefix: str, skip_autopilot: bool):
        cmd = [
            sys.executable,
            str(self.project_root / "scripts" / "ops" / "phase6_research.py"),
            "--workspace",
            workspace,
            "--rounds",
            str(rounds),
            "--proof-ratio-min",
            str(proof_ratio_min),
            "--output-prefix",
            output_prefix,
        ]
        if skip_autopilot:
            cmd.append("--skip-autopilot")
        return engine_cli.subprocess.call(cmd)

    def run_phase7_research(self, workspace: str, rounds: int, proof_ratio_min: float, output_prefix: str, skip_autopilot: bool, autotune_apply: bool, min_samples: int, baseline: float, learning_rate: float):
        cmd = [
            sys.executable,
            str(self.project_root / "scripts" / "ops" / "phase7_research.py"),
            "--workspace",
            workspace,
            "--rounds",
            str(rounds),
            "--proof-ratio-min",
            str(proof_ratio_min),
            "--output-prefix",
            output_prefix,
            "--min-samples",
            str(min_samples),
            "--baseline",
            str(baseline),
            "--learning-rate",
            str(learning_rate),
        ]
        if skip_autopilot:
            cmd.append("--skip-autopilot")
        if autotune_apply:
            cmd.append("--autotune-apply")
        return engine_cli.subprocess.call(cmd)

    def run_skills_autotune(self, apply: bool, min_samples: int, baseline: float, learning_rate: float):
        cmd = [
            sys.executable,
            str(self.project_root / "scripts" / "ops" / "skills_autotune.py"),
            "--min-samples",
            str(min_samples),
            "--baseline",
            str(baseline),
            "--learning-rate",
            str(learning_rate),
        ]
        if apply:
            cmd.append("--apply")
        return engine_cli.subprocess.call(cmd)

    def run_skills_health(self, output: str, workspace: str):
        cmd = [
            sys.executable,
            str(self.project_root / "scripts" / "ops" / "skills_health.py"),
            "--output",
            output,
            "--workspace",
            workspace,
        ]
        return engine_cli.subprocess.call(cmd)

    def run_skills_optimize(self, max_items: int, rebound: float):
        cmd = [
            sys.executable,
            str(self.project_root / "scripts" / "ops" / "skills_optimization_runner.py"),
            "--max-items",
            str(max_items),
            "--rebound",
            str(rebound),
        ]
        return engine_cli.subprocess.call(cmd)

    def run_profile(self, action: str, name: str):
        if action == "apply" and name == "prod":
            payload = {"name": "prod", "delivery_mode": "high"}
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            self.profile_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.runtime_profile = payload
            return 0
        return 1

    def run_release_ready(self):
        gate_script = self.project_root / "scripts" / "ops" / "nexus_release_gate.sh"
        acceptance_script = self.project_root / "scripts" / "ops" / "nexus_acceptance_check.py"
        rc1 = engine_cli.subprocess.call([str(gate_script)])
        if rc1 != 0:
            return rc1
        return engine_cli.subprocess.call([sys.executable, str(acceptance_script)])

if __name__ == "__main__":
    main()
