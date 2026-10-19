"""Codeintel lookup target from the task's own files (#2721)."""

from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.lookup_target import derive_codeintel_lookup
from nexus.services.codeintel.skeleton_provider import lookup_implementation


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def test_picks_the_symbol_the_task_talks_about(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/config.py",
        "def parse_config(text):\n    return {}\n\ndef render(x):\n    return x\n",
    )
    _write(
        tmp_path,
        "pkg/net.py",
        "class HttpClient:\n    def fetch_url(self, url):\n        return url\n",
    )

    found = derive_codeintel_lookup(
        "parse_config drops keys when the config text has comments",
        ["pkg/config.py", "pkg/net.py"],
        tmp_path,
    )

    assert found == {
        "target_symbol": "pkg.config.parse_config",
        "search_paths": ["pkg/config.py", "pkg/net.py"],
    }
    assert lookup_implementation(
        tmp_path, found["target_symbol"], search_paths=found["search_paths"]
    ).found


def test_camel_and_method_names_are_matched_by_their_words(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/net.py",
        "class HttpClient:\n    def fetch_url(self, url):\n        return url\n",
    )

    found = derive_codeintel_lookup(
        "the http client fetch url retries forever", ["pkg/net.py"], tmp_path
    )

    assert found["target_symbol"] in {"pkg.net.HttpClient", "pkg.net.HttpClient.fetch_url"}


def test_nothing_when_no_existing_python_file_or_no_match(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# x\n")
    _write(tmp_path, "pkg/a.py", "def alpha():\n    return 1\n")

    assert derive_codeintel_lookup("fix alpha", ["README.md", "pkg/new.py"], tmp_path) == {}
    assert derive_codeintel_lookup("unrelated words entirely", ["pkg/a.py"], tmp_path) == {}
    assert derive_codeintel_lookup("", ["pkg/a.py"], tmp_path) == {}


def test_at_most_four_search_paths(tmp_path: Path) -> None:
    for i in range(6):
        _write(tmp_path, f"pkg/m{i}.py", f"def handler_{i}():\n    return {i}\n")

    found = derive_codeintel_lookup(
        "handler 5 crashes", [f"pkg/m{i}.py" for i in range(6)], tmp_path
    )

    assert len(found["search_paths"]) == 4


def test_symlinked_workspace_root_is_resolved(tmp_path: Path) -> None:
    """macOS /var -> /private/var: an unresolved root made relative_to() raise."""
    real = tmp_path / "real"
    _write(real, "pkg/config.py", "def parse_config(text):\n    return {}\n")
    link = tmp_path / "link"
    link.symlink_to(real)

    found = derive_codeintel_lookup("parse_config breaks", ["pkg/config.py"], link)

    assert found["target_symbol"] == "pkg.config.parse_config"


def test_errors_never_escape(tmp_path: Path) -> None:
    assert derive_codeintel_lookup("x", ["a.py"], tmp_path / "missing") == {}


def test_files_outside_the_worktree_are_never_read(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "pkg/a.py", "def alpha():\n    return 1\n")
    _write(tmp_path, "outside.py", "def secret_parser():\n    return 1\n")
    (root / "pkg" / "link.py").symlink_to(tmp_path / "outside.py")

    for rel in (
        "../outside.py",
        str(tmp_path / "outside.py"),
        "pkg/link.py",
        "pkg/../../outside.py",
    ):
        assert derive_codeintel_lookup("secret parser alpha", [rel], root) == {}


def test_malformed_inputs_and_bounds(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/a.py", "def alpha():\n    return 1\n")
    assert derive_codeintel_lookup("alpha", 5, tmp_path) == {}
    assert derive_codeintel_lookup("alpha", "pkg/a.py", tmp_path) == {}
    assert derive_codeintel_lookup(None, ["pkg/a.py"], tmp_path) == {}
    _write(
        tmp_path, "pkg/big.py", "def big_alpha():\n    return 1\n" + "#" * (1024 * 1024 + 10) + "\n"
    )
    assert derive_codeintel_lookup("big alpha", ["pkg/big.py"], tmp_path) == {}
    found = derive_codeintel_lookup("alpha", ["pkg/a.py"] * 10, tmp_path)
    assert found["search_paths"] == ["pkg/a.py"]


def test_symlinked_parent_directory_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(tmp_path, "outside/secret.py", "def secret_parser():\n    return 1\n")
    root.mkdir()
    (root / "pkg").symlink_to(tmp_path / "outside")

    assert derive_codeintel_lookup("secret parser", ["pkg/secret.py"], root) == {}


def test_non_identifier_module_names_do_not_block_a_valid_symbol(tmp_path: Path) -> None:
    _write(tmp_path, "my-mod.py", "def parse_widget():\n    return 1\n")
    _write(tmp_path, "pkg/widgets.py", "def parse_widget():\n    return 2\n")

    found = derive_codeintel_lookup("parse widget", ["my-mod.py", "pkg/widgets.py"], tmp_path)

    assert found["target_symbol"] == "pkg.widgets.parse_widget"
