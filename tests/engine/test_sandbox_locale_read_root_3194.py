"""#3194: the shared confinement profile reads the system locale data, read-only.

``/usr/share/locale`` is one of the shared system read subpaths, so a confined Perl tool
(``/usr/bin/shasum``) can set up ``LANG``/``LC_ALL=C.UTF-8``. On macOS the tests run the real
sandbox-exec barrier; without a barrier (Linux CI) they prove the profile text and that the
shared confinement refuses to run at all (fail closed), so nothing is skipped."""

import os
import sys
from pathlib import Path

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.engine.sandboxed_lane import SandboxError, os_sandbox_available

LOCALE = "/usr/share/locale"
PRE_3194_SUBPATHS = tuple(path for path in lane.SANDBOX_SYSTEM_READ_SUBPATHS if path != LOCALE)


def _profile(tmp_path: Path) -> str:
    box = tmp_path / "box"
    box.mkdir(exist_ok=True)
    return lane.build_sandbox_profile(
        writable=[str(box)], read_roots=lane.checked_read_roots([str(box)])
    )


def test_locale_data_is_a_shared_read_root_and_never_writable(tmp_path):
    assert LOCALE in lane.SANDBOX_SYSTEM_READ_SUBPATHS
    profile = _profile(tmp_path)
    has_locale = os.path.isdir(LOCALE)
    read_rules = [line for line in profile.splitlines() if line.startswith("(allow file-read*")]
    assert any(f'(subpath "{LOCALE}")' in line for line in read_rules) == has_locale
    write_rules = [line for line in profile.splitlines() if line.startswith("(allow file-write")]
    assert write_rules and all("/usr/share" not in line for line in write_rules)


def test_only_the_locale_subpath_was_added_to_the_profile(tmp_path, monkeypatch):
    after = _profile(tmp_path).splitlines()
    monkeypatch.setattr(lane, "SANDBOX_SYSTEM_READ_SUBPATHS", PRE_3194_SUBPATHS)
    before = _profile(tmp_path).splitlines()
    changed = [(old, new) for old, new in zip(before, after, strict=True) if old != new]
    if not os.path.isdir(LOCALE):
        assert changed == []
        return
    assert len(changed) == 1
    old, new = changed[0]
    assert old.startswith("(allow file-read* ")
    # Exactly one more subpath in the read allow rule: nothing else became readable.
    token = f' (subpath "{LOCALE}")'
    assert token not in old and new.count(token) == 1
    assert new.replace(token, "", 1) == old


def _confined(tmp_path: Path) -> tuple[lane.Confinement, Path]:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "f").write_text("hi", encoding="utf-8")
    return lane.confinement(sandbox=sandbox, extra_readable=lane.tool_read_roots()), sandbox


def test_confined_shasum_runs_under_c_utf8_without_a_locale_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    if not os_sandbox_available():
        with pytest.raises(SandboxError, match="no_os_barrier"):
            _confined(tmp_path)
        return
    assert os.path.isfile("/usr/bin/shasum") and os.path.isdir(LOCALE)
    box, sandbox = _confined(tmp_path)
    assert box.env["LANG"] == box.env["LC_ALL"] == "C.UTF-8"

    done = box.run(["/usr/bin/shasum", "f"], cwd=sandbox, timeout=60)

    assert done.returncode == 0, done.stderr
    assert done.stdout.split()[0] == "c22b5f9178342609428d6f51b2c5af4c0bde6a42"
    assert "locale" not in done.stderr.lower()


def test_confined_locale_data_is_readable_but_not_writable_and_siblings_stay_closed(tmp_path):
    if not os_sandbox_available():
        with pytest.raises(SandboxError, match="no_os_barrier"):
            _confined(tmp_path)
        return
    box, sandbox = _confined(tmp_path)
    ctype = Path(LOCALE) / "C.UTF-8" / "LC_CTYPE"
    assert ctype.is_file()

    read = box.run(["/usr/bin/wc", "-c", str(ctype)], cwd=sandbox, timeout=60)
    assert read.returncode == 0, read.stderr
    write = box.run(
        ["/usr/bin/touch", str(Path(LOCALE) / "nexus-3194-probe")], cwd=sandbox, timeout=60
    )
    assert write.returncode != 0
    assert not (Path(LOCALE) / "nexus-3194-probe").exists()
    # A /usr/share entry outside the granted subpaths is still unreadable.
    granted = {Path(path).name for path in lane.SANDBOX_SYSTEM_READ_SUBPATHS}
    sibling = next(
        entry
        for entry in sorted(Path("/usr/share").iterdir())
        if entry.name not in granted and entry.is_dir() and not entry.is_symlink()
    )
    listed = box.run(["/bin/ls", str(sibling)], cwd=sandbox, timeout=60)
    assert listed.returncode != 0
    assert "Operation not permitted" in listed.stderr


def test_a_shared_system_read_root_is_read_only_under_the_barrier(tmp_path, monkeypatch):
    """The sandbox itself (not file ownership) refuses writes under a shared system read root:
    a root the test owns, granted the way ``/usr/share/locale`` is, can be read, not written."""
    system_root = (tmp_path / "system-root").resolve()
    system_root.mkdir()
    (system_root / "data").write_text("public", encoding="utf-8")
    monkeypatch.setattr(
        lane, "SANDBOX_SYSTEM_READ_SUBPATHS", (*lane.SANDBOX_SYSTEM_READ_SUBPATHS, str(system_root))
    )
    if not os_sandbox_available():
        with pytest.raises(SandboxError, match="no_os_barrier"):
            _confined(tmp_path)
        return
    box, sandbox = _confined(tmp_path)

    read = box.run(["/bin/cat", str(system_root / "data")], cwd=sandbox, timeout=60)
    write = box.run(
        [sys.executable, "-I", "-c", f"open({str(system_root / 'new')!r}, 'w').write('x')"],
        cwd=sandbox,
        timeout=60,
    )

    assert read.returncode == 0 and read.stdout == "public", read.stderr
    assert write.returncode != 0 and "Operation not permitted" in write.stderr
    assert not (system_root / "new").exists()
