"""Repository-surface checks for machine-local TLS and private-key leakage."""

import subprocess
from pathlib import Path

PRIVATE_KEY_SUFFIXES = (".key",)
PEM_PRIVATE_KEY_HEADERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _tracked_paths(repo: Path) -> tuple[str, ...]:
    result = _git(repo, "ls-files", "-z")
    assert result.returncode == 0, result.stderr
    return tuple(path for path in result.stdout.rstrip("\0").split("\0") if path)


def _tracked_private_key_paths(repo: Path) -> tuple[str, ...]:
    return tuple(
        path for path in _tracked_paths(repo) if path.lower().endswith(PRIVATE_KEY_SUFFIXES)
    )


def _tracked_pem_private_key_paths(repo: Path) -> tuple[str, ...]:
    matches: set[str] = set()
    for header in PEM_PRIVATE_KEY_HEADERS:
        result = _git(repo, "grep", "--cached", "-I", "-l", "-e", header, "--")
        assert result.returncode in (0, 1), result.stderr
        matches.update(path for path in result.stdout.splitlines() if path)
    return tuple(sorted(matches))


def _init_fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture-repo"
    result = subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return repo


def test_root_tailscale_tls_artifacts_are_ignored_without_blanket_cert_rules() -> None:
    repo = Path(__file__).resolve().parents[2]
    for path in ("machine.ts.net.key", "machine.ts.net.crt"):
        result = _git(repo, "check-ignore", "--no-index", "--quiet", "--", path)
        assert result.returncode == 0, path

    for path in ("nested/machine.ts.net.crt", "machine.crt"):
        result = _git(repo, "check-ignore", "--no-index", "--quiet", "--", path)
        assert result.returncode == 1, path


def test_clean_repository_has_no_tracked_private_key_suffixes_or_pem_headers() -> None:
    repo = Path(__file__).resolve().parents[2]
    assert _tracked_private_key_paths(repo) == ()
    assert _tracked_pem_private_key_paths(repo) == ()


def test_tracked_private_key_suffix_is_rejected_with_path_only_diagnostics(tmp_path: Path) -> None:
    repo = _init_fixture_repo(tmp_path)
    private_key = repo / "fixtures" / "machine.key"
    private_key.parent.mkdir()
    private_key.write_text("fixture placeholder\n", encoding="utf-8")
    result = _git(repo, "add", "--", "fixtures/machine.key")
    assert result.returncode == 0, result.stderr

    assert _tracked_private_key_paths(repo) == ("fixtures/machine.key",)


def test_tracked_pem_private_key_header_is_rejected_with_path_only_diagnostics(
    tmp_path: Path,
) -> None:
    repo = _init_fixture_repo(tmp_path)
    fixture = repo / "fixtures" / "settings.txt"
    fixture.parent.mkdir()
    fixture.write_text(f"{PEM_PRIVATE_KEY_HEADERS[0]}\n", encoding="utf-8")
    result = _git(repo, "add", "--", "fixtures/settings.txt")
    assert result.returncode == 0, result.stderr

    assert _tracked_pem_private_key_paths(repo) == ("fixtures/settings.txt",)
