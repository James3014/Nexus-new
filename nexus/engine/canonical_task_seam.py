from pathlib import Path
import importlib


def infer_task_kind(task_text: str) -> str:
    text = str(task_text or "").strip().lower()
    feature_keywords = (
        "build",
        "create",
        "add",
        "implement",
        "feature",
        "新增",
        "建立",
        "實作",
        "開發",
    )
    if any(keyword in text for keyword in feature_keywords):
        return "feature"
    return "bug"


def build_engine(project_root: Path, **config_overrides):
    from nexus.engine.config import EngineConfig
    from nexus.engine.coordinator import NexusEngine

    return NexusEngine(EngineConfig(project_root=project_root, **config_overrides))


def build_command_service(project_root: Path):
    NexusCommandService = importlib.import_module("nexus." + "app.command_service").NexusCommandService
    return NexusCommandService(build_engine(project_root))


class LegacyTaskServiceAdapter:
    def __init__(self, command_service):
        self._command_service = command_service

    def execute_bug(self, task: str, delivery_mode: str = "standard", bug_id: str | None = None, **kwargs):
        TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

        request = TaskRequest(
            task=task,
            task_id=bug_id,
            plan_only=bool(kwargs.get("plan_only", False)),
            delivery_mode=delivery_mode,
            verify_commands=kwargs.get("verify_commands"),
            artifact_paths=kwargs.get("artifact_paths"),
        )
        return self._command_service.execute_bug(request)

    def execute_feature(self, task: str, domain: str | None = None, delivery_mode: str = "standard", **kwargs):
        TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

        request = TaskRequest(
            task=task,
            domain=domain,
            plan_only=bool(kwargs.get("plan_only", False)),
            delivery_mode=delivery_mode,
            verify_commands=kwargs.get("verify_commands"),
            artifact_paths=kwargs.get("artifact_paths"),
        )
        return self._command_service.execute_feature(request)


def build_legacy_cli_service(project_root: Path):
    return LegacyTaskServiceAdapter(build_command_service(project_root))


def execute_single_task_via_service(task_text: str, project_root: Path) -> bool:
    TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

    service = build_command_service(project_root)
    request = TaskRequest(task=task_text, delivery_mode="standard")
    if infer_task_kind(task_text) == "feature":
        return bool(service.execute_feature(request))
    return bool(service.execute_bug(request))
