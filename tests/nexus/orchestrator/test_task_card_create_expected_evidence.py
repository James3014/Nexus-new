"""``nexus_task_card_create`` declares the expected evidence universe (#2218).

The universe is honoured only from one fenced ``nexus-expected-evidence`` block
in the hashed task card (#2181). These witnesses pin the card-creation side:

- the optional ``expected_evidence`` argument is validated with the reader's
  own ``ExpectedEvidenceUniverse`` model and parser rules;
- it is rendered as exactly one block that reads back as the same universe and
  the same Core universe identity, and is covered by the card hash;
- without the argument the card bytes are the legacy bytes;
- worker-facing tools still cannot supply a universe.

The Core-backed end-to-end witnesses (card created here, then driven to a
``core_verdict``) live in ``test_evidence_coverage_live_path.py`` so they share
its pinned-Core fixture and CI no-skip rule.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import nexus.orchestrator.unified_mcp_gateway as gateway_module
from nexus.orchestrator.ambient_core import core_universe_identity
from nexus.orchestrator.task_contract import (
    TASK_CARD_EXPECTED_EVIDENCE_FENCE,
    EvidenceRequirementMode,
    EvidenceSubjectApplicability,
    ExpectedEvidenceSubject,
    ExpectedEvidenceUniverse,
    expected_evidence_universe_identity,
    parse_task_card_expected_evidence,
)
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

HEAD = "a" * 40
AUTHORITY_ARGS = {
    "authority_goal_id": "goal-test",
    "authority_coordination_scope_id": "thread-test",
}
BASE_ARGUMENTS: dict[str, Any] = {
    **AUTHORITY_ARGS,
    "owner_confirmation": True,
    "campaign_id": "coverage-campaign",
    "task_id": "first-card",
    "objective": "Change README.md in one bounded step.",
    "allowed_files": ["README.md"],
    "verifier_commands": ["git diff --check"],
}

# The exact card the pre-#2218 handler wrote for BASE_ARGUMENTS. A card created
# without ``expected_evidence`` must stay byte-identical to it.
LEGACY_CARD = (
    "# Task Card: first-card\n"
    "\n"
    "artifact_authority: current\n"
    "task_id: `first-card`\n"
    "owner: James Chen\n"
    "status: ACTIVE\n"
    "execution_lane: GOVERNED\n"
    "commit_required: true\n"
    "candidate_required: true\n"
    "worker_may_commit: true\n"
    "worker_may_approve: false\n"
    "worker_may_integrate: false\n"
    "worker_may_push: false\n"
    "AUTO_CHAIN: false\n"
    "\n"
    "## Objective\n"
    "\n"
    "Change README.md in one bounded step.\n"
    "\n"
    "## Allowed files\n"
    "\n"
    "- `README.md`\n"
    "\n"
    "## Verification commands\n"
    "\n"
    "```bash\n"
    "git diff --check\n"
    "```\n"
    "\n"
    "## Exit criteria\n"
    "\n"
    "Owner review of the exact scoped commit.\n"
    "\n"
    "## Block classification\n"
    "\n"
    "Unverifiable or out-of-scope mutation is a HARD_BLOCK.\n"
)


def _subject(sid: str, kind: str, mode: str = "REQUIRED", applicability: str = "APPLICABLE"):
    return {
        "logical_subject_id": sid,
        "evidence_kind": kind,
        "requirement_mode": mode,
        "applicability": applicability,
    }


# Deliberately unsorted: the card must hold the canonical (sorted) form.
UNIVERSE = {
    "universe_generation": 3,
    "subjects": [
        _subject("review:security", "review-report", "CONDITIONALLY_REQUIRED", "UNRESOLVED"),
        _subject("git diff --check", "verifier-run"),
        _subject("lint:ruff", "lint-report", "NOT_APPLICABLE", "NOT_APPLICABLE"),
    ],
}


@pytest.fixture
def owner_effects(monkeypatch, tmp_path) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []

    def allow(action, effect, *, key):
        effects.append(dict(effect))
        return {
            "schema": "nexus.standing_grant_effect_authorization.v1",
            "action": action.value,
            "effect": dict(effect),
            "mutation_authorized": True,
            "authorization_hash": "f" * 64,
        }

    monkeypatch.setattr(UnifiedMCPGateway, "_require_owner_effect_authority", staticmethod(allow))
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: HEAD)
    return effects


def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = UnifiedMCPGateway(service=MagicMock()).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    return response["result"]


def _create(arguments: dict[str, Any]) -> dict[str, Any]:
    return _call("nexus_task_card_create", arguments)


def _card(root: Path, payload: dict[str, Any]) -> bytes:
    return (root / payload["card_path"]).read_bytes()


def test_task_card_create_without_universe_is_byte_identical_to_legacy_card(
    owner_effects, tmp_path
):
    result = _create(dict(BASE_ARGUMENTS))
    assert result["isError"] is False, result
    payload = result["structuredContent"]
    card = _card(tmp_path, payload)
    assert card == LEGACY_CARD.encode("utf-8")
    assert payload["card_hash"] == hashlib.sha256(LEGACY_CARD.encode("utf-8")).hexdigest()
    assert TASK_CARD_EXPECTED_EVIDENCE_FENCE.encode() not in card
    assert parse_task_card_expected_evidence(card.decode("utf-8")) is None
    # The Owner authorization effect is unchanged for legacy cards too.
    assert "expected_evidence_identity" not in owner_effects[0]


def test_task_card_create_null_universe_equals_absent(owner_effects, tmp_path):
    result = _create({**BASE_ARGUMENTS, "expected_evidence": None})
    assert result["isError"] is False, result
    assert _card(tmp_path, result["structuredContent"]) == LEGACY_CARD.encode("utf-8")


def test_task_card_create_universe_round_trips_through_the_card_parser(
    owner_effects, tmp_path, reference_core_universe_identity
):
    result = _create({**BASE_ARGUMENTS, "expected_evidence": UNIVERSE})
    assert result["isError"] is False, result
    payload = result["structuredContent"]
    card_bytes = _card(tmp_path, payload)
    card = card_bytes.decode("utf-8")

    parsed = parse_task_card_expected_evidence(card)
    expected = ExpectedEvidenceUniverse.model_validate(UNIVERSE).model_dump(mode="json")
    assert parsed == expected
    assert core_universe_identity(parsed) == core_universe_identity(UNIVERSE)
    assert expected_evidence_universe_identity(parsed) == expected_evidence_universe_identity(
        UNIVERSE
    )

    # Exactly one block, in the canonical (compact, sorted) form.
    opener = "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE
    lines = card.splitlines()
    assert lines.count(opener) == 1
    body = lines[lines.index(opener) + 1]
    assert body == ExpectedEvidenceUniverse.model_validate(UNIVERSE).canonical_json()
    assert lines[lines.index(opener) + 2] == "```"

    # The block is covered by the card hash the worker path binds to.
    assert payload["card_hash"] == hashlib.sha256(card_bytes).hexdigest()
    # Only the block was added: removing it restores the legacy bytes.
    block = "## Expected evidence\n\n" + opener + "\n" + body + "\n```\n\n"
    assert card.replace(block, "") == LEGACY_CARD
    # The Owner authorization is bound to the exact declared universe.
    assert owner_effects[0]["expected_evidence_identity"] == expected_evidence_universe_identity(
        UNIVERSE
    )


@pytest.mark.parametrize(
    ("universe", "reason"),
    [
        (
            {"universe_generation": 1, "subjects": [_subject("a", "k"), _subject("a", "other")]},
            "duplicate logical_subject_id",
        ),
        (
            {"universe_generation": 1, "subjects": [_subject("a", "k", mode="MANDATORY")]},
            "requirement_mode",
        ),
        (
            {"universe_generation": 1, "subjects": [_subject("a", "k", applicability="MAYBE")]},
            "applicability",
        ),
        ({"universe_generation": 1, "subjects": [_subject("a", "   ")]}, "evidence_kind"),
        (
            {"universe_generation": 1, "subjects": [{**_subject("a", "k"), "status": "PASS"}]},
            "status",
        ),
        ({"universe_generation": 1, "subjects": [_subject("a", "k")], "observed": []}, "observed"),
        (
            {
                "universe_generation": 1,
                "subjects": [_subject("a", "k", applicability="NOT_APPLICABLE")],
            },
            "REQUIRED",
        ),
        ({"universe_generation": True, "subjects": [_subject("a", "k")]}, "universe_generation"),
        ({"universe_generation": -1, "subjects": [_subject("a", "k")]}, "universe_generation"),
        ({"universe_generation": 1, "subjects": []}, "subjects"),
        ({"subjects": [_subject("a", "k")]}, "universe_generation"),
        ([_subject("a", "k")], "must be an object"),
        ("{}", "must be an object"),
    ],
    ids=[
        "duplicate-subjects",
        "bad-requirement-mode",
        "bad-applicability",
        "blank-kind",
        "unknown-subject-field",
        "unknown-universe-field",
        "required-not-applicable",
        "bool-generation",
        "negative-generation",
        "empty-subjects",
        "missing-generation",
        "list-not-object",
        "string-not-object",
    ],
)
def test_task_card_create_rejects_invalid_universe_with_zero_mutation(
    owner_effects, tmp_path, universe, reason
):
    result = _create({**BASE_ARGUMENTS, "expected_evidence": universe})
    assert result["isError"] is True
    error = result["structuredContent"]["error"]
    assert "TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID" in error
    assert reason in error
    assert owner_effects == []
    assert not (tmp_path / "tasks").exists()


@pytest.mark.parametrize("with_universe", [False, True], ids=["legacy", "universe"])
@pytest.mark.parametrize("field", ["objective", "verifier_commands"])
def test_task_card_create_rejects_a_block_smuggled_through_card_text(
    owner_effects, tmp_path, field, with_universe
):
    smuggled = "\n".join([
        "```",
        "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE,
        json.dumps({"universe_generation": 9, "subjects": [_subject("anything", "k")]}),
        "```",
    ])
    arguments: dict[str, Any] = dict(BASE_ARGUMENTS)
    arguments[field] = smuggled if field == "objective" else [smuggled]
    if with_universe:
        arguments["expected_evidence"] = UNIVERSE
    result = _create(arguments)
    assert result["isError"] is True
    assert "TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID" in result["structuredContent"]["error"]
    assert not (tmp_path / "tasks" / "coverage-campaign").exists()


def test_task_card_create_schema_declares_the_universe_with_the_model_enums():
    specs = {spec["name"]: spec["inputSchema"] for spec in UnifiedMCPGateway.tool_specs()}
    schema = specs["nexus_task_card_create"]
    assert "expected_evidence" not in schema["required"]
    declared = schema["properties"]["expected_evidence"]
    assert declared["additionalProperties"] is False
    subject = declared["properties"]["subjects"]["items"]
    assert subject["additionalProperties"] is False
    assert (
        set(subject["required"])
        == set(subject["properties"])
        == set(ExpectedEvidenceSubject.model_fields)
    )
    assert (
        set(declared["required"])
        == set(declared["properties"])
        == set(ExpectedEvidenceUniverse.model_fields)
    )
    assert subject["properties"]["requirement_mode"]["enum"] == [
        m.value for m in EvidenceRequirementMode
    ]
    assert subject["properties"]["applicability"]["enum"] == [
        a.value for a in EvidenceSubjectApplicability
    ]
    # The schema bounds are advisory; the model is the validator of record.
    too_many = {
        "universe_generation": 0,
        "subjects": [
            _subject(f"s{i}", "k")
            for i in range(declared["properties"]["subjects"]["maxItems"] + 1)
        ],
    }
    with pytest.raises(ValueError):
        ExpectedEvidenceUniverse.model_validate(too_many)


def test_only_the_card_creator_tool_can_declare_a_universe():
    for spec in UnifiedMCPGateway.tool_specs():
        properties = set((spec["inputSchema"].get("properties") or {}))
        if spec["name"] == "nexus_task_card_create":
            assert "expected_evidence" in properties
            continue
        assert not {"expected_evidence", "core_envelope_required"} & properties, spec["name"]


@pytest.mark.parametrize("field", ["expected_evidence", "core_envelope_required"])
def test_worker_candidate_still_rejects_a_supplied_universe(field):
    service = MagicMock()
    value: Any = UNIVERSE if field == "expected_evidence" else True
    result = UnifiedMCPGateway(service=service).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "nexus_worker_candidate",
            "arguments": {
                "task_id": "w",
                "what": "bounded",
                "why": "bounded",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
                "owner_confirmation": True,
                "task_card_path": "tasks/coverage-campaign/00-first-card.md",
                "task_card_hash": "0" * 64,
                field: value,
            },
        },
    })["result"]
    assert result["isError"] is True
    assert f"WORKER_CANDIDATE_UNKNOWN_FIELDS:{field}" in result["structuredContent"]["error"]
    service.submit_task.assert_not_called()


# --- #2532: Issue promises bound to expected-evidence subjects ------------
#
# Frozen RED tests (Owner decision on #2532, 2026-10-17): they land before the
# implementation. The required exact-base impact gate treats an added test
# that skips or xfails as not passed, so until the implementation PR the class
# carries a ``__test__ = _RED_2532`` gate and is collected only with
# ``NEXUS_RED_2532=1``. ``test_issue_promise_red_class_is_frozen`` pins the
# region between the two marker comments, ignoring blank lines and the gate
# line. The implementation PR deletes the gate line, ``_RED_2532`` and its
# ``os`` import (outside the region) and may reformat blank lines; any other
# edit to the region changes the hash and shows up in review.

_RED_2532 = os.environ.get("NEXUS_RED_2532") == "1"

# >>> frozen #2532 RED region


def _task_contract_module() -> Any:
    # Imported by name: the promise API does not exist before the
    # implementation PR, and a static import would break type checking.
    return importlib.import_module("nexus.orchestrator.task_contract")


class TestTaskCardCreateIssuePromises:

    ENTRY = "python -m pytest tests/test_feature.py::test_real_entry"
    OTHER = "python -m pytest tests/test_feature.py::test_other_entry"
    PROMISE_UNIVERSE = {
        "universe_generation": 4,
        "subjects": [
            _subject("python -m pytest tests/test_feature.py::test_real_entry", "verifier-run"),
            _subject("python -m pytest tests/test_feature.py::test_other_entry", "verifier-run"),
            _subject("review:security", "review-report", "CONDITIONALLY_REQUIRED", "UNRESOLVED"),
        ],
    }

    @staticmethod
    def _promise(pid: str, phase: str = "PRE_MERGE", risk: str = "STANDARD") -> dict[str, Any]:
        return {
            "promise_id": pid,
            "statement_sha256": hashlib.sha256(pid.encode()).hexdigest(),
            "phase": phase,
            "risk": risk,
        }

    def _binding(self, mapping: dict[str, list[str]], promise_ids=("P1", "P2")) -> dict[str, Any]:
        return {
            "repository": "James3014/Nexus-new",
            "issue_number": 4242,
            "issue_contract_hash": "c" * 64,
            "expected_evidence_identity": expected_evidence_universe_identity(
                self.PROMISE_UNIVERSE
            ),
            "promise_set": {
                "promise_set_generation": 1,
                # Deliberately unsorted: the card holds the canonical form.
                "promises": [self._promise(pid) for pid in reversed(promise_ids)],
            },
            "map": [{"promise_id": pid, "subject_ids": sids} for pid, sids in mapping.items()],
        }

    def _valid(self) -> dict[str, Any]:
        return self._binding({"P2": [self.OTHER], "P1": [self.ENTRY, "review:security"]})

    def _arguments(self, binding: Any, *, universe: Any = None) -> dict[str, Any]:
        return {
            **BASE_ARGUMENTS,
            "expected_evidence": self.PROMISE_UNIVERSE if universe is None else universe,
            "issue_promises": binding,
        }

    def _assert_rejected(self, result, owner_effects, tmp_path, reason: str) -> None:
        assert result["isError"] is True, result
        error = result["structuredContent"]["error"]
        assert "TASK_CARD_CREATE_ISSUE_PROMISES_INVALID" in error
        assert reason in error
        # Zero writes: no authority recorded, no campaign directory.
        assert owner_effects == []
        assert not (tmp_path / "tasks").exists()

    def test_universe_only_card_has_no_promise_block(self, owner_effects, tmp_path):
        result = _create({**BASE_ARGUMENTS, "expected_evidence": UNIVERSE})
        assert result["isError"] is False, result
        card = _card(tmp_path, result["structuredContent"]).decode("utf-8")
        contract = _task_contract_module()
        assert contract.TASK_CARD_ISSUE_PROMISES_FENCE not in card
        assert contract.parse_task_card_issue_promises(card) is None
        assert "issue_promises_identity" not in owner_effects[0]

    def test_promises_round_trip_through_the_card_parser(self, owner_effects, tmp_path):
        contract = _task_contract_module()
        binding = self._valid()
        result = _create(self._arguments(binding))
        assert result["isError"] is False, result
        payload = result["structuredContent"]
        card_bytes = _card(tmp_path, payload)
        card = card_bytes.decode("utf-8")

        canonical = contract.IssuePromiseBinding.model_validate(binding)
        parsed = contract.parse_task_card_issue_promises(card)
        assert parsed == canonical.model_dump(mode="json")
        assert [p["promise_id"] for p in parsed["promise_set"]["promises"]] == ["P1", "P2"]
        assert [m["promise_id"] for m in parsed["map"]] == ["P1", "P2"]

        opener = "```" + contract.TASK_CARD_ISSUE_PROMISES_FENCE
        lines = card.splitlines()
        assert lines.count(opener) == 1
        body = lines[lines.index(opener) + 1]
        assert body == canonical.canonical_json()
        assert lines[lines.index(opener) + 2] == "```"
        # The universe block is untouched and still parses to the same universe.
        assert parse_task_card_expected_evidence(card) == ExpectedEvidenceUniverse.model_validate(
            self.PROMISE_UNIVERSE
        ).model_dump(mode="json")
        # Covered by the card hash; removing the section restores the universe-only card.
        assert payload["card_hash"] == hashlib.sha256(card_bytes).hexdigest()
        block = "## Issue promises\n\n" + opener + "\n" + body + "\n```\n\n"
        assert block in card
        # The Owner authorization is bound to the exact promise binding.
        assert owner_effects[0]["issue_promises_identity"] == canonical.binding_identity
        assert owner_effects[0][
            "expected_evidence_identity"
        ] == expected_evidence_universe_identity(self.PROMISE_UNIVERSE)

    def test_missing_promise_is_rejected_with_zero_writes(self, owner_effects, tmp_path):
        binding = self._binding({"P1": [self.ENTRY]})
        self._assert_rejected(_create(self._arguments(binding)), owner_effects, tmp_path, "P2")

    def test_promise_outside_the_issue_set_is_rejected(self, owner_effects, tmp_path):
        binding = self._binding({"P1": [self.ENTRY], "P2": [self.OTHER], "P9": [self.ENTRY]})
        self._assert_rejected(_create(self._arguments(binding)), owner_effects, tmp_path, "P9")

    def test_subject_outside_the_card_universe_is_rejected(self, owner_effects, tmp_path):
        binding = self._binding({"P1": [self.ENTRY], "P2": ["pytest tests/never_declared.py"]})
        self._assert_rejected(
            _create(self._arguments(binding)), owner_effects, tmp_path, "never_declared"
        )

    def test_promise_without_a_required_subject_is_rejected(self, owner_effects, tmp_path):
        binding = self._binding({"P1": [self.ENTRY], "P2": ["review:security"]})
        self._assert_rejected(_create(self._arguments(binding)), owner_effects, tmp_path, "P2")

    def test_binding_for_another_universe_is_rejected(self, owner_effects, tmp_path):
        binding = {**self._valid(), "expected_evidence_identity": "sha256:" + "f" * 64}
        self._assert_rejected(
            _create(self._arguments(binding)), owner_effects, tmp_path, "expected_evidence_identity"
        )

    def test_deeply_nested_smuggled_block_fails_closed(self, owner_effects, tmp_path, monkeypatch):
        contract = _task_contract_module()

        def explode(*_args, **_kwargs):
            raise RecursionError("maximum recursion depth exceeded")

        monkeypatch.setattr(contract.json, "loads", explode)
        smuggled = "\n".join([
            "```",
            "```" + contract.TASK_CARD_ISSUE_PROMISES_FENCE,
            "[[[]]]",
            "```",
        ])
        result = _create({**BASE_ARGUMENTS, "objective": smuggled})
        assert result["isError"] is True
        assert "TASK_CARD_CREATE_ISSUE_PROMISES_INVALID" in result["structuredContent"]["error"]
        assert owner_effects == []
        assert not (tmp_path / "tasks").exists()

    def test_promises_without_a_universe_are_rejected(self, owner_effects, tmp_path):
        arguments = {**BASE_ARGUMENTS, "issue_promises": self._valid()}
        self._assert_rejected(_create(arguments), owner_effects, tmp_path, "expected_evidence")

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda b: {**b, "issue_number": 0},
            lambda b: {**b, "issue_contract_hash": "short"},
            lambda b: {**b, "repository": "not a repo"},
            lambda b: {**b, "status": "COVERED"},
            lambda b: {**b, "map": [{"promise_id": "P1", "subject_ids": []}]},
            lambda b: "not an object",
        ],
        ids=[
            "issue-number",
            "contract-hash",
            "repository",
            "extra-field",
            "empty-subjects",
            "string",
        ],
    )
    def test_malformed_binding_is_rejected_with_zero_writes(self, owner_effects, tmp_path, mutate):
        result = _create(self._arguments(mutate(self._valid())))
        self._assert_rejected(result, owner_effects, tmp_path, "")

    @pytest.mark.parametrize("with_promises", [False, True], ids=["universe-only", "promises"])
    def test_a_promise_block_smuggled_through_objective_is_rejected(
        self, owner_effects, tmp_path, with_promises
    ):
        contract = _task_contract_module()
        smuggled = "\n".join([
            "```",
            "```" + contract.TASK_CARD_ISSUE_PROMISES_FENCE,
            json.dumps(self._valid()),
            "```",
        ])
        arguments: dict[str, Any] = {
            **BASE_ARGUMENTS,
            "objective": smuggled,
            "expected_evidence": self.PROMISE_UNIVERSE,
        }
        if with_promises:
            arguments["issue_promises"] = self._valid()
        result = _create(arguments)
        assert result["isError"] is True
        assert "TASK_CARD_CREATE_ISSUE_PROMISES_INVALID" in result["structuredContent"]["error"]
        # Rejected before any Owner authority is checked or recorded.
        assert owner_effects == []
        assert not (tmp_path / "tasks" / "coverage-campaign").exists()

    def test_schema_declares_issue_promises_on_the_card_creator_only(self):
        for spec in UnifiedMCPGateway.tool_specs():
            properties = set(spec["inputSchema"].get("properties") or {})
            if spec["name"] == "nexus_task_card_create":
                assert "issue_promises" in properties
                assert "issue_promises" not in spec["inputSchema"]["required"]
                assert (
                    spec["inputSchema"]["properties"]["issue_promises"]["additionalProperties"]
                    is False
                )
                continue
            assert "issue_promises" not in properties, spec["name"]


# <<< frozen #2532 RED region


def test_control_null_issue_promises_equals_absent(owner_effects, tmp_path):
    # Control, not RED: green before and after #2532.
    result = _create({**BASE_ARGUMENTS, "issue_promises": None})
    assert result["isError"] is False, result
    assert _card(tmp_path, result["structuredContent"]) == LEGACY_CARD.encode("utf-8")
    assert "issue_promises_identity" not in owner_effects[0]


def test_worker_candidate_rejects_supplied_issue_promises():
    # Control, not RED (green before #2532 lands): a worker can never supply
    # or override the promise binding; only the hashed card carries it.
    service = MagicMock()
    response = UnifiedMCPGateway(service=service).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "nexus_worker_candidate",
            "arguments": {
                "task_id": "w",
                "what": "bounded",
                "why": "bounded",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
                "owner_confirmation": True,
                "task_card_path": "tasks/coverage-campaign/00-first-card.md",
                "task_card_hash": "0" * 64,
                "issue_promises": {"map": []},
            },
        },
    })
    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert "WORKER_CANDIDATE_UNKNOWN_FIELDS:issue_promises" in result["structuredContent"]["error"]
    service.submit_task.assert_not_called()


_REGION_START = "# >>> frozen #2532 RED region"
_REGION_END = "# <<< frozen #2532 RED region"
# sha256 of the frozen region without blank lines and the gate line, each
# line stripped, so deleting the gate and reformatting blank lines keep it.
_FROZEN_ISSUE_PROMISE_CLASS_SHA256 = (
    "721ac42cc80284faa10b2ff93ba9cb879eb92a7ccdd04cec421f5bcbfb3c3e5e"
)


def test_issue_promise_red_class_is_frozen():
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    start = lines.index(_REGION_START)
    end = lines.index(_REGION_END)
    kept = [
        line.strip()
        for line in lines[start + 1 : end]
        if line.strip() and line.strip() != "__test__ = _RED_2532"
    ]
    digest = hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()
    assert digest == _FROZEN_ISSUE_PROMISE_CLASS_SHA256
