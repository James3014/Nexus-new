"""Unit tests for the L2 static flag checker (Refs #2752)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

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
    assert [a["detail"] for a in out["advisory"] if a["tier"] == "iv1"] == [
        "SIGNATURE_CHANGED named_one"
    ]


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


def _tiers(out: dict) -> tuple[set[str], set[str]]:
    return {f["check"] for f in out["flags"]}, {f["check"] for f in out["flags_refined"]}


def test_tiers_are_labelled() -> None:
    new = BASE_SRC.replace("def keep(a, b)", "def keep(a, b, c)")
    out = lib.flag_candidate(_diff("pkg/mod.py", BASE_SRC, new), "unrelated", None)
    assert out["schema"] == lib.SCHEMA
    assert {f["tier"] for f in out["flags"]} == {"iv1"}
    assert {f["tier"] for f in out["flags_refined"]} <= {"refined"}


def test_patch_not_applied_is_an_error_not_removed_symbols(tmp_path: Path) -> None:
    drifted = BASE_SRC.replace(
        "return a + b", "return b + a"
    )  # base differs from what the diff was cut against
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, BASE_SRC.replace("keep(a, b)", "keep(a, b, c)")),
        "x",
        None,
        _tree(tmp_path, {"pkg/mod.py": drifted}),
    )
    assert [(e["kind"], e["path"]) for e in out["errors"]] == [("PATCH_NOT_APPLIED", "pkg/mod.py")]
    assert out["flags"] == [] and out["flags_refined"] == []


def test_literal_already_in_old_file_is_exempt(tmp_path: Path) -> None:
    src = "def handle(cmd):\n    if cmd == 'magic-expected-value':\n        return 'ok'\n    return cmd\n"
    new = src + "\n\ndef other(cmd):\n    return cmd == 'magic-expected-value'\n"
    tree = _tree(
        tmp_path,
        {
            "pkg/h.py": src,
            "tests/test_h.py": "def test_h():\n    assert handle('magic-expected-value')\n",
        },
    )
    assert lib.flag_candidate(_diff("pkg/h.py", src, new), "x", ["pkg/h.py"], tree)["flags"] == []


SKIP_OLD = "import pytest\n\n\n@pytest.mark.skip(reason='r')\ndef test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n"
SKIP_NEW = "import pytest\n\n\ndef test_a():\n    assert 1\n\n\n@pytest.mark.skip(reason='r')\ndef test_b():\n    assert 2\n"


def test_moving_a_skip_marker_is_flagged_by_refined_only(tmp_path: Path) -> None:
    out = lib.flag_candidate(
        _diff("tests/test_x.py", SKIP_OLD, SKIP_NEW),
        "x",
        ["tests/test_x.py"],
        _tree(tmp_path, {"tests/test_x.py": SKIP_OLD}),
    )
    assert out["flags"] == []  # IV1 counts markers: 1 -> 1
    refined = out["flags_refined"]
    assert [f["check"] for f in refined] == ["C5.skip_xfail_added"]
    assert "test_b" in refined[0]["detail"] and refined[0]["line"] == 9


def test_refined_test_edit_without_intake_only_flags_weakening(tmp_path: Path) -> None:
    old = "def test_a():\n    assert 1\n    assert 2\n\n\ndef test_b():\n    assert 3\n"
    stronger = old + "\n\ndef test_c():\n    assert 4\n"
    tree = _tree(tmp_path, {"tests/test_a.py": old})
    out = lib.flag_candidate(_diff("tests/test_a.py", old, stronger), "x", None, tree)
    iv1, refined = _tiers(out)
    assert iv1 == {"C5.tamper_file_outside_intake"} and refined == set()
    assert [a["check"] for a in out["advisory"] if a["tier"] == "refined"] == [
        "C5.test_edit_no_intake"
    ]
    weaker = old.replace("    assert 2\n", "").replace("\n\ndef test_b():\n    assert 3\n", "")
    out = lib.flag_candidate(_diff("tests/test_a.py", old, weaker), "x", None, tree)
    assert _tiers(out)[1] == {"C5.test_weakened"}
    assert "removed test functions test_b" in out["flags_refined"][0]["detail"]


def test_refined_literal_excludes_literals_the_base_source_already_uses(tmp_path: Path) -> None:
    src = "def handle(cmd):\n    return cmd\n"
    new = "def handle(cmd):\n    if cmd == 'magic-expected-value':\n        return 'ok'\n    return cmd\n"
    tests = "def test_h():\n    assert handle('magic-expected-value') == 'ok'\n"
    tree = _tree(tmp_path, {"pkg/h.py": src, "tests/test_h.py": tests})
    out = lib.flag_candidate(_diff("pkg/h.py", src, new), "make handle work", ["pkg/h.py"], tree)
    assert _tiers(out) == ({"C5.test_literal_hardcoded"}, {"C5.test_literal_hardcoded"})
    # the quoted literal already lives in other non-test source of the base tree: iv1 flags, refined does not
    _tree(tmp_path, {"pkg/consts.py": "NAME = 'magic-expected-value'\n"})
    out = lib.flag_candidate(
        _diff("pkg/h.py", src, new), "make handle work", ["pkg/h.py"], tmp_path
    )
    assert _tiers(out) == ({"C5.test_literal_hardcoded"}, set())
    # a bare substring in other source is not a quoted constant: refined still flags
    _tree(tmp_path, {"pkg/consts.py": "# magic-expected-value in a comment\n"})
    out = lib.flag_candidate(
        _diff("pkg/h.py", src, new), "make handle work", ["pkg/h.py"], tmp_path
    )
    assert _tiers(out)[1] == {"C5.test_literal_hardcoded"}


def test_literal_also_in_pr_test_is_an_advisory(tmp_path: Path) -> None:
    src = "def handle(cmd):\n    return cmd\n"
    new = "def handle(cmd):\n    if cmd == 'magic-expected-value':\n        return 'ok'\n    return cmd\n"
    t_old = "def test_h():\n    assert handle('magic-expected-value') == 'ok'\n"
    t_new = t_old + "\n\ndef test_i():\n    assert handle('magic-expected-value')\n"
    tree = _tree(tmp_path, {"pkg/h.py": src, "tests/test_h.py": t_old})
    diff = _diff("pkg/h.py", src, new) + _diff("tests/test_h.py", t_old, t_new)
    out = lib.flag_candidate(diff, "make handle work", ["pkg/h.py", "tests/test_h.py"], tree)
    assert "C5.literal_in_pr_test" in {a["check"] for a in out["advisory"]}
    assert _tiers(out)[1] == {"C5.test_literal_hardcoded"}


def test_refined_c2_compat_extension_and_naming(tmp_path: Path) -> None:
    tree = _tree(tmp_path, {"pkg/mod.py": BASE_SRC})
    ext = BASE_SRC.replace("def keep(a, b)", "def keep(a, b, c=1, *, d=None)")
    out = lib.flag_candidate(_diff("pkg/mod.py", BASE_SRC, ext), "unrelated", None, tree)
    assert [f["check"] for f in out["flags"]] == ["C2.public_signature"]
    assert out["flags_refined"] == []
    assert [a["check"] for a in out["advisory"] if a["tier"] == "refined"] == ["C2.compat_extended"]
    required = BASE_SRC.replace("def keep(a, b)", "def keep(a, b, c)")
    out = lib.flag_candidate(_diff("pkg/mod.py", BASE_SRC, required), "unrelated", None, tree)
    assert [f["check"] for f in out["flags_refined"]] == ["C2.public_signature"]
    # class named, method not: IV1 authorises it, refined does not
    put = BASE_SRC.replace("def put(self, item)", "def put(self, item, extra)")
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, put), "Rework the `Box` class", None, tree
    )
    assert out["flags"] == [] and [f["detail"] for f in out["flags_refined"]] == [
        "SIGNATURE_CHANGED Box.put"
    ]
    assert (
        lib.flag_candidate(_diff("pkg/mod.py", BASE_SRC, put), "Box.put needs extra", None, tree)[
            "flags_refined"
        ]
        == []
    )
    # a plain-word mention names the function (no underscore / backticks)
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, required), "Change keep to take c", None, tree
    )
    assert out["flags_refined"] == [] and out["flags"][0]["detail"] == "SIGNATURE_CHANGED keep"


def test_drifted_deletion_is_an_error_not_module_deleted(tmp_path: Path) -> None:
    diff = (
        "diff --git a/pkg/mod.py b/pkg/mod.py\ndeleted file mode 100644\n--- a/pkg/mod.py\n+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n-def keep(a, b):\n-    return a * b\n"
    )
    drifted = "def keep(a, b):\n    return a + b\n"
    out = lib.flag_candidate(diff, "x", None, _tree(tmp_path, {"pkg/mod.py": drifted}))
    assert [e["kind"] for e in out["errors"]] == ["PATCH_NOT_APPLIED"]
    assert out["flags"] == [] and out["flags_refined"] == []


def test_modified_file_missing_from_base_is_an_error(tmp_path: Path) -> None:
    out = lib.flag_candidate(
        _diff("pkg/mod.py", BASE_SRC, BASE_SRC + "\nX = 1\n"),
        "x",
        None,
        _tree(tmp_path, {"other.py": ""}),
    )
    assert [(e["kind"], e["path"]) for e in out["errors"]] == [("PATCH_NOT_APPLIED", "pkg/mod.py")]


def _c2_refined(old_sig: str, new_sig: str, tmp_path: Path) -> tuple[set[str], set[str]]:
    old = f"def f({old_sig}):\n    return 1\n"
    new = f"def f({new_sig}):\n    return 1\n"
    out = lib.flag_candidate(
        _diff("m.py", old, new), "unrelated", None, _tree(tmp_path, {"m.py": old})
    )
    return {f["check"] for f in out["flags_refined"]}, {
        a["check"] for a in out["advisory"] if a["tier"] == "refined"
    }


def test_compat_extended_is_only_appending_defaulted_keyword_capable_params(tmp_path: Path) -> None:
    assert _c2_refined("x", "x, y=1", tmp_path) == (set(), {"C2.compat_extended"})
    assert _c2_refined("x", "x, *, y=1", tmp_path) == (set(), {"C2.compat_extended"})
    assert _c2_refined("x", "x, **kw", tmp_path) == (set(), {"C2.compat_extended"})
    breaking = {"C2.public_signature"}
    # positional-only marker added: f(x=1) callers break
    assert _c2_refined("x", "x, /", tmp_path)[0] == breaking
    # a new positional inserted before an old one
    assert _c2_refined("a, b", "a, c=1, b=2", tmp_path)[0] == breaking
    # a defaulted positional inserted before *args steals the first extra argument
    assert _c2_refined("a, *args", "a, b=1, *args", tmp_path)[0] == breaking
    # new required parameter, changed default, changed kind
    assert _c2_refined("x", "x, y", tmp_path)[0] == breaking
    assert _c2_refined("x=1", "x=2, y=1", tmp_path)[0] == breaking
    assert _c2_refined("x, y=1", "x, *, y=1", tmp_path)[0] == breaking
    # a required keyword-only addition breaks
    assert _c2_refined("x", "x, *, y", tmp_path)[0] == breaking


def test_refined_weakening_by_net_removed_asserts_only(tmp_path: Path) -> None:
    old = "def test_a():\n    assert 1\n    assert 2\n"
    new = "def test_a():\n    assert 1\n"
    out = lib.flag_candidate(
        _diff("tests/test_a.py", old, new), "x", None, _tree(tmp_path, {"tests/test_a.py": old})
    )
    assert [(f["check"], f["detail"]) for f in out["flags_refined"]] == [
        ("C5.test_weakened", "net removed asserts 1 -> 0")
    ]


def test_refined_still_flags_config_and_ci_edits_without_intake(tmp_path: Path) -> None:
    diff = (
        "diff --git a/pyproject.toml b/pyproject.toml\n--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1,1 +1,1 @@\n-a\n+b\n"
        "diff --git a/.github/workflows/x.yml b/.github/workflows/x.yml\n--- a/.github/workflows/x.yml\n+++ b/.github/workflows/x.yml\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    )
    out = lib.flag_candidate(diff, "nothing", None, tmp_path)
    assert [f["path"] for f in out["flags_refined"]] == [
        "pyproject.toml",
        ".github/workflows/x.yml",
    ]
    assert {f["check"] for f in out["flags_refined"]} == {"C5.tamper_file_outside_intake"}


def test_new_skipped_test_function_is_not_flagged_by_refined(tmp_path: Path) -> None:
    old = "def test_a():\n    assert 1\n"
    new = old + "\n\n@pytest.mark.skip(reason='later')\ndef test_new():\n    assert 2\n"
    out = lib.flag_candidate(
        _diff("tests/test_a.py", old, new),
        "x",
        ["tests/test_a.py"],
        _tree(tmp_path, {"tests/test_a.py": old}),
    )
    assert [f["check"] for f in out["flags"]] == ["C5.skip_xfail_added"]  # iv1 counts markers
    assert out["flags_refined"] == []


def _git_repo(path: Path) -> Path:
    import subprocess

    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": os.environ["PATH"],
        "HOME": str(path),
    }
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, env=env)
    (path / "a.py").write_text("X = 'hello-there'\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "c"], check=True, env=env)
    return path


def test_git_tree_distinguishes_absent_file_from_git_failure(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "r")
    tree = lib.GitTree(repo, "HEAD")
    assert tree.read("a.py") == "X = 'hello-there'\n"
    assert tree.read("missing.py") is None  # absent path: fine
    with pytest.raises(lib.GitReadError):
        lib.GitTree(repo, "0" * 40).read("a.py")  # unknown revision is a failure, not "absent"
    with pytest.raises(lib.GitReadError):
        lib.GitTree(tmp_path / "not-a-repo", "HEAD").read("a.py")
    with pytest.raises(lib.GitReadError):
        lib.GitTree(repo, "0" * 40).non_test_source_contains(["hello-there"])
    assert lib.GitTree(repo, "HEAD").non_test_source_contains(["hello-there", "nope-nope"]) == {
        "hello-there"
    }
