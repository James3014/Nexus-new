"""The local-heal patch applier does not rewrite a target that is not UTF-8 (#3023).

The contained read decodes undecodable bytes as U+FFFD, and writing that text back would change
bytes the patch never touched while the result still says success. PatchApplier now refuses
such a target with ``TARGET_NOT_UTF8`` and leaves the file as it was, the same rule #3026 put
in the Patch Apply v2 engine and in SafePatcher's direct-write fallback.

Every refusal case checks the file's exact bytes afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services.local_heal.interface import LocalizedFile
from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

WRONG = "def add(a, b):\n    return a - b\n"
RIGHT = "def add(a, b):\n    return a + b\n"

# Not valid UTF-8: a latin-1 comment, and a lone continuation byte.
NOT_UTF8 = {
    "latin1": b"# caf\xe9\n" + WRONG.encode(),
    "invalid": b"# \x80 stray byte\n" + WRONG.encode(),
}


@pytest.fixture(autouse=True)
def _standard_protocol(monkeypatch):
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "standard")


def _intents(text: str):
    parser = SolidSearchReplaceProtocol()
    intents = parser.parse(text)
    assert isinstance(intents, list) and intents
    return parser, intents


def _apply(repo: Path, file_path: str, localized: list[LocalizedFile] | None = None):
    parser, intents = _intents(
        f"FILE: {file_path}\n<<<<<<< SEARCH\n{WRONG}=======\n{RIGHT}>>>>>>> REPLACE\n"
    )
    return PatchApplier(parser, Patcher()).apply_and_validate(
        intents=intents, repo_dir=repo, localized_files=localized or []
    )


@pytest.mark.parametrize("kind", sorted(NOT_UTF8))
def test_non_utf8_target_is_refused_and_keeps_its_bytes(tmp_path, kind):
    (tmp_path / "calc.py").write_bytes(NOT_UTF8[kind])
    result = _apply(tmp_path, "calc.py")
    assert result.success is False
    assert result.error_reason == "TARGET_NOT_UTF8:calc.py"
    assert result.applied_diffs == []
    assert (tmp_path / "calc.py").read_bytes() == NOT_UTF8[kind]


def test_cross_file_fallback_refuses_a_non_utf8_match_and_keeps_its_bytes(tmp_path):
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_bytes(NOT_UTF8["latin1"])
    result = _apply(tmp_path, "calc.py", [LocalizedFile(path="other.py", content="")])
    assert result.success is False
    assert result.error_reason == "TARGET_NOT_UTF8:other.py"
    assert (tmp_path / "other.py").read_bytes() == NOT_UTF8["latin1"]
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == "x = 1\n"


def test_non_utf8_target_without_a_match_still_falls_back_to_a_utf8_file(tmp_path):
    # The non-UTF-8 file is never written, so the cross-file fallback still runs as before.
    original = b"# caf\xe9\nx = 1\n"
    (tmp_path / "calc.py").write_bytes(original)
    (tmp_path / "other.py").write_text(WRONG, encoding="utf-8")
    result = _apply(tmp_path, "calc.py", [LocalizedFile(path="other.py", content="")])
    assert result.success is True, result.error_reason
    assert (tmp_path / "other.py").read_text(encoding="utf-8") == RIGHT
    assert (tmp_path / "calc.py").read_bytes() == original


def test_preflight_full_file_parse_refuses_a_non_utf8_target(tmp_path):
    # An indented REPLACE does not parse alone, so preflight reads and parses the whole file.
    original = b"# caf\xe9\nclass C:\n    def add(self, a, b):\n        return a - b\n"
    (tmp_path / "calc.py").write_bytes(original)
    parser, intents = _intents(
        "FILE: calc.py\n<<<<<<< SEARCH\n        return a - b\n=======\n"
        "        if a:\n            return a + b\n        return b\n>>>>>>> REPLACE\n"
    )
    applier = PatchApplier(parser, Patcher())
    passed, reason, telemetry = applier.preflight_check(intents, tmp_path)
    assert passed is False
    assert reason == "TARGET_NOT_UTF8:calc.py"
    assert telemetry["preflight_checks"][-1]["check"] == "target_utf8"
    result = applier.apply_and_validate(intents=intents, repo_dir=tmp_path, localized_files=[])
    assert result.success is False
    assert result.error_reason == "TARGET_NOT_UTF8:calc.py"
    assert (tmp_path / "calc.py").read_bytes() == original


def test_preflight_does_not_refuse_a_non_utf8_target_the_search_is_not_in(tmp_path):
    # Indented REPLACE (preflight parses the whole file), the named target is not UTF-8 and does
    # not hold the SEARCH, a UTF-8 localized file does: the cross-file fallback applies there.
    target = b"# caf\xe9\nclass D:\n    pass\n"
    (tmp_path / "calc.py").write_bytes(target)
    (tmp_path / "other.py").write_text(
        "class C:\n    def add(self, a, b):\n        return a - b\n", encoding="utf-8"
    )
    parser, intents = _intents(
        "FILE: calc.py\n<<<<<<< SEARCH\n        return a - b\n=======\n"
        "        if a:\n            return a + b\n        return b\n>>>>>>> REPLACE\n"
    )
    result = PatchApplier(parser, Patcher()).apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[LocalizedFile(path="other.py", content="")],
    )
    assert result.success is True, result.error_reason
    assert "return a + b" in (tmp_path / "other.py").read_text(encoding="utf-8")
    assert (tmp_path / "calc.py").read_bytes() == target


def test_indented_replace_on_a_valid_utf8_target_with_the_search_still_applies(tmp_path):
    # Preflight parses the whole file (indented REPLACE) and the target holds the SEARCH: a
    # UTF-8 target passes both the preflight and the apply-time check and is patched.
    original = "# café\nclass C:\n    def add(self, a, b):\n        return a - b\n"
    (tmp_path / "calc.py").write_text(original, encoding="utf-8")
    parser, intents = _intents(
        "FILE: calc.py\n<<<<<<< SEARCH\n        return a - b\n=======\n"
        "        if a:\n            return a + b\n        return b\n>>>>>>> REPLACE\n"
    )
    result = PatchApplier(parser, Patcher()).apply_and_validate(
        intents=intents, repo_dir=tmp_path, localized_files=[]
    )
    assert result.success is True, result.error_reason
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == original.replace(
        "        return a - b\n", "        if a:\n            return a + b\n        return b\n"
    )


def test_valid_utf8_target_with_non_ascii_text_still_applies(tmp_path):
    original = "# café, naïve, 日本語\n" + WRONG
    (tmp_path / "calc.py").write_text(original, encoding="utf-8")
    result = _apply(tmp_path, "calc.py")
    assert result.success is True, result.error_reason
    assert (tmp_path / "calc.py").read_bytes() == ("# café, naïve, 日本語\n" + RIGHT).encode()


def test_valid_utf8_cross_file_fallback_still_applies(tmp_path):
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("# café\n" + WRONG, encoding="utf-8")
    result = _apply(tmp_path, "calc.py", [LocalizedFile(path="other.py", content="")])
    assert result.success is True, result.error_reason
    assert (tmp_path / "other.py").read_text(encoding="utf-8") == "# café\n" + RIGHT


def test_valid_utf8_target_with_a_literal_replacement_character_is_refused_too(tmp_path):
    # The check looks for U+FFFD in the decoded text, so it cannot tell a literal one from a
    # decoding artefact; it refuses both and changes nothing.
    original = "# \ufffd\n" + WRONG
    (tmp_path / "calc.py").write_text(original, encoding="utf-8")
    result = _apply(tmp_path, "calc.py")
    assert result.success is False
    assert result.error_reason == "TARGET_NOT_UTF8:calc.py"
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == original
