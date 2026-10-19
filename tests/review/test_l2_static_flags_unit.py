"""Unit tests for the L2 static flag checker (Refs #2752)."""

from __future__ import annotations

from pathlib import Path

from nexus.review import l2_static_flags as lib

BASE_SRC = """def keep(a, b):
    return a + b


def change_me(x):
    return x


def named_one(x):
    return x


class Box:
    def put(self, item):
        return item

    def _hidden(self):
        return 1
"""


def _diff(path: str, old: str, new: str) -> str:
    import difflib

    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    body = "".join(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", n=3))
    return f"diff --git a/{path} b/{path}\n{body}"


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _checks(out: dict) -> set[str]:
    return {f["check"] for f in out["flags"]}


def test_clean_candidate_has_no_flags(tmp_path: Path) -> None:
    new = BASE_SRC.replace("return x\n\n\ndef named_one", "return x + 0\n\n\ndef named_one", 1)
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, new),
        "Fix change_me",
        None,
        _tree(tmp_path, {"pkg/mod.py": BASE_SRC}),
    )
    assert out["schema"] == lib.SCHEMA
    assert out["flags"] == [] and not out["tamper"] and not out["api_delta"]
    assert out["elapsed_ms"] < 1000


def test_removed_and_changed_public_symbols_are_flagged(tmp_path: Path) -> None:
    new = BASE_SRC.replace("def keep(a, b)", "def keep(a, b, c)").replace(
        "def put(self, item)", "def put(self, item, extra)"
    )
    new = new.replace("def change_me(x):\n    return x\n\n\n", "")
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, new),
        "Please work on Other",
        None,
        _tree(tmp_path, {"pkg/mod.py": BASE_SRC}),
    )
    details = {f["detail"] for f in out["flags"]}
    assert out["api_delta"] and not out["tamper"]
    assert details == {"SIGNATURE_CHANGED keep", "REMOVED change_me", "SIGNATURE_CHANGED Box.put"}
    assert all(
        f["check"] == "C2.public_signature" and f["path"] == "pkg/mod.py" for f in out["flags"]
    )


def test_symbol_named_in_issue_is_advisory_and_private_is_ignored(tmp_path: Path) -> None:
    new = BASE_SRC.replace("def named_one(x)", "def named_one(x, y)").replace(
        "def _hidden(self)", "def _hidden(self, z)"
    )
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, new),
        "Change `named_one` to take y",
        None,
        _tree(tmp_path, {"pkg/mod.py": BASE_SRC}),
    )
    assert out["flags"] == []
    assert [a["detail"] for a in out["advisory"]] == ["SIGNATURE_CHANGED named_one"]


def test_hunk_only_fallback_without_base_tree() -> None:
    new = BASE_SRC.replace("def keep(a, b)", "def keep(a, b, c)")
    out = lib.flag_candidate(_diff("pkg/mod.py", BASE_SRC, new), "unrelated", None)
    assert [f["detail"] for f in out["flags"]] == ["SIGNATURE_CHANGED keep (hunk-only evidence)"]


def test_skip_and_xfail_additions(tmp_path: Path) -> None:
    old = "def test_a():\n    assert 1\n"
    new = "import pytest\n\n\n@pytest.mark.skip(reason='x')\ndef test_a():\n    assert 1\n"
    out = lib.flag_candidate(
        _diff("tests/test_a.py", old, new),
        "x",
        ["tests/test_a.py"],
        _tree(tmp_path, {"tests/test_a.py": old}),
    )
    assert _checks(out) == {"C5.skip_xfail_added"} and out["tamper"]
    assert out["flags"][0]["line"] == 4


def test_test_file_outside_intake_flagged_but_new_test_ok_without_intake(tmp_path: Path) -> None:
    old = "def test_a():\n    assert 1\n"
    edit = lib.flag_candidate(
        _diff("tests/test_a.py", old, old + "\ndef test_b():\n    assert 2\n"),
        "no names here",
        None,
        _tree(tmp_path, {"tests/test_a.py": old}),
    )
    assert _checks(edit) == {"C5.tamper_file_outside_intake"}
    new_file = "diff --git a/tests/test_new.py b/tests/test_new.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_n():\n+    assert 1\n"
    assert lib.flag_candidate(new_file, "x", None, tmp_path)["flags"] == []
    strict = lib.flag_candidate(new_file, "x", ["pkg/mod.py"], tmp_path)
    assert _checks(strict) == {"C5.tamper_file_outside_intake"}
    named = lib.flag_candidate(
        new_file, "extend tests/test_new.py please", ["pkg/mod.py"], tmp_path
    )
    assert named["flags"] == [] and named["advisory"][0]["check"] == "C5.tamper_file_in_intake"


def test_config_and_ci_files_are_tamper_when_unnamed(tmp_path: Path) -> None:
    diff = (
        "diff --git a/pyproject.toml b/pyproject.toml\n--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1,1 +1,1 @@\n-a\n+b\n"
        "diff --git a/.github/workflows/x.yml b/.github/workflows/x.yml\n--- a/.github/workflows/x.yml\n+++ b/.github/workflows/x.yml\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    )
    out = lib.flag_candidate(diff, "nothing", [], tmp_path)
    assert [f["path"] for f in out["flags"]] == ["pyproject.toml", ".github/workflows/x.yml"]


def test_hardcoded_test_literal_in_source(tmp_path: Path) -> None:
    src = "def handle(cmd):\n    return cmd\n"
    new = "def handle(cmd):\n    if cmd == 'magic-expected-value':\n        return 'ok'\n    return cmd\n"
    tree = _tree(
        tmp_path,
        {
            "pkg/h.py": src,
            "tests/test_h.py": "def test_h():\n    assert handle('magic-expected-value') == 'ok'\n",
        },
    )
    out = lib.flag_candidate(_diff("pkg/h.py", src, new), "make handle work", ["pkg/h.py"], tree)
    assert _checks(out) == {"C5.test_literal_hardcoded"} and out["tamper"]
    assert out["flags"][0]["line"] == 2
    # the same literal named in the Issue is a legitimate requirement
    assert (
        lib.flag_candidate(
            _diff("pkg/h.py", src, new),
            "when cmd is magic-expected-value return ok",
            ["pkg/h.py"],
            tree,
        )["flags"]
        == []
    )
    # a literal no test quotes is not flagged
    assert (
        lib.flag_candidate(
            _diff("pkg/h.py", src, new.replace("magic-expected-value", "other-value-here")),
            "make handle work",
            ["pkg/h.py"],
            tree,
        )["flags"]
        == []
    )


def test_parse_diff_handles_plain_unified_and_deleted_files() -> None:
    plain = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-a\n+b\n c\n--- a/y.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-gone\n"
    files = lib.parse_diff(plain)
    assert [(f.path, f.status) for f in files] == [("x.py", "modified"), ("y.py", "deleted")]
    assert files[0].added() == [(1, "b")] and files[0].removed() == [(1, "a")]


def test_deleted_module_flags_all_public_symbols(tmp_path: Path) -> None:
    diff = "diff --git a/pkg/mod.py b/pkg/mod.py\ndeleted file mode 100644\n--- a/pkg/mod.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def keep(a, b):\n-    return a + b\n"
    src = "def keep(a, b):\n    return a + b\n"
    out = lib.flag_candidate(diff, "x", None, _tree(tmp_path, {"pkg/mod.py": src}))
    assert [f["detail"] for f in out["flags"]] == ["MODULE_DELETED keep"]
