"""Characterization of the ambient-Core / Track-1 cluster of ``SelfHostedTaskService`` (S10).

Big-file split step S10 (Issue #2692) moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``_ambient_core_required``, ``_prepare_ambient_core`` and ``_revalidate_ambient_core``
  (the ambient Core mutation binding, through the instance's ``ambient_core_port``);
* the static ``_card_evidence_binding_error`` and ``_direct_lane_claims_evidence`` (the
  declared evidence universe and the Core requirement bound to the hashed Task Card);
* the static ``_core_blocked_receipt`` and ``_verify_ambient_core_candidate`` (Core's
  verdict on a verified Candidate);
* ``_record_track1_verified_outcome`` (the telemetry-only Track-1 research mirror).

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* every refusal of every member, in its order, with its exact code, and every
  pass-through; the exact arguments of every collaborator (the control port, the
  ambient-Core helpers, the research-evidence collector and trajectory binder, ``git
  diff``);
* that every facade-module name the moved code reads (``ambient_core_required``,
  ``normalize_preparation``, ``build_core_verdict``, ``normalize_verification_projection``,
  ``projection_hash``, ``AmbientCoreVerdictBlocked``, ``parse_task_card_expected_evidence``,
  ``_resolve_task_card_path``, ``replace``, ``subprocess`` and the
  module's ``__file__``) is resolved through the facade at call time (patched after a
  first call that reached the same site);
* that the Track-1 refresh receives the repository root derived from the facade's own
  file (``Path(__file__).resolve().parents[2]``), not from wherever the code lives;
* that instance, class and subclass patches of the members it reaches through ``self``
  are honoured, also from the runtime coordination bridge.

No test reaches a real Core, runs a worker or writes research evidence: the control port,
the research collector and the trajectory binder are recorders, and ``git diff`` is a
recorded stand-in.  No test asserts on inode numbers, file modes or other platform
details.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
import nexus.research.clm_system_one.candidate_evidence_collector as collector_module
import nexus.research.clm_system_one.research_evidence_root as evidence_root_module
import nexus.research.clm_system_one.trajectory_continuity as continuity_module
from nexus.orchestrator import runtime_coordination_bridge
from nexus.orchestrator.ambient_core import (
    CORE_RESPONSE_SCHEMA,
    PREPARATION_SCHEMA,
    AmbientCoreVerdictBlocked,
)
from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt, VerifierEvidence
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

MEMBERS = (
    "_ambient_core_required",
    "_prepare_ambient_core",
    "_revalidate_ambient_core",
    "_card_evidence_binding_error",
    "_direct_lane_claims_evidence",
    "_core_blocked_receipt",
    "_verify_ambient_core_candidate",
    "_record_track1_verified_outcome",
)
CARD_DOC = (
    "Bind the declared universe and the Core requirement to the hashed card (#2181).\n\n"
    "Runs for every task, before the Core short-circuit, at intake and at\n"
    "finalize. A card that declares a universe cannot be satisfied by a\n"
    "request that drops it, and a universe never comes from anywhere but\n"
    "the card. For a card-less legacy request nothing is read."
)
VERIFY_DOC = (
    "Obtain and record Core's verdict; raise ``AmbientCoreVerdictBlocked`` when blocked.\n\n"
    "The blocked exception carries the durable blocked receipt so the\n"
    "caller can persist the verdict before failing the attempt."
)
TRACK1_DOC = (
    "Mirror one natural self-hosted Candidate into Track-1 research evidence.\n\n"
    "This is telemetry only. It reuses the existing candidate-evidence and\n"
    "trajectory contracts and never changes selection, verification,\n"
    "acceptance, routing, or admission. Failures are returned as bounded\n"
    "metadata so the caller can preserve runtime behavior."
)
MEMBER_TABLE = {
    "_ambient_core_required": (
        "function",
        "(self, contract, request: 'Mapping[str, Any]') -> 'bool'",
        None,
    ),
    "_prepare_ambient_core": (
        "function",
        "(self, contract, request: 'Mapping[str, Any]', lease, state: 'Mapping[str, Any]', *, "
        "task_id: 'str', attempt_id: 'str') -> 'Mapping[str, Any]'",
        None,
    ),
    "_revalidate_ambient_core": (
        "function",
        "(self, preparation: 'Mapping[str, Any]', contract, request: 'Mapping[str, Any]', "
        "lease, state: 'Mapping[str, Any]', *, task_id: 'str', attempt_id: 'str', "
        "active_provider: 'str') -> 'None'",
        None,
    ),
    "_card_evidence_binding_error": (
        "staticmethod",
        "(contract, request: 'Mapping[str, Any]') -> 'Optional[str]'",
        CARD_DOC,
    ),
    "_direct_lane_claims_evidence": (
        "staticmethod",
        "(request: 'Mapping[str, Any]') -> 'bool'",
        None,
    ),
    "_core_blocked_receipt": (
        "staticmethod",
        "(verified: 'VerifiedCandidateReceipt', verdict: 'Mapping[str, Any]') -> "
        "'VerifiedCandidateReceipt'",
        None,
    ),
    "_verify_ambient_core_candidate": (
        "function",
        "(self, *, contract, request: 'Mapping[str, Any]', lease, state: 'Mapping[str, Any]', "
        "candidate, verified: 'VerifiedCandidateReceipt') -> 'VerifiedCandidateReceipt'",
        VERIFY_DOC,
    ),
    "_record_track1_verified_outcome": (
        "function",
        "(self, *, contract, lease, state: 'Mapping[str, Any]', candidate, verified: "
        "'VerifiedCandidateReceipt', execution: 'WorkerExecutionReceipt') -> 'dict[str, Any]'",
        TRACK1_DOC,
    ),
}
PREP = {
    "schema": PREPARATION_SCHEMA,
    "session_id": "cms_" + "1" * 32,
    "binding_id": "binding-1",
    "binding_hash": "sha256:" + "2" * 64,
    "operation_id": "operation-1",
    "attempt_id": "attempt",
    "acceptance_contract_hash": "sha256:" + "3" * 64,
    "source_revision": "git-commit:" + "8" * 40,
    "source_tree": "git-tree:" + "9" * 40,
}
# the repository root of this checkout (tests/contracts/<this file> -> parents[2])
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# fixtures


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


class _Port:
    """A recording ambient Core control port."""

    def __init__(
        self,
        log: list[Any],
        *,
        prepared: Any = None,
        projection: Any = None,
        error: Optional[BaseException] = None,
    ) -> None:
        self.log, self.prepared, self.projection, self.error = log, prepared, projection, error

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Any:
        self.log.append(("open", kwargs))
        return self.prepared

    def revalidate_mutation_binding(self, normalized: Any, **kwargs: Any) -> Any:
        self.log.append(("revalidate", normalized, kwargs))
        return "ignored-return"

    def verify_candidate(self, **kwargs: Any) -> Any:
        self.log.append(("verify", kwargs))
        if self.error is not None:
            raise self.error
        return self.projection


def _receipt(**extra: Any) -> VerifiedCandidateReceipt:
    fields: dict[str, Any] = {
        "schema": "nexus.verified_candidate_receipt.v1",
        "task_id": "task-1",
        "contract_hash": "contract",
        "lease_id": "lease",
        "candidate_state_hash": "candidate-state",
        "scope_gate_passed": True,
        "deletion_gate_passed": True,
        "controller_gate_passed": True,
        "protected_contract_gate_passed": True,
        "verifier_gate_passed": True,
        "verified": True,
        "candidate_commit_allowed": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "failure_reasons": ["local-reason"],
        "verifier_evidence": (),
        "candidate_commit_created": False,
        "merge_performed": False,
    }
    fields.update(extra)
    return VerifiedCandidateReceipt(**fields)


def _evidence(command: str, status: str = "COMPLETED", exit_code: Optional[int] = 0) -> Any:
    return VerifierEvidence(
        command=command,
        status=status,
        exit_code=exit_code,
        stdout_sha256="5" * 64,
        stderr_sha256="6" * 64,
        wall_time_ms=1,
    )


# ---------------------------------------------------------------------------
# member table


def test_member_table() -> None:
    table = {}
    for name in MEMBERS:
        static = inspect.getattr_static(SelfHostedTaskService, name)
        func = static.__func__ if isinstance(static, staticmethod) else static
        # cleandoc: Python 3.13+ strips docstring indentation at compile time, 3.12 does not
        doc = inspect.cleandoc(func.__doc__) if func.__doc__ else func.__doc__
        table[name] = (type(static).__name__, str(inspect.signature(func)), doc)
    assert table == MEMBER_TABLE


def test_static_members_are_the_same_through_class_and_instance(service) -> None:
    for name in (
        "_card_evidence_binding_error",
        "_direct_lane_claims_evidence",
        "_core_blocked_receipt",
    ):
        assert getattr(service, name) is getattr(SelfHostedTaskService, name)


# ---------------------------------------------------------------------------
# _ambient_core_required


def test_ambient_core_required_reads_the_request_flag(service) -> None:
    assert service._ambient_core_required("ignored", {}) is False
    assert service._ambient_core_required(None, {"core_envelope_required": False}) is False
    assert service._ambient_core_required(None, {"core_envelope_required": True}) is True
    with pytest.raises(ValueError, match="^core_envelope_required must be boolean$"):
        service._ambient_core_required(None, {"core_envelope_required": "yes"})


def test_late_ambient_core_required(service, monkeypatch) -> None:
    assert service._ambient_core_required("C", {"core_envelope_required": True}) is True
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module, "ambient_core_required", lambda request: (seen.append(request), "late")[1]
    )
    request = {"core_envelope_required": True}
    assert service._ambient_core_required("C", request) == "late"
    assert seen == [request] and seen[0] is request


# ---------------------------------------------------------------------------
# _prepare_ambient_core / _revalidate_ambient_core


def test_prepare_refuses_when_core_is_not_required(service) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log, prepared=PREP)
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_PREPARATION_NOT_REQUIRED$"):
        service._prepare_ambient_core("C", {}, "L", {}, task_id="t1", attempt_id="attempt")
    assert log == []


def test_prepare_refuses_without_a_port(service) -> None:
    assert service.ambient_core_port is None
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_CONTROL_PORT_REQUIRED$"):
        service._prepare_ambient_core(
            "C", {"core_envelope_required": True}, "L", {}, task_id="t1", attempt_id="attempt"
        )


def test_prepare_opens_the_binding_and_normalizes_it(service) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log, prepared={**PREP, "extra": "dropped"})
    request = {"core_envelope_required": True}
    state = {"s": 1}
    out = service._prepare_ambient_core(
        "C", request, "L", state, task_id="t1", attempt_id="attempt"
    )
    assert out == PREP
    assert log == [
        (
            "open",
            {
                "contract": "C",
                "request": request,
                "lease": "L",
                "state": state,
                "task_id": "t1",
                "attempt_id": "attempt",
            },
        )
    ]
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_ATTEMPT_MISMATCH$"):
        service._prepare_ambient_core("C", request, "L", state, task_id="t1", attempt_id="other")


def test_prepare_uses_the_instance_required_check(service, monkeypatch) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log, prepared=PREP)
    calls: list[Any] = []
    monkeypatch.setattr(
        service, "_ambient_core_required", lambda c, r: (calls.append((c, r)), True)[1]
    )
    out = service._prepare_ambient_core("C", {}, "L", {}, task_id="t1", attempt_id="attempt")
    assert out == PREP and calls == [("C", {})]


def test_late_normalize_preparation_in_prepare(service, monkeypatch) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log, prepared=PREP)
    request = {"core_envelope_required": True}
    service._prepare_ambient_core("C", request, "L", {}, task_id="t1", attempt_id="attempt")
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "normalize_preparation",
        lambda value, *, attempt_id: (seen.append((value, attempt_id)), {"late": 1})[1],
    )
    out = service._prepare_ambient_core("C", request, "L", {}, task_id="t1", attempt_id="attempt")
    assert out == {"late": 1} and seen == [(PREP, "attempt")]


def test_revalidate_refuses_when_core_is_not_required(service) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log)
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_PREPARATION_UNEXPECTED$"):
        service._revalidate_ambient_core(
            PREP, "C", {}, "L", {}, task_id="t1", attempt_id="attempt", active_provider="codex"
        )
    assert log == []


def test_revalidate_refuses_without_a_port(service) -> None:
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_CONTROL_PORT_REQUIRED$"):
        service._revalidate_ambient_core(
            PREP,
            "C",
            {"core_envelope_required": True},
            "L",
            {},
            task_id="t1",
            attempt_id="attempt",
            active_provider="codex",
        )


def test_revalidate_normalizes_before_the_port(service) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log)
    request = {"core_envelope_required": True}
    state = {"s": 1}
    assert (
        service._revalidate_ambient_core(
            {**PREP, "extra": "dropped"},
            "C",
            request,
            "L",
            state,
            task_id="t1",
            attempt_id="attempt",
            active_provider="gemini",
        )
        is None
    )
    assert log == [
        (
            "revalidate",
            PREP,
            {
                "contract": "C",
                "request": request,
                "lease": "L",
                "state": state,
                "task_id": "t1",
                "attempt_id": "attempt",
                "active_provider": "gemini",
            },
        )
    ]
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_INVALID:session_id$"):
        service._revalidate_ambient_core(
            {**PREP, "session_id": "bad"},
            "C",
            request,
            "L",
            state,
            task_id="t1",
            attempt_id="attempt",
            active_provider="gemini",
        )
    assert len(log) == 1


def test_late_normalize_preparation_in_revalidate(service, monkeypatch) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log)
    request = {"core_envelope_required": True}
    args = ("C", request, "L", {})
    kwargs = {"task_id": "t1", "attempt_id": "attempt", "active_provider": "codex"}
    service._revalidate_ambient_core(PREP, *args, **kwargs)
    monkeypatch.setattr(
        service_module, "normalize_preparation", lambda value, *, attempt_id: {"late": attempt_id}
    )
    service._revalidate_ambient_core(PREP, *args, **kwargs)
    assert log[0][1] == PREP and log[1][1] == {"late": "attempt"}


def test_bridge_reaches_the_ambient_members_through_the_service(service, monkeypatch) -> None:
    log: list[Any] = []
    service.ambient_core_port = _Port(log, prepared=PREP)
    contract_port = runtime_coordination_bridge._Contract(service)
    assert contract_port.host_preparation_required("C", {"core_envelope_required": True}) is True
    assert contract_port.host_preparation_required("C", {}) is False
    preparation_port = runtime_coordination_bridge._Preparation(service)
    claims: list[Any] = []
    mutations: list[Any] = []
    monkeypatch.setattr(service, "_bridge_validate_claim", lambda *a, **k: claims.append((a, k)))
    monkeypatch.setattr(service, "_mutate_state", lambda task_id, fn: mutations.append(task_id))
    request = {"core_envelope_required": True}
    assert (
        preparation_port.prepare_before_worker(
            "C", request, "L", {}, task_id="t1", attempt_id="attempt"
        )
        == PREP
    )
    assert claims == [(("t1", "attempt"), {"operation": "HOST_PREPARATION"})]
    assert mutations == ["t1"]
    preparation_port.revalidate_before_worker(
        PREP, "C", request, "L", {}, task_id="t1", attempt_id="attempt", active_provider="codex"
    )
    assert [entry[0] for entry in log] == ["open", "revalidate"]


# ---------------------------------------------------------------------------
# _card_evidence_binding_error


class _Cards:
    """Task Card files under tmp_path; the facade's card parser is a lookup table."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.declared: dict[bytes, Any] = {}
        self.parsed: list[str] = []
        self.resolved: list[Any] = []
        monkeypatch.setattr(service_module, "_resolve_task_card_path", self.resolve)
        monkeypatch.setattr(service_module, "parse_task_card_expected_evidence", self.parse)

    def resolve(self, value: Any) -> Path:
        self.resolved.append(value)
        return self.root / str(value)

    def parse(self, text: str) -> Any:
        self.parsed.append(text)
        if text.startswith("invalid"):
            raise ValueError("bad card")
        return self.declared.get(text.encode("utf-8"))

    def card(self, name: str, body: bytes, declared: Any = None) -> dict[str, str]:
        (self.root / name).write_bytes(body)
        self.declared[body] = declared
        return {"task_card_path": name, "task_card_hash": hashlib.sha256(body).hexdigest()}


UNIVERSE = {"universe_generation": 1, "subjects": [["diff", "check"]]}


class _Universe:
    def __init__(self, value: Any) -> None:
        self.value = value

    def model_dump(self, mode: str = "python") -> Any:
        assert mode == "json"
        return self.value


@pytest.fixture
def cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Cards:
    root = tmp_path / "cards"
    root.mkdir()
    return _Cards(root, monkeypatch)


def _contract(universe: Any = None) -> Any:
    return SimpleNamespace(expected_evidence=universe)


card_error = SelfHostedTaskService._card_evidence_binding_error


def test_card_check_without_a_card_path(cards) -> None:
    assert card_error(_contract(), {}) is None
    assert card_error(_contract(), {"core_envelope_required": True}) is None
    assert card_error(_contract(), {"task_card_path": ""}) is None
    assert card_error(_contract(), {"task_card_path": 7}) is None
    assert card_error(_contract(UNIVERSE), {}) == "EXPECTED_EVIDENCE_UNIVERSE_NOT_CARD_BOUND"
    # a model_dump()-able universe is dumped in JSON mode first
    assert card_error(_contract(_Universe(UNIVERSE)), {}) == (
        "EXPECTED_EVIDENCE_UNIVERSE_NOT_CARD_BOUND"
    )
    assert card_error(_contract(_Universe(None)), {}) is None
    assert cards.resolved == [] and cards.parsed == []


@pytest.mark.parametrize(
    ("universe", "core", "code"),
    [
        (None, False, None),
        (UNIVERSE, False, "EXPECTED_EVIDENCE_TASK_CARD_UNREADABLE"),
        (None, True, "EXPECTED_EVIDENCE_TASK_CARD_UNREADABLE"),
    ],
)
def test_card_check_unreadable_card(cards, universe, core, code) -> None:
    request = {"task_card_path": "missing.md", "core_envelope_required": core}
    assert card_error(_contract(universe), request) == code
    assert cards.resolved == ["missing.md"] and cards.parsed == []


@pytest.mark.parametrize(
    ("universe", "core", "code"),
    [
        (None, False, None),
        (UNIVERSE, False, "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISMATCH"),
        (None, True, "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISMATCH"),
    ],
)
def test_card_check_hash_mismatch(cards, universe, core, code) -> None:
    request = {**cards.card("c.md", b"body", None), "core_envelope_required": core}
    request["task_card_hash"] = "0" * 64
    assert card_error(_contract(universe), request) == code
    assert cards.parsed == []


def test_card_check_without_a_hash_still_reads_the_card(cards) -> None:
    request = cards.card("c.md", b"universe-card", UNIVERSE)
    del request["task_card_hash"]
    request["core_envelope_required"] = True
    assert card_error(_contract(UNIVERSE), request) == "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISSING"
    request["task_card_hash"] = ""
    assert card_error(_contract(UNIVERSE), request) == "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISSING"
    request["task_card_hash"] = 5
    assert card_error(_contract(UNIVERSE), request) == "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISSING"
    assert cards.parsed == ["universe-card"] * 3


def test_card_check_invalid_card(cards) -> None:
    # unreadable text or a parser ValueError: always refused, even for a legacy task
    request = cards.card("c.md", b"invalid card", None)
    assert card_error(_contract(), request) == "EXPECTED_EVIDENCE_TASK_CARD_INVALID"
    request = cards.card("d.md", b"\xff\xfe", None)
    assert card_error(_contract(), request) == "EXPECTED_EVIDENCE_TASK_CARD_INVALID"


@pytest.mark.parametrize(
    ("contract_universe", "card_universe", "core", "code"),
    [
        (None, None, False, None),
        (UNIVERSE, UNIVERSE, True, None),
        (UNIVERSE, None, False, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"),
        (None, UNIVERSE, True, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"),
        ({"other": 1}, UNIVERSE, True, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"),
        (UNIVERSE, UNIVERSE, False, "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"),
        (None, None, True, "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"),
    ],
)
def test_card_check_universe_and_core_flag(
    cards, contract_universe, card_universe, core, code
) -> None:
    request = {**cards.card("c.md", b"card", card_universe), "core_envelope_required": core}
    assert card_error(_contract(contract_universe), request) == code


def test_card_check_core_flag_type_error_propagates(cards) -> None:
    with pytest.raises(ValueError, match="^core_envelope_required must be boolean$"):
        card_error(_contract(), {"core_envelope_required": 1})


def test_card_check_with_the_real_parser(tmp_path, monkeypatch) -> None:
    # no stubs: the facade's own resolver and parser; a legacy card declares nothing
    card = tmp_path / "legacy-card.md"
    card.write_text("# Task\n\nNo evidence universe here.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    body = card.read_bytes()
    request = {"task_card_path": str(card), "task_card_hash": hashlib.sha256(body).hexdigest()}
    assert card_error(_contract(), request) is None
    assert card_error(_contract(), {**request, "core_envelope_required": True}) == (
        "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"
    )


def test_late_card_helpers_in_the_card_check(cards, monkeypatch) -> None:
    request = {**cards.card("c.md", b"card", None)}
    assert card_error(_contract(), request) is None
    # each facade name is re-read: resolver, parser, ambient_core_required
    monkeypatch.setattr(service_module, "_resolve_task_card_path", lambda v: cards.root / "nope")
    assert card_error(_contract(UNIVERSE), request) == "EXPECTED_EVIDENCE_TASK_CARD_UNREADABLE"
    monkeypatch.setattr(service_module, "_resolve_task_card_path", cards.resolve)
    assert card_error(_contract(UNIVERSE), request) == "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"
    monkeypatch.setattr(service_module, "parse_task_card_expected_evidence", lambda text: UNIVERSE)
    assert card_error(_contract(UNIVERSE), request) == "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"
    monkeypatch.setattr(service_module, "ambient_core_required", lambda r: True)
    assert card_error(_contract(UNIVERSE), request) is None


# ---------------------------------------------------------------------------
# _direct_lane_claims_evidence


claims_evidence = SelfHostedTaskService._direct_lane_claims_evidence


def test_direct_lane_request_fields(cards) -> None:
    assert claims_evidence({}) is False
    assert claims_evidence({"expected_evidence": {}}) is True
    assert claims_evidence({"expected_evidence": None}) is False
    assert claims_evidence({"core_envelope_required": True}) is True
    assert claims_evidence({"core_envelope_required": "yes"}) is True
    assert claims_evidence({"core_envelope_required": 0}) is False
    assert claims_evidence({"task_card_path": ""}) is False
    assert claims_evidence({"task_card_path": 3}) is False
    assert cards.resolved == []


def test_direct_lane_reads_any_supplied_card(cards) -> None:
    universe_card = cards.card("u.md", b"universe", UNIVERSE)
    legacy_card = cards.card("l.md", b"legacy", None)
    assert claims_evidence(universe_card) is True
    assert claims_evidence({"task_card_path": "u.md"}) is True  # no hash: still read
    assert claims_evidence(legacy_card) is False
    assert claims_evidence({**legacy_card, "task_card_hash": "0" * 64}) is False  # hash unchecked
    # unreadable, undecodable or unparsable cards fail closed for this lane
    assert claims_evidence({"task_card_path": "missing.md"}) is True
    assert claims_evidence(cards.card("x.md", b"\xff", None)) is True
    assert claims_evidence(cards.card("i.md", b"invalid", None)) is True
    assert cards.parsed == ["universe", "universe", "legacy", "legacy", "invalid"]


def test_late_card_helpers_in_the_direct_lane(cards, monkeypatch) -> None:
    legacy_card = cards.card("l.md", b"legacy", None)
    assert claims_evidence(legacy_card) is False
    monkeypatch.setattr(service_module, "parse_task_card_expected_evidence", lambda text: {})
    assert claims_evidence(legacy_card) is True
    monkeypatch.setattr(service_module, "parse_task_card_expected_evidence", cards.parse)
    monkeypatch.setattr(service_module, "_resolve_task_card_path", lambda v: cards.root / "nope")
    assert claims_evidence(legacy_card) is True


# ---------------------------------------------------------------------------
# _core_blocked_receipt


def test_core_blocked_receipt_fields() -> None:
    verified = _receipt(core_verification_status="VERIFIED", core_provenance_required=False)
    verdict = {
        "host_reason_codes": ["H1", "H2"],
        "reason_codes": ["R1"],
        "core_status": "FAILED",
        "projection_hash": "sha256:abc",
    }
    out = SelfHostedTaskService._core_blocked_receipt(verified, verdict)
    assert out is not verified and verified.verified is True
    expected = dataclasses.replace(
        verified,
        verified=False,
        candidate_commit_allowed=False,
        core_provenance_required=True,
        core_verification_status="HOST_BLOCKED:FAILED",
        core_verification_result_hash="sha256:abc",
        core_verdict=verdict,
        failure_reasons=["local-reason", "AMBIENT_CORE:H1", "AMBIENT_CORE:H2", "AMBIENT_CORE:R1"],
    )
    assert out == expected
    assert out.core_verdict is not verdict and type(out.core_verdict) is dict


def test_core_blocked_receipt_defaults() -> None:
    out = SelfHostedTaskService._core_blocked_receipt(_receipt(failure_reasons=[]), {})
    assert out.core_verification_status == "HOST_BLOCKED:UNAVAILABLE"
    assert out.core_verification_result_hash == ""
    assert out.failure_reasons == [] and out.core_verdict == {}
    out = SelfHostedTaskService._core_blocked_receipt(
        _receipt(), {"core_status": "", "projection_hash": None, "reason_codes": ("X",)}
    )
    assert out.core_verification_status == "HOST_BLOCKED:UNAVAILABLE"
    assert out.core_verification_result_hash == ""
    assert out.failure_reasons == ["local-reason", "AMBIENT_CORE:X"]
    # a Core VERIFIED status never reads as verified on the blocked receipt
    out = SelfHostedTaskService._core_blocked_receipt(_receipt(), {"core_status": "VERIFIED"})
    assert out.core_verification_status == "HOST_BLOCKED:VERIFIED" and out.verified is False


def test_late_replace_in_the_blocked_receipt(monkeypatch) -> None:
    SelfHostedTaskService._core_blocked_receipt(_receipt(), {})
    seen: list[Any] = []
    real = dataclasses.replace

    def late(obj: Any, **changes: Any) -> Any:
        seen.append(sorted(changes))
        return real(obj, **changes)

    monkeypatch.setattr(service_module, "replace", late)
    SelfHostedTaskService._core_blocked_receipt(_receipt(), {})
    assert seen == [
        sorted([
            "verified",
            "candidate_commit_allowed",
            "core_provenance_required",
            "core_verification_status",
            "core_verification_result_hash",
            "core_verdict",
            "failure_reasons",
        ])
    ]


# ---------------------------------------------------------------------------
# _verify_ambient_core_candidate


class _Verify:
    """Stubs every ambient-Core helper on the facade and records the calls."""

    def __init__(self, service: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self.service, self.log = service, []
        self.card_error: Optional[str] = None
        self.required = True
        self.verdict: dict[str, Any] = {"blocking": False, "host_reason_codes": [], "v": 1}
        self.projection_error: Optional[str] = None
        self.preparation_error: Optional[str] = None
        self.port = _Port(self.log, projection={"raw": "projection"})
        service.ambient_core_port = self.port
        monkeypatch.setattr(service, "_card_evidence_binding_error", self.card_check)
        monkeypatch.setattr(service, "_ambient_core_required", self.required_check)
        monkeypatch.setattr(service_module, "build_core_verdict", self.build)
        monkeypatch.setattr(service_module, "normalize_preparation", self.normalize_preparation)
        monkeypatch.setattr(
            service_module, "normalize_verification_projection", self.normalize_projection
        )
        monkeypatch.setattr(service_module, "projection_hash", self.hash)

    def card_check(self, contract: Any, request: Any) -> Optional[str]:
        self.log.append(("card", contract, request))
        return self.card_error

    def required_check(self, contract: Any, request: Any) -> bool:
        self.log.append(("required", contract, request))
        return self.required

    def build(self, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("build", kwargs))
        if "transport_error" in kwargs:
            return {"blocking": True, "host_reason_codes": [kwargs["transport_error"]]}
        return dict(self.verdict)

    def normalize_preparation(self, value: Any, *, attempt_id: str) -> dict[str, str]:
        self.log.append(("prep", value, attempt_id))
        if self.preparation_error is not None:
            raise RuntimeError(self.preparation_error)
        return {"binding_hash": "BH", "session_id": "SID", "from": "prep"}

    def normalize_projection(self, raw: Any, *, preparation: Any, candidate_state_hash: str) -> Any:
        self.log.append(("projection", raw, preparation, candidate_state_hash))
        if self.projection_error is not None:
            raise RuntimeError(self.projection_error)
        return {
            "core_response": {"hashes": {"change_set_hash": "CS", "evidence_bundle_hash": "EB"}}
        }

    def hash(self, value: Any) -> str:
        self.log.append(("hash", value))
        return "PH"

    def run(self, **extra: Any) -> Any:
        kwargs: dict[str, Any] = {
            "contract": "C",
            "request": {"r": 1},
            "lease": "L",
            "state": {"attempt_id": "A1", "host_preparation": {"p": 1}},
            "candidate": "CAND",
            "verified": _receipt(),
        }
        kwargs.update(extra)
        return self.service._verify_ambient_core_candidate(**kwargs)

    def names(self) -> list[str]:
        return [entry[0] for entry in self.log]


@pytest.fixture
def verify(service, monkeypatch) -> _Verify:
    return _Verify(service, monkeypatch)


def test_verify_success_records_the_core_fields(verify) -> None:
    verified = _receipt(verifier_evidence=(_evidence("pytest"),))
    out = verify.run(verified=verified)
    assert verify.names() == ["card", "required", "prep", "verify", "build", "projection", "hash"]
    assert verify.log[0] == ("card", "C", {"r": 1})
    assert verify.log[2] == ("prep", {"p": 1}, "A1")
    assert verify.log[3] == (
        "verify",
        {
            "preparation": {"binding_hash": "BH", "session_id": "SID", "from": "prep"},
            "contract": "C",
            "request": {"r": 1},
            "lease": "L",
            "state": {"attempt_id": "A1", "host_preparation": {"p": 1}},
            "candidate": "CAND",
            "verifier_evidence": verified.verifier_evidence,
        },
    )
    assert verify.log[4] == ("build", {"contract": "C", "projection": {"raw": "projection"}})
    assert verify.log[5][1:] == (
        {"raw": "projection"},
        {"binding_hash": "BH", "session_id": "SID", "from": "prep"},
        "candidate-state",
    )
    assert out == dataclasses.replace(
        verified,
        core_provenance_required=True,
        core_binding_hash="BH",
        core_mutation_session_id="SID",
        core_verification_status="VERIFIED",
        core_change_set_hash="CS",
        core_evidence_bundle_hash="EB",
        core_verification_result_hash="PH",
        core_verdict={"blocking": False, "host_reason_codes": [], "v": 1},
        candidate_commit_allowed=True,
    )


def test_verify_success_commit_follows_the_local_verdict(verify) -> None:
    out = verify.run(verified=_receipt(verified=False, candidate_commit_allowed=True))
    assert out.candidate_commit_allowed is False and out.core_verification_status == "VERIFIED"


def test_verify_card_error_fails_closed_before_anything_else(verify) -> None:
    verify.card_error = "EXPECTED_EVIDENCE_TASK_CARD_INVALID"
    verify.required = False
    with pytest.raises(
        AmbientCoreVerdictBlocked, match="^EXPECTED_EVIDENCE_TASK_CARD_INVALID$"
    ) as exc:
        verify.run()
    assert verify.names() == ["card", "build"]
    assert verify.log[1] == (
        "build",
        {
            "contract": "C",
            "projection": None,
            "transport_error": "EXPECTED_EVIDENCE_TASK_CARD_INVALID",
        },
    )
    receipt = exc.value.receipt
    assert receipt.verified is False and receipt.candidate_commit_allowed is False
    assert receipt.failure_reasons == [
        "local-reason",
        "AMBIENT_CORE:EXPECTED_EVIDENCE_TASK_CARD_INVALID",
    ]
    assert exc.value.verdict == {
        "blocking": True,
        "host_reason_codes": ["EXPECTED_EVIDENCE_TASK_CARD_INVALID"],
    }


def test_verify_returns_the_receipt_when_core_is_not_required(verify) -> None:
    verify.required = False
    verified = _receipt()
    assert verify.run(verified=verified) is verified
    assert verify.names() == ["card", "required"]


def test_verify_without_a_port_fails_closed(verify) -> None:
    verify.service.ambient_core_port = None
    with pytest.raises(AmbientCoreVerdictBlocked, match="^AMBIENT_CORE_CONTROL_PORT_REQUIRED$"):
        verify.run()
    assert verify.names() == ["card", "required", "build"]


def test_verify_invalid_preparation_fails_closed(verify) -> None:
    verify.preparation_error = "AMBIENT_CORE_INVALID:session_id"
    with pytest.raises(AmbientCoreVerdictBlocked, match="^AMBIENT_CORE_INVALID:session_id$") as exc:
        verify.run(state={"attempt_id": None})
    assert verify.log[2] == ("prep", {}, "")
    assert verify.names() == ["card", "required", "prep", "build"]
    assert isinstance(exc.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (RuntimeError("CORE_DOWN: details: more"), "CORE_TRANSPORT_FAILED:CORE_DOWN"),
        (OSError("  "), "CORE_TRANSPORT_FAILED:OSError"),
        (ValueError(":after"), "CORE_TRANSPORT_FAILED:ValueError"),
        (KeyError("k"), "CORE_TRANSPORT_FAILED:'k'"),
    ],
)
def test_verify_transport_failure_fails_closed(verify, error, code) -> None:
    verify.port.error = error
    with pytest.raises(AmbientCoreVerdictBlocked) as exc:
        verify.run()
    assert str(exc.value) == code and exc.value.__cause__ is error
    assert verify.names() == ["card", "required", "prep", "verify", "build"]
    assert verify.log[-1][1]["transport_error"] == code


def test_verify_blocking_verdict_raises_the_first_host_reason(verify) -> None:
    verify.verdict = {
        "blocking": True,
        "host_reason_codes": ["FIRST", "SECOND"],
        "core_status": "X",
    }
    with pytest.raises(AmbientCoreVerdictBlocked, match="^FIRST$") as exc:
        verify.run()
    assert verify.names() == ["card", "required", "prep", "verify", "build"]
    assert exc.value.verdict == verify.verdict
    assert exc.value.receipt.core_verification_status == "HOST_BLOCKED:X"


def test_verify_projection_mismatch_extends_the_verdict(verify) -> None:
    verify.projection_error = "AMBIENT_CORE_SESSION_MISMATCH"
    verify.verdict = {"blocking": False, "host_reason_codes": ["KEEP"], "coverage_complete": True}
    with pytest.raises(AmbientCoreVerdictBlocked, match="^AMBIENT_CORE_SESSION_MISMATCH$") as exc:
        verify.run()
    assert exc.value.verdict == {
        "blocking": True,
        "coverage_complete": False,
        "host_reason_codes": ["KEEP", "AMBIENT_CORE_SESSION_MISMATCH"],
    }
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert verify.names() == ["card", "required", "prep", "verify", "build", "projection"]


def test_verify_blocked_receipts_come_from_the_instance(verify, monkeypatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        verify.service, "_core_blocked_receipt", lambda v, d: (seen.append(dict(d)), "R")[1]
    )
    verify.card_error = "CARD"
    with pytest.raises(AmbientCoreVerdictBlocked) as exc:
        verify.run()
    assert exc.value.receipt == "R" and seen == [{"blocking": True, "host_reason_codes": ["CARD"]}]


def test_verify_with_the_real_ambient_helpers(service) -> None:
    # no facade stubs: the real normalizers, verdict builder and projection hash
    hashes = {
        "acceptance_contract_hash": PREP["acceptance_contract_hash"],
        "change_set_hash": "sha256:" + "4" * 64,
        "verification_plan_hash": "sha256:" + "5" * 64,
        "evidence_bundle_hash": "sha256:" + "6" * 64,
        "change_manifest_hash": "sha256:" + "7" * 64,
    }
    projection = {
        "session_id": PREP["session_id"],
        "binding_hash": PREP["binding_hash"],
        "candidate_state_hash": "candidate-state",
        "core_response": {
            "schema": CORE_RESPONSE_SCHEMA,
            "verification": {"status": "VERIFIED", "reason_codes": []},
            "hashes": hashes,
        },
    }
    log: list[Any] = []
    service.ambient_core_port = _Port(log, projection=projection)
    out = service._verify_ambient_core_candidate(
        contract=SimpleNamespace(expected_evidence=None),
        request={"core_envelope_required": False},
        lease=None,
        state={"attempt_id": "attempt", "host_preparation": PREP},
        candidate=None,
        verified=_receipt(),
    )
    assert out is not None and log == []  # Core is not required for this request
    out = service._verify_ambient_core_candidate(
        contract=SimpleNamespace(expected_evidence=None),
        request={"core_envelope_required": True},
        lease=None,
        state={"attempt_id": "attempt", "host_preparation": PREP},
        candidate=None,
        verified=_receipt(),
    )
    assert out.core_verification_status == "VERIFIED"
    assert out.core_binding_hash == PREP["binding_hash"]
    assert out.core_change_set_hash == hashes["change_set_hash"]
    assert out.core_evidence_bundle_hash == hashes["evidence_bundle_hash"]
    assert out.core_verification_result_hash.startswith("sha256:")
    assert out.core_verdict is not None and out.core_verdict["blocking"] is False


def test_late_ambient_helpers_in_verify(service, monkeypatch) -> None:
    # each facade helper is re-read after a first call that reached it
    verify = _Verify(service, monkeypatch)
    verify.run()
    builds: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "build_core_verdict",
        lambda **k: (
            builds.append(sorted(k)),
            {"blocking": False, "host_reason_codes": [], "late": 1},
        )[1],
    )
    assert verify.run().core_verdict == {"blocking": False, "host_reason_codes": [], "late": 1}
    monkeypatch.setattr(service_module, "projection_hash", lambda value: "LATE-PH")
    assert verify.run().core_verification_result_hash == "LATE-PH"
    monkeypatch.setattr(
        service_module,
        "normalize_verification_projection",
        lambda raw, **k: {
            "core_response": {"hashes": {"change_set_hash": "L", "evidence_bundle_hash": "E"}}
        },
    )
    assert verify.run().core_change_set_hash == "L"
    monkeypatch.setattr(
        service_module,
        "normalize_preparation",
        lambda value, *, attempt_id: {"binding_hash": "LB", "session_id": "LS"},
    )
    assert verify.run().core_binding_hash == "LB"
    assert builds == [["contract", "projection"]] * 4

    class LateBlocked(AmbientCoreVerdictBlocked):
        pass

    verify.card_error = "CARD"
    with pytest.raises(AmbientCoreVerdictBlocked) as exc:
        verify.run()
    assert type(exc.value) is AmbientCoreVerdictBlocked
    monkeypatch.setattr(service_module, "AmbientCoreVerdictBlocked", LateBlocked)
    with pytest.raises(LateBlocked):
        verify.run()
    verify.card_error = None
    real = dataclasses.replace
    replaced: list[Any] = []
    monkeypatch.setattr(
        service_module, "replace", lambda obj, **k: (replaced.append(sorted(k)), real(obj, **k))[1]
    )
    verify.run()
    assert replaced == [
        sorted([
            "core_provenance_required",
            "core_binding_hash",
            "core_mutation_session_id",
            "core_verification_status",
            "core_change_set_hash",
            "core_evidence_bundle_hash",
            "core_verification_result_hash",
            "core_verdict",
            "candidate_commit_allowed",
        ])
    ]


# ---------------------------------------------------------------------------
# _record_track1_verified_outcome


class _Track1:
    """Records the research-evidence collaborators and the ``git diff`` call."""

    def __init__(self, service: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.service, self.log = service, []
        self.configured = True
        self.eligible = 1
        self.row_refs: list[Any] = ["row-ref-1"]
        self.diff = SimpleNamespace(returncode=0, stdout="DIFF")
        self.refresh: dict[str, Any] = {
            "readiness": {"disposition": "READY"},
            "checkpoint": {"status": "CP", "checkpoint_sha256": "CPSHA"},
        }
        self.tmp_path = tmp_path
        monkeypatch.setattr(
            evidence_root_module, "explicit_research_evidence_root_configured", self.is_configured
        )
        monkeypatch.setattr(collector_module, "collect_candidate_group", self.collect)
        monkeypatch.setattr(continuity_module, "bind_trajectory_outcome", self.bind)
        monkeypatch.setattr(continuity_module, "refresh_registered_experiment", self.refresh_call)
        monkeypatch.setattr(continuity_module, "resolve_research_evidence_root", self.resolve_root)
        monkeypatch.setattr(continuity_module, "self_hosted_worker_trajectory_id", self.trajectory)
        monkeypatch.setattr(
            service_module, "subprocess", SimpleNamespace(run=self.run_git, real=subprocess)
        )

    def is_configured(self) -> bool:
        self.log.append(("configured",))
        return self.configured

    def resolve_root(self, repo_root: Any) -> Path:
        self.log.append(("root", repo_root))
        return self.tmp_path / "evidence"

    def trajectory(self, **kwargs: Any) -> str:
        self.log.append(("trajectory", kwargs))
        return "TRAJ"

    def run_git(self, argv: Any, **kwargs: Any) -> Any:
        self.log.append(("git", argv, kwargs))
        return self.diff

    def collect(self, **kwargs: Any) -> Any:
        self.log.append(("collect", kwargs))
        return SimpleNamespace(
            status="COLLECTED",
            eligible_count=self.eligible,
            group_sha256="GROUP",
            row_refs=list(self.row_refs),
        )

    def bind(self, **kwargs: Any) -> None:
        self.log.append(("bind", kwargs))

    def refresh_call(self, **kwargs: Any) -> Any:
        self.log.append(("refresh", kwargs))
        return self.refresh

    def names(self) -> list[str]:
        return [entry[0] for entry in self.log]

    def entry(self, name: str) -> Any:
        (found,) = [entry for entry in self.log if entry[0] == name]
        return found

    def run(self, **extra: Any) -> Any:
        kwargs: dict[str, Any] = {
            "contract": _Track1Contract(),
            "lease": SimpleNamespace(target_worktree=self.tmp_path / "target"),
            "state": {"attempt_id": "A1", "selected_model": "model-x"},
            "candidate": SimpleNamespace(
                tracked_diff_sha256="TDS",
                untracked_content_hashes={"u.py": "UH"},
                changed_files=("a.py",),
                untracked_files=["u.py"],
                deleted_files=None,
                candidate_state_hash="CSH",
            ),
            "verified": _receipt(
                verifier_evidence=(_evidence("pytest a"), _evidence("pytest b", "FAILED", 0))
            ),
            "execution": SimpleNamespace(provider="agy"),
        }
        kwargs.update(extra)
        return self.service._record_track1_verified_outcome(**kwargs)


class _Track1Contract:
    task_id = "task-1"
    controller_repo_root = "/controller"
    target_repo_root = "/target"
    target_base_revision = "BASE"
    controller_revision = "CTRL"
    verifier_commands = ("pytest a", "pytest b")

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {"task_id": self.task_id, "mode": mode}


@pytest.fixture
def track1(service, monkeypatch, tmp_path) -> _Track1:
    return _Track1(service, monkeypatch, tmp_path)


def _payload(**extra: Any) -> str:
    payload: dict[str, Any] = {
        "schema": "nexus.self_hosted_candidate_payload.v1",
        "tracked_diff": "DIFF",
        "tracked_diff_sha256": "TDS",
        "untracked_content_hashes": {"u.py": "UH"},
        "changed_files": ["a.py"],
        "untracked_files": ["u.py"],
        "deleted_files": [],
        "candidate_state_hash": "CSH",
    }
    payload.update(extra)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _gate(command: str, passed: bool) -> dict[str, Any]:
    return {"cmd_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(), "passed": passed}


def test_track1_skips_without_a_configured_evidence_root(track1) -> None:
    track1.configured = False
    assert track1.run() == {"status": "SKIPPED", "reason": "shared_evidence_root_not_configured"}
    assert track1.names() == ["configured"]


@pytest.mark.parametrize(
    ("provider", "state"),
    [
        ("", {"attempt_id": "A1"}),
        (None, {"attempt_id": "A1"}),
        ("agy", {}),
        ("agy", {"attempt_id": ""}),
    ],
)
def test_track1_skips_without_a_trajectory_identity(track1, provider, state) -> None:
    out = track1.run(execution=SimpleNamespace(provider=provider), state=state)
    assert out == {"status": "SKIPPED", "reason": "trajectory_identity_missing"}
    assert track1.names() == ["configured"]


def test_track1_execution_without_a_provider_attribute(track1) -> None:
    out = track1.run(execution=object())
    assert out == {"status": "SKIPPED", "reason": "trajectory_identity_missing"}


def test_track1_binds_a_strong_outcome(track1) -> None:
    out = track1.run()
    assert track1.names() == [
        "configured",
        "root",
        "trajectory",
        "git",
        "collect",
        "bind",
        "refresh",
    ]
    assert track1.entry("root") == ("root", "/controller")
    assert track1.entry("trajectory") == (
        "trajectory",
        {"task_id": "task-1", "attempt_id": "A1", "provider": "agy"},
    )
    assert track1.entry("git") == (
        "git",
        ["git", "diff", "--binary", "--no-ext-diff", "BASE", "--"],
        {
            "cwd": str(track1.tmp_path / "target"),
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 30,
        },
    )
    collect = track1.entry("collect")[1]
    assert collect == {
        "repo_root": "/controller",
        "task_id": "task-1",
        "attempt_id": "A1",
        "collector_source": "self_hosted_worker",
        "source_revision": "BASE",
        "contract_identity": {"task_id": "task-1", "mode": "json"},
        "verifier_identity": {"kind": "candidate_verifier", "commands": ["pytest a", "pytest b"]},
        "candidates": [
            {
                "candidate_id": "task-1#self-hosted-A1",
                "candidate_model": "model-x",
                "candidate_source": "agy",
                "candidate_payload": _payload(),
                "candidate_state_hash": "CSH",
                "verifier_status": "PASS",
                # the gates (one failed) disagree with the verified receipt
                "label_quality": "TRACE_ONLY",
                "verifier_evidence": {
                    "gate_results": [_gate("pytest a", True), _gate("pytest b", False)]
                },
                "failure_reason_codes": ["local-reason"],
                "selected": True,
            }
        ],
        "winner_id": "task-1#self-hosted-A1",
    }
    assert track1.entry("bind") == (
        "bind",
        {
            "evidence_root": track1.tmp_path / "evidence",
            "trajectory_id": "TRAJ",
            "candidate_evidence_ref": "row-ref-1",
        },
    )
    assert track1.entry("refresh") == (
        "refresh",
        {"repo_root": REPO_ROOT, "candidate_evidence_root": track1.tmp_path / "evidence"},
    )
    assert out == {
        "status": "COLLECTED",
        "eligible_count": 1,
        "trajectory_id": "TRAJ",
        "group_sha256": "GROUP",
        "outcome_bound": True,
        "readiness": "READY",
        "checkpoint_status": "CP",
        "checkpoint_sha256": "CPSHA",
    }


def test_track1_refresh_repo_root_is_the_facade_files_repository(track1) -> None:
    # the repository root comes from the facade module's own file, three levels up
    track1.run()
    repo_root = track1.entry("refresh")[1]["repo_root"]
    assert repo_root == Path(service_module.__file__).resolve().parents[2]
    assert (repo_root / "nexus" / "orchestrator" / "self_hosted_task_service.py").is_file()
    assert (repo_root / "pyproject.toml").is_file()


def test_late_module_file_in_track1(track1, monkeypatch, tmp_path) -> None:
    track1.run()
    fake = tmp_path / "elsewhere" / "nexus" / "orchestrator" / "self_hosted_task_service.py"
    monkeypatch.setattr(service_module, "__file__", str(fake))
    track1.log.clear()
    track1.run()
    assert track1.entry("refresh")[1]["repo_root"] == (tmp_path / "elsewhere").resolve()


def test_track1_mechanical_gate_and_failed_candidate(track1) -> None:
    verified = _receipt(
        verified=False,
        failure_reasons=["F1"],
        verifier_evidence=(
            _evidence("pytest a", "COMPLETED", 1),
            _evidence("pytest b", "TIMEOUT", 0),
        ),
    )
    out = track1.run(verified=verified, state={"attempt_id": "A1"})
    candidate = track1.entry("collect")[1]["candidates"][0]
    assert candidate["verifier_status"] == "FAIL"
    # every gate failed and the receipt is not verified: the gates are mechanical truth
    assert candidate["label_quality"] == "MECHANICAL_GATE"
    assert candidate["selected"] is False and candidate["failure_reason_codes"] == ["F1"]
    assert candidate["candidate_model"] == ""
    assert track1.entry("collect")[1]["winner_id"] == ""
    assert out["outcome_bound"] is True


def test_track1_all_gates_passing_on_a_verified_receipt_is_mechanical(track1) -> None:
    verified = _receipt(verifier_evidence=(_evidence("pytest a"),))
    track1.run(verified=verified)
    assert track1.entry("collect")[1]["candidates"][0]["label_quality"] == "MECHANICAL_GATE"


def test_track1_without_gates_is_trace_only(track1) -> None:
    track1.run(verified=_receipt(verifier_evidence=()))
    candidate = track1.entry("collect")[1]["candidates"][0]
    assert candidate["label_quality"] == "TRACE_ONLY"
    assert candidate["verifier_evidence"] == {"gate_results": []}


def test_track1_model_falls_back_to_the_dispatch_envelope(track1) -> None:
    track1.run(state={"attempt_id": "A1", "canonical_dispatch_envelope": {"model": "env-model"}})
    assert track1.entry("collect")[1]["candidates"][0]["candidate_model"] == "env-model"
    track1.log.clear()
    track1.run(state={"attempt_id": "A1", "canonical_dispatch_envelope": ["not", "a", "mapping"]})
    assert track1.entry("collect")[1]["candidates"][0]["candidate_model"] == ""


def test_track1_revision_and_root_fallbacks(track1) -> None:
    contract = _Track1Contract()
    contract.controller_repo_root = ""
    contract.target_base_revision = ""
    track1.run(contract=contract)
    assert track1.entry("root") == ("root", "/target")
    assert track1.entry("git")[1][4] == "CTRL"
    assert track1.entry("collect")[1]["source_revision"] == "CTRL"


@pytest.mark.parametrize(("code", "diff"), [(0, "DIFF"), (1, "DIFF"), (2, ""), (128, "")])
def test_track1_diff_exit_codes(track1, code, diff) -> None:
    track1.diff = SimpleNamespace(returncode=code, stdout="DIFF")
    track1.run()
    payload = json.loads(track1.entry("collect")[1]["candidates"][0]["candidate_payload"])
    assert payload["tracked_diff"] == diff


def test_track1_without_strong_truth_does_not_bind(track1) -> None:
    track1.eligible = 0
    out = track1.run()
    assert "bind" not in track1.names() and "refresh" not in track1.names()
    assert out == {
        "status": "COLLECTED",
        "eligible_count": 0,
        "trajectory_id": "TRAJ",
        "group_sha256": "GROUP",
        "outcome_bound": False,
        "reason": "strong_verifier_truth_unavailable",
    }
    track1.log.clear()
    track1.eligible, track1.row_refs = 1, []
    assert track1.run()["reason"] == "strong_verifier_truth_unavailable"


def test_track1_refresh_without_readiness_or_checkpoint(track1) -> None:
    track1.refresh = {}
    out = track1.run()
    assert out["readiness"] is None and out["checkpoint_status"] is None
    assert out["checkpoint_sha256"] is None


@pytest.mark.parametrize("stage", ["root", "trajectory", "git", "collect", "bind", "refresh"])
def test_track1_failures_are_bounded_metadata(track1, stage, monkeypatch) -> None:
    class Boom(Exception):
        pass

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise Boom("secret detail")

    target = {
        "root": (continuity_module, "resolve_research_evidence_root"),
        "trajectory": (continuity_module, "self_hosted_worker_trajectory_id"),
        "collect": (collector_module, "collect_candidate_group"),
        "bind": (continuity_module, "bind_trajectory_outcome"),
        "refresh": (continuity_module, "refresh_registered_experiment"),
    }
    if stage == "git":
        monkeypatch.setattr(service_module, "subprocess", SimpleNamespace(run=fail))
    else:
        monkeypatch.setattr(*target[stage], fail)
    assert track1.run() == {"status": "ERROR", "error_type": "Boom"}


def test_track1_configuration_check_failure_propagates(track1, monkeypatch) -> None:
    monkeypatch.setattr(
        evidence_root_module,
        "explicit_research_evidence_root_configured",
        lambda: (_ for _ in ()).throw(LookupError("cfg")),
    )
    with pytest.raises(LookupError, match="^cfg$"):
        track1.run()


def test_late_subprocess_in_track1(track1, monkeypatch) -> None:
    track1.run()
    assert track1.entry("collect")[1]["candidates"][0]["candidate_payload"] == _payload()
    # subprocess is re-read from the facade
    calls: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "subprocess",
        SimpleNamespace(
            run=lambda argv, **k: (calls.append(argv), SimpleNamespace(returncode=0, stdout="L"))[1]
        ),
    )
    track1.log.clear()
    track1.run()
    assert calls == [["git", "diff", "--binary", "--no-ext-diff", "BASE", "--"]]


def test_track1_with_the_real_git_diff(service, tmp_path, monkeypatch) -> None:
    # the real facade subprocess against a throwaway repository
    repo = tmp_path / "repo"
    repo.mkdir()
    git = [
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True)
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run([*git, "add", "a.txt"], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-qm", "base"], cwd=repo, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    track1 = _Track1(service, monkeypatch, tmp_path)
    monkeypatch.setattr(service_module, "subprocess", subprocess)
    contract = _Track1Contract()
    contract.target_base_revision = base
    track1.run(contract=contract, lease=SimpleNamespace(target_worktree=repo))
    payload = json.loads(track1.entry("collect")[1]["candidates"][0]["candidate_payload"])
    assert "-one\n+two\n" in payload["tracked_diff"]


# ---------------------------------------------------------------------------
# self dispatch: instance, class and subclass patches


def test_class_patch_of_reached_members_and_undo(tmp_path) -> None:
    hits: list[str] = []
    real = inspect.getattr_static(SelfHostedTaskService, "_ambient_core_required")
    mp = pytest.MonkeyPatch()
    mp.setattr(
        SelfHostedTaskService,
        "_ambient_core_required",
        lambda self, c, r: (hits.append("required"), True)[1],
    )
    svc = SelfHostedTaskService(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_CONTROL_PORT_REQUIRED$"):
        svc._prepare_ambient_core("C", {}, "L", {}, task_id="t", attempt_id="a")
    mp.undo()
    assert hits == ["required"]
    assert inspect.getattr_static(SelfHostedTaskService, "_ambient_core_required") is real


def test_subclass_overrides_are_dispatched_through_self(tmp_path) -> None:
    class Sub(SelfHostedTaskService):
        def _ambient_core_required(self, contract: Any, request: Any) -> bool:
            return True

        @staticmethod
        def _card_evidence_binding_error(contract: Any, request: Any) -> Optional[str]:
            return "SUB_CARD"

        @staticmethod
        def _core_blocked_receipt(verified: Any, verdict: Any) -> Any:
            return ("sub-receipt", dict(verdict)["host_reason_codes"])

    sub = Sub(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    with pytest.raises(RuntimeError, match="^AMBIENT_CORE_CONTROL_PORT_REQUIRED$"):
        sub._revalidate_ambient_core(
            PREP, "C", {}, "L", {}, task_id="t", attempt_id="attempt", active_provider="codex"
        )
    with pytest.raises(AmbientCoreVerdictBlocked, match="^SUB_CARD$") as exc:
        sub._verify_ambient_core_candidate(
            contract=SimpleNamespace(expected_evidence=None),
            request={},
            lease=None,
            state={},
            candidate=None,
            verified=_receipt(),
        )
    assert exc.value.receipt == ("sub-receipt", ["SUB_CARD"])
    assert runtime_coordination_bridge._Contract(sub).host_preparation_required("C", {}) is True


def test_subclass_override_of_track1_is_what_the_service_exposes(tmp_path) -> None:
    class Sub(SelfHostedTaskService):
        def _record_track1_verified_outcome(self, **kwargs: Any) -> dict[str, Any]:
            return {"status": "SUB"}

    sub = Sub(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    assert cast(Any, sub)._record_track1_verified_outcome(contract=None) == {"status": "SUB"}
