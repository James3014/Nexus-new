from __future__ import annotations

import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.ops.hybrid_replication_activation as activation
import scripts.ops.hybrid_replication_daemon as daemon

FAKE_GH = """#!{python}
import json, os, sys

log = os.environ["FAKE_GH_LOG"]
state_path = os.environ["FAKE_GH_STATE"]
argv = sys.argv[1:]
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(argv) + "\\n")
if os.environ.get("FAKE_GH_FAIL_REPO") and os.environ["FAKE_GH_FAIL_REPO"] in argv:
    sys.stderr.write("boom")
    sys.exit(1)
try:
    state = json.load(open(state_path, encoding="utf-8"))
except FileNotFoundError:
    state = {{}}
repo = argv[argv.index("--repo") + 1]
if argv[:2] == ["variable", "set"]:
    state.setdefault(repo, {{}})[argv[2]] = argv[argv.index("--body") + 1]
    json.dump(state, open(state_path, "w", encoding="utf-8"))
elif argv[:2] == ["variable", "list"]:
    rows = [{{"name": k, "value": v}} for k, v in state.get(repo, {{}}).items()]
    print(json.dumps(rows))
else:
    sys.exit(64)
"""

EXCLUDED = ["James3014/Nexus-new#1553", "James3014/Nexus-new#1500"]


def _manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "nexus.hybrid_replication.activation_manifest.v1",
        "generation": "V11",
        "activation_state": "AUTOMATIC_CAPTURE_READY",
        "t_auto": "2026-10-12T00:00:00Z",
        "excluded_tasks": list(EXCLUDED),
        "readiness_control_token": "tok-123",
    }
    payload.update(overrides)
    return payload


def _write_manifest(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "manifest.json"
    payload = _manifest_payload(**overrides)
    for key in [key for key, value in overrides.items() if value is ...]:
        payload.pop(key)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path, Path]:
    script = tmp_path / "fake_gh"
    script.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    state = tmp_path / "gh_state.json"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    return str(script), log, state


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_default_repositories_match_daemon_candidate_list() -> None:
    assert activation.CANDIDATE_REPOSITORIES == daemon.CANDIDATE_REPOSITORIES
    assert len(activation.CANDIDATE_REPOSITORIES) == 8


def test_variable_names_match_capture_workflow() -> None:
    workflow = Path(".github/workflows/hybrid-replication-capture.yml").read_text(encoding="utf-8")
    for name in activation.VARIABLE_NAMES:
        assert f"vars.{name}" in workflow


def test_render_derives_exclusion_hash_and_covers_every_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path)
    assert activation.main(["render", "--manifest", str(manifest)]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert sorted(rendered) == sorted(activation.CANDIDATE_REPOSITORIES)
    expected_hash = hashlib.sha256(",".join(sorted(EXCLUDED)).encode("utf-8")).hexdigest()
    for variables in rendered.values():
        assert variables == {
            "NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE": "AUTOMATIC_CAPTURE_READY",
            "NEXUS_HYBRID_REPLICATION_T_AUTO": "2026-10-12T00:00:00Z",
            "NEXUS_HYBRID_REPLICATION_EXCLUDED_TASKS": ",".join(sorted(EXCLUDED)),
            "NEXUS_HYBRID_REPLICATION_EXCLUSION_SET_SHA256": expected_hash,
            "NEXUS_HYBRID_REPLICATION_READINESS_CONTROL_TOKEN": "tok-123",
        }


def test_render_not_ready_uses_empty_strings_and_empty_set_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(
        tmp_path,
        activation_state="NOT_READY",
        t_auto=None,
        excluded_tasks=[],
        readiness_control_token="",
        repositories=["James3014/Nexus-new"],
    )
    assert activation.main(["render", "--manifest", str(manifest)]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert list(rendered) == ["James3014/Nexus-new"]
    variables = rendered["James3014/Nexus-new"]
    assert variables["NEXUS_HYBRID_REPLICATION_T_AUTO"] == ""
    assert variables["NEXUS_HYBRID_REPLICATION_EXCLUDED_TASKS"] == ""
    assert (
        variables["NEXUS_HYBRID_REPLICATION_EXCLUSION_SET_SHA256"]
        == hashlib.sha256(b"").hexdigest()
    )
    assert variables["NEXUS_HYBRID_REPLICATION_READINESS_CONTROL_TOKEN"] == ""


def test_push_sets_every_variable_for_every_repository_without_shell(
    tmp_path: Path, fake_gh: tuple[str, Path, Path]
) -> None:
    gh, log, _ = fake_gh
    manifest = _write_manifest(tmp_path)
    assert activation.main(["push", "--manifest", str(manifest), "--gh", gh]) == 0
    calls = _calls(log)
    assert len(calls) == 8 * 5
    expected: list[list[str]] = []
    for repository in activation.CANDIDATE_REPOSITORIES:
        for name, value in activation.load_manifest(manifest).variables().items():
            expected.append(["variable", "set", name, "--repo", repository, "--body", value])
    assert calls == expected


def test_push_reports_failures_and_still_attempts_all_repositories(
    tmp_path: Path,
    fake_gh: tuple[str, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gh, log, _ = fake_gh
    monkeypatch.setenv("FAKE_GH_FAIL_REPO", "James3014/devspace")
    manifest = _write_manifest(tmp_path)
    assert activation.main(["push", "--manifest", str(manifest), "--gh", gh]) == 3
    report = json.loads(capsys.readouterr().out)
    assert len(report["failures"]) == 5
    assert {item["repository"] for item in report["failures"]} == {"James3014/devspace"}
    assert len(_calls(log)) == 40


def test_readback_passes_after_push(
    tmp_path: Path, fake_gh: tuple[str, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    gh, log, _ = fake_gh
    manifest = _write_manifest(tmp_path)
    assert activation.main(["push", "--manifest", str(manifest), "--gh", gh]) == 0
    capsys.readouterr()
    log.write_text("", encoding="utf-8")
    assert activation.main(["readback", "--manifest", str(manifest), "--gh", gh]) == 0
    assert json.loads(capsys.readouterr().out)["drift"] == []
    assert _calls(log) == [
        ["variable", "list", "--repo", repository, "--json", "name,value"]
        for repository in activation.CANDIDATE_REPOSITORIES
    ]


def test_readback_reports_drift_and_exits_2(
    tmp_path: Path, fake_gh: tuple[str, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    gh, _, state = fake_gh
    manifest = _write_manifest(tmp_path)
    assert activation.main(["push", "--manifest", str(manifest), "--gh", gh]) == 0
    capsys.readouterr()
    live = json.loads(state.read_text(encoding="utf-8"))
    live["James3014/devspace"]["NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE"] = "NOT_READY"
    del live["James3014/nexus-core"]["NEXUS_HYBRID_REPLICATION_T_AUTO"]
    state.write_text(json.dumps(live), encoding="utf-8")

    assert activation.main(["readback", "--manifest", str(manifest), "--gh", gh]) == 2
    drift = json.loads(capsys.readouterr().out)["drift"]
    assert drift == [
        {
            "repository": "James3014/devspace",
            "variable": "NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE",
            "expected": "AUTOMATIC_CAPTURE_READY",
            "actual": "NOT_READY",
        },
        {
            "repository": "James3014/nexus-core",
            "variable": "NEXUS_HYBRID_REPLICATION_T_AUTO",
            "expected": "2026-10-12T00:00:00Z",
            "actual": None,
        },
    ]


def test_readback_gh_failure_is_drift(
    tmp_path: Path,
    fake_gh: tuple[str, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gh, _, _ = fake_gh
    monkeypatch.setenv("FAKE_GH_FAIL_REPO", "James3014/nexus-runtime")
    manifest = _write_manifest(tmp_path, repositories=["James3014/nexus-runtime"])
    assert activation.main(["readback", "--manifest", str(manifest), "--gh", gh]) == 2
    drift = json.loads(capsys.readouterr().out)["drift"]
    assert drift[0]["error"] == "gh_variable_list_failed"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"activation_state": "AUTOMATIC_CAPTURE_READY", "t_auto": None}, "requires_t_auto"),
        ({"activation_state": "BOGUS"}, "invalid_activation_state"),
        ({"t_auto": "2026-10-12 00:00:00"}, "t_auto_must_be_rfc3339_utc_or_null"),
        ({"schema": "other.v1"}, "manifest_schema_mismatch"),
        ({"exclusion_set_sha256": "a" * 64}, "derived_and_must_not_be_supplied"),
        ({"surprise": 1}, "unknown_manifest_keys"),
        ({"generation": ...}, "missing_manifest_keys"),
        ({"excluded_tasks": ["a#1", "a#1"]}, "excluded_tasks_must_be_unique"),
        ({"excluded_tasks": ["a#1,b#2"]}, "excluded_tasks_must_be_list_of_comma_free_strings"),
        ({"readiness_control_token": None}, "readiness_control_token_must_be_string"),
        ({"repositories": []}, "repositories_must_be_non_empty_list_of_strings"),
        ({"repositories": ["a/b", "a/b"]}, "repositories_must_be_unique"),
    ],
)
def test_invalid_manifest_is_rejected_before_any_gh_call(
    tmp_path: Path,
    fake_gh: tuple[str, Path, Path],
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, Any],
    error: str,
) -> None:
    gh, log, _ = fake_gh
    manifest = _write_manifest(tmp_path, **overrides)
    assert activation.main(["push", "--manifest", str(manifest), "--gh", gh]) == 1
    assert error in capsys.readouterr().err
    assert not log.exists()


def test_unreadable_manifest_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert activation.main(["render", "--manifest", str(tmp_path / "missing.json")]) == 1
    assert "manifest_unreadable" in capsys.readouterr().err


def test_runner_is_injectable_and_invoked_without_shell() -> None:
    seen: list[dict[str, Any]] = []

    class Done:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def runner(argv: list[str], **kwargs: Any) -> Done:
        seen.append({"argv": argv, **kwargs})
        return Done()

    manifest = activation.parse_manifest(_manifest_payload(repositories=["James3014/Nexus-new"]))
    assert activation.push(manifest, gh="/opt/gh", runner=runner) == []
    assert len(seen) == 5
    assert all(call["argv"][0] == "/opt/gh" for call in seen)
    assert all(
        call["check"] is False and call["capture_output"] is True and call["text"] is True
        for call in seen
    )
    assert all("shell" not in call for call in seen)


def test_contract_points_to_activation_script() -> None:
    contract = json.loads(
        Path("docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        contract["activation_manifest"]["script"] == "scripts/ops/hybrid_replication_activation.py"
    )
    assert Path(contract["activation_manifest"]["script"]).is_file()
