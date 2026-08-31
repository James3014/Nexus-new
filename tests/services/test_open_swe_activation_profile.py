from __future__ import annotations

import json
from pathlib import Path

import scripts.ops.external_intelligence_service as service_module
from scripts.ops.external_intelligence_service import ServiceConfig, build_automation

PROFILE = Path("configs/runtime/external_intelligence_open_swe_activation_v1.json")


def _config(tmp_path, **overrides):
    values = dict(
        repositories=("o/r",),
        repository_roots={"o/r": str(tmp_path / "repo")},
        state_root=tmp_path / "state",
        workspace_root=tmp_path / "workspaces",
        opencli_profile="test-profile",
        opencode_executable="/tmp/opencode",
    )
    values.update(overrides)
    return ServiceConfig(**values)


def test_activation_profile_selects_both_open_swe_backends(tmp_path, monkeypatch):
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    semantic_calls = []
    worker_calls = []

    class FakeSemantic:
        def __init__(self, **kwargs):
            semantic_calls.append(kwargs)

    class FakeWorker:
        def __init__(self, **kwargs):
            worker_calls.append(kwargs)

    monkeypatch.setattr(service_module, "OpenSWEExternalIntelligenceTransport", FakeSemantic)
    monkeypatch.setattr(service_module, "OpenSWEWorkerTransport", FakeWorker)

    automation = build_automation(_config(tmp_path, **profile), "o/r")

    assert isinstance(automation.sidecar.transport, FakeSemantic)
    assert isinstance(automation.c_runtime.transport, FakeWorker)
    assert semantic_calls[0]["model_provider"] == "google_genai"
    assert semantic_calls[0]["model_id"] == "gemini-3.7-flash"
    assert worker_calls[0]["model_provider"] == "google_genai"
    assert worker_calls[0]["model_id"] == "gemini-3.7-flash"


def test_activation_profile_rolls_back_to_existing_control_arm(tmp_path):
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile.update(semantic_backend="opencli", worker_backend="opencode")

    automation = build_automation(_config(tmp_path, **profile), "o/r")

    assert isinstance(
        automation.sidecar.transport, service_module.OpenCLIExternalIntelligenceTransport
    )
    assert not isinstance(automation.c_runtime.transport, service_module.OpenSWEWorkerTransport)
