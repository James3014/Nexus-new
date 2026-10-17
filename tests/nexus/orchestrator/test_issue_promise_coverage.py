"""Issue promise coverage projection (#2532), frozen RED tests.

Owner decision on #2532 (2026-10-17): an Issue declares its behavior promises
in one ``nexus.issue_promise_set.v1`` fence in the Issue body; a Task Card maps
every promise to at least one REQUIRED/APPLICABLE expected-evidence subject in
a hashed ``nexus-issue-promises`` block; a pure projection turns the durable
``core_verdict`` into a per-promise status. #2453's closer, not this module,
reads the projection. Promise tests are frozen by merging them first (RED),
then the implementation.

The six G0 §4 scenarios each have a class below:

1. generic tests green, but the promise's real entry was never run
2. the worker drops (or relaxes) the promise's subject
3. a PR that delivers 2 of 3 promises
4. a fake PASS from an unfrozen, worker-added test
5. wrong commit, Issue edit or promise generation → STALE
6. an author-forged CLOSE: the output is projection-only

plus a Core verdict that blocked or failed, which must never read COMPLETE.

RED gate: these tests land before the implementation, and the required
exact-base impact gate treats an added test that skips or xfails as not
passed. So until the implementation PR, each RED class carries a
``__test__ = _RED_2532`` gate and is collected only with ``NEXUS_RED_2532=1``
(run that to see them fail). ``test_frozen_red_tests_are_unchanged`` pins the
frozen region between the two marker comments, ignoring blank lines and the
gate lines. The implementation PR deletes the gate lines, ``_RED_2532`` and
its ``os`` import (all outside the region or excluded) and may reformat blank
lines; any other edit to the region changes the hash and shows up in review.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import os
from pathlib import Path
from typing import Any

import pytest

_RED_2532 = os.environ.get("NEXUS_RED_2532") == "1"

# >>> frozen #2532 RED region

HEAD = "1" * 40
OTHER_HEAD = "2" * 40
ISSUE_CONTRACT_HASH = "c" * 64
REPOSITORY = "James3014/Nexus-new"
ISSUE_NUMBER = 4242
# The Nexus contract identity of the card universe the binding was made for.
CARD_UNIVERSE_IDENTITY = "sha256:" + "a" * 64
OTHER_UNIVERSE_IDENTITY = "sha256:" + "f" * 64

GENERIC = "python -m pytest tests/"
ENTRY_P1 = "python -m pytest tests/test_feature.py::test_real_entry_p1"
ENTRY_P2 = "python -m pytest tests/test_feature.py::test_real_entry_p2"
ENTRY_P3 = "python -m pytest tests/test_feature.py::test_real_entry_p3"
WORKER_ADDED = "python -m pytest tests/test_feature.py::test_worker_wrote_this"


def _contract() -> Any:
    return importlib.import_module("nexus.orchestrator.task_contract")


def _projection_module() -> Any:
    return importlib.import_module("nexus.orchestrator.issue_promise_coverage")


def _promise(pid: str, *, phase: str = "PRE_MERGE", risk: str = "STANDARD") -> dict[str, Any]:
    return {
        "promise_id": pid,
        "statement_sha256": hashlib.sha256(pid.encode()).hexdigest(),
        "phase": phase,
        "risk": risk,
    }


def _promise_set(*promises: dict[str, Any], generation: int = 1) -> dict[str, Any]:
    return {"promise_set_generation": generation, "promises": list(promises)}


def _binding(promise_set: dict[str, Any], mapping: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "issue_number": ISSUE_NUMBER,
        "issue_contract_hash": ISSUE_CONTRACT_HASH,
        "expected_evidence_identity": CARD_UNIVERSE_IDENTITY,
        "promise_set": promise_set,
        "map": [{"promise_id": pid, "subject_ids": sids} for pid, sids in mapping.items()],
    }


def _entry(
    sid: str,
    category: str = "COVERED",
    observed: str | None = "PASS",
    *,
    mode: str = "REQUIRED",
    applicability: str = "APPLICABLE",
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "logical_subject_id": sid,
        "evidence_kind": "verifier-run",
        "requirement_mode": mode,
        "applicability": applicability,
        "category": category,
    }
    if observed is not None:
        value["observed_status"] = observed
    return value


def _verdict(
    entries: list[dict[str, Any]],
    *,
    core_status: str | None = "VERIFIED",
    provenance: str = "CORE_REVISION_PINNED",
    identity_matches: bool | None = True,
    unexpected: list[dict[str, Any]] | None = None,
    integrity: str | None = "VALID",
    blocking: bool | None = None,
    host_reason_codes: list[str] | None = None,
    contract_universe_identity: str = CARD_UNIVERSE_IDENTITY,
) -> dict[str, Any]:
    """A durable ``core_verdict`` shaped like ``ambient_core.build_core_verdict``."""
    return {
        "schema": "nexus.ambient_core_verdict.v1",
        "core_status": core_status,
        "reason_codes": [],
        "integrity": integrity,
        "host_reason_codes": host_reason_codes or [],
        "blocking": (core_status != "VERIFIED") if blocking is None else blocking,
        "universe_declared": True,
        "universe_generation": 1,
        "contract_universe_identity": contract_universe_identity,
        "core_universe_identity": "sha256:" + "b" * 64,
        "core_universe_identity_matches": identity_matches,
        "coverage": {
            "universe_generation": 1,
            "universe_identity": "sha256:" + "b" * 64,
            "entries": sorted(entries, key=lambda e: e["logical_subject_id"]),
            "unexpected_subjects": unexpected or [],
        },
        "coverage_complete": core_status == "VERIFIED",
        "core_provenance": {"status": provenance},
        "projection_hash": "d" * 64,
    }


def _live(
    promise_set: dict[str, Any], *, contract_hash: str = ISSUE_CONTRACT_HASH
) -> dict[str, Any]:
    return {
        "issue_contract_hash": contract_hash,
        "promise_set_identity": _contract().issue_promise_set_identity(promise_set),
    }


def _project(
    binding: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
    *,
    expected_head: str = HEAD,
    evidence_head: str | None = HEAD,
    live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if live is None and binding is not None:
        live = _live(binding["promise_set"])
    return _projection_module().project_issue_promise_coverage(
        binding,
        verdict,
        expected_head,
        evidence_head=evidence_head,
        live_issue=live,
    )


def _statuses(result: dict[str, Any]) -> dict[str, str]:
    return {item["promise_id"]: item["status"] for item in result["promises"]}


THREE = _promise_set(_promise("P1"), _promise("P2"), _promise("P3"))
THREE_MAP = {"P1": [ENTRY_P1], "P2": [ENTRY_P2], "P3": [ENTRY_P3]}


class TestIssuePromiseSetFence:
    """The Issue body fence and the card block parse fail-closed."""


    def test_issue_body_without_fence_is_legacy(self):
        assert _contract().parse_issue_promise_set("Plain Issue body.\n") is None

    def test_issue_body_fence_round_trips_in_canonical_order(self):
        body = "\n".join([
            "## Promises",
            "```" + _contract().ISSUE_PROMISE_SET_FENCE,
            '{"promise_set_generation": 2, "promises": ['
            + ",".join(
                '{"promise_id": "%s", "statement_sha256": "%s", "phase": "PRE_MERGE", "risk": "STANDARD"}'
                % (p["promise_id"], p["statement_sha256"])
                for p in (_promise("P2"), _promise("P1"))
            )
            + "]}",
            "```",
        ])
        parsed = _contract().parse_issue_promise_set(body)
        assert parsed["promise_set_generation"] == 2
        assert [p["promise_id"] for p in parsed["promises"]] == ["P1", "P2"]
        assert _contract().issue_promise_set_identity(parsed).startswith("sha256:")

    @pytest.mark.parametrize(
        "body",
        [
            "```nexus.issue_promise_set.v1\n{}\n```\n```nexus.issue_promise_set.v1\n{}\n```",
            '```nexus.issue_promise_set.v1\n{"promise_set_generation": 1}\n',
            "```nexus.issue_promise_set.v1 extra\n{}\n```",
            "```nexus.issue_promise_set.v1\nnot json\n```",
        ],
        ids=["duplicate", "unterminated", "near-miss-info-string", "not-json"],
    )
    def test_malformed_issue_fence_fails_closed(self, body):
        with pytest.raises(ValueError, match="ISSUE_PROMISE_SET_INVALID"):
            _contract().parse_issue_promise_set(body)

    @pytest.mark.parametrize(
        "promise_set",
        [
            _promise_set(_promise("P1"), _promise("P1")),
            _promise_set(),
            {**_promise_set(_promise("P1")), "promise_set_generation": True},
            _promise_set({**_promise("P1"), "phase": "SOMETIME"}),
            _promise_set({**_promise("P1"), "risk": "LOW"}),
            _promise_set({**_promise("P1"), "statement_sha256": "short"}),
            _promise_set({**_promise("P1"), "status": "DONE"}),
        ],
        ids=[
            "duplicate-id",
            "empty",
            "bool-generation",
            "bad-phase",
            "bad-risk",
            "bad-hash",
            "extra-field",
        ],
    )
    def test_invalid_promise_set_is_rejected(self, promise_set):
        with pytest.raises(ValueError):
            _contract().IssuePromiseSet.model_validate(promise_set)

    def test_binding_must_map_exactly_the_issue_promise_set(self):
        model = _contract().IssuePromiseBinding
        model.model_validate(_binding(THREE, THREE_MAP))
        with pytest.raises(ValueError, match="P3"):
            model.model_validate(_binding(THREE, {"P1": [ENTRY_P1], "P2": [ENTRY_P2]}))
        with pytest.raises(ValueError, match="P4"):
            model.model_validate(_binding(THREE, {**THREE_MAP, "P4": [ENTRY_P1]}))
        with pytest.raises(ValueError):
            model.model_validate(_binding(THREE, {**THREE_MAP, "P1": []}))
        with pytest.raises(ValueError, match="expected_evidence_identity"):
            model.model_validate({
                **_binding(THREE, THREE_MAP),
                "expected_evidence_identity": "not-an-identity",
            })

    @pytest.mark.parametrize(
        "parse_name", ["parse_issue_promise_set", "parse_task_card_issue_promises"]
    )
    def test_deeply_nested_json_fails_closed_not_with_recursion_error(
        self, monkeypatch, parse_name
    ):
        contract = _contract()
        fence = (
            contract.ISSUE_PROMISE_SET_FENCE
            if parse_name == "parse_issue_promise_set"
            else contract.TASK_CARD_ISSUE_PROMISES_FENCE
        )

        def explode(*_args, **_kwargs):
            raise RecursionError("maximum recursion depth exceeded")

        monkeypatch.setattr(contract.json, "loads", explode)
        with pytest.raises(ValueError, match="INVALID"):
            getattr(contract, parse_name)("```" + fence + "\n[[[[]]]]\n```\n")


class TestScenario1GenericGreenEntryNotRun:
    """G0 §4 row 1: a green generic suite never covers an unexercised entry."""


    def test_generic_suite_pass_does_not_cover_the_promise_entry(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(GENERIC), _entry(ENTRY_P1, "NOT_COVERED", None)])
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "NOT_COVERED"}
        assert result["overall"] != "COMPLETE"

    def test_the_real_entry_passing_covers_the_promise(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(GENERIC), _entry(ENTRY_P1)])
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "COVERED"}
        assert result["overall"] == "COMPLETE"

    def test_a_failed_entry_is_failed_not_covered(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict(
            [_entry(GENERIC), _entry(ENTRY_P1, "COVERED", "FAIL")],
            core_status="FAILED_VERIFICATION",
        )
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "FAILED"}
        assert result["overall"] == "BLOCKED"

    def test_a_fail_observation_in_any_category_is_failed(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict(
            [_entry(ENTRY_P1, "NOT_COVERED", "FAIL")], core_status="FAILED_VERIFICATION"
        )
        assert _statuses(_project(binding, verdict)) == {"P1": "FAILED"}

    def test_honest_non_execution_is_not_covered(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        result = _project(binding, None, evidence_head=None)
        assert _statuses(result) == {"P1": "NOT_COVERED"}
        assert result["overall"] == "PARTIAL"


class TestScenario2WorkerDropsSubject:
    """G0 §4 row 2: dropping or relaxing the mapped subject never covers."""


    def test_mapped_subject_absent_from_coverage_is_not_covered(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        result = _project(binding, _verdict([_entry(GENERIC)]))
        assert _statuses(result) == {"P1": "NOT_COVERED"}
        assert result["overall"] != "COMPLETE"

    def test_relaxed_to_not_applicable_does_not_cover(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        relaxed = _entry(
            ENTRY_P1,
            "CONDITIONALLY_NOT_APPLICABLE",
            None,
            mode="CONDITIONALLY_REQUIRED",
            applicability="NOT_APPLICABLE",
        )
        result = _project(binding, _verdict([_entry(GENERIC), relaxed]))
        assert _statuses(result) == {"P1": "NOT_COVERED"}

    def test_a_changed_universe_makes_the_receipt_stale(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(ENTRY_P1)], identity_matches=False)
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "STALE"}
        assert result["overall"] == "BLOCKED"

    def test_unpinned_core_provenance_never_covers(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(ENTRY_P1)], provenance="CORE_REVISION_UNPINNED")
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "NOT_COVERED"}


class TestScenario3TwoOfThreePromises:
    """G0 §4 row 3: delivering 2 of 3 promises is PARTIAL, whatever is claimed."""


    def test_two_of_three_is_partial(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([
            _entry(ENTRY_P1),
            _entry(ENTRY_P2),
            _entry(ENTRY_P3, "NOT_COVERED", None),
        ])
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "COVERED", "P2": "COVERED", "P3": "NOT_COVERED"}
        assert result["overall"] == "PARTIAL"

    def test_claimed_items_are_not_evidence(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([
            _entry(ENTRY_P1),
            _entry(ENTRY_P2),
            _entry(ENTRY_P3, "NOT_COVERED", None),
        ])
        verdict["claimed_items"] = ["P1", "P2", "P3"]
        verdict["coverage_complete"] = True
        result = _project(binding, verdict)
        assert result["overall"] == "PARTIAL"

    def test_all_three_covered_is_complete(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)])
        assert _project(binding, verdict)["overall"] == "COMPLETE"

    def test_post_merge_and_high_risk_promises_wait_for_a_live_witness(self):
        promise_set = _promise_set(
            _promise("P1"),
            _promise("P2", phase="POST_MERGE"),
            _promise("P3", risk="HIGH"),
        )
        binding = _binding(promise_set, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)])
        result = _project(binding, verdict)
        assert _statuses(result) == {
            "P1": "COVERED",
            "P2": "PENDING_EXTERNAL_WITNESS",
            "P3": "PENDING_EXTERNAL_WITNESS",
        }
        assert result["overall"] == "PARTIAL"
        assert result["pending_external_witness"] == ["P2", "P3"]

    def test_high_risk_promise_still_needs_its_pre_merge_evidence(self):
        promise_set = _promise_set(_promise("P1", risk="HIGH"))
        binding = _binding(promise_set, {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(ENTRY_P1, "NOT_COVERED", None)])
        assert _statuses(_project(binding, verdict)) == {"P1": "NOT_COVERED"}


class TestScenario4FakePassUnfrozenTest:
    """G0 §4 row 4: a worker-added test cannot stand in for the frozen subject."""


    def test_unexpected_worker_subject_passing_does_not_cover(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict(
            [_entry(ENTRY_P1, "NOT_COVERED", None)],
            unexpected=[{"logical_subject_id": WORKER_ADDED, "evidence_kind": "verifier-run"}],
        )
        result = _project(binding, verdict)
        assert _statuses(result) == {"P1": "NOT_COVERED"}

    def test_covered_without_an_observed_pass_does_not_cover(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(ENTRY_P1, "COVERED", None)])
        assert _statuses(_project(binding, verdict)) == {"P1": "NOT_COVERED"}

    def test_every_mapped_subject_must_pass(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1, ENTRY_P2]})
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2, "NOT_COVERED", None)])
        assert _statuses(_project(binding, verdict)) == {"P1": "NOT_COVERED"}


class TestScenario5StaleBinding:
    """G0 §4 row 5: wrong commit, Issue edit or promise generation → STALE."""


    def _covered(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        return binding, _verdict([_entry(ENTRY_P1)])

    def test_evidence_for_another_commit_is_stale(self):
        binding, verdict = self._covered()
        result = _project(binding, verdict, evidence_head=OTHER_HEAD)
        assert _statuses(result) == {"P1": "STALE"}
        assert result["overall"] == "BLOCKED"

    def test_unknown_evidence_commit_is_stale(self):
        binding, verdict = self._covered()
        assert _statuses(_project(binding, verdict, evidence_head=None)) == {"P1": "STALE"}

    def test_edited_issue_contract_is_stale(self):
        binding, verdict = self._covered()
        live = _live(binding["promise_set"], contract_hash="e" * 64)
        assert _statuses(_project(binding, verdict, live=live)) == {"P1": "STALE"}

    def test_new_promise_generation_is_stale(self):
        binding, verdict = self._covered()
        live = _live(_promise_set(_promise("P1"), generation=2))
        assert _statuses(_project(binding, verdict, live=live)) == {"P1": "STALE"}

    def test_a_verdict_for_another_card_universe_is_stale(self):
        binding = _binding(_promise_set(_promise("P1")), {"P1": [ENTRY_P1]})
        verdict = _verdict([_entry(ENTRY_P1)], contract_universe_identity=OTHER_UNIVERSE_IDENTITY)
        assert _statuses(_project(binding, verdict)) == {"P1": "STALE"}

    def test_unconfirmed_live_issue_is_stale(self):
        binding, verdict = self._covered()
        result = _projection_module().project_issue_promise_coverage(
            binding, verdict, HEAD, evidence_head=HEAD, live_issue=None
        )
        assert _statuses(result) == {"P1": "STALE"}

    def test_malformed_expected_head_is_blocked(self):
        binding, verdict = self._covered()
        result = _project(binding, verdict, expected_head="HEAD", evidence_head="HEAD")
        assert result["overall"] == "BLOCKED"


class TestScenario6ForgedCloseIsProjectionOnly:
    """G0 §4 row 6: the projection grants nothing and cannot be talked into COMPLETE."""


    _AUTHORITY_WORDS = ("approv", "merge", "close", "closure", "authoriz", "grant", "release")

    def _keys(self, value: Any) -> set[str]:
        if isinstance(value, dict):
            found = set(value)
            for item in value.values():
                found |= self._keys(item)
            return found
        if isinstance(value, list):
            return set().union(*(self._keys(item) for item in value)) if value else set()
        return set()

    def test_output_has_no_authority_fields(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)])
        result = _project(binding, verdict)
        assert result["schema"] == "nexus.issue_promise_coverage.v1"
        for key in self._keys(result):
            assert not any(word in key.lower() for word in self._AUTHORITY_WORDS), key

    def test_forged_close_fields_in_the_verdict_do_not_complete(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1, "NOT_COVERED", None)])
        verdict.update({"closure": "CLOSE", "issue_closed": True, "all_promises_met": True})
        result = _project(binding, verdict)
        assert result["overall"] != "COMPLETE"
        assert "closure" not in result

    def test_missing_or_invalid_promise_block_is_blocked(self):
        verdict = _verdict([_entry(ENTRY_P1)])
        assert _project(None, verdict, live={})["overall"] == "BLOCKED"
        forged = _binding(THREE, {"P1": [ENTRY_P1]})
        assert _project(forged, verdict)["overall"] == "BLOCKED"

    def test_projection_module_is_pure(self):
        source = Path(inspect.getfile(_projection_module())).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = (
            "subprocess",
            "os",
            "requests",
            "urllib",
            "github",
            "closure",
            "gateway",
            "socket",
        )
        for name in imported:
            assert not any(part in name.split(".")[-1] for part in forbidden), name

    def test_projection_does_not_mutate_its_inputs(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)])
        before = (repr(binding), repr(verdict))
        _project(binding, verdict)
        assert (repr(binding), repr(verdict)) == before


class TestBlockedCoreVerdictNeverCompletes:
    """A Core verdict that blocked, failed or lost integrity never reads COMPLETE.

    The promise's own subjects all PASS here; what failed is the rest of the
    verdict. Integrity other than VALID (or no Core status at all) means no
    entry is trustworthy, so no promise is COVERED either.
    """

    __test__ = _RED_2532

    @pytest.mark.parametrize(
        ("overrides", "any_covered_allowed"),
        [
            ({"core_status": "FAILED_VERIFICATION"}, True),
            ({"core_status": "UNVERIFIABLE"}, True),
            ({"blocking": True, "host_reason_codes": ["CORE_COVERAGE_UNEXPECTED_SUBJECTS"]}, True),
            ({"integrity": "INVALID"}, False),
            ({"integrity": "MALFORMED", "core_status": "UNVERIFIABLE"}, False),
            ({"integrity": None}, False),
            ({"core_status": None}, False),
        ],
        ids=[
            "failed-verification",
            "unverifiable",
            "host-blocking",
            "integrity-invalid",
            "integrity-malformed",
            "integrity-missing",
            "core-status-missing",
        ],
    )
    def test_blocked_verdict_is_never_complete(self, overrides, any_covered_allowed):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict([_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)], **overrides)
        result = _project(binding, verdict)
        assert result["overall"] != "COMPLETE"
        if not any_covered_allowed:
            assert "COVERED" not in _statuses(result).values()

    def test_blocking_verdict_with_every_promise_passing_is_blocked(self):
        binding = _binding(THREE, THREE_MAP)
        verdict = _verdict(
            [_entry(ENTRY_P1), _entry(ENTRY_P2), _entry(ENTRY_P3)],
            core_status="FAILED_VERIFICATION",
        )
        assert _project(binding, verdict)["overall"] == "BLOCKED"


# <<< frozen #2532 RED region


# --- freeze guard (always collected) -------------------------------------

_REGION_START = "# >>> frozen #2532 RED region"
_REGION_END = "# <<< frozen #2532 RED region"
# sha256 of the frozen region (between the two marker lines), without blank
# lines, without the ``__test__ = _RED_2532`` gate lines and with each line
# stripped, so deleting the gates and reformatting blank lines keep it.
_FROZEN_SOURCE_SHA256 = "c11c3e2c02b1a77063c362b51111159f93e1dcab7c5dd379a1cff03a61dc7c28"


def _frozen_source_sha256(text: str) -> str:
    lines = text.splitlines()
    start = lines.index(_REGION_START)
    end = lines.index(_REGION_END)
    kept = [
        line.strip()
        for line in lines[start + 1 : end]
        if line.strip() and line.strip() != "__test__ = _RED_2532"
    ]
    return hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()


def test_frozen_red_tests_are_unchanged():
    text = Path(__file__).read_text(encoding="utf-8")
    assert _frozen_source_sha256(text) == _FROZEN_SOURCE_SHA256
