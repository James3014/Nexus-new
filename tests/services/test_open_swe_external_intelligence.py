from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomllib


def _module():
    return importlib.import_module("nexus.services.open_swe_external_intelligence")


_RUNTIME_EXECUTABLE = "/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime"
_RUNTIME_HASH = "a" * 64
_MISSING = object()


def test_nexus_adapter_is_thin_and_has_no_deepagents_or_langchain_imports():
    source = Path("nexus/services/open_swe_external_intelligence.py").read_text(encoding="utf-8")
    assert "import deepagents" not in source
    assert "from deepagents" not in source
    assert "import langchain" not in source
    assert "from langchain" not in source


def test_semantic_transport_maps_external_protocol_and_reconcile_is_separate(tmp_path, monkeypatch):
    module = _module()
    calls = []
    envelope = {"schema": "external_execution_envelope.v1", "binding": {"task": "t1"}}

    def runtime_call(executable, payload, *, provider_id, timeout):
        calls.append((executable, dict(payload), provider_id, timeout))
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
                "raw": json.dumps(envelope),
                "process_started": payload["operation"] == "semantic_run",
                "outcome_unknown": False,
                "retry_safe": False,
                "started_at": "2026-09-01T00:00:00Z",
                "finished_at": "2026-09-01T00:00:01Z",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
        runtime_state_root=tmp_path / "runtime-state",
    )

    first = transport.invoke("prompt")
    reconciled = transport.reconcile("prompt")

    assert first.status == "INTELLIGENCE_COMPLETED"
    assert json.loads(first.raw) == envelope
    assert reconciled.status == "INTELLIGENCE_COMPLETED"
    assert [call[1]["operation"] for call in calls] == [
        "identity",
        "semantic_run",
        "identity",
        "semantic_reconcile",
    ]
    assert calls[1][1]["operation_id"] == calls[3][1]["operation_id"]
    assert first.safe_argv == (_RUNTIME_EXECUTABLE, "<json-stdin>")


def test_semantic_timeout_is_unknown_and_never_retry_safe(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_runtime_call",
        lambda *_args, **_kwargs: (
            (_identity(module, _args[1]), "", False, "")
            if _args[1]["operation"] == "identity"
            else (None, "", True, "runtime_timeout")
        ),
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.retry_safe is False


def test_semantic_runtime_missing_before_start_is_retry_safe(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_runtime_call",
        lambda *_args, **_kwargs: (
            (_identity(module, _args[1]), "", False, "")
            if _args[1]["operation"] == "identity"
            else (None, "", False, "runtime_not_found")
        ),
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_RUNTIME_NOT_FOUND"
    assert result.outcome_unknown is False
    assert result.retry_safe is True


def test_semantic_model_attestation_mismatch_fails_closed(tmp_path, monkeypatch):
    module = _module()

    def runtime_call(*_args, **_kwargs):
        payload = _args[1]
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "other",
                "model_id": "wrong",
                "raw": "{}",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(
        module,
        "_runtime_call",
        runtime_call,
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_MODEL_ATTESTATION_MISMATCH"
    assert result.outcome_unknown is True


@pytest.mark.parametrize(
    ("operation", "field", "value"),
    (
        (operation, field, value)
        for operation in ("semantic_run", "semantic_reconcile")
        for field, value in (
            ("provider_id", _MISSING),
            ("provider_id", None),
            ("provider_id", ""),
            ("provider_id", "   "),
            ("provider_id", {"provider": "google_genai"}),
            ("provider_id", 42),
            ("provider_id", False),
            ("model_id", _MISSING),
            ("model_id", None),
            ("model_id", ""),
            ("model_id", "   "),
            ("model_id", ["gemini-test"]),
            ("model_id", 42),
            ("model_id", False),
        )
    ),
)
def test_semantic_missing_or_malformed_attestation_fails_closed_without_redispatch(
    tmp_path, monkeypatch, operation, field, value
):
    module = _module()
    calls = []

    def runtime_call(*_args, **_kwargs):
        payload = _args[1]
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        result = {
            "schema": module.PROTOCOL_RESULT_SCHEMA,
            "kind": "semantic",
            "status": "INTELLIGENCE_COMPLETED",
            "provider_id": "google_genai",
            "model_id": "gemini-test",
            "raw": "{}",
        }
        if value is _MISSING:
            del result[field]
        else:
            result[field] = value
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = (
        transport.invoke("prompt") if operation == "semantic_run" else transport.reconcile("prompt")
    )

    assert result.status == "OPEN_SWE_MODEL_ATTESTATION_MISMATCH"
    assert result.outcome_unknown is True
    assert calls == ["identity", operation]


@pytest.mark.parametrize(
    ("operation", "field", "value"),
    (
        (operation, field, value)
        for operation in ("semantic_run", "semantic_reconcile")
        for field, value in (
            ("provider_id", "other-provider"),
            ("model_id", "other-model"),
        )
    ),
)
def test_semantic_single_identity_mismatch_fails_closed(
    tmp_path, monkeypatch, operation, field, value
):
    module = _module()
    calls = []

    def runtime_call(*_args, **_kwargs):
        payload = _args[1]
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        result = {
            "schema": module.PROTOCOL_RESULT_SCHEMA,
            "kind": "semantic",
            "status": "INTELLIGENCE_COMPLETED",
            "provider_id": "google_genai",
            "model_id": "gemini-test",
        }
        result[field] = value
        return result, "", True, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = (
        transport.invoke("prompt") if operation == "semantic_run" else transport.reconcile("prompt")
    )

    assert result.status == "OPEN_SWE_MODEL_ATTESTATION_MISMATCH"
    assert result.outcome_unknown is True
    assert result.retry_safe is False
    assert calls == ["identity", operation]


def test_semantic_reconcile_accepts_valid_explicit_attestation(tmp_path, monkeypatch):
    module = _module()

    def runtime_call(*_args, **_kwargs):
        payload = _args[1]
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
                "raw": "{}",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.reconcile("prompt")

    assert result.status == "INTELLIGENCE_COMPLETED"
    assert result.outcome_unknown is False


def test_semantic_subprocess_json_missing_attestation_fails_closed(tmp_path):
    module = _module()
    script = tmp_path / "runtime.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "if request['operation'] == 'identity':\n"
        "    result = {'schema': 'nexus.open_swe_runtime.result.v1', 'kind': 'identity', 'status': 'IDENTIFIED', 'distribution_name': 'nexus-open-swe-runtime', 'distribution_version': 'test', 'runtime_protocol_version': 'nexus.open_swe_runtime.request.v1', 'authority_boundary': 'execution_runtime_only', 'process_started': False, 'outcome_unknown': False, 'retry_safe': True, 'artifact_identity': {'module_file': '/opt/runtime.py', 'module_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'deepagents_version': 'test'}}\n"
        "else:\n"
        "    result = {'schema': 'nexus.open_swe_runtime.result.v1', 'kind': 'semantic', 'status': 'INTELLIGENCE_COMPLETED', 'raw': '{}'}\n"
        "print(json.dumps(result))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=str(script),
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_MODEL_ATTESTATION_MISMATCH"
    assert result.outcome_unknown is True
    assert result.retry_safe is False


def test_runtime_environment_passes_selected_provider_key_but_not_github_credentials(monkeypatch):
    module = _module()
    monkeypatch.setenv("GEMINI_API_KEY", "provider-sentinel")
    monkeypatch.setenv("GITHUB_TOKEN", "github-sentinel")
    monkeypatch.setenv("GH_TOKEN", "gh-sentinel")
    monkeypatch.setenv("UNRELATED_SECRET", "unrelated-sentinel")

    env = module._runtime_env("google_genai")

    assert "GEMINI_API_KEY" in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "UNRELATED_SECRET" not in env


def test_runtime_environment_never_passes_opencli_binding_env(monkeypatch):
    module = _module()
    monkeypatch.setenv("NEXUS_OPENCLI_EXECUTABLE", "/tmp/wrong-opencli")
    monkeypatch.setenv("NEXUS_OPENCLI_PROFILE", "wrong-profile")
    monkeypatch.setenv("NEXUS_OPENCLI_SITE_SESSION", "wrong-session")
    monkeypatch.setenv("NEXUS_OPENCLI_TIMEOUT_SECONDS", "999")

    env = module._runtime_env("opencli_chatgpt")

    assert not any(name.startswith("NEXUS_OPENCLI_") for name in env)


def test_opencli_semantic_transport_sends_explicit_binding(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def runtime_call(executable, payload, *, provider_id, timeout):
        calls.append(dict(payload))
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "opencli_chatgpt",
                "model_id": "very-high",
                "raw": "{}",
                "process_started": True,
                "outcome_unknown": False,
                "retry_safe": False,
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    binding = {
        "executable": "/opt/opencli",
        "profile": "profile-a",
        "site_session": "persistent",
        "timeout_seconds": 240,
    }
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="opencli_chatgpt",
        model_id="very-high",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
        transport_config=binding,
    )

    transport.invoke("prompt")

    assert calls[0]["transport_config"] == binding


def test_opencli_worker_transport_sends_explicit_binding(tmp_path, monkeypatch):
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}\n", encoding="utf-8")
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(dict(payload))
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return None, "", True, "runtime_timeout"

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    binding = {
        "executable": "/opt/opencli",
        "profile": "profile-a",
        "site_session": "persistent",
        "timeout_seconds": 240,
    }
    transport = module.OpenSWEWorkerTransport(
        model_provider="opencli_chatgpt",
        model_id="very-high",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
        transport_config=binding,
    )

    result = transport.run_new(
        prompt='task_id=t1\nunit_id=u1\nauthorized_mutation_paths=["a.py"]',
        artifact_path=str(artifact),
        workspace_path=str(workspace),
    )

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.retry_safe is False
    assert calls[0]["transport_config"] == binding


def test_opencli_transport_binding_validation_is_fail_closed(tmp_path):
    module = _module()
    valid = {
        "executable": "/opt/opencli",
        "profile": "profile-a",
        "site_session": "ephemeral",
        "timeout_seconds": 30,
    }
    module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="opencli_chatgpt",
        model_id="very-high",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
        transport_config=valid,
    )
    module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="opencli_chatgpt",
        model_id="very-high",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
        transport_config={**valid, "timeout_seconds": 900},
    )
    for invalid in (
        None,
        {**valid, "executable": "opencli"},
        {**valid, "profile": ""},
        {**valid, "timeout_seconds": 29},
        {**valid, "timeout_seconds": 901},
        {**valid, "site_session": "session-a"},
        {**valid, "extra": "unexpected"},
    ):
        with pytest.raises(
            module.OpenSWEExternalIntelligenceError,
            match="OPEN_SWE_TRANSPORT_CONFIG_(REQUIRED|INVALID)",
        ):
            module.OpenSWEExternalIntelligenceTransport(
                repository_root=tmp_path,
                model_provider="opencli_chatgpt",
                model_id="very-high",
                executable=_RUNTIME_EXECUTABLE,
                expected_artifact_sha256=_RUNTIME_HASH,
                transport_config=invalid,
            )
    with pytest.raises(
        module.OpenSWEExternalIntelligenceError,
        match="OPEN_SWE_TRANSPORT_CONFIG_PROVIDER_MISMATCH",
    ):
        module.OpenSWEExternalIntelligenceTransport(
            repository_root=tmp_path,
            model_provider="google_genai",
            model_id="gemini-test",
            executable=_RUNTIME_EXECUTABLE,
            expected_artifact_sha256=_RUNTIME_HASH,
            transport_config=valid,
        )


def test_empty_external_runtime_executable_is_rejected(tmp_path):
    module = _module()
    with pytest.raises(
        module.OpenSWEExternalIntelligenceError, match="OPEN_SWE_EXECUTABLE_REQUIRED"
    ):
        module.OpenSWEExternalIntelligenceTransport(
            repository_root=tmp_path,
            model_provider="google_genai",
            model_id="gemini-test",
            executable="",
            expected_artifact_sha256=_RUNTIME_HASH,
        )


@pytest.mark.parametrize(
    ("executable", "expected_artifact_sha256", "error"),
    (
        ("", _RUNTIME_HASH, "OPEN_SWE_EXECUTABLE_REQUIRED"),
        (_RUNTIME_EXECUTABLE, "", "OPEN_SWE_EXPECTED_ARTIFACT_HASH_REQUIRED"),
        ("relative/runtime", _RUNTIME_HASH, "OPEN_SWE_EXECUTABLE_ABSOLUTE_REQUIRED"),
    ),
)
def test_runtime_binding_requires_explicit_absolute_executable_and_hash(
    tmp_path, executable, expected_artifact_sha256, error
):
    module = _module()
    with pytest.raises(module.OpenSWEExternalIntelligenceError, match=error):
        module.OpenSWEExternalIntelligenceTransport(
            repository_root=tmp_path,
            model_provider="google_genai",
            model_id="gemini-test",
            executable=executable,
            expected_artifact_sha256=expected_artifact_sha256,
        )


def _identity(module, payload, *, module_hash="a" * 64):
    return {
        "schema": module.PROTOCOL_RESULT_SCHEMA,
        "kind": "identity",
        "status": "IDENTIFIED",
        "distribution_name": "nexus-open-swe-runtime",
        "distribution_version": "0.1.0",
        "runtime_protocol_version": module.PROTOCOL_REQUEST_SCHEMA,
        "artifact_identity": {
            "module_file": "/opt/nexus-open-swe-runtime/cli.py",
            "module_sha256": module_hash,
            "deepagents_version": "0.7.6",
        },
        "authority_boundary": "execution_runtime_only",
        "process_started": False,
        "outcome_unknown": False,
        "retry_safe": True,
    }


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("distribution_name", "wrong-runtime", "OPEN_SWE_RUNTIME_IDENTITY_INVALID"),
        ("runtime_protocol_version", "wrong-protocol", "OPEN_SWE_RUNTIME_IDENTITY_INVALID"),
        ("authority_boundary", "controller-authority", "OPEN_SWE_RUNTIME_IDENTITY_INVALID"),
        (
            "artifact_identity",
            {"module_file": "/opt/runtime.py", "module_sha256": "b" * 64},
            "OPEN_SWE_RUNTIME_ARTIFACT_MISMATCH",
        ),
    ),
)
def test_invalid_runtime_identity_blocks_semantic_effect(
    tmp_path, monkeypatch, field, value, error
):
    module = _module()
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(payload["operation"])
        identity = _identity(module, payload)
        identity[field] = value
        return identity, "", False, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_RUNTIME_IDENTITY_FAILED"
    assert result.outcome_unknown is False
    assert result.retry_safe is False
    assert calls == ["identity"]


def test_runtime_identity_is_required_before_semantic_dispatch(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "OK",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    transport.invoke("prompt")
    assert calls == ["identity", "semantic_run"]


def test_runtime_identity_hash_mismatch_blocks_worker_before_effect(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(payload["operation"])
        return _identity(module, payload, module_hash="b" * 64), "", False, ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}", encoding="utf-8")
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
    )
    result = transport.run_new(
        prompt="p", artifact_path=str(artifact), workspace_path=str(workspace)
    )
    assert result.status == "OPEN_SWE_RUNTIME_IDENTITY_FAILED"
    assert calls == ["identity"]


def test_runtime_identity_is_revalidated_after_runtime_change(tmp_path, monkeypatch):
    module = _module()
    calls = []
    identity_count = 0

    def runtime_call(_executable, payload, **_kwargs):
        nonlocal identity_count
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            identity_count += 1
            return (
                _identity(
                    module, payload, module_hash=_RUNTIME_HASH if identity_count == 1 else "b" * 64
                ),
                "",
                False,
                "",
            )
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "OK",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    assert transport.invoke("first").status == "OK"
    changed = transport.invoke("second")
    assert changed.status == "OPEN_SWE_RUNTIME_IDENTITY_FAILED"
    assert calls == ["identity", "semantic_run", "identity"]


def test_failed_reconcile_is_unknown_and_never_retry_safe(tmp_path, monkeypatch):
    module = _module()
    calls = []

    def runtime_call(_executable, payload, **_kwargs):
        calls.append(payload["operation"])
        if payload["operation"] == "identity":
            return _identity(module, payload), "", False, ""
        if payload["operation"] == "semantic_reconcile":
            return None, "", True, "runtime_timeout"
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "OK",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable=_RUNTIME_EXECUTABLE,
        expected_artifact_sha256=_RUNTIME_HASH,
    )

    assert transport.invoke("prompt").status == "OK"
    reconciled = transport.reconcile("prompt")
    assert reconciled.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert reconciled.outcome_unknown is True
    assert reconciled.retry_safe is False
    assert calls == ["identity", "semantic_run", "identity", "semantic_reconcile"]


# Exact-base lineage witnesses. The historical node IDs remain collected while
# the asserted behavior has moved from the Nexus process into the external
# runtime owner. The locked runtime suite supplies the real Deep Agents proof.
def _external_runtime_module():
    path = Path("runtimes/open_swe/nexus_open_swe_runtime/cli.py").resolve()
    spec = importlib.util.spec_from_file_location("nexus_open_swe_runtime_compat_semantic", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RuntimeGraph:
    def __init__(self, surface, *, output=None, error=None):
        self.surface = tuple(surface)
        self.output = output
        self.error = error
        self.calls = 0

    def get_graph(self):
        tools = {name: object() for name in self.surface}
        data = SimpleNamespace(tools_by_name=tools)
        return SimpleNamespace(nodes={"tools": SimpleNamespace(data=data)})

    def invoke(self, _payload, config=None):
        self.calls += 1
        assert config == {"recursion_limit": 40}
        if self.error is not None:
            raise self.error
        return self.output


def _runtime_record(name: str, envelope: dict):
    return {
        "messages": [SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": envelope}}])]
    }


def _semantic_runtime_request(tmp_path: Path) -> dict:
    repository = tmp_path / "repo"
    repository.mkdir()
    return {
        "operation_id": "a" * 64,
        "provider_id": "google_genai",
        "model_id": "gemini-test",
        "repository_root": str(repository),
        "runtime_state_root": str(tmp_path / "state"),
        "prompt": "bounded semantic prompt",
    }


def _runtime_loader():
    return {"human_message": lambda content: content}


def test_transport_returns_recorded_envelope_and_reconciles_without_redispatch(tmp_path):
    runtime = _external_runtime_module()
    request = _semantic_runtime_request(tmp_path)
    envelope = {"schema": "external_execution_envelope.v1", "binding": {"task": "t1"}}
    graph = _RuntimeGraph(
        runtime.SEMANTIC_TOOLS,
        output=_runtime_record("record_finding", envelope),
    )

    first = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )
    reconciled = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )

    assert first["status"] == "INTELLIGENCE_COMPLETED"
    assert json.loads(first["raw"]) == envelope
    assert reconciled == first
    assert graph.calls == 1


def test_transport_rejects_compiled_mutation_surface(tmp_path):
    runtime = _external_runtime_module()
    request = _semantic_runtime_request(tmp_path)
    graph = _RuntimeGraph(
        set(runtime.SEMANTIC_TOOLS) | {"write_file"},
        output=_runtime_record("record_finding", {}),
    )

    result = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["error"] == "RuntimeErrorBounded"
    assert graph.calls == 0


def test_hidden_mutation_call_is_not_accepted_as_semantic_result(tmp_path):
    runtime = _external_runtime_module()
    request = _semantic_runtime_request(tmp_path)
    graph = _RuntimeGraph(
        runtime.SEMANTIC_TOOLS,
        output=_runtime_record("write_file", {"path": "forbidden"}),
    )

    result = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["error"] == "RuntimeErrorBounded"
    assert graph.calls == 1


def test_ambiguous_graph_outcome_reconciles_without_second_invoke(tmp_path):
    runtime = _external_runtime_module()
    request = _semantic_runtime_request(tmp_path)
    graph = _RuntimeGraph(runtime.SEMANTIC_TOOLS, error=TimeoutError("ambiguous"))

    first = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )
    reconciled = runtime._semantic_run(
        request,
        runtime_loader=_runtime_loader,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: graph,
    )

    assert first["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert first["outcome_unknown"] is True
    assert reconciled == first
    assert graph.calls == 1


def test_missing_optional_runtime_fails_closed_at_transport_construction(tmp_path):
    runtime = _external_runtime_module()
    request = _semantic_runtime_request(tmp_path)

    def missing_runtime():
        raise ImportError("deepagents unavailable")

    result = runtime._semantic_run(
        request,
        runtime_loader=missing_runtime,
        model_factory=lambda *_args: object(),
        graph_factory=lambda *_args: pytest.fail("graph must not be built without runtime"),
    )

    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["outcome_unknown"] is True
    assert result["error"] == "ImportError"


def test_open_swe_optional_dependency_contract_is_exactly_pinned():
    nested = tomllib.loads(Path("runtimes/open_swe/pyproject.toml").read_text(encoding="utf-8"))
    root = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert nested["project"]["dependencies"] == [
        "deepagents==0.7.6",
        "google-genai==1.74.0",
        "langchain-core==1.5.2",
        "langchain-google-genai==4.3.2",
    ]
    assert "open-swe" not in root["project"].get("optional-dependencies", {})


def test_real_deepagents_toolnode_is_physically_read_only_when_optional_extra_installed(tmp_path):
    pytest.importorskip("deepagents")
    runtime = _external_runtime_module()
    assert runtime.SEMANTIC_TOOLS == frozenset({
        "glob",
        "grep",
        "ls",
        "read_file",
        "record_finding",
    })
