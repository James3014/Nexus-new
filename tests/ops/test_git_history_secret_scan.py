import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops.git_history_secret_scan import ScanError, scan_repository


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc


def _commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _commit(repo, "initial", {"README.md": "ok\n"})
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _refresh_remote_ref(repo: Path, branch: str, commit: str) -> None:
    _git(repo, "update-ref", f"refs/remotes/origin/{branch}", commit)


def test_secret_on_non_default_historical_branch_after_deletion_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "checkout", "-b", "feature")
    google_token = "AIza" + "Q7x9mN2pR4sT6vW8yZ1aB3cD5eF7gH9jK2L"
    secret_commit = _commit(
        repo,
        "add secret",
        {"secret.txt": f"GOOGLE_API_KEY={google_token}\n"},
    )
    _commit(repo, "remove secret", {"secret.txt": "removed\n"})
    _refresh_remote_ref(repo, "feature", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert receipt["blocking_finding_count"] >= 1
    assert any(f["object_id"] for f in receipt["findings"] if f["blocking"])
    assert secret_commit in _git(repo, "rev-list", "refs/remotes/origin/feature").stdout


def test_secret_in_commit_message_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    openai_token = "sk-" + "q7A4nB9cD2eF6gH8jK1mN5pR3sT0vW4xY7z"
    _git(repo, "commit", "--allow-empty", "-m", f"token {openai_token}")
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(f["subject_type"] == "commit_message" and f["blocking"] for f in receipt["findings"])


def test_real_pem_block_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    pem = (
        "-----BEGIN PRIVATE KEY-----\n"
        + ("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0123456789+/" * 3)
        + "\n-----END PRIVATE KEY-----\n"
    )
    _commit(repo, "pem", {"key.txt": pem})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert any(f["detector"] == "pem_private_key" and f["blocking"] for f in receipt["findings"])


def test_high_confidence_provider_token_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    github_token = "ghp_" + "q7A4nB9cD2eF6gH8jK1mN5pR3sT0vW4xY7z"
    _commit(repo, "token", {"x.txt": f"GITHUB_TOKEN={github_token}\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    blocking = [f for f in receipt["findings"] if f["blocking"]]
    assert any(f["detector"] == "github_token" for f in blocking)
    assert not any(f["detector"] == "high_entropy_secret_assignment" for f in blocking)


def test_generic_high_entropy_assignment_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "secret", {"x.txt": "client_secret=Q8v6K1mP9zT2yR4uW7nB3cD5fG0hJ2kL\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert any(
        f["detector"] == "high_entropy_secret_assignment" and f["blocking"]
        for f in receipt["findings"]
    )


def test_placeholder_fixture_and_env_template_are_nonblocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(
        repo,
        "fixture",
        {
            "tests/fixture.txt": "OPENAI_API_KEY=sk-example-placeholder-abcdefghijklmnopqrstuvwxyz\n",
            ".env.template": "OPENAI_API_KEY=\nGOOGLE_API_KEY=\n",
        },
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "PASS"
    assert receipt["blocking_finding_count"] == 0


def test_obvious_sequential_provider_fixtures_are_nonblocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    google_fixture = "AIza" + "12345678901234567890123456789012345"
    github_fixture = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    openai_fixture = "sk-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123456"
    _commit(
        repo,
        "sequential fixtures",
        {
            "fixtures.txt": (
                f"GOOGLE_API_KEY={google_fixture}\n"
                f"GITHUB_TOKEN={github_fixture}\n"
                f"OPENAI_API_KEY={openai_fixture}\n"
            )
        },
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    provider_findings = [
        finding
        for finding in receipt["findings"]
        if finding["detector"] in {"google_api_key", "github_token", "openai_api_key"}
    ]
    assert receipt["status"] == "PASS"
    assert len(provider_findings) == 3
    assert all(finding["classification"] == "OBVIOUS_FIXTURE" for finding in provider_findings)


def test_output_is_redacted_and_does_not_emit_secret(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    secret = "sk-" + "q7A4nB9cD2eF6gH8jK1mN5pR3sT0vW4xY7z"
    _commit(repo, "secret", {"x.txt": f"OPENAI_API_KEY={secret}\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    payload = json.dumps(receipt, sort_keys=True)
    assert secret not in payload
    assert receipt["secret_values_emitted"] is False
    assert all("fingerprint" in finding for finding in receipt["findings"])


def test_git_error_fails_closed(tmp_path: Path) -> None:
    nonrepo = tmp_path / "not-a-repo"
    nonrepo.mkdir()
    with pytest.raises(ScanError):
        scan_repository(nonrepo)
