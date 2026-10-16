"""PR-5e: executor resolution is observable; executor self-check for the live Gateway."""

from __future__ import annotations

import logging
import sys
from typing import Any

import pytest

from nexus.core import capability_executor_registry as executor_registry
from nexus.services import capability_registry as registry
from nexus.services import executor_self_check


class _ResolverBoom(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _clean_errors():
    registry.clear_executor_resolution_errors()
    yield
    registry.clear_executor_resolution_errors()


def _raise_on(name_key: str, message: str = "registry exploded"):
    real = executor_registry.get_executor

    def fake(key: str) -> Any:
        if key == name_key:
            raise _ResolverBoom(message)
        return real(key)

    return fake


def test_resolver_raising_reports_error_reason_and_boolean_false(monkeypatch, caplog):
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate"))
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        status = registry.executor_resolution_status("pregate")
        assert registry._has_physical_executor("pregate") is False

    assert status["status"] == "error"
    reason = status["error"]
    assert reason["capability"] == "pregate"
    assert reason["registry_key"] == "pregate"
    assert reason["error_type"] == "_ResolverBoom"
    assert reason["error_message"] == "registry exploded"
    assert reason["resolver_origin"] == registry.HOST_EXECUTOR_RESOLVER_ORIGIN
    assert registry.last_executor_resolution_errors()["pregate"] == reason
    # WARNING once per (name, exception type), not once per call.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "pregate" in warnings[0].getMessage()


def test_resolver_returning_none_is_missing(monkeypatch):
    monkeypatch.setattr(executor_registry, "get_executor", lambda key: None)
    status = registry.executor_resolution_status("pregate")
    assert status["status"] == "missing"
    assert "error" not in status
    assert registry._has_physical_executor("pregate") is False
    assert registry.last_executor_resolution_errors() == {}


def test_resolved_executor_reports_resolved_and_clears_stale_error(monkeypatch):
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("sandbox_runner"))
    assert registry.executor_resolution_status("sandbox")["status"] == "error"
    monkeypatch.undo()
    status = registry.executor_resolution_status("sandbox")
    assert status["status"] == "resolved"
    assert status["registry_key"] == "sandbox_runner"
    assert status["executor"]
    assert registry._has_physical_executor("sandbox") is True
    assert "sandbox" not in registry.last_executor_resolution_errors()


def test_untrusted_error_text_is_sanitized_and_truncated(monkeypatch, caplog):
    hostile = "line1\nline2\x1b[31m::error::" + "x" * 500
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate", hostile))
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        reason = registry.executor_resolution_status("pregate")["error"]
    message = reason["error_message"]
    assert "\n" not in message and "\x1b" not in message
    assert len(message) <= 200
    assert all("\n" not in r.getMessage() and "\x1b" not in r.getMessage() for r in caplog.records)


def test_wiring_matrix_row_carries_executor_resolution_error(monkeypatch):
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("ultra_review"))
    rows = {row["name"]: row for row in registry.build_wiring_matrix()["rows"]}
    error = rows["ultra_review"]["executor_resolution_error"]
    assert error["error_type"] == "_ResolverBoom"
    assert "executor_resolution_error" not in rows["pregate"]


def test_no_executor_receipt_says_resolver_raised(monkeypatch):
    def import_fails(key: str) -> Any:
        raise ImportError("executor registry import failed")

    monkeypatch.setattr(executor_registry, "get_executor", import_fails)
    assert registry.build_real_executor_invoker("ultra_review") is None
    invokers = registry.build_default_mainchain_invokers(include_postflight_gates=False)
    # Escalation-gated capability, triggered: BLOCKED receipt names the resolver error.
    receipt = invokers["xray"]({"task_id": "t1", "escalate_triggered": True})
    assert receipt["reason"] == registry.BLOCKED_EXECUTOR_UNAVAILABLE
    assert receipt["executor_resolution_error"]["error_type"] == "ImportError"
    assert receipt["response"]["executor_resolution_error"]["capability"] == "xray"
    # Default fallback (explicit skip) also carries it instead of a bare "not implemented".
    skipped = invokers["pregate"]({"task_id": "t1"})
    assert skipped["executor_resolution_error"]["capability"] == "pregate"


def test_runtime_seam_resolver_records_and_reraises(monkeypatch):
    from nexus.services import runtime_compat

    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("ultra_review"))
    with pytest.raises(_ResolverBoom):
        runtime_compat._resolve_physical_executor("ultra_review")
    reason = registry.last_executor_resolution_errors()["ultra_review"]
    assert reason["resolver_origin"] == runtime_compat.RUNTIME_SEAM_RESOLVER_ORIGIN


def test_self_check_reports_every_capability_and_passes_on_test_registry():
    report = executor_self_check.collect()
    assert report["ok"] is True
    assert report["exit_code"] == 0
    assert report["resolver_registered"] is True
    rows = {row["capability"]: row for row in report["capabilities"]}
    for name in executor_self_check.DEFAULT_REQUIRED:
        assert rows[name]["status"] == "resolved", name
        assert rows[name]["required"] is True
    assert report["status_counts"]["resolved"] >= len(executor_self_check.DEFAULT_REQUIRED)
    assert report["capability_count"] == len(rows)


def test_self_check_surfaces_resolver_error_and_fails(monkeypatch, capsys):
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("file_lock_security_gate"))
    assert executor_self_check.main(["--check-executors"]) == 1
    out = capsys.readouterr().out
    assert "REQUIRED file_lock (file_lock_security_gate): error _ResolverBoom" in out
    report = executor_self_check.collect()
    assert report["unresolved_required"] == ["file_lock"]
    assert report["capabilities"]
    row = next(r for r in report["capabilities"] if r["capability"] == "file_lock")
    assert row["error"]["error_type"] == "_ResolverBoom"


def test_self_check_missing_required_fails(monkeypatch):
    monkeypatch.setattr(executor_registry, "get_executor", lambda key: None)
    report = executor_self_check.collect(("pregate",))
    assert report["ok"] is False
    assert report["unresolved_required"] == ["pregate"]
    assert executor_self_check.main(["--require", "pregate"]) == 1


def test_self_check_bootstrap_failure_exits_2(monkeypatch):
    def boom(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == executor_self_check.BOOTSTRAP_MODULE:
            raise RuntimeError("gateway bootstrap broke")
        return real_import(name, *args, **kwargs)

    real_import = executor_self_check.importlib.import_module
    monkeypatch.setattr(executor_self_check.importlib, "import_module", boom)
    report = executor_self_check.collect()
    assert report["exit_code"] == 2
    assert report["bootstrap_error"]["error_message"] == "gateway bootstrap broke"


def test_runtime_compat_module_entry_runs_self_check():
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "nexus.services.runtime_compat", "--check-executors", "--json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert '"schema": "nexus.executor_self_check.v1"' in proc.stdout


_GHP = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
_URL_PASSWORD = "hunter2-very-secret"
_HOSTILE_SECRET = (
    f"clone failed token={_GHP} remote https://deploy:{_URL_PASSWORD}@git.example.com/r.git"
)


def test_secrets_are_redacted_from_log_receipt_and_self_check(monkeypatch, caplog, capsys):
    monkeypatch.setattr(
        executor_registry, "get_executor", _raise_on("ultra_review", _HOSTILE_SECRET)
    )
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        reason = registry.executor_resolution_status("ultra_review")["error"]
        invokers = registry.build_default_mainchain_invokers(include_postflight_gates=False)
        receipt = invokers["ultra_review"]({"task_id": "t1", "escalate_triggered": True})
    assert executor_self_check.main(["--check-executors"]) == 1
    text_out = capsys.readouterr().out
    assert executor_self_check.main(["--json"]) == 1
    json_out = capsys.readouterr().out
    surfaces = {
        "reason": reason["error_message"],
        "receipt": repr(receipt),
        "log": "\n".join(r.getMessage() for r in caplog.records),
        "text": text_out,
        "json": json_out,
    }
    assert "[REDACTED]" in reason["error_message"]
    assert "executor_resolution_error" in receipt
    for where, value in surfaces.items():
        assert _GHP not in value, where
        assert _URL_PASSWORD not in value, where
        assert "ghp_" not in value, where


def test_self_check_sanitizer_matches_registry_sanitizer():
    samples = [
        _HOSTILE_SECRET,
        "Authorization: Bearer abcdefgh.ijklmnop.qrstuvwx",
        "password: 'p a s s' api_key=XYZ123 " + "AK" + "IAABCDEFGHIJKLMNOP",
        "No module named nexus.core.capability_executor_registry",
        "line\nbreak\x1b[0m" + "y" * 300,
    ]
    for sample in samples:
        assert executor_self_check._sanitize_resolution_text(
            sample
        ) == registry._sanitize_resolution_text(sample)
    assert "[REDACTED]" in executor_self_check._sanitize_resolution_text(samples[1])
    assert "abcdefgh" not in executor_self_check._sanitize_resolution_text(samples[1])
    plain = executor_self_check._sanitize_resolution_text(samples[3])
    assert plain == samples[3]


def test_self_check_raising_non_required_resolver_fails(monkeypatch, capsys):
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("xray"))
    report = executor_self_check.collect()
    assert report["unresolved_required"] == []
    assert report["error_capabilities"] == ["xray"]
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert executor_self_check.main([]) == 1
    assert "FAIL: resolver raised for: xray" in capsys.readouterr().out


def test_self_check_internal_failure_after_bootstrap_exits_2(monkeypatch, capsys):
    from nexus_runtime.support.services import capability_registry as runtime_registry

    def broken() -> Any:
        raise LookupError("planner node table unreadable")

    monkeypatch.setattr(runtime_registry, "list_planner_capability_names", broken)
    report = executor_self_check.collect()
    assert report["exit_code"] == 2
    assert report["ok"] is False
    assert report["internal_error"]["error_type"] == "LookupError"
    assert executor_self_check.main([]) == 2
    out = capsys.readouterr().out
    assert out.startswith(
        executor_self_check.TEXT_LINE_PREFIX
        + "INTERNAL_FAILED LookupError: planner node table unreadable"
    )
    assert "Traceback" not in out


def test_self_check_missing_runtime_seam_fails(monkeypatch):
    real_import = executor_self_check.importlib.import_module

    def no_seam(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == executor_self_check.BINDING_MODULE:
            raise ImportError("runtime predates executor_binding")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(executor_self_check.importlib, "import_module", no_seam)
    report = executor_self_check.collect()
    assert report["seam_available"] is False
    assert report["resolver_registered"] is False
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert any("seam unavailable" in failure for failure in report["failures"])
    # Rows still come from the host registry for reference.
    assert report["status_counts"]["resolved"] > 0


def test_self_check_unregistered_resolver_fails(monkeypatch):
    from nexus_runtime.support.services import executor_binding

    monkeypatch.setattr(executor_binding, "_resolver", None)
    report = executor_self_check.collect()
    assert report["resolver_registered"] is False
    assert report["exit_code"] == 1
    assert "no resolver registered with the runtime executor seam" in report["failures"]


def test_runtime_seam_records_under_alias_names_and_clears_on_success(monkeypatch):
    from nexus.services import runtime_compat

    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("sandbox_runner"))
    with pytest.raises(_ResolverBoom):
        runtime_compat._resolve_physical_executor("sandbox_runner")
    reason = registry.executor_resolution_error("sandbox")
    assert reason is not None
    assert reason["registry_key"] == "sandbox_runner"
    assert reason["resolver_origin"] == runtime_compat.RUNTIME_SEAM_RESOLVER_ORIGIN
    monkeypatch.undo()
    assert runtime_compat._resolve_physical_executor("sandbox_runner") is not None
    assert registry.executor_resolution_error("sandbox") is None
    assert "sandbox_runner" not in registry.last_executor_resolution_errors()


def test_status_never_raises_when_key_mapping_fails(monkeypatch):
    def broken_key(name: str) -> str:
        raise KeyError(name)

    monkeypatch.setattr(registry, "_resolve_executor_registry_key", broken_key)
    status = registry.executor_resolution_status("pregate")
    assert status["status"] == "error"
    assert status["error"]["error_type"] == "KeyError"
    assert registry._has_physical_executor("pregate") is False


class _HostileExecutorProxy:
    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"proxy refuses {name}")


def test_executor_whose_getattr_raises_is_error_not_exception(monkeypatch):
    monkeypatch.setattr(executor_registry, "get_executor", lambda key: _HostileExecutorProxy())
    status = registry.executor_resolution_status("pregate")
    assert status["status"] == "error"
    assert status["error"]["error_type"] == "RuntimeError"
    assert registry._has_physical_executor("pregate") is False
    report = executor_self_check.collect(("pregate",))
    row = next(r for r in report["capabilities"] if r["capability"] == "pregate")
    assert row["status"] == "error"
    assert report["exit_code"] == 1


def test_ci_workflow_commands_never_begin_an_output_line(monkeypatch, capsys, caplog):
    message = "::error title=x::boom ::add-mask::abc ##[group]g"
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate", message))
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        reason = registry.executor_resolution_status("pregate")["error"]
    assert "::" not in reason["error_message"]
    assert "##[" not in reason["error_message"]
    assert executor_self_check.main([]) == 1
    out = capsys.readouterr().out
    for line in out.splitlines():
        assert line.startswith(executor_self_check.TEXT_LINE_PREFIX), line
        assert not line.lstrip().startswith(("::", "##["))
    assert "::error" not in out and "::add-mask" not in out and "##[" not in out
    for record in caplog.records:
        assert "::" not in record.getMessage()


def test_warning_dedupe_resets_on_recovery_and_keys_on_message(monkeypatch, caplog):
    def warnings() -> list[logging.LogRecord]:
        return [r for r in caplog.records if r.levelno == logging.WARNING]

    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate", "first"))
        registry.executor_resolution_status("pregate")
        registry.executor_resolution_status("pregate")
        assert len(warnings()) == 1
        # Same type, different message: logged.
        monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate", "second"))
        registry.executor_resolution_status("pregate")
        assert len(warnings()) == 2
        # Recovery, then the first failure again: logged again.
        monkeypatch.undo()
        assert registry.executor_resolution_status("pregate")["status"] == "resolved"
        monkeypatch.setattr(executor_registry, "get_executor", _raise_on("pregate", "first"))
        registry.executor_resolution_status("pregate")
        assert len(warnings()) == 3
