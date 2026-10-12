from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.ops import check_fixture_secret_literals as lint

# Fake secrets are assembled from split literals so this file itself is clean.
FAKE_SLACK = "xo" + "xb-" + "8a7B6c5D4e3F2g1H0jKl"
FAKE_AWS = "AK" + "IA" + "Q7ZP4MXN2KD9TRWB"


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "tests").mkdir()
    return tmp_path


def test_flags_contiguous_literal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text(f'TOKEN = "{FAKE_SLACK}"\n')
    out = lint.scan_paths(repo, ["tests/test_a.py"])
    assert [(p, d) for p, d, _ in out] == [("tests/test_a.py", "slack_token")]


def test_split_literal_source_is_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text('TOKEN = "xo" + "xb-" + "8a7B6c5D4e3F2g1H0jKl"\n')
    assert lint.scan_paths(repo, ["tests/test_a.py"]) == []


def test_ignores_files_outside_tests(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "x.py").write_text(f'TOKEN = "{FAKE_SLACK}"\n')
    assert lint.scan_paths(repo, ["x.py"]) == []


def test_main_all_fails_with_remediation(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text(f'KEY = "{FAKE_AWS}"\n')
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    assert lint.main(["--all", "--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "aws_access_key" in out
    assert '"xo" + "xb-"' in out
    assert "rewrite the branch history" in out


def test_main_all_passes_on_clean_tree(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    assert lint.main(["--all", "--repo", str(repo)]) == 0
    assert "OK" in capsys.readouterr().out


def test_default_mode_sees_untracked_changed_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "i",
        ],
        check=True,
    )
    (repo / "tests" / "test_new.py").write_text(f'TOKEN = "{FAKE_SLACK}"\n')
    assert lint.main(["--repo", str(repo), "--base", "HEAD"]) == 1
