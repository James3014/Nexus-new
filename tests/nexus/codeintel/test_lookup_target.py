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


def test_root_init_symbols_match_the_skeleton_provider(tmp_path: Path) -> None:
    _write(tmp_path, "__init__.py", "def handler():\n    return 1\n")

    found = derive_codeintel_lookup("handler fails", ["__init__.py"], tmp_path)

    assert found["target_symbol"] == "handler"
    assert lookup_implementation(tmp_path, "handler", search_paths=["__init__.py"]).found


def test_symbol_cap_applies_while_parsing(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.codeintel import lookup_target

    monkeypatch.setattr(lookup_target, "MAX_SYMBOLS", 5)
    _write(tmp_path, "many.py", "".join(f"def fn_{i}():\n    return {i}\n" for i in range(50)))
    seen: list[int] = []
    real = lookup_target._symbols
    monkeypatch.setattr(
        lookup_target, "_symbols", lambda m, s, n: seen.append(len(real(m, s, n))) or real(m, s, n)
    )

    lookup_target.derive_codeintel_lookup("fn 3", ["many.py"], tmp_path)

    assert seen and max(seen) <= 5


def test_a_file_with_a_syntax_error_is_skipped_not_fatal(tmp_path: Path) -> None:
    """One unparsable allowed file dropped the whole derivation (#2721)."""
    _write(tmp_path, "pkg/broken.py", "def parse_config(:\n    return\n")
    _write(tmp_path, "pkg/config.py", "def parse_config(text):\n    return {}\n")

    found = derive_codeintel_lookup(
        "parse_config drops keys", ["pkg/broken.py", "pkg/config.py"], tmp_path
    )

    assert found == {"target_symbol": "pkg.config.parse_config", "search_paths": ["pkg/config.py"]}


def test_a_file_with_a_null_byte_is_skipped_not_fatal(tmp_path: Path) -> None:
    """``ast.parse`` raises ValueError on a NUL byte."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "nul.py").write_bytes(b"def a():\n    return 1\x00\n")
    _write(tmp_path, "pkg/config.py", "def parse_config(text):\n    return {}\n")

    found = derive_codeintel_lookup(
        "parse_config drops keys", ["pkg/nul.py", "pkg/config.py"], tmp_path
    )

    assert found["search_paths"] == ["pkg/config.py"]


# --- directory scopes (#2721, #2786) -------------------------------------------

_NAMES = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel")


def test_directory_scope_with_nested_packages_yields_the_matching_symbol(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/net.py",
        "class HttpClient:\n    def fetch_url(self, url):\n        return url\n",
    )
    _write(tmp_path, "pkg/sub/__init__.py", "")
    _write(tmp_path, "pkg/sub/deep/config.py", "def parse_config(text):\n    return {}\n")

    found = derive_codeintel_lookup("parse_config drops keys with comments", ["pkg/"], tmp_path)

    assert found["target_symbol"] == "pkg.sub.deep.config.parse_config"
    assert found["search_paths"][0] == "pkg/sub/deep/config.py"
    assert lookup_implementation(
        tmp_path, found["target_symbol"], search_paths=found["search_paths"]
    ).found


def test_directory_scope_skips_tests_hidden_dirs_and_pycache(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/core.py", "def unrelated_helper():\n    return 1\n")
    for rel in (
        "pkg/tests/helpers.py",
        "pkg/test/helpers.py",
        "pkg/testing/helpers.py",
        "pkg/.hidden/helpers.py",
        "pkg/__pycache__/helpers.py",
        "pkg/test_parser.py",
        "pkg/parser_test.py",
        "pkg/conftest.py",
        "pkg/.secret.py",
    ):
        _write(tmp_path, rel, "def secret_parser():\n    return 1\n")

    assert derive_codeintel_lookup("secret parser", ["pkg/"], tmp_path) == {}
    assert derive_codeintel_lookup("unrelated helper secret parser", ["pkg/"], tmp_path) == {
        "target_symbol": "pkg.core.unrelated_helper",
        "search_paths": ["pkg/core.py"],
    }
    # A directory entry that itself names a test or hidden directory is ignored.
    for scope in ("pkg/tests/", "pkg/.hidden/", "pkg/__pycache__/", "tests/"):
        assert derive_codeintel_lookup("secret parser", [scope], tmp_path) == {}


def test_directory_scope_never_reads_through_test_dirs(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.codeintel import lookup_target

    _write(tmp_path, "pkg/core.py", "def parse_config():\n    return 1\n")
    _write(tmp_path, "pkg/tests/test_core.py", "def parse_config_test():\n    return 1\n")
    read: list[tuple[str, ...]] = []
    real = lookup_target._read_inside
    monkeypatch.setattr(
        lookup_target,
        "_read_inside",
        lambda root, parts, **kw: read.append(parts) or real(root, parts, **kw),
    )

    found = lookup_target.derive_codeintel_lookup("parse config", ["pkg/"], tmp_path)

    assert found["search_paths"] == ["pkg/core.py"]
    assert read == [("pkg", "core.py")]


def test_directory_scope_does_not_follow_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "pkg/core.py", "def unrelated_helper():\n    return 1\n")
    _write(tmp_path, "outside/secret.py", "def secret_parser():\n    return 1\n")
    (root / "pkg" / "linked_dir").symlink_to(tmp_path / "outside")
    (root / "pkg" / "linked.py").symlink_to(tmp_path / "outside" / "secret.py")

    assert derive_codeintel_lookup("secret parser", ["pkg/"], root) == {}
    assert derive_codeintel_lookup("unrelated helper secret parser", ["pkg/"], root) == {
        "target_symbol": "pkg.core.unrelated_helper",
        "search_paths": ["pkg/core.py"],
    }
    # The scope directory itself as a symlink is not followed either.
    (root / "scope").symlink_to(tmp_path / "outside")
    assert derive_codeintel_lookup("secret parser", ["scope/"], root) == {}


def test_directory_scope_walk_stops_at_the_file_cap(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.codeintel import lookup_target

    monkeypatch.setattr(lookup_target, "MAX_WALK_FILES", 3)
    for i, name in enumerate(_NAMES[:6]):
        _write(tmp_path, f"pkg/m{i}.py", f"def {name}_handler():\n    return {i}\n")

    # Sorted walk: m0..m2 are read, m5 is beyond the cap.
    assert lookup_target.derive_codeintel_lookup("foxtrot crashes", ["pkg/"], tmp_path) == {}
    found = lookup_target.derive_codeintel_lookup("charlie crashes", ["pkg/"], tmp_path)
    assert found["target_symbol"] == "pkg.m2.charlie_handler"


def test_directory_scope_walk_stops_at_the_directory_cap(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.codeintel import lookup_target

    monkeypatch.setattr(lookup_target, "MAX_WALK_DIRS", 2)
    _write(tmp_path, "pkg/a/one.py", "def alpha_handler():\n    return 1\n")
    _write(tmp_path, "pkg/b/two.py", "def bravo_handler():\n    return 2\n")

    # Breadth-first over sorted names: pkg, pkg/a visited; pkg/b is beyond the cap.
    assert lookup_target.derive_codeintel_lookup("bravo fails", ["pkg/"], tmp_path) == {}
    assert lookup_target.derive_codeintel_lookup("alpha fails", ["pkg/"], tmp_path)


def test_directory_scope_without_a_bm25_match_is_empty(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/a.py", "def alpha():\n    return 1\n")

    assert derive_codeintel_lookup("unrelated words entirely", ["pkg/"], tmp_path) == {}
    assert derive_codeintel_lookup("alpha", ["pkg/"], tmp_path)["target_symbol"] == "pkg.a.alpha"
    assert derive_codeintel_lookup("alpha", ["missing/"], tmp_path) == {}


def test_malformed_directory_entries_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/a.py", "def alpha():\n    return 1\n")
    for scope in ("pkg//", "/pkg/", "../pkg/", "pkg/../pkg/", "./pkg/", "pkg\\", "/"):
        assert derive_codeintel_lookup("alpha", [scope], tmp_path) == {}
    assert derive_codeintel_lookup("alpha", ["pkg/"], tmp_path)["target_symbol"] == "pkg.a.alpha"


def test_mixed_file_and_directory_scope(tmp_path: Path) -> None:
    _write(tmp_path, "cli.py", "def run_cli():\n    return 1\n")
    _write(tmp_path, "pkg/config.py", "def parse_config(text):\n    return {}\n")
    _write(tmp_path, "pkg/net.py", "def fetch_url(url):\n    return url\n")

    found = derive_codeintel_lookup(
        "parse_config breaks on cli url input", ["cli.py", "pkg/"], tmp_path
    )

    assert found["target_symbol"] == "pkg.config.parse_config"
    assert found["search_paths"][0] == "pkg/config.py"
    assert set(found["search_paths"]) == {"pkg/config.py", "cli.py", "pkg/net.py"}
    assert derive_codeintel_lookup("run cli", ["cli.py", "pkg/"], tmp_path) == {
        "target_symbol": "cli.run_cli",
        "search_paths": ["cli.py"],
    }


def test_directory_scope_search_paths_are_bounded_and_winner_first(tmp_path: Path) -> None:
    for i, name in enumerate(_NAMES):
        _write(tmp_path, f"pkg/m{i}.py", f"def {name}_handler():\n    return {i}\n")

    found = derive_codeintel_lookup("golf handler crashes", ["pkg/"], tmp_path)

    assert found["target_symbol"] == "pkg.m6.golf_handler"
    assert found["search_paths"][0] == "pkg/m6.py"
    assert len(found["search_paths"]) == 4


def test_file_scope_behaviour_is_unchanged_next_to_a_directory(tmp_path: Path) -> None:
    """A file-only scope keeps the first-four-files rule and its order."""
    for i, name in enumerate(_NAMES[:6]):
        _write(tmp_path, f"pkg/m{i}.py", f"def {name}_handler():\n    return {i}\n")

    files = [f"pkg/m{i}.py" for i in range(6)]
    assert derive_codeintel_lookup("foxtrot crashes", files, tmp_path) == {}
    assert derive_codeintel_lookup("bravo crashes", files, tmp_path) == {
        "target_symbol": "pkg.m1.bravo_handler",
        "search_paths": files[:4],
    }
    assert derive_codeintel_lookup("foxtrot crashes", ["pkg/"], tmp_path)["target_symbol"] == (
        "pkg.m5.foxtrot_handler"
    )


# --- Codex r1 on #2818 ---------------------------------------------------------


def test_directory_scope_test_exclusion_ignores_case(tmp_path: Path) -> None:
    """On APFS ``Tests/`` and ``Conftest.py`` are the real test files."""
    _write(tmp_path, "pkg/core.py", "def unrelated_helper():\n    return 1\n")
    for rel in (
        "pkg/Tests/x.py",
        "pkg/TEST/core.py",
        "pkg/Testing/y.py",
        "pkg/__PYCACHE__/z.py",
        "pkg/Conftest.py",
        "pkg/Test_foo.py",
        "pkg/foo_TEST.py",
        "pkg/Test.py",
        "pkg/Tests.py",
        "pkg/foo_Tests.py",
    ):
        _write(tmp_path, rel, "def secret_parser():\n    return 1\n")

    assert derive_codeintel_lookup("secret parser", ["pkg/"], tmp_path) == {}
    for scope in ("pkg/Tests/", "pkg/TEST/", "pkg/Testing/"):
        assert derive_codeintel_lookup("secret parser", [scope], tmp_path) == {}
    assert derive_codeintel_lookup("unrelated helper", ["pkg/"], tmp_path)["search_paths"] == [
        "pkg/core.py"
    ]


def test_directory_scope_skips_hard_linked_files(tmp_path: Path) -> None:
    import os

    root = tmp_path / "ws"
    _write(root, "pkg/core.py", "def unrelated_helper():\n    return 1\n")
    _write(tmp_path, "outside.py", "def secret_parser():\n    return 1\n")
    os.link(tmp_path / "outside.py", root / "pkg" / "linked.py")

    assert derive_codeintel_lookup("secret parser", ["pkg/"], root) == {}
    assert derive_codeintel_lookup("secret parser", ["pkg/linked.py", "pkg/"], root) == {}
    assert derive_codeintel_lookup("unrelated helper", ["pkg/"], root)["search_paths"] == [
        "pkg/core.py"
    ]


def test_directory_walk_queue_never_exceeds_the_directory_cap(tmp_path: Path, monkeypatch) -> None:
    from collections import deque

    from nexus.services.codeintel import lookup_target

    longest: list[int] = [0]

    class _Recording(deque):
        def append(self, item):
            super().append(item)
            longest[0] = max(longest[0], len(self))

        def extend(self, items):
            super().extend(items)
            longest[0] = max(longest[0], len(self))

    monkeypatch.setattr(lookup_target, "deque", _Recording)
    monkeypatch.setattr(lookup_target, "MAX_WALK_DIRS", 3)
    for i in range(10):
        _write(tmp_path, f"pkg/d{i}/m.py", f"def handler_{i}():\n    return {i}\n")

    found = lookup_target.derive_codeintel_lookup("handler", ["pkg/"], tmp_path)

    assert found["search_paths"] == ["pkg/d0/m.py", "pkg/d1/m.py"]
    assert longest[0] <= 3


def test_directory_walk_byte_budget_is_checked_before_reading(tmp_path: Path, monkeypatch) -> None:
    from nexus.services.codeintel import lookup_target

    _write(tmp_path, "pkg/a.py", "def alpha_handler():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "def bravo_handler():\n    return 2\n" + "#" * 500 + "\n")
    _write(tmp_path, "pkg/c.py", "def charlie_handler():\n    return 3\n")
    small = (tmp_path / "pkg/a.py").stat().st_size + (tmp_path / "pkg/c.py").stat().st_size
    monkeypatch.setattr(lookup_target, "MAX_WALK_BYTES", small + 10)
    read: list[int] = []
    real = lookup_target.os.read
    monkeypatch.setattr(lookup_target.os, "read", lambda fd, n: read.append(n) or real(fd, n))

    assert lookup_target.derive_codeintel_lookup("bravo", ["pkg/"], tmp_path) == {}
    found = lookup_target.derive_codeintel_lookup("charlie", ["pkg/"], tmp_path)
    assert found["target_symbol"] == "pkg.c.charlie_handler"
    assert max(read) <= small + 11


def test_explicit_file_is_read_before_a_large_directory_fills_the_budget(
    tmp_path: Path,
) -> None:
    """Codex r2 on #2818: ``["pkg/", "target.py"]`` with 200+ files under pkg/."""
    for i in range(205):
        _write(tmp_path, f"pkg/m{i:03d}.py", f"def filler_{i}():\n    return {i}\n")
    _write(tmp_path, "target.py", "def parse_widget_config():\n    return 1\n")

    found = derive_codeintel_lookup("parse widget config", ["pkg/", "target.py"], tmp_path)

    assert found == {"target_symbol": "target.parse_widget_config", "search_paths": ["target.py"]}


def _call_with_timeout(fn, fifo: Path, timeout: float = 5.0):
    """Run ``fn`` in a thread; a blocked FIFO open is released by a writer afterwards."""
    import os
    import threading

    box: dict[str, object] = {}

    def run() -> None:
        box["value"] = fn()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    blocked = worker.is_alive()
    if blocked:  # free the stuck reader so the test process does not leak a thread
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        worker.join(2)
    assert not blocked, "opening a FIFO blocked: O_NONBLOCK is missing"
    return box["value"]


def test_fifo_in_allowed_files_does_not_block(tmp_path: Path) -> None:
    import os

    from nexus.services.codeintel import lookup_target

    (tmp_path / "pkg").mkdir()
    fifo = tmp_path / "pkg/fifo.py"
    os.mkfifo(fifo)

    found = _call_with_timeout(
        lambda: lookup_target.derive_codeintel_lookup("fifo", ["pkg/fifo.py"], tmp_path), fifo
    )

    assert found == {}


def test_fifo_swapped_in_after_directory_listing_does_not_block(
    tmp_path: Path, monkeypatch
) -> None:
    """The listing only returns regular files, so simulate the scandir->open swap race:
    the listing reports ``fifo.py`` although the entry is a FIFO when it is opened."""
    import os

    from nexus.services.codeintel import lookup_target

    (tmp_path / "pkg").mkdir()
    fifo = tmp_path / "pkg/fifo.py"
    os.mkfifo(fifo)
    monkeypatch.setattr(lookup_target, "_list_inside", lambda root, parts: ([], ["fifo.py"]))

    found = _call_with_timeout(
        lambda: lookup_target.derive_codeintel_lookup("fifo", ["pkg/"], tmp_path), fifo
    )

    assert found == {}


def test_directory_entry_cap_boundary_at_4096(tmp_path: Path) -> None:
    from nexus.services.codeintel import lookup_target

    assert lookup_target.MAX_DIR_ENTRIES == 4096
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for number in range(4096):
        (pkg / f"m{number:04d}.py").touch()

    at_limit = lookup_target._list_inside(tmp_path, ("pkg",))
    assert at_limit is not None and len(at_limit[1]) == 4096

    (pkg / "m4096.py").touch()
    assert lookup_target._list_inside(tmp_path, ("pkg",)) is None


def test_directory_entry_cap_skips_an_oversized_directory_in_a_scope(
    tmp_path: Path, monkeypatch
) -> None:
    from nexus.services.codeintel import lookup_target

    monkeypatch.setattr(lookup_target, "MAX_DIR_ENTRIES", 2)
    _write(tmp_path, "pkg/a.py", "def alpha():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "def bravo():\n    return 2\n")

    found = lookup_target.derive_codeintel_lookup("alpha", ["pkg/"], tmp_path)
    assert found["target_symbol"] == "pkg.a.alpha"

    _write(tmp_path, "pkg/c.py", "def charlie():\n    return 3\n")
    assert lookup_target.derive_codeintel_lookup("alpha", ["pkg/"], tmp_path) == {}
