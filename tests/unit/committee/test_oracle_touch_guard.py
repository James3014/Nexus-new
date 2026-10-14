"""Committee candidates that modify a test or oracle file are rejected before selection."""

from __future__ import annotations

import pytest

from nexus.committee.controller import CommitteeControllerV263
from nexus.committee.oracle_touch_guard import (
    FAILURE_CODE,
    GUARD_NAME,
    is_test_or_oracle_path,
    patch_violations,
)
from nexus.verifiers.contracts import VerifierVerdict

SOURCE_DIFF = """--- a/pkg/sessions.py
+++ b/pkg/sessions.py
@@ -1,2 +1,2 @@
-    for token, session in store.items():
+    for token in list(store):
"""
REPRO_DIFF = """--- a/repro.py
+++ b/repro.py
@@ -1,2 +1,2 @@
-assert expire() == ["a"]
+assert True
"""
MIXED_DIFF = SOURCE_DIFF + REPRO_DIFF


@pytest.mark.parametrize(
    "path",
    [
        "repro.py",
        "reproduce_bug.py",
        "sub/dir/test_repro.py",
        "debug_repro.py",
        "nexus_repro_contract.py",
        "tests/unit/foo.py",
        "pkg/Tests/helpers/data.json",
        "pkg/test/x.py",
        "testing/fixtures.py",
        "pkg/test_sessions.py",
        "pkg/sessions_test.py",
        "conftest.py",
        "a/b/CONFTEST.PY",
        "Repro.py",
    ],
)
def test_test_or_oracle_paths_are_recognised(path):
    assert is_test_or_oracle_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "pkg/sessions.py",
        "pkg/contest.py",
        "pkg/latest.py",
        "pkg/testimony/model.py",
        "pkg/attestation.py",
        "pkg/test_data.txt",
        "",
    ],
)
def test_source_paths_are_not_test_or_oracle(path):
    assert not is_test_or_oracle_path(path)


def test_source_only_diff_has_no_violation():
    assert patch_violations(SOURCE_DIFF) == []


def test_bare_snippet_without_headers_is_left_to_verifiers():
    assert patch_violations("pd.DataFrame()") == []
    assert patch_violations("") == []


@pytest.mark.parametrize(
    "patch, expected",
    [
        (REPRO_DIFF, "test_or_oracle:repro.py"),
        (MIXED_DIFF, "test_or_oracle:repro.py"),
        (
            "diff --git a/tests/test_x.py b/tests/test_x.py\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/tests/test_x.py\n@@ -0,0 +1 @@\n+def test_x(): pass\n",
            "test_or_oracle:tests/test_x.py",
        ),
        (
            "diff --git a/conftest.py b/conftest.py\ndeleted file mode 100644\n"
            "--- a/conftest.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-import x\n",
            "test_or_oracle:conftest.py",
        ),
        (
            "diff --git a/pkg/helper.py b/tests/helper.py\nsimilarity index 100%\n"
            "rename from pkg/helper.py\nrename to tests/helper.py\n",
            "test_or_oracle:tests/helper.py",
        ),
        (
            "diff --git a/tests/data.bin b/tests/data.bin\n"
            "Binary files a/tests/data.bin and b/tests/data.bin differ\n",
            "test_or_oracle:tests/data.bin",
        ),
    ],
)
def test_test_or_oracle_diffs_are_rejected(patch, expected):
    assert expected in patch_violations(patch)


def test_hunk_body_lines_that_look_like_headers_are_not_paths():
    patch = SOURCE_DIFF + "--- tests/notes.sql\n"
    assert patch_violations(patch) == []


def test_source_diff_reaching_oracle_by_rename_target_is_rejected():
    patch = "rename from pkg/a.py\nrename to repro.py\n"
    assert "test_or_oracle:repro.py" in patch_violations(patch)


@pytest.mark.parametrize(
    "patch",
    [
        "diff --git garbage\n",
        "--- a/x.py\n+++ \n",
        "Binary files differ\n",
    ],
)
def test_malformed_diff_header_fails_closed(patch):
    reasons = patch_violations(patch)
    assert reasons and reasons[0].startswith("unparseable_diff_header:")


@pytest.fixture(autouse=True)
def _hermetic_committee_env(monkeypatch):
    # Other committee tests set these process-wide; pin the defaults so packs and temperature
    # scaling do not leak into these controller assertions.
    monkeypatch.setenv("NEXUS_USE_PACKS", "0")
    monkeypatch.setenv("NEXUS_USE_TS", "0")


class _PassEverything:
    """Stand-in execution verifier: passes every candidate it is asked about. The score is taken
    from ``scores`` by patch text (default 10.0) so a round can have a clear winner."""

    def __init__(self, scores=None):
        self.seen: list[str] = []
        self.scores = scores or {}

    def evaluate(self, candidate_id, patch):
        self.seen.append(patch)
        return VerifierVerdict(
            verifier_name="exec",
            candidate_id=candidate_id,
            passed=True,
            score=self.scores.get(patch, 10.0),
        )


def _controller(verifier):
    controller = CommitteeControllerV263("task-guard", verifiers=[verifier])
    controller.enabled = True
    return controller


def _proposal(model, attempt, patch):
    return {"model": model, "attempt": attempt, "raw_label": "r:0,p:3", "artifacts": [patch]}


SOURCE_DIFF_B = SOURCE_DIFF.replace("list(store)", "tuple(store)")


def test_controller_never_verifies_or_selects_an_oracle_editing_candidate():
    verifier = _PassEverything({SOURCE_DIFF: 10.0, SOURCE_DIFF_B: 5.0, MIXED_DIFF: 50.0})
    receipt = _controller(verifier).process_proposals([
        _proposal("7B", 1, MIXED_DIFF),
        _proposal("14B", 1, SOURCE_DIFF),
        _proposal("32B", 1, SOURCE_DIFF_B),
    ])

    guarded = [v for v in receipt.verdicts if v.verifier_name == GUARD_NAME]
    assert len(guarded) == 1
    assert guarded[0].passed is False
    assert guarded[0].failure_tags[0].code == FAILURE_CODE
    assert sorted(verifier.seen) == sorted([SOURCE_DIFF, SOURCE_DIFF_B])
    winner = next(c for c in receipt.candidates if c.candidate_id == receipt.winner_id)
    assert winner.artifact_refs == [SOURCE_DIFF]
    assert winner.candidate_id != guarded[0].candidate_id


def test_guarded_candidate_does_not_hand_the_last_eligible_one_a_win():
    # One eligible candidate left: the abstention policy abstains, as it does for a single
    # proposal; the guarded one does not create an artificial score gap.
    verifier = _PassEverything()
    receipt = _controller(verifier).process_proposals([
        _proposal("7B", 1, REPRO_DIFF),
        _proposal("14B", 1, SOURCE_DIFF),
    ])

    assert receipt.winner_id is None
    assert verifier.seen == [SOURCE_DIFF]


def test_controller_abstains_when_every_candidate_edits_an_oracle():
    verifier = _PassEverything()
    receipt = _controller(verifier).process_proposals([
        _proposal("7B", 1, REPRO_DIFF),
        _proposal("14B", 1, MIXED_DIFF),
    ])

    assert receipt.winner_id is None
    assert receipt.abstained
    assert receipt.failure_bucket == "test_or_oracle_modified"
    assert receipt.abstain_reason == "ALL_CANDIDATES_MODIFY_TEST_OR_ORACLE"
    assert verifier.seen == []
    assert {v.verifier_name for v in receipt.verdicts} == {GUARD_NAME}


def test_controller_unchanged_for_source_only_candidates():
    verifier = _PassEverything({SOURCE_DIFF: 10.0, SOURCE_DIFF_B: 5.0})
    receipt = _controller(verifier).process_proposals([
        _proposal("7B", 1, SOURCE_DIFF),
        _proposal("14B", 1, SOURCE_DIFF_B),
    ])

    assert len(verifier.seen) == 2
    assert all(v.verifier_name == "exec" for v in receipt.verdicts)
    winner = next(c for c in receipt.candidates if c.candidate_id == receipt.winner_id)
    assert winner.artifact_refs == [SOURCE_DIFF]
    assert receipt.abstain_reason is None


def test_form_feed_cannot_hide_a_test_file_header():
    patch = "--- a/tests/test_x.py\t\f\n+++ b/tests/test_x.py\t\f\n@@ -1 +1 @@\n-assert 1 == 2\n+assert True\n"
    assert "test_or_oracle:tests/test_x.py" in patch_violations(patch)


def test_crlf_headers_are_parsed():
    patch = REPRO_DIFF.replace("\n", "\r\n")
    assert "test_or_oracle:repro.py" in patch_violations(patch)


def test_c_quoted_path_with_escapes_fails_closed():
    patch = (
        '--- "a/t\\145sts/t\\145st_x.py"\n+++ "b/t\\145sts/t\\145st_x.py"\n'
        "@@ -1 +1 @@\n-assert 1 == 2\n+assert True\n"
    )
    reasons = patch_violations(patch)
    assert reasons and reasons[0].startswith("unparseable_diff_header:")


@pytest.mark.parametrize("path", ["app/tests.py", "pkg/sessions_tests.py", "reproduction.py"])
def test_more_test_and_oracle_names_are_recognised(path):
    assert is_test_or_oracle_path(path)
