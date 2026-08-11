from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops import repo_doctor


def write_core(root: Path) -> None:
    for relative in repo_doctor.CORE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")


def test_clean_core_does_not_require_provider_tools_or_secrets(tmp_path, monkeypatch):
    write_core(tmp_path)
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    for name in repo_doctor.PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(repo_doctor.shutil, "which", lambda _name: None)

    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 8))

    assert report["core"]["status"] == "ready"
    assert report["provider"]["status"] == "optional_missing"
    assert report["provider"]["required_for_core"] is False
    assert "production-ready" not in json.dumps(report).lower()


def test_unwritable_cache_fails_precisely(tmp_path, monkeypatch):
    write_core(tmp_path)
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))

    def deny_cache(*_args, **_kwargs):
        raise PermissionError("unwritable")

    monkeypatch.setattr(repo_doctor.tempfile, "NamedTemporaryFile", deny_cache)
    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 8))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["passed"] is False
    assert cache["reason"] == "cache_unwritable"
    assert "UV_CACHE_DIR" in cache["guidance"]


def test_project_local_cache_is_allowed_when_repo_is_under_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = home / "repo"
    root.mkdir(parents=True)
    write_core(root)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)

    report = repo_doctor.build_report(root, python_version=(3, 12, 8))

    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["passed"] is True
    assert cache["location"] == "project_local"


def test_relative_and_global_home_cache_are_rejected_before_write(tmp_path, monkeypatch):
    write_core(tmp_path)
    monkeypatch.setenv("UV_CACHE_DIR", "relative-cache")
    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 8))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "cache_path_not_absolute"
    assert not (tmp_path / "relative-cache").exists()

    home_cache = Path.home() / ".cache" / "nexus-doctor-must-not-create"
    monkeypatch.setenv("UV_CACHE_DIR", str(home_cache))
    report = repo_doctor.build_report(tmp_path, python_version=(3, 12, 8))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "home_cache_rejected"
    assert not home_cache.exists()


def test_cache_symlink_escape_is_rejected_before_write(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    write_core(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    cache_parent = root / ".tmp"
    cache_parent.mkdir()
    (cache_parent / "uv-cache").symlink_to(outside, target_is_directory=True)
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)

    report = repo_doctor.build_report(root, python_version=(3, 12, 8))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "project_cache_symlink_escape"

    configured_link = tmp_path / "configured-cache"
    configured_link.symlink_to("/usr", target_is_directory=True)
    monkeypatch.setenv("UV_CACHE_DIR", str(configured_link))
    report = repo_doctor.build_report(root, python_version=(3, 12, 8))
    cache = next(item for item in report["core"]["checks"] if item["name"] == "uv_cache")
    assert cache["reason"] == "cache_location_not_allowed"


@pytest.mark.parametrize("version", [(3, 10, 9), (3, 11, 9), (3, 15, 0)])
def test_unsupported_python_is_core_blocker(tmp_path, version):
    write_core(tmp_path)
    report = repo_doctor.build_report(tmp_path, python_version=version)
    python = next(item for item in report["core"]["checks"] if item["name"] == "python")
    assert report["core"]["status"] == "blocked"
    assert python["reason"] == "unsupported_python"


def test_supported_non_pinned_python_is_explicit_warning_not_blocker(tmp_path):
    write_core(tmp_path)
    report = repo_doctor.build_report(tmp_path, python_version=(3, 14, 6))
    python = next(item for item in report["core"]["checks"] if item["name"] == "python")
    assert report["core"]["status"] == "ready"
    assert python["reason"] == "supported_non_pinned"
    assert python["pinned_match"] is False
    assert "Python 3.12" in python["guidance"]


def test_json_cli_is_secret_and_home_path_free(capsys, tmp_path, monkeypatch):
    write_core(tmp_path)
    secrets = {
        "GEMINI_API_KEY": "gemini-live-secret",
        "GEMINI_MODEL": "private-model",
        "NEXUS_GEMINI_MODEL_NAME": "private-nexus-model",
        "OPENAI_API_KEY": "openai-live-secret",
        "JINA_API_KEY": "jina-live-secret",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    exit_code = repo_doctor.main(["--format", "json", "--repo-root", str(tmp_path)])
    output = capsys.readouterr().out
    assert exit_code in {0, 1}
    assert all(value not in output for value in secrets.values())
    assert str(Path.home()) not in output
    payload = json.loads(output)
    assert payload["provider"]["status"] == "optional_configured_unverified"
    assert payload["provider"]["reason"] == "provider_inputs_detected_without_auth_probe"


def test_tracked_setup_surfaces_are_portable_and_redacted():
    preflight = Path("scripts/ops/_nexus_preflight.sh").read_text()
    template = Path(".env.template").read_text()
    assert "/Users/" not in preflight
    assert "PRODUCTION-READY" not in preflight
    assert "NEXUS_PREFLIGHT_PROVIDER" in preflight
    assert "value redacted" in preflight
    assert "your_api_key" not in template
    assert "OPENAI_API_KEY=" in template
    assert Path(".python-version").read_text().strip() == "3.12"
