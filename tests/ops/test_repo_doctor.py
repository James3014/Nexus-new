from __future__ import annotations

import json
from pathlib import Path

from scripts.ops import repo_doctor


def write_core(root: Path) -> None:
    for relative in repo_doctor.CORE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")


def test_core_is_provider_free_and_reports_optional_provider_separately(tmp_path, monkeypatch):
    write_core(tmp_path)
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    for name in repo_doctor.PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(repo_doctor.shutil, "which", lambda _name: None)

    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 8))

    assert report["core"]["status"] == "ready"
    assert report["provider"] == {
        "status": "optional_missing",
        "required_for_core": False,
        "tools": {"gemini": False, "node": False},
        "variables_present": {name: False for name in repo_doctor.PROVIDER_VARS},
        "reason": "provider_not_detected",
    }


def test_missing_core_file_fails_closed(tmp_path, monkeypatch):
    write_core(tmp_path)
    (tmp_path / "uv.lock").unlink()
    monkeypatch.setattr(repo_doctor.shutil, "which", lambda _name: False)

    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 0))

    assert report["core"]["status"] == "blocked"
    assert any(item["reason"] == "missing_core_file" for item in report["core"]["checks"])


def test_cache_paths_are_absolute_and_contained(tmp_path, monkeypatch):
    write_core(tmp_path)
    monkeypatch.setenv("UV_CACHE_DIR", "relative-cache")
    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 0))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "cache_path_not_absolute"
    assert not (tmp_path / "relative-cache").exists()

    outside = Path.home() / "doctor-outside-cache"
    monkeypatch.setenv("UV_CACHE_DIR", str(outside))
    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 0))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "cache_location_not_allowed"
    assert not outside.exists()


def test_unsupported_python_blocks(tmp_path):
    write_core(tmp_path)
    report = repo_doctor.build_report(tmp_path, python_version=(3, 9, 9))
    python = next(item for item in report["core"]["checks"] if item["name"] == "python")
    assert report["core"]["status"] == "blocked"
    assert python["reason"] == "unsupported_python"


def test_json_output_redacts_secret_values(tmp_path, monkeypatch, capsys):
    write_core(tmp_path)
    secret = "doctor-secret-must-not-appear"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr(repo_doctor.shutil, "which", lambda _name: False)

    exit_code = repo_doctor.main(["--format", "json", "--repo-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert secret not in output
    payload = json.loads(output)
    assert payload["provider"]["variables_present"]["OPENAI_API_KEY"] is True
    assert "runtime" in payload["claim"]
