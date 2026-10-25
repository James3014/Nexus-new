"""Governance test fixtures: the notifier must never speak or pop up under pytest, and no test may write into the checkout."""

from pathlib import Path

import pytest

from nexus.core.notifier import NexusNotifier


class NotifierRecorder:
    """Records notifier side-effect calls instead of executing say/osascript."""

    def __init__(self, real_voice, real_ui):
        self.voice = []
        self.ui = []
        self.real_voice = real_voice
        self.real_ui = real_ui


@pytest.fixture(autouse=True)
def notifier_calls(monkeypatch):
    rec = NotifierRecorder(NexusNotifier._voice_alert, NexusNotifier._system_ui_notify)
    monkeypatch.setattr(NexusNotifier, "_voice_alert", staticmethod(rec.voice.append))
    monkeypatch.setattr(
        NexusNotifier,
        "_system_ui_notify",
        staticmethod(lambda title, message: rec.ui.append((title, message))),
    )
    return rec


# Tests must not write into the repository checkout. Cairnwork runs these files as
# pass-to-pass tests inside a sandboxed checkout and fails a candidate whose checkout
# changed (cairnwork#209). Writers such as continuous_learning and UCCRouter default to
# the cwd or a given project root, so a test that passes "." lands in <repo>/.nexus.
REPO_ROOT = Path(__file__).resolve().parents[2]
_IGNORED_TOP_LEVEL = frozenset({"__pycache__", ".pytest_cache"})


def checkout_snapshot(root: Path) -> tuple[frozenset[str], dict[str, tuple[int, int]]]:
    """Top-level entry names of ``root`` and (size, mtime_ns) of every file under ``root/.nexus``."""
    top = frozenset(p.name for p in root.iterdir() if p.name not in _IGNORED_TOP_LEVEL)
    files: dict[str, tuple[int, int]] = {}
    nexus_dir = root / ".nexus"
    if nexus_dir.is_dir():
        for path in nexus_dir.rglob("*"):
            if path.is_file():
                st = path.stat()
                files[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return top, files


def checkout_changes(before, after) -> list[str]:
    """Paths created or modified between two ``checkout_snapshot`` results (sorted)."""
    top_before, files_before = before
    top_after, files_after = after
    changed = set(top_after - top_before)
    changed |= {p for p, sig in files_after.items() if files_before.get(p) != sig}
    return sorted(changed)


@pytest.fixture
def checkout_guard_helpers():
    return checkout_snapshot, checkout_changes


@pytest.fixture(autouse=True)
def no_checkout_writes():
    before = checkout_snapshot(REPO_ROOT)
    yield
    changes = checkout_changes(before, checkout_snapshot(REPO_ROOT))
    if changes:
        pytest.fail(
            "test wrote into the repository checkout (use tmp_path): " + ", ".join(changes),
            pytrace=False,
        )
