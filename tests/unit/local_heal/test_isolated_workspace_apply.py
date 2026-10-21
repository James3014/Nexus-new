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
