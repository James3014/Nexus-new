import hashlib
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
    begin = "-----" + "BEGIN PRIVATE KEY" + "-----"
    end = "-----" + "END PRIVATE KEY" + "-----"
    pem = begin + "\n" + ("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0123456789+/" * 3) + "\n" + end + "\n"
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
    generic_secret = "R7m4C9x2V6b1K8p3" + "T5y0N2w7D4f9H1j6"
    _commit(repo, "secret", {"x.txt": f"client_secret={generic_secret}\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert any(
        f["detector"] == "high_entropy_secret_assignment" and f["blocking"]
        for f in receipt["findings"]
    )


def test_json_quoted_high_entropy_assignment_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    json_secret = "M9q2V7x4N8b1K6r3" + "T0y5P2w7C4d9F1h8"
    _commit(
        repo,
        "json secret",
        {"config.json": f'{{"client_secret": "{json_secret}"}}\n'},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "high_entropy_secret_assignment" and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_prefixed_aws_secret_access_key_with_punctuation_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    secret_value = "Q8$v6!K1@mP9#zT2%yR4^uW7&nB3*cD5"
    _commit(
        repo,
        "aws secret",
        {"config.env": f'AWS_SECRET_ACCESS_KEY="{secret_value}"\n'},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "high_entropy_secret_assignment" and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_base64_like_api_key_is_blocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    encoded_value = "UVdKak1xN0E0bkI5Y0QyZUY2Z0g4aks9PQ=="
    _commit(repo, "encoded secret", {"x.env": f"api_key={encoded_value}\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "high_entropy_secret_assignment" and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_single_template_reference_is_nonblocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    template_reference = "{" + "runtime_secret_value" + "}"
    _commit(
        repo,
        "template reference",
        {"config.json": f'{{"client_secret": "{template_reference}"}}\n'},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "PASS"
    assert receipt["blocking_finding_count"] == 0


def test_known_historical_fixture_bytes_are_blocking_outside_bound_provenance(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    historical_fixture = "Q8v6K1mP9zT2yR4u" + "W7nB3cD5fG0hJ2kL"
    _commit(
        repo,
        "same bytes, different provenance",
        {"config.json": f'{{"client_secret": "{historical_fixture}"}}\n'},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "high_entropy_secret_assignment" and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_go_selector_is_not_treated_as_literal_secret(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(
        repo,
        "go selector",
        {"config.go": "cfg := Config{Password: fixtures.DefaultTestPassword}\n"},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "PASS"
    assert receipt["blocking_finding_count"] == 0


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


def test_placeholder_word_in_context_does_not_hide_secret(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    openai_token = "sk-" + "q7A4nB9cD2eF6gH8jK1mN5pR3sT0vW4xY7z"
    generic_secret = "S8n5D2x7V4b9K1p6" + "T3y0M7w2C5f8H4j1"
    _commit(
        repo,
        "context must not suppress secrets",
        {
            "x.txt": (
                f"OPENAI_API_KEY={openai_token}  # example\n"
                f"client_secret={generic_secret}  # placeholder\n"
            )
        },
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    blocking = [finding for finding in receipt["findings"] if finding["blocking"]]
    assert receipt["status"] == "FAIL"
    assert any(finding["detector"] == "openai_api_key" for finding in blocking)
    assert any(finding["detector"] == "high_entropy_secret_assignment" for finding in blocking)


def test_delimited_placeholder_marker_remains_nonblocking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "fixture marker", {"x.txt": "access_token=nexus-dashboard-unconfigured\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "PASS"
    assert receipt["blocking_finding_count"] == 0


def test_placeholder_substring_inside_secret_value_does_not_hide_secret(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    generic_secret = "Q8v6K1mP9zTfakeR4uW7nB3cD5fG0hJ2kL"
    _commit(repo, "secret substring", {"x.txt": f"client_secret={generic_secret}\n"})
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "high_entropy_secret_assignment" and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_placeholder_comment_does_not_hide_secret_bearing_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(
        repo,
        "tracked env",
        {".env": "# production config; see example below\nDATABASE_URL=postgresql://local\n"},
    )
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())
    receipt = scan_repository(repo)
    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "secret_bearing_path"
        and finding["path"] == ".env"
        and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_historical_secret_path_survives_same_blob_move_to_safe_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "tracked env", {".env": "MODE=development\n"})
    env_blob = _git(repo, "rev-parse", "HEAD:.env").stdout.strip()
    (repo / "safe.txt").write_text("MODE=development\n", encoding="utf-8")
    (repo / ".env").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "move env bytes to safe path")
    assert _git(repo, "rev-parse", "HEAD:safe.txt").stdout.strip() == env_blob
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())

    receipt = scan_repository(repo)

    assert receipt["status"] == "FAIL"
    assert any(
        finding["detector"] == "secret_bearing_path"
        and finding["path"] == ".env"
        and finding["object_id"] == env_blob
        and finding["blocking"]
        for finding in receipt["findings"]
    )


def test_receipt_binds_exact_head_and_published_ref_snapshot(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    receipt = scan_repository(repo)
    snapshot = f"refs/remotes/origin/main {head}\n".encode()
    assert receipt["source_revision"] == head
    assert receipt["published_ref_count"] == 1
    assert receipt["published_ref_snapshot_sha256"] == hashlib.sha256(snapshot).hexdigest()

    _refresh_remote_ref(repo, "feature", head)
    expanded = scan_repository(repo)
    expanded_snapshot = (
        f"refs/remotes/origin/feature {head}\nrefs/remotes/origin/main {head}\n"
    ).encode()
    assert expanded["source_revision"] == head
    assert expanded["published_ref_count"] == 2
    assert (
        expanded["published_ref_snapshot_sha256"] == hashlib.sha256(expanded_snapshot).hexdigest()
    )
    assert expanded["published_ref_snapshot_sha256"] != receipt["published_ref_snapshot_sha256"]

    _git(repo, "tag", "-a", "v1", "-m", "annotated fixture tag")
    tagged = scan_repository(repo)
    tag_oid = _git(repo, "rev-parse", "refs/tags/v1").stdout.strip()
    tagged_snapshot = (
        f"refs/remotes/origin/feature {head}\n"
        f"refs/remotes/origin/main {head}\n"
        f"refs/tags/v1 {tag_oid}\n"
    ).encode()
    assert tagged["tag_ref_count"] == 1
    assert tagged["published_ref_snapshot_sha256"] == hashlib.sha256(tagged_snapshot).hexdigest()


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


def test_unavailable_gitlink_target_is_ignored_as_non_blob(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    fake_gitlink_oid = "1" * 40
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{fake_gitlink_oid},vendor/submodule",
    )
    _git(repo, "commit", "-m", "add unavailable gitlink")
    _refresh_remote_ref(repo, "main", _git(repo, "rev-parse", "HEAD").stdout.strip())

    receipt = scan_repository(repo)

    assert receipt["status"] == "PASS"
    assert receipt["blocking_finding_count"] == 0


def test_git_error_fails_closed(tmp_path: Path) -> None:
    nonrepo = tmp_path / "not-a-repo"
    nonrepo.mkdir()
    with pytest.raises(ScanError):
        scan_repository(nonrepo)


def test_workflow_enforces_continuous_repository_coverage() -> None:
    workflow = Path(".github/workflows/git-history-secret-audit.yml").read_text(encoding="utf-8")
    pull_request_block = workflow.split("  pull_request:\n", 1)[1].split("  push:\n", 1)[0]
    assert "branches: [main]" in pull_request_block
    assert "paths:" not in pull_request_block
    assert "  push:\n    branches: [main]\n" in workflow
    assert "  schedule:\n    - cron:" in workflow
    assert "  workflow_dispatch:\n" in workflow


def test_workflow_preserves_least_privilege_and_immutable_actions() -> None:
    workflow = Path(".github/workflows/git-history-secret-audit.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read\n" in workflow
    action_lines = [line.strip() for line in workflow.splitlines() if line.strip().startswith("uses: ")]
    assert action_lines
    for line in action_lines:
        ref = line.split("@", 1)[1].split()[0]
        assert len(ref) == 40
        assert all(char in "0123456789abcdef" for char in ref)
