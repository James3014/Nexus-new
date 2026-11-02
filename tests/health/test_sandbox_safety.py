from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from nexus.health import sandbox as sandbox_module
from nexus.health.executor import RepairExecutor
from nexus.health.sandbox import SpeculativeSandbox


def test_tmpdir_fork_preserves_external_symlink_without_copying_target(tmp_path: Path) -> None:
    # The name is historical: an outward link is no longer kept in the copy (#3162). What the
    # test holds is that the target's bytes never enter the copy, and that nothing written by
    # path in the copy reaches the target.
    source = tmp_path / "source"
    source.mkdir()
    (source / "repo.txt").write_text("repo", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    (external / "large.bin").write_bytes(b"x" * (2 * 1024 * 1024))
    (source / "escape").symlink_to(external, target_is_directory=True)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    try:
        assert (sandbox_root / "repo.txt").read_text(encoding="utf-8") == "repo"
        assert not os.path.lexists(sandbox_root / "escape")

        visited_files = []
        for _root, _dirs, files in os.walk(sandbox_root, followlinks=False):
            visited_files.extend(files)
        assert "large.bin" not in visited_files

        # A repair command writing by path in the copy stays in the copy.
        (sandbox_root / "escape").mkdir()
        (sandbox_root / "escape" / "planted.txt").write_text("x", encoding="utf-8")
        assert sorted(p.name for p in external.iterdir()) == ["large.bin"]
    finally:
        sandbox.cleanup()
    assert (source / "escape").is_symlink()


def test_fork_failure_removes_partial_sandbox(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    partial_root = tmp_path / "nexus_sandbox_partial"

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "nexus_sandbox_"
        partial_root.mkdir()
        return str(partial_root)

    def exploding_copytree(_src, dst, **_kwargs):
        dst = Path(dst)
        dst.mkdir(parents=True)
        (dst / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected copy failure")

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(sandbox_module.shutil, "copytree", exploding_copytree)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    with pytest.raises(OSError, match="injected copy failure"):
        sandbox.fork()

    assert not partial_root.exists()
    assert sandbox.sandbox_root is None
    assert sandbox._temp_root is None


def test_cleanup_does_not_follow_symlink_outside_sandbox(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (source / "escape").symlink_to(external, target_is_directory=True)

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    temp_root = sandbox_root.parent
    # The copy leaves the outward link out (#3162); a command run in the copy can still make
    # one, and cleanup must remove the link without following it.
    assert not os.path.lexists(sandbox_root / "escape")
    (sandbox_root / "made-by-run").symlink_to(external, target_is_directory=True)

    sandbox.cleanup()

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert external.exists()
    assert not temp_root.exists()


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    temp_root = sandbox_root.parent

    sandbox.cleanup()
    sandbox.cleanup()

    assert not temp_root.exists()
    assert sandbox.sandbox_root is None
    assert sandbox._temp_root is None


def test_broad_source_roots_are_rejected_before_temp_creation(monkeypatch, tmp_path: Path) -> None:
    created = False

    def unexpected_mkdtemp(*, prefix: str) -> str:
        nonlocal created
        created = True
        return str(tmp_path / prefix)

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", unexpected_mkdtemp)

    sandbox = SpeculativeSandbox(Path(tempfile.gettempdir()), mode="tmpdir")
    with pytest.raises(ValueError, match="too broad"):
        sandbox.fork()

    assert created is False
    assert sandbox.sandbox_root is None


def test_source_root_symlink_is_rejected(tmp_path: Path) -> None:
    real_source = tmp_path / "real-source"
    real_source.mkdir()
    linked_source = tmp_path / "linked-source"
    linked_source.symlink_to(real_source, target_is_directory=True)

    sandbox = SpeculativeSandbox(linked_source, mode="tmpdir")
    with pytest.raises(ValueError, match="must not be a symlink"):
        sandbox.fork()


def test_normal_tmpdir_fork_copies_regular_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("content", encoding="utf-8")

    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    sandbox_root = sandbox.fork()
    try:
        assert (sandbox_root / "file.txt").read_text(encoding="utf-8") == "content"
    finally:
        sandbox.cleanup()


def test_executor_cleanup_runs_when_fork_raises_after_partial_initialization(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    partial_root = tmp_path / "nexus_sandbox_executor_partial"

    monkeypatch.setattr(SpeculativeSandbox, "_docker_available", staticmethod(lambda: False))

    def partial_fork(self: SpeculativeSandbox) -> Path:
        partial_root.mkdir()
        self._temp_root = partial_root
        self.sandbox_root = partial_root / "repo"
        self.sandbox_root.mkdir()
        (self.sandbox_root / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected fork failure")

    monkeypatch.setattr(SpeculativeSandbox, "fork", partial_fork)

    executor = RepairExecutor(repo_root, task_runner=lambda _manifest: 0)
    rc, note = executor._validate_in_sandbox([])

    assert rc == 1
    assert note.startswith("sandbox_error:OSError:injected fork failure")
    assert not partial_root.exists()


# #2291: a harness that overrides HOME must not turn the real account home, or a tree
# that contains the running checkout, into an acceptable source root.

ACCOUNT_HOME = "is the account home"
HOME_SHAPE = "has the shape of an account home"
CONTAINS_CHECKOUT = "contains the checkout"


def _real_account_home() -> Path:
    pwd = pytest.importorskip("pwd")
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()


def _refuse_mkdtemp(monkeypatch, tmp_path: Path) -> list[str]:
    created: list[str] = []

    def unexpected_mkdtemp(*, prefix: str) -> str:
        created.append(prefix)
        return str(tmp_path / prefix)

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", unexpected_mkdtemp)
    return created


def _fake_home(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "scratch-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    assert Path.home().resolve() == fake_home.resolve()


def test_real_account_home_is_refused_when_home_is_overridden(monkeypatch, tmp_path: Path) -> None:
    real_home = _real_account_home()
    _fake_home(monkeypatch, tmp_path)
    created = _refuse_mkdtemp(monkeypatch, tmp_path)

    sandbox = SpeculativeSandbox(real_home, mode="tmpdir")
    with pytest.raises(ValueError, match=ACCOUNT_HOME):
        sandbox.fork()
    assert created == []
    assert sandbox.sandbox_root is None


def test_account_home_found_by_pwd_alone(monkeypatch, tmp_path: Path) -> None:
    real_home = _real_account_home()
    _fake_home(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox_module, "_expanduser_home", lambda: None)
    with pytest.raises(ValueError, match=ACCOUNT_HOME):
        SpeculativeSandbox(real_home, mode="tmpdir").fork()


def test_account_home_found_by_expanduser_alone(monkeypatch, tmp_path: Path) -> None:
    real_home = _real_account_home()
    _fake_home(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox_module, "_pwd_home", lambda: None)
    with pytest.raises(ValueError, match=ACCOUNT_HOME):
        SpeculativeSandbox(real_home, mode="tmpdir").fork()


def test_account_home_shape_is_refused_without_account_lookups(monkeypatch, tmp_path: Path) -> None:
    homes = tmp_path / "homes"
    (homes / "alice" / "project").mkdir(parents=True)
    _fake_home(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox_module, "_account_homes", lambda: set())
    monkeypatch.setattr(sandbox_module, "_ACCOUNT_HOME_PARENTS", (str(homes),))
    with pytest.raises(ValueError, match=HOME_SHAPE):
        SpeculativeSandbox(homes / "alice", mode="tmpdir").fork()
    sandbox = SpeculativeSandbox(homes / "alice" / "project", mode="tmpdir")
    try:
        assert sandbox.fork().is_dir()
    finally:
        sandbox.cleanup()


def test_default_account_home_shapes() -> None:
    assert sandbox_module._has_account_home_shape(Path("/Users/someone"))
    assert sandbox_module._has_account_home_shape(Path("/home/someone").resolve())
    assert sandbox_module._has_account_home_shape(Path("/root").resolve())
    assert not sandbox_module._has_account_home_shape(Path("/Users/someone/project"))
    assert not sandbox_module._has_account_home_shape(Path("/home/runner/work/repo"))


def test_account_homes_ignore_home_env(monkeypatch, tmp_path: Path) -> None:
    real_home = _real_account_home()
    monkeypatch.setenv("HOME", str(tmp_path))
    assert real_home in sandbox_module._account_homes()
    assert tmp_path.resolve() not in sandbox_module._account_homes()


def test_ancestor_of_running_checkout_is_refused(monkeypatch, tmp_path: Path) -> None:
    outer = tmp_path / "workspace"
    checkout = outer / "checkout"
    (checkout / "nexus").mkdir(parents=True)
    monkeypatch.setattr(sandbox_module, "_running_checkout_root", lambda: checkout)
    created = _refuse_mkdtemp(monkeypatch, tmp_path)

    sandbox = SpeculativeSandbox(outer, mode="tmpdir")
    with pytest.raises(ValueError, match=CONTAINS_CHECKOUT):
        sandbox.fork()
    assert created == []


def test_running_checkout_root_is_the_git_checkout_of_this_module() -> None:
    module = Path(sandbox_module.__file__).resolve()
    root = sandbox_module._running_checkout_root()
    expected = next((p for p in module.parents if (p / ".git").exists()), None)
    assert root == expected
    if root is not None:
        assert module.is_relative_to(root)


def test_checkout_itself_is_a_valid_source(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "nexus").mkdir(parents=True)
    monkeypatch.setattr(sandbox_module, "_running_checkout_root", lambda: checkout)
    sandbox = SpeculativeSandbox(checkout, mode="tmpdir")
    try:
        assert (sandbox.fork() / "nexus").is_dir()
    finally:
        sandbox.cleanup()


def test_checkout_rule_is_skipped_outside_a_git_checkout(monkeypatch, tmp_path: Path) -> None:
    # A non-editable install with no .git above it: the project root stays valid.
    monkeypatch.setattr(sandbox_module, "_running_checkout_root", lambda: None)
    source = tmp_path / "project"
    source.mkdir()
    (source / "f.txt").write_text("x", encoding="utf-8")
    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    try:
        assert (sandbox.fork() / "f.txt").exists()
    finally:
        sandbox.cleanup()


def test_cwd_inside_nested_checkout_does_not_block_fork(monkeypatch, tmp_path: Path) -> None:
    # RepairExecutor may run from inside a submodule of its repo_root.
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub" / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo / "sub")
    sandbox = SpeculativeSandbox(repo, mode="tmpdir")
    try:
        assert (sandbox.fork() / "sub").is_dir()
    finally:
        sandbox.cleanup()


def test_nexus_runs_is_not_copied_or_counted(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / ".nexus" / "runs").mkdir(parents=True)
    (source / ".nexus" / "runs" / "big.bin").write_bytes(b"x" * 10_000)
    (source / ".nexus" / "config.toml").write_text("k = 1\n", encoding="utf-8")
    (source / "pkg" / "runs").mkdir(parents=True)  # "runs" elsewhere is copied
    (source / "pkg" / "runs" / "r.txt").write_text("r", encoding="utf-8")
    monkeypatch.setattr(sandbox_module, "SANDBOX_MAX_SOURCE_BYTES", 1000)
    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    try:
        root = sandbox.fork()
        assert not (root / ".nexus" / "runs").exists()
        assert (root / ".nexus" / "config.toml").exists()
        assert (root / "pkg" / "runs" / "r.txt").exists()
    finally:
        sandbox.cleanup()


def test_source_root_with_too_many_top_level_entries_is_refused(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for i in range(4):
        (source / f"f{i}").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sandbox_module, "SANDBOX_MAX_TOP_LEVEL_ENTRIES", 3)
    created = _refuse_mkdtemp(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="SANDBOX_MAX_TOP_LEVEL_ENTRIES=3"):
        SpeculativeSandbox(source, mode="tmpdir").fork()
    assert created == []


def test_source_root_over_size_cap_is_refused(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "pkg").mkdir(parents=True)
    (source / "pkg" / "big.bin").write_bytes(b"x" * 200)
    # Ignored names do not count toward the cap.
    (source / ".venv").mkdir()
    (source / ".venv" / "huge.bin").write_bytes(b"x" * 10_000)
    monkeypatch.setattr(sandbox_module, "SANDBOX_MAX_SOURCE_BYTES", 500)
    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    try:
        assert (sandbox.fork() / "pkg" / "big.bin").exists()
    finally:
        sandbox.cleanup()

    monkeypatch.setattr(sandbox_module, "SANDBOX_MAX_SOURCE_BYTES", 100)
    created = _refuse_mkdtemp(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="SANDBOX_MAX_SOURCE_BYTES=100"):
        SpeculativeSandbox(source, mode="tmpdir").fork()
    assert created == []


def test_small_project_dir_still_forks_with_home_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    source = tmp_path / "project"
    (source / "pkg").mkdir(parents=True)
    (source / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    sandbox = SpeculativeSandbox(source, mode="tmpdir")
    try:
        assert (sandbox.fork() / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    finally:
        sandbox.cleanup()
