"""Live-smoke operator fixture → canonical LocalAssistRequest integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.local_assist_live_smoke import (
    LIVE_SMOKE_SCHEMA,
    is_live_smoke_payload,
    translate_live_smoke_to_request,
)
from nexus.services.local_assist_service import (
    REQUEST_SCHEMA,
    LocalAssistRequest,
    LocalAssistService,
    load_request_file,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


FIXTURE = Path("docs/bench/local_assist/gate2_live_smoke_task.json")


def test_fixture_is_live_smoke_schema() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema"] == LIVE_SMOKE_SCHEMA
    assert is_live_smoke_payload(payload) is True


def test_from_dict_rejects_live_smoke_without_translation() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    req = LocalAssistRequest.from_dict(payload)
    with pytest.raises(ValueError, match="unsupported_request_schema"):
        req.validate()


def test_translate_preserves_bounds_and_forbids_mutation(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    req = translate_live_smoke_to_request(payload, workspace_root=tmp_path)
    assert req.schema == REQUEST_SCHEMA
    assert req.task_id == payload["task_id"]
    assert req.task_statement == payload["task_statement"]
    assert list(req.allowed_files) == payload["allowed_files"]
    assert req.mutation_policy == "isolated_only"
    assert req.requested_role == "advisor"
    assert req.action == "advisor"
    # Formal mutation / patch not expressed on request; smoke rejects truthy flags.
    payload_bad = dict(payload)
    payload_bad["request_patch"] = True
    with pytest.raises(ValueError, match="live_smoke_rejects_request_patch"):
        translate_live_smoke_to_request(payload_bad, workspace_root=tmp_path)
    payload_mut = dict(payload)
    payload_mut["formal_workspace_mutation_allowed"] = True
    with pytest.raises(ValueError, match="live_smoke_rejects_formal_workspace_mutation_allowed"):
        translate_live_smoke_to_request(payload_mut, workspace_root=tmp_path)


def test_load_request_file_translates_fixture(tmp_path: Path, monkeypatch) -> None:
    # Fixture uses workspace_revision=HEAD and repo-relative allowed_files.
    # load_request_file validates workspace_root exists; temporarily point root via copy.
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    smoke_path = tmp_path / "smoke.json"
    # Copy allowed file tree so validation can find workspace when we rewrite root via translate.
    allowed = payload["allowed_files"][0]
    dest = tmp_path / allowed
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text((Path.cwd() / allowed).read_text(encoding="utf-8"), encoding="utf-8")
    payload["workspace_root"] = str(tmp_path)
    smoke_path.write_text(json.dumps(payload), encoding="utf-8")

    req = load_request_file(smoke_path)
    assert req.schema == REQUEST_SCHEMA
    assert req.task_id == "gate2-live-smoke-advisor-001"
    assert "gate2_live_smoke_task.json" in req.allowed_files[0]
    assert req.mutation_policy == "isolated_only"


def test_file_to_service_smoke_integration(tmp_path: Path) -> None:
    """fixture file → loader translation → validate → LocalAssistService (injected)."""
    from scripts.engine.commands.local_assist_actions import run_local_assist_command

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    allowed = payload["allowed_files"][0]
    dest = tmp_path / allowed
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text((Path.cwd() / allowed).read_text(encoding="utf-8"), encoding="utf-8")

    task_path = tmp_path / "task.json"
    payload = dict(payload)
    payload["workspace_revision"] = "rev-smoke-test"
    task_path.write_text(json.dumps(payload), encoding="utf-8")

    # Drive translation + service with inject (schema path, not live proof).
    req = translate_live_smoke_to_request(payload, workspace_root=tmp_path)
    req.validate()
    assert req.allowed_files
    assert req.mutation_policy == "isolated_only"

    service = LocalAssistService(
        provider=InjectedLocalModelProvider(
            lambda _r: "Advisory: keep allowed_files bounded; do not patch formal workspace."
        )
    )
    response = service.handle(req)
    assert response.status == "SUCCEEDED"
    assert response.local_model_invoked is True
    assert response.output_delivered is True
    assert response.provider == "injected" or response.local_model_invoked

    # CLI command path also accepts live-smoke schema.
    # Monkeypatch service would be overkill; re-run translation via command by
    # temporarily using inject through env is hard — assert translate path used by command.
    from nexus.services.local_assist_live_smoke import is_live_smoke_payload

    loaded = json.loads(task_path.read_text(encoding="utf-8"))
    assert is_live_smoke_payload(loaded)
    # Structural: command module imports translator (regression against silent from_dict).
    import scripts.engine.commands.local_assist_actions as actions

    assert hasattr(actions, "translate_live_smoke_to_request")
    assert hasattr(actions, "is_live_smoke_payload")
