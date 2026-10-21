from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)


def test_isolated_workspace_apply_blocked() -> None:
    request = IsolatedApplyRequest(
        task_id="t1",
        source_root=".",
        target_file="test.py",
        unified_diff="",
        selected_candidate_hash="",
        mutation_allowed=False,
    )
    receipt = run_isolated_workspace_apply(request)
    assert receipt.patch_apply_status == "blocked"
    assert "mutation_not_allowed" in receipt.patch_apply_error


def test_isolated_workspace_apply_traversal() -> None:
    request = IsolatedApplyRequest(
        task_id="t2",
        source_root=".",
        target_file="../outside.py",
        unified_diff="",
        selected_candidate_hash="",
        mutation_allowed=True,
    )
    receipt = run_isolated_workspace_apply(request)
    assert receipt.patch_apply_status == "blocked"
    assert "path_traversal_detected" in receipt.patch_apply_error


def test_isolated_workspace_apply_success_and_mismatch() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)

        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        diff_hash = hashlib.sha256(diff.strip().encode("utf-8")).hexdigest()

        request_match = IsolatedApplyRequest(
            task_id="t3",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff,
            selected_candidate_hash=diff_hash,
            mutation_allowed=True,
            work_dir=os.path.join(src_root, "artifacts"),
        )

        receipt_match = run_isolated_workspace_apply(request_match)
        assert receipt_match.patch_apply_status == "applied"
        assert receipt_match.selected_candidate_hash_matches_applied is True
        assert receipt_match.candidate_output_isolated is True
        assert receipt_match.applied_patch_hash_source == "git_diff"

        if os.path.exists(receipt_match.workspace_path):
            shutil.rmtree(receipt_match.workspace_path)

        request_mismatch = IsolatedApplyRequest(
            task_id="t4",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff,
            selected_candidate_hash="wrong_hash_provenance",
            mutation_allowed=True,
            work_dir=os.path.join(src_root, "artifacts-mismatch"),
        )
        receipt_mismatch = run_isolated_workspace_apply(request_mismatch)
        assert receipt_mismatch.patch_apply_status == "applied"
        assert receipt_mismatch.selected_candidate_hash_matches_applied is False
        assert receipt_mismatch.applied_patch_hash_source == "git_diff"

        if os.path.exists(receipt_mismatch.workspace_path):
            shutil.rmtree(receipt_mismatch.workspace_path)

        with open(src_path, "r", encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"


def test_isolated_workspace_apply_metadata_diff_but_canonical_matches() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)

        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        # Unified diff without git headers
        diff_no_header = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        # Let's calculate the hash of canonicalized diff_no_header
        # In isolated_workspace_apply, selected_candidate_hash will be compared against the canonicalized version of actual_diff
        # Let's import the normalizer or calculate it manually
        import re
        def canonicalize_diff(diff_text: str) -> str:
            lines = []
            raw_lines = diff_text.replace("\r\n", "\n").split("\n")
            for line in raw_lines:
                line_rstrip = line.rstrip()
                if line_rstrip.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
                    continue
                if line_rstrip.startswith("@@"):
                    m = re.match(
                        r"^@@\s+-\d+(?:,(\d+))?\s+\+\d+(?:,(\d+))?\s+@@",
                        line_rstrip,
                    )
                    if m:
                        lines.append(
                            f"@@ -0,{m.group(1) or '1'} +0,{m.group(2) or '1'} @@"
                        )
                    continue
                if line_rstrip.startswith(("-", "+", " ")):
                    op = line_rstrip[0]
                    content = line[1:].rstrip()
                    lines.append(f"{op}{content}")
                    continue
            return "\n".join(lines).strip()

        canon = canonicalize_diff(diff_no_header)
        canon_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()

        request = IsolatedApplyRequest(
            task_id="t5",
            source_root=src_root,
            target_file=test_file,
            unified_diff=diff_no_header,
            selected_candidate_hash=canon_hash,
            mutation_allowed=True,
            work_dir=os.path.join(src_root, "artifacts-canonical"),
        )

        receipt = run_isolated_workspace_apply(request)
        assert receipt.patch_apply_status == "applied"
        assert receipt.selected_candidate_hash_matches_applied is True

        # Clean up
        if os.path.exists(receipt.workspace_path):
            shutil.rmtree(receipt.workspace_path)

        # Verification of strict formatting invariants (Commit 2 check)
        # 1. Indentation mismatch check
        diff_with_indent = "@@ -1 +1 @@\n-print('hello')\n+  print('world')\n"
        diff_no_indent = "@@ -1 +1 @@\n-print('hello')\n+print('world')\n"
        assert canonicalize_diff(diff_with_indent) != canonicalize_diff(diff_no_indent)

        # 2. String literal space mismatch check
        diff_with_double_space = "@@ -1 +1 @@\n-print('hello')\n+print('world  space')\n"
        diff_with_single_space = "@@ -1 +1 @@\n-print('hello')\n+print('world space')\n"
        assert canonicalize_diff(diff_with_double_space) != canonicalize_diff(diff_with_single_space)

        # 3. Newline blank lines check
        diff_with_blank_line = "@@ -1 +1 @@\n-print('hello')\n+\n+print('world')\n"
        diff_without_blank_line = "@@ -1 +1 @@\n-print('hello')\n+print('world')\n"
        assert canonicalize_diff(diff_with_blank_line) != canonicalize_diff(diff_without_blank_line)

def test_apply_hash_ignores_stale_hunk_line_start(tmp_path) -> None:
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / "repo"
    source.mkdir()
    target = source / "target.py"
    target.write_text("def target():\n    return 'broken'\n", encoding="utf-8")

    patch = (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -2,2 +2,2 @@\n"
        " def target():\n"
        "-    return 'broken'\n"
        "+    return 'verified'\n"
    )
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="stale-hunk-start",
            source_root=str(source),
            target_file="target.py",
            unified_diff=patch,
            selected_candidate_hash=_canonical_candidate_hash(patch),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts"),
        )
    )

    assert receipt.patch_apply_status == "applied"
    assert receipt.candidate_output_isolated is True
    assert receipt.selected_candidate_hash_matches_applied is True
    assert receipt.applied_patch_hash == receipt.selected_candidate_hash
    assert receipt.selected_candidate_hash != hashlib.sha256(patch.encode()).hexdigest()


def test_apply_hash_ignores_git_added_unchanged_context(tmp_path) -> None:
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / "repo"
    source.mkdir()
    target = source / "target.py"
    target.write_text(
        "class Marker:\n"
        "    pass\n"
        "\n"
        "def target(value):\n"
        "    try:\n"
        "        return str(value)\n"
        "    except ValueError:\n"
        "        raise\n"
        "\n"
        "def untouched():\n"
        "    return True\n",
        encoding="utf-8",
    )
    patch = (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -4,5 +4,5 @@\n"
        " def target(value):\n"
        "     try:\n"
        "-        return str(value)\n"
        "+        return value if isinstance(value, str) else str(value)\n"
        "     except ValueError:\n"
        "         raise\n"
    )

    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="git-added-context",
            source_root=str(source),
            target_file="target.py",
            unified_diff=patch,
            selected_candidate_hash=_canonical_candidate_hash(patch),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts"),
        )
    )

    assert receipt.patch_apply_status == "applied"
    assert receipt.candidate_output_isolated is True
    assert receipt.selected_candidate_hash_matches_applied is True
    assert receipt.applied_patch_hash == receipt.selected_candidate_hash


def test_apply_hash_matches_expanded_leading_context_window(tmp_path) -> None:
    from nexus.services.local_assist_service import _canonical_candidate_hash
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    source = tmp_path / "repo"
    source.mkdir()
    target = source / "record.py"
    target.write_text(
        "class Record:\n"
        "    count: int\n"
        "\n"
        "def serialize_record(record: Record) -> str:\n"
        "    return json.dumps(asdict(record), sort_keys=True)\n",
        encoding="utf-8",
    )
    selected = (
        "--- a/record.py\n"
        "+++ b/record.py\n"
        "@@ -9,2 +9,2 @@\n"
        " def serialize_record(record: Record) -> str:\n"
        "-    return json.dumps(asdict(record), sort_keys=True)\n"
        "+    return json.dumps(asdict(record), sort_keys=True, separators=(',', ':'))\n"
    )
    applied = (
        "diff --git a/record.py b/record.py\n"
        "@@ -7,4 +7,4 @@ class Record:\n"
        "     count: int\n"
        "\n"
        " def serialize_record(record: Record) -> str:\n"
        "-    return json.dumps(asdict(record), sort_keys=True)\n"
        "+    return json.dumps(asdict(record), sort_keys=True, separators=(',', ':'))\n"
    )
    assert _canonicalize_effective_diff(selected) == _canonicalize_effective_diff(applied)
    assert _canonical_candidate_hash(selected) == _canonical_candidate_hash(applied)

    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="expanded-leading-context",
            source_root=str(source),
            target_file="record.py",
            unified_diff=selected,
            selected_candidate_hash=_canonical_candidate_hash(selected),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts"),
        )
    )
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True
    assert receipt.applied_patch_hash == receipt.selected_candidate_hash


def test_apply_hash_still_binds_nonblank_context_and_changed_payload() -> None:
    from nexus.services.local_assist_service import _canonical_candidate_hash

    patch = "@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2\n"
    context_tamper = "@@ -1,2 +1,2 @@\n def other():\n-    return 1\n+    return 2\n"
    payload_tamper = "@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 3\n"
    blank_line_change = "@@ -1 +1,2 @@\n def target():\n+\n"

    candidate_hash = _canonical_candidate_hash(patch)
    assert candidate_hash != _canonical_candidate_hash(context_tamper)
    assert candidate_hash != _canonical_candidate_hash(payload_tamper)
    assert candidate_hash != _canonical_candidate_hash(blank_line_change)

    multi_change = (
        "@@ -1,6 +1,6 @@\n"
        " def target():\n"
        "-    first = 1\n"
        "+    first = 2\n"
        "    middle_anchor = 10\n"
        "-    second = 1\n"
        "+    second = 2\n"
    )
    multi_change_tamper = multi_change.replace("middle_anchor = 10", "middle_anchor = 11")
    assert _canonical_candidate_hash(multi_change) != _canonical_candidate_hash(multi_change_tamper)


def test_blank_context_next_to_the_change_does_not_move_the_anchor() -> None:
    """#2769: git may render a blank context line next to the change; the selected
    and the applied diff of the same edit must canonicalize (and hash) alike."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    selected = "@@ -2,3 +2,3 @@\n \n-X\n+Y\n c\n"
    applied = "@@ -1,4 +1,4 @@\n a\n \n-X\n+Y\n c\n"
    assert _canonicalize_effective_diff(selected) == _canonicalize_effective_diff(applied)


def test_no_newline_at_eof_marker_is_part_of_the_identity() -> None:
    """#2821 item 1: a patch producing ``Y\\n`` and one producing ``Y`` differ."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    with_newline = "@@ -1 +1 @@\n-X\n+Y\n"
    without_newline = "@@ -1 +1 @@\n-X\n+Y\n\\ No newline at end of file\n"
    old_without_newline = "@@ -1 +1 @@\n-X\n\\ No newline at end of file\n+Y\n"
    assert _canonicalize_effective_diff(with_newline) != _canonicalize_effective_diff(without_newline)
    assert _canonicalize_effective_diff(without_newline) != _canonicalize_effective_diff(
        old_without_newline
    )
    # Same marker, different surrounding noise (CRLF transport, header lines) still binds.
    assert _canonicalize_effective_diff(without_newline) == _canonicalize_effective_diff(
        "--- a/f\n+++ b/f\n" + without_newline.replace("\n", "\r\n")
    )
    # A marker after a trailing context line is kept too.
    context_marker = "@@ -1,2 +1,2 @@\n-X\n+Y\n c\n\\ No newline at end of file\n"
    assert _canonicalize_effective_diff(context_marker) != _canonicalize_effective_diff(
        "@@ -1,2 +1,2 @@\n-X\n+Y\n c\n"
    )


def test_apply_binds_no_newline_at_eof_end_to_end(tmp_path) -> None:
    """#2821 item 1: the receipt binds the EOF-newline effect git really applied."""
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / "repo"
    source.mkdir()
    (source / "f.txt").write_text("a\nX\n", encoding="utf-8")
    honest = (
        "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n a\n-X\n+Y\n\\ No newline at end of file\n"
    )
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="eof-marker",
            source_root=str(source),
            target_file="f.txt",
            unified_diff=honest,
            selected_candidate_hash=_canonical_candidate_hash(honest),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts"),
        )
    )
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True

    # Claiming the identity of the newline-terminated edit while git applied the
    # no-newline one must not bind.
    newline_variant = "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n a\n-X\n+Y\n"
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="eof-marker-claim",
            source_root=str(source),
            target_file="f.txt",
            unified_diff=honest,
            selected_candidate_hash=_canonical_candidate_hash(newline_variant),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts2"),
        )
    )
    assert receipt.selected_candidate_hash_matches_applied is False


def test_whitespace_normalisation_is_the_documented_accepted_behaviour() -> None:
    """#2821 item 2: trailing whitespace / CR are stripped on purpose.

    ``git apply --whitespace=fix`` strips them from added lines itself and matches
    removed lines ignoring them, so selected and applied diffs only bind when the
    identity ignores them.  Whitespace inside a line is still identity.
    """
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    base = "@@ -1 +1 @@\n-X\n+Y\n"
    assert _canonicalize_effective_diff(base) == _canonicalize_effective_diff(
        "@@ -1 +1 @@\r\n-X  \r\n+Y\t\r\n"
    )
    assert _canonicalize_effective_diff(base) != _canonicalize_effective_diff(
        "@@ -1 +1 @@\n-X\n+ Y\n"
    )
    assert _canonicalize_effective_diff(base) != _canonicalize_effective_diff(
        "@@ -1 +1 @@\n-X\n+Y Z\n"
    )
    docstring = _canonicalize_effective_diff.__doc__ or ""
    assert "Accepted, deliberately" in docstring and "whitespace=fix" in docstring


def test_apply_binds_trailing_whitespace_added_line_after_git_fix(tmp_path) -> None:
    """#2821 item 2: why it must stay accepted: git rewrites the added line itself."""
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / "repo"
    source.mkdir()
    (source / "f.txt").write_text("a\nX\n", encoding="utf-8")
    patch = "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n a\n-X\n+Y   \n"
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="ws-fix",
            source_root=str(source),
            target_file="f.txt",
            unified_diff=patch,
            selected_candidate_hash=_canonical_candidate_hash(patch),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts"),
        )
    )
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True


def test_separate_hunks_versus_merged_hunk_is_documented_fail_closed() -> None:
    """#2821 item 3: accepted. Different forms (never a false match), and documented."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    separate = "@@ -2 +2 @@\n-b\n+B\n@@ -4 +4 @@\n-d\n+D\n"
    merged = "@@ -2,3 +2,3 @@\n-b\n+B\n c\n-d\n+D\n"
    assert _canonicalize_effective_diff(separate) != _canonicalize_effective_diff(merged)
    # The edits themselves are still bound in both forms.
    assert _canonicalize_effective_diff(separate) != _canonicalize_effective_diff(
        separate.replace("+D", "+E")
    )
    docstring = _canonicalize_effective_diff.__doc__ or ""
    assert "separate hunks" in docstring and "fails closed" in docstring


def test_file_headers_of_further_files_are_not_edited_lines() -> None:
    """#2821 item 4: ``--- a/y`` / ``+++ b/y`` between hunks are headers, not payload."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    two_files = (
        "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/y b/y\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-c\n+d\n"
    )
    canonical = _canonicalize_effective_diff(two_files)
    assert canonical == "@@ -0,1 +0,1 @@\n-a\n+b\n@@ -0,1 +0,1 @@\n-c\n+d"
    # Plain unified diff (no ``diff --git`` line): the count of the first hunk ends it.
    plain = (
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-c\n+d\n"
    )
    assert _canonicalize_effective_diff(plain) == canonical
    # A payload line that merely looks like a header stays payload while the counts say so.
    lookalike = "@@ -1 +1 @@\n--- x\n+++ y\n"
    assert _canonicalize_effective_diff(lookalike) == "@@ -0,1 +0,1 @@\n--- x\n+++ y"
    # Stray lines after a complete hunk are not smuggled in as payload.
    assert _canonicalize_effective_diff("@@ -1 +1 @@\n-a\n+b\n+evil\n") == (
        "@@ -0,1 +0,1 @@\n-a\n+b"
    )
    # A short-counted hunk is cut at the next ``diff --git`` line.
    assert _canonicalize_effective_diff("@@ -1,5 +1,5 @@\n-a\n+b\ndiff --git a/y b/y\n+q\n") == (
        "@@ -0,1 +0,1 @@\n-a\n+b"
    )


def test_canonicalize_docstring_no_longer_claims_a_local_anchor() -> None:
    """#2821 item 5: the docstring states the post-#2820 anchor behaviour."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    docstring = _canonicalize_effective_diff.__doc__ or ""
    assert "preserves a local anchor" not in docstring
    assert "keeps no anchor" in docstring


def test_only_git_trailing_whitespace_is_ignored_not_other_unicode_whitespace() -> None:
    """#2821 review: git keeps ``\\f`` / NBSP on added lines, so they stay identity."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    base = "@@ -1 +1 @@\n-X\n+Y\n"
    assert _canonicalize_effective_diff(base) != _canonicalize_effective_diff("@@ -1 +1 @@\n-X\n+Y\x0c\n")
    assert _canonicalize_effective_diff(base) != _canonicalize_effective_diff("@@ -1 +1 @@\n-X\n+Y \n")
    assert _canonicalize_effective_diff(base) == _canonicalize_effective_diff("@@ -1 +1 @@\n-X \t\r\n+Y \t\r\n")


def test_hunk_counts_include_blank_lines_and_default_to_one() -> None:
    """#2821 review: blank lines count against the hunk (as git), omitted count means 1."""
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    # blank context line counts: hunk -1,3 +1,3 is complete after "-X", "+Y", blank, so "+evil" is outside.
    with_blank = "@@ -1,3 +1,3 @@\n a\n\n-X\n+Y\n+evil\n"
    assert "evil" not in _canonicalize_effective_diff(with_blank)
    # a hunk that is still open keeps its later lines
    assert "+Y" in _canonicalize_effective_diff("@@ -1,4 +1,4 @@\n a\n\n-X\n+Y\n")
    # omitted counts default to 1/1: the extra added line is outside the hunk
    assert _canonicalize_effective_diff("@@ -1 +1 @@\n-X\n+Y\n+evil\n") == "@@ -0,1 +0,1 @@\n-X\n+Y"
    # a marker after a non-hunk line attaches to nothing
    assert "No newline" not in _canonicalize_effective_diff("@@ -1 +1 @@\n-X\n+Y\n+evil\n\\ No newline at end of file\n")


# --- #2836: the selected patch must be hunk edits of target_file only --------------------

_HONEST_F = "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n+b = 3\n"


def _scope_apply(tmp_path, diff: str, *, name: str = "scope", verifier_files=()):
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / f"repo-{name}"
    source.mkdir()
    (source / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    (source / "repro.py").write_text("print('ok')\n", encoding="utf-8")
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id=name,
            source_root=str(source),
            target_file="f.py",
            unified_diff=diff,
            selected_candidate_hash=_canonical_candidate_hash(diff),
            mutation_allowed=True,
            work_dir=str(tmp_path / f"artifacts-{name}"),
            verifier_files=tuple(verifier_files),
        )
    )
    return receipt, tmp_path / f"artifacts-{name}"


def _assert_refused(receipt, workdir, needle: str) -> None:
    assert receipt.patch_apply_status == "blocked"
    assert receipt.patch_apply_error.startswith("patch_scope_scope:")
    assert needle in receipt.patch_apply_error
    assert receipt.selected_candidate_hash_matches_applied is False
    assert receipt.candidate_output_isolated is False
    assert receipt.workspace_path == ""
    assert not workdir.exists() or not any(workdir.iterdir())  # nothing was applied anywhere


def test_scope_extra_conftest_file_is_refused_end_to_end(tmp_path) -> None:
    extra = (
        "diff --git a/conftest.py b/conftest.py\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/conftest.py\n@@ -0,0 +1 @@\n+import os\n"
    )
    receipt, workdir = _scope_apply(tmp_path, _HONEST_F + extra)
    _assert_refused(receipt, workdir, "conftest.py")


def test_scope_empty_new_file_without_hunks_is_refused(tmp_path) -> None:
    extra = "diff --git a/conftest.py b/conftest.py\nnew file mode 100644\nindex 0000000..e69de29\n"
    receipt, workdir = _scope_apply(tmp_path, _HONEST_F + extra, name="empty")
    _assert_refused(receipt, workdir, "conftest.py")


def test_scope_binary_sidecar_is_refused_end_to_end(tmp_path) -> None:
    import subprocess

    repo = tmp_path / "binrepo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "blob.bin").write_bytes(bytes(range(256)))
    subprocess.run(["git", "add", "blob.bin"], cwd=repo, check=True)
    binary = subprocess.run(
        ["git", "diff", "--cached", "--binary"], cwd=repo, check=True, capture_output=True
    ).stdout.decode("utf-8")
    assert "GIT binary patch" in binary
    receipt, workdir = _scope_apply(tmp_path, _HONEST_F + binary, name="binary")
    _assert_refused(receipt, workdir, "blob.bin")


def test_scope_binary_patch_for_the_target_itself_is_refused(tmp_path) -> None:
    import subprocess

    repo = tmp_path / "binself"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "f.py").write_bytes(bytes(range(256)))
    subprocess.run(["git", "add", "f.py"], cwd=repo, check=True)
    binary = subprocess.run(
        ["git", "diff", "--cached", "--binary"], cwd=repo, check=True, capture_output=True
    ).stdout.decode("utf-8")
    receipt, workdir = _scope_apply(tmp_path, binary, name="binself")
    assert receipt.patch_apply_status == "blocked"
    assert receipt.selected_candidate_hash_matches_applied is False


def test_scope_rename_is_refused_end_to_end(tmp_path) -> None:
    rename = (
        "diff --git a/f.py b/g.py\nsimilarity index 100%\nrename from f.py\nrename to g.py\n"
    )
    receipt, workdir = _scope_apply(tmp_path, rename, name="rename")
    _assert_refused(receipt, workdir, "g.py")
    renamed_with_edit = (
        "diff --git a/f.py b/g.py\nsimilarity index 50%\nrename from f.py\nrename to g.py\n"
        "--- a/f.py\n+++ b/g.py\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n+b = 3\n"
    )
    receipt, workdir = _scope_apply(tmp_path, renamed_with_edit, name="rename2")
    _assert_refused(receipt, workdir, "g.py")


def test_scope_copy_is_refused(tmp_path) -> None:
    copy = "diff --git a/f.py b/h.py\nsimilarity index 100%\ncopy from f.py\ncopy to h.py\n"
    receipt, workdir = _scope_apply(tmp_path, _HONEST_F + copy, name="copy")
    assert receipt.patch_apply_status == "blocked"
    assert receipt.selected_candidate_hash_matches_applied is False


def test_scope_mode_change_is_refused_end_to_end(tmp_path) -> None:
    mode_only = "diff --git a/f.py b/f.py\nold mode 100644\nnew mode 100755\n"
    receipt, workdir = _scope_apply(tmp_path, mode_only, name="mode")
    _assert_refused(receipt, workdir, "mode")
    mode_plus_edit = (
        "diff --git a/f.py b/f.py\nold mode 100644\nnew mode 100755\n"
        "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n+b = 3\n"
    )
    receipt, workdir = _scope_apply(tmp_path, mode_plus_edit, name="mode2")
    _assert_refused(receipt, workdir, "mode")
    other_mode = _HONEST_F + "diff --git a/repro.py b/repro.py\nold mode 100644\nnew mode 100755\n"
    receipt, workdir = _scope_apply(tmp_path, other_mode, name="mode3")
    _assert_refused(receipt, workdir, "repro.py")


def test_scope_delete_outside_the_allowed_set_is_refused(tmp_path) -> None:
    delete = (
        "diff --git a/repro.py b/repro.py\ndeleted file mode 100644\n"
        "--- a/repro.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-print('ok')\n"
    )
    receipt, workdir = _scope_apply(
        tmp_path, _HONEST_F + delete, name="delete", verifier_files=("repro.py",)
    )
    _assert_refused(receipt, workdir, "repro.py")


def test_scope_edit_of_a_verifier_input_file_is_refused(tmp_path) -> None:
    edit_repro = "--- a/repro.py\n+++ b/repro.py\n@@ -1 +1 @@\n-print('ok')\n+print('pwned')\n"
    receipt, workdir = _scope_apply(
        tmp_path, _HONEST_F + edit_repro, name="verifier", verifier_files=("repro.py",)
    )
    _assert_refused(receipt, workdir, "repro.py")


def test_scope_extra_hunk_headers_hidden_from_hunk_parser_are_refused() -> None:
    from nexus.services.local_heal.isolated_workspace_apply import (
        _hunk_payload_counts,
        _patch_scope_violation,
    )

    assert _hunk_payload_counts(_HONEST_F) == (1, 1)
    assert _patch_scope_violation("f.py", _HONEST_F) is None
    # git reads two sections for f.py; the parser reads both too, so counts still agree
    assert _patch_scope_violation("f.py", _HONEST_F + _HONEST_F) is None
    # a file the target gate never named
    kind, detail = _patch_scope_violation("f.py", _HONEST_F.replace("f.py", "other.py")) or ("", "")
    assert kind == "scope" and "other.py" in detail


def test_scope_garbage_patch_fails_closed_as_unparseable(tmp_path) -> None:
    receipt, _ = _scope_apply(tmp_path, "this is not a patch\n", name="garbage")
    assert receipt.patch_apply_status == "failed"
    assert receipt.patch_apply_error.startswith("patch_scope_unparseable:")
    assert receipt.selected_candidate_hash_matches_applied is False
    assert receipt.workspace_path == ""


def test_scope_valid_single_file_patch_still_binds(tmp_path) -> None:
    receipt, _ = _scope_apply(tmp_path, _HONEST_F, name="single")
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True
    assert (
        open(os.path.join(receipt.workspace_path, "f.py"), encoding="utf-8").read()
        == "a = 1\nb = 3\n"
    )
    assert not os.path.exists(os.path.join(receipt.workspace_path, "conftest.py"))


def test_scope_valid_multi_hunk_patch_still_binds(tmp_path) -> None:
    from nexus.services.local_assist_service import _canonical_candidate_hash

    source = tmp_path / "repo-multi"
    source.mkdir()
    original = "".join(f"line{n}\n" for n in range(1, 21))
    (source / "f.py").write_text(original, encoding="utf-8")
    diff = (
        "--- a/f.py\n+++ b/f.py\n"
        "@@ -2,3 +2,3 @@\n line2\n-line3\n+LINE3\n line4\n"
        "@@ -17,3 +17,4 @@\n line17\n-line18\n+LINE18\n+EXTRA\n line19\n"
    )
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="multi",
            source_root=str(source),
            target_file="f.py",
            unified_diff=diff,
            selected_candidate_hash=_canonical_candidate_hash(diff),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts-multi"),
        )
    )
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True
    text = open(os.path.join(receipt.workspace_path, "f.py"), encoding="utf-8").read()
    assert "LINE3\n" in text and "LINE18\nEXTRA\n" in text


def test_canonicalize_docstring_names_the_scope_gate() -> None:
    from nexus.services.local_heal.isolated_workspace_apply import _canonicalize_effective_diff

    docstring = _canonicalize_effective_diff.__doc__ or ""
    assert "_patch_scope_violation" in docstring
    assert "No gate here checks" not in docstring


def test_scope_new_mode_without_old_mode_is_refused(tmp_path) -> None:
    diff = (
        "diff --git a/f.py b/f.py\nnew mode 100755\n"
        "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n+b = 3\n"
    )
    receipt, workdir = _scope_apply(tmp_path, diff, name="newmode")
    _assert_refused(receipt, workdir, "mode")


def test_scope_mismatched_file_headers_are_refused(tmp_path) -> None:
    diff = "--- a/conftest.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n a = 1\n-b = 2\n+b = 3\n"
    receipt, workdir = _scope_apply(tmp_path, diff, name="mismatch")
    _assert_refused(receipt, workdir, "conftest.py")
    diff = "diff --git a/f.py b/conftest.py\n" + _HONEST_F
    receipt, workdir = _scope_apply(tmp_path, diff, name="mismatch2")
    _assert_refused(receipt, workdir, "conftest.py")


def test_scope_patch_without_hunks_is_refused(tmp_path) -> None:
    diff = "diff --git a/f.py b/f.py\nindex 1111111..2222222 100644\n"
    receipt, workdir = _scope_apply(tmp_path, diff, name="nohunk")
    _assert_refused(receipt, workdir, "no hunk")


def test_scope_traditional_patches_git_guesses_create_or_delete_for_still_bind(tmp_path) -> None:
    """Review finding: a header-less hunk from/to an empty file is an edit of the tracked target."""
    from nexus.services.local_assist_service import _canonical_candidate_hash

    cases = {
        "clear": ("a = 1\nb = 2\n", "--- a/f.py\n+++ b/f.py\n@@ -1,2 +0,0 @@\n-a = 1\n-b = 2\n"),
        "fill": ("", "--- a/f.py\n+++ b/f.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n"),
        "insert": ("a = 1\nb = 2\n", "--- a/f.py\n+++ b/f.py\n@@ -2,0 +3 @@\n+c = 3\n"),
    }
    for name, (original, diff) in cases.items():
        source = tmp_path / f"repo-{name}"
        source.mkdir()
        (source / "f.py").write_text(original, encoding="utf-8")
        receipt = run_isolated_workspace_apply(
            IsolatedApplyRequest(
                task_id=name,
                source_root=str(source),
                target_file="f.py",
                unified_diff=diff,
                selected_candidate_hash=_canonical_candidate_hash(diff),
                mutation_allowed=True,
                work_dir=str(tmp_path / f"artifacts-{name}"),
            )
        )
        assert receipt.patch_apply_status == "applied", (name, receipt.patch_apply_error)
        assert not os.path.exists(os.path.join(receipt.workspace_path, "conftest.py"))
    missing = tmp_path / "repo-missing"
    missing.mkdir()
    diff = cases["fill"][1].replace("f.py", "new.py")
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id="missing",
            source_root=str(missing),
            target_file="new.py",
            unified_diff=diff,
            selected_candidate_hash=_canonical_candidate_hash(diff),
            mutation_allowed=True,
            work_dir=str(tmp_path / "artifacts-missing"),
        )
    )
    assert receipt.patch_apply_status == "applied", receipt.patch_apply_error
    assert receipt.selected_candidate_hash_matches_applied is True
