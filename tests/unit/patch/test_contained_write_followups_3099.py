"""Follow-ups from #3023 (#3099): strict decode, CRLF multi-line SEARCH, root writability,
host-code path case, and two changed files in target discovery."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.contained_write import PathContainmentError, read_text_in_root
from nexus.engine.model_output_sandbox import holds_host_code
from nexus.engine.patch.apply_engine import PatchApplyEngine
from nexus.engine.patch.target_discovery import TargetFileDiscovery


def _block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n"


def test_read_text_in_root_strict_refuses_non_utf8(tmp_path):
    (tmp_path / "bad.py").write_bytes(b"x = '\xff'\n")
    with pytest.raises(PathContainmentError, match="not_utf8:bad.py"):
        read_text_in_root(tmp_path, "bad.py", strict=True)
    assert "\ufffd" in read_text_in_root(tmp_path, "bad.py")


def test_engine_refuses_non_utf8_target_without_rewriting(tmp_path):
    raw = b"a = 1\n# \xff\n"
    (tmp_path / "t.py").write_bytes(raw)
    result = PatchApplyEngine(tmp_path).apply_patch("t", "t.py", _block("a = 1", "a = 2"))
    assert result["reason"] == "TARGET_NOT_UTF8: t.py"
    assert (tmp_path / "t.py").read_bytes() == raw


def test_multi_line_search_matches_crlf_file_and_keeps_crlf(tmp_path):
    (tmp_path / "t.py").write_bytes(b"a = 1\r\nb = 2\r\nc = 3\r\n")
    result = PatchApplyEngine(tmp_path).apply_patch(
        "t", "t.py", _block("a = 1\nb = 2", "a = 10\nb = 20")
    )
    assert result["success"] is True
    assert (tmp_path / "t.py").read_bytes() == b"a = 10\r\nb = 20\r\nc = 3\r\n"


def test_mixed_line_endings_are_left_as_they_were(tmp_path):
    (tmp_path / "t.py").write_bytes(b"a = 1\r\nb = 2\nc = 3\n")
    result = PatchApplyEngine(tmp_path).apply_patch("t", "t.py", _block("c = 3", "c = 4"))
    assert result["success"] is True
    assert (tmp_path / "t.py").read_bytes() == b"a = 1\r\nb = 2\nc = 4\n"


def test_read_only_target_refused_when_access_always_says_writable(tmp_path, monkeypatch):
    # root: os.access(W_OK) is true for every file; the mode bits still say read-only.
    target = tmp_path / "t.py"
    target.write_text("a = 1\n", encoding="utf-8")
    target.chmod(0o444)
    monkeypatch.setattr(os, "access", lambda *a, **k: True)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    result = PatchApplyEngine(tmp_path).apply_patch("t", "t.py", _block("a = 1", "a = 2"))
    assert result["reason"] == "TARGET_NOT_WRITABLE: t.py"
    assert target.read_text(encoding="utf-8") == "a = 1\n"


def test_holds_host_code_ignores_case_of_a_package_path(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    (root / "nexus" / "core").mkdir(parents=True)
    monkeypatch.setattr(sys, "path", [str(root)])
    monkeypatch.setattr(
        "nexus.engine.model_output_sandbox.host_code_roots", lambda: (root.resolve(),)
    )
    assert holds_host_code(root / "nexus" / "core") is True
    # Spelled with other case, as a case-insensitive filesystem would accept it.
    upper = Path(str(root.resolve()).replace("checkout", "CheckOut")) / "NEXUS" / "Core"
    assert holds_host_code(upper) is True
    assert holds_host_code(root / ".nexus" / "work") is False


def test_two_changed_files_and_no_other_candidate_is_not_resolved(tmp_path):
    (tmp_path / "one.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("y = 1\n", encoding="utf-8")
    status = MagicMock(returncode=0, stdout=" M one.py\n M two.py\n")
    with patch("subprocess.run", return_value=status):
        result = TargetFileDiscovery().resolve("no file named here", project_root=str(tmp_path))
    assert result.resolved is False
    assert result.reason == "NO_TARGET_FILE_FOUND"
