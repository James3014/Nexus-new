from pathlib import Path

from nexus.delivery.suggestions import detect_verification_language, suggest_verification_commands


def test_detect_verification_language_prefers_rust_task_hints(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    assert detect_verification_language(tmp_path, "fix rust lifetime bug in nexus-core") == "rust"


def test_detect_verification_language_prefers_go_task_hints(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    assert detect_verification_language(tmp_path, "patch go worker in nexus-swarm") == "go"


def test_suggest_verification_commands_for_python_repo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    assert suggest_verification_commands(tmp_path, "fix login bug") == ["uv run pytest -q"]


def test_suggest_verification_commands_for_rust_subrepo(tmp_path: Path) -> None:
    rust_dir = tmp_path / "nexus-core-rs"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname='nexus-core-rs'\n", encoding="utf-8")

    # The nexus-core-rs sub-crate hint was retired with the crate (2026-10-16, #2359).
    assert suggest_verification_commands(tmp_path, "fix rust leak in nexus-core") == ["cargo test"]


def test_suggest_verification_commands_for_go_subrepo(tmp_path: Path) -> None:
    go_dir = tmp_path / "nexus-swarm"
    go_dir.mkdir()
    (go_dir / "go.mod").write_text("module nexus-swarm\n", encoding="utf-8")

    assert suggest_verification_commands(tmp_path, "patch go scheduler in nexus-swarm") == [
        "cd nexus-swarm && go test ./..."
    ]


def test_suggest_verification_commands_for_retained_rust_crate(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    rust_dir = tmp_path / "nexus-core-rs"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname='nexus-core-rs'\n", encoding="utf-8")

    # No sub-crate special case any more: a stray nexus-core-rs/ is not a target.
    assert suggest_verification_commands(tmp_path, "fix rust receipt verifier") == ["cargo test"]


def test_suggest_verification_commands_for_this_repo_targets_retained_crate() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    # nexus-core-rs/ was deleted (2026-10-16, #2359); this repo has no Rust crate left.
    assert not (repo_root / "nexus-core-rs").exists()
    assert suggest_verification_commands(repo_root, "fix rust flow machine") == ["cargo test"]
