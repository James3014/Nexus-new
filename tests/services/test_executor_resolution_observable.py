"""PR-5e: executor resolution is observable; executor self-check for the live Gateway."""

from __future__ import annotations

import logging
import sys
import time
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


# Secret-shaped fixtures are built from split literals (secret audit, check_fixture_secret_literals).
_GH_TOKEN = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz0123456789"
_AWS_ID = "AK" + "IA" + "IOSFODNN7EXAMPLE"
_OPENAI = "sk-" + "proj-" + "abcdefghij1234567890"
_SLACK = "xo" + "xb-" + "1234567890-abcdefghij"
_JWT = (
    "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0"
    ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)
_AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY"

# (label, raw text, substrings that must NOT survive, substrings that MUST survive)
_REDACTION_CASES = [
    ("ghp kv", f"SENTINEL token={_GH_TOKEN}", [_GH_TOKEN, "abcdefghijklmnop"], ["SENTINEL token="]),
    ("ghp bare", f"failed with {_GH_TOKEN} now", [_GH_TOKEN], ["failed with", "now"]),
    ("after newline", f"first line\n{_GH_TOKEN}", [_GH_TOKEN], ["first line"]),
    ("after newline kv", "x\npassword=hunter2hunter2", ["hunter2"], ["password="]),
    (
        "two credentials across lines",
        "Authorization: Bearer my_token_12345\npassword: top_secret_password",
        ["my_token_12345", "top_secret_password"],
        ["Authorization:", "password:"],
    ),
    (
        "mixed case auth",
        "AuThOrIzAtIoN: BeArEr abc.DEF-ghi_jkl~mno+pq/rs=",
        ["abc.DEF", "BeArEr"],
        ["AuThOrIzAtIoN:"],
    ),
    ("upper auth", "AUTHORIZATION: bearer X1y2Z3", ["X1y2Z3"], ["AUTHORIZATION:"]),
    (
        "auth no colon",
        "header Authorization Bearer abcdefghijklmnop",
        ["abcdefghijklmnop"],
        ["header"],
    ),
    ("basic", "Basic dXNlcjpwYXNzd29yZA==", ["dXNlcjpw"], ["Basic"]),
    (
        "b64 pad",
        "blob eyJhbGciOiJIUzI1NiJ9-_abcdEFGH1234ijklMNOP== end",
        ["abcdEFGH"],
        ["blob", "end"],
    ),
    ("aws id", f"key {_AWS_ID} used", [_AWS_ID], ["key", "used"]),
    ("aws id kv", f"aws_access_key_id={_AWS_ID}", [_AWS_ID], ["aws_access_key_id="]),
    ("aws secret", f"aws_secret_access_key {_AWS_SECRET}", [_AWS_SECRET, "bPxRfiCY"], []),
    (
        "url creds",
        "https://user:pa55w0rd@github.com/x.git",
        ["pa55w0rd", "user:"],
        ["github.com/x.git"],
    ),
    ("sk", f"openai {_OPENAI}", [_OPENAI], ["openai"]),
    ("slack", _SLACK, [_SLACK, "abcdefghij"], []),
    ("jwt", _JWT, ["hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "zdWIiOiIx", "dozjgNry"], []),
    (
        "pem",
        "-----BEGIN " + "RSA PRIVATE KEY-----MIIEowIBAAKCAQEA",
        ["MIIEowIBAAKCAQEA"],
        [],
    ),
    ("short password", "password: abc", ["abc"], ["password:"]),
    ("quoted kv", 'api_key="sk_live_51Habc"', ["51Habc"], ["api_key="]),
    ("json kv", '{"token": "abcd1234efgh"}', ["abcd1234efgh"], ['{"token": "', '"}']),
    ("escaped json", '{\\"password\\": \\"hunter2\\"}', ["hunter2"], ["password"]),
    (
        "kv inside json string",
        '{"query": "password=secret123"}',
        ["secret123"],
        ['{"query": "password=', '"}'],
    ),
    ("signature b64", "signature=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=", ["MDEyMzQ1"], []),
    (
        "padded 32",
        "blob aaaaaaaaaaaaaaa111111111111111== tail",
        ["aaaaaaaaaaaaaaa111"],
        ["blob", "tail"],
    ),
    (
        "git sha",
        "pinned at e73d152f17d5d06b78da258b62354cca11d6a352",
        ["e73d152f17d5"],
        ["pinned at"],
    ),
    (
        "plain socket",
        "connection refused to 127.0.0.1:8080",
        [],
        ["connection refused to 127.0.0.1:8080"],
    ),
    (
        "module path",
        "No module named 'nexus_runtime.support.services.executor_binding'",
        [],
        ["No module named 'nexus_runtime.support.services.executor_binding'"],
    ),
    (
        "attribute error",
        "AttributeError: module 'nexus.core.capability_executor_registry' has no attribute 'get_executor'",
        [],
        ["module 'nexus.core.capability_executor_registry' has no attribute 'get_executor'"],
    ),
    (
        "site-packages path",
        "/opt/homebrew/lib/python3.14/site-packages/nexus_runtime/support/services/x.py",
        [],
        ["/opt/homebrew/lib/python3.14/site-packages/nexus_runtime/support/services/x.py"],
    ),
]


@pytest.mark.parametrize(
    ("raw", "forbidden", "kept"),
    [case[1:] for case in _REDACTION_CASES],
    ids=[case[0].replace(" ", "_") for case in _REDACTION_CASES],
)
def test_redaction_table(raw, forbidden, kept):
    out = registry._sanitize_resolution_text(raw, 2000)
    assert out == executor_self_check._sanitize_resolution_text(raw, 2000)
    for value in forbidden:
        assert value not in out, (value, out)
    for value in kept:
        assert value in out, (value, out)


@pytest.mark.parametrize(
    "raw",
    ["a.b.token." * 1000, "tokenx" * 4000, "a" * 200_000 + "://", "A1" * 100_000],
    ids=["dotted_token_10k", "tokenx_24k", "long_scheme", "b64_run_200k"],
)
def test_sanitizer_is_linear_on_keyword_laden_input(raw):
    started = time.perf_counter()
    registry._sanitize_resolution_text(raw)
    executor_self_check._sanitize_resolution_text(raw)
    assert time.perf_counter() - started < 0.05


def test_sanitizer_caps_raw_text_before_scanning():
    raw = "x" * 5000 + f" token={_GH_TOKEN}"
    out = registry._sanitize_resolution_text(raw, 10_000)
    assert len(out) <= registry._RESOLUTION_RAW_MAX


def test_registry_key_is_not_recorded_as_pseudo_capability(monkeypatch):
    from nexus.services import runtime_compat

    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("file_lock_security_gate"))
    with pytest.raises(_ResolverBoom):
        runtime_compat._resolve_physical_executor("file_lock_security_gate")
    recorded = registry.last_executor_resolution_errors()
    assert "file_lock" in recorded
    assert "file_lock_security_gate" not in recorded
    # A key that is also a planner capability keeps its own entry.
    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("research"))
    with pytest.raises(_ResolverBoom):
        runtime_compat._resolve_physical_executor("research")
    recorded = registry.last_executor_resolution_errors()
    assert {"research", "research_route"} <= set(recorded)


def test_seam_missing_result_keeps_recorded_error(monkeypatch):
    from nexus.services import runtime_compat

    monkeypatch.setattr(executor_registry, "get_executor", _raise_on("sandbox_runner"))
    with pytest.raises(_ResolverBoom):
        runtime_compat._resolve_physical_executor("sandbox_runner")
    monkeypatch.setattr(executor_registry, "get_executor", lambda key: None)
    assert runtime_compat._resolve_physical_executor("sandbox_runner") is None
    assert registry.executor_resolution_error("sandbox") is not None


def test_warnings_capped_per_capability_and_type(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger=registry.__name__):
        for index in range(12):
            monkeypatch.setattr(
                executor_registry, "get_executor", _raise_on("pregate", f"varying message {index}")
            )
            registry.executor_resolution_status("pregate")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == registry._EXECUTOR_RESOLUTION_WARN_MAX


_ROUND3_CASES = [
    (
        "url query token",
        f"GET https://example.com/api?token={_GH_TOKEN} failed",
        [_GH_TOKEN],
        ["https://example.com/api?token=", "failed"],
    ),
    (
        "url query password",
        "http://host/auth?password=supersecret&x=1#frag",
        ["supersecret"],
        ["http://host/auth?password=", "&x=1#frag"],
    ),
    ("url query api key", f"https://h/v1?api_key={_OPENAI}", [_OPENAI], ["https://h/v1?api_key="]),
    ("url path blob", f"https://h/{_GH_TOKEN}/x", [_GH_TOKEN], ["https://h/", "/x"]),
    ("token in parens", f"failed with token ({_GH_TOKEN})", [_GH_TOKEN], ["failed with token ("]),
    (
        "bearer in parens",
        "error in (Bearer my_token_12345)",
        ["my_token_12345"],
        ["error in (Bearer"],
    ),
    ("angle brackets", f"<{_GH_TOKEN}>", [_GH_TOKEN], ["<", ">"]),
    (
        "plain url",
        "https://docs.example.com/path/page.html?q=1",
        [],
        ["https://docs.example.com/path/page.html?q=1"],
    ),
]


@pytest.mark.parametrize(
    ("raw", "forbidden", "kept"),
    [case[1:] for case in _ROUND3_CASES],
    ids=[case[0].replace(" ", "_") for case in _ROUND3_CASES],
)
def test_redaction_table_round3(raw, forbidden, kept):
    out = registry._sanitize_resolution_text(raw, 2000)
    assert out == executor_self_check._sanitize_resolution_text(raw, 2000)
    for value in forbidden:
        assert value not in out, (value, out)
    for value in kept:
        assert value in out, (value, out)


def test_raw_cap_drops_the_token_it_cuts():
    partial_key = "AK" + "IA1234567890ABCDEF"
    raw = " " * 1985 + partial_key
    for sanitize in (
        registry._sanitize_resolution_text,
        executor_self_check._sanitize_resolution_text,
    ):
        out = sanitize(raw, 5000)
        assert "AK" + "IA1234567890A" not in out
        assert "1234567890" not in out


@pytest.mark.parametrize(
    "identifier",
    [
        "OAuth2AuthenticationError",
        "Http404NotFoundException",
        "harness_preflight_sensor_v2",
        "LocalModelExecutorV2",
    ],
)
def test_identifier_fields_are_never_secret_redacted(identifier):
    assert registry._sanitize_identifier(identifier) == identifier
    assert executor_self_check._sanitize_identifier(identifier) == identifier
    error_class = type(identifier, (RuntimeError,), {})
    reason = registry.record_executor_resolution_error(
        identifier, error_class("boom"), origin="test", registry_key=identifier
    )
    assert reason["capability"] == identifier
    assert reason["registry_key"] == identifier
    assert reason["error_type"] == identifier
    assert identifier in registry.last_executor_resolution_errors()


def test_error_recorded_under_long_versioned_name_is_cleared_by_name():
    name = "harness_preflight_sensor_v2"
    registry.record_executor_resolution_error(
        name, RuntimeError("boom"), origin="test", registry_key=name
    )
    assert registry.executor_resolution_error(name) is not None
    assert "[REDACTED]" not in registry.last_executor_resolution_errors()
    registry._clear_resolution_error(name)
    assert registry.executor_resolution_error(name) is None
    assert registry.last_executor_resolution_errors() == {}


def test_executor_qualname_is_an_identifier(monkeypatch):
    def LocalModelExecutorV2(plan: Any, statement: str) -> Any:  # noqa: N802
        return None

    monkeypatch.setattr(executor_registry, "get_executor", lambda key: LocalModelExecutorV2)
    status = registry.executor_resolution_status("pregate")
    assert status["status"] == "resolved"
    assert status["executor"].endswith("LocalModelExecutorV2")
