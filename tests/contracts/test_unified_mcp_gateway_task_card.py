"""Characterization tests for the gateway's Task Card create/commit (big-file split G9a).

These pin ``_task_card_create``, ``_task_card_expected_evidence``,
``_task_card_issue_promises``, ``_task_card_commit`` and the shared ``_safe_slug`` /
``_exact_hash`` helpers of ``UnifiedMCPGateway`` before they move out of the facade class
into a mixin.

The Controller and path-scope collaborators (``_require_bound_controller``, ``_text``,
``_safe_relative_path``, ``protected_path_reason``, ``bootstrap_agent_authority`` and
``_git``) are replaced on the gateway facade module with recording probes, and so are the
process effects (``subprocess.run`` and ``os.replace``). The tests therefore pin both the
order in which each operation calls them, including every denial path, and that facade
patches keep reaching the moved code. The owner-authority helpers (``_owner_effect_key``,
``_require_owner_effect_authority``) and the shared helpers are probed on the instance.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from nexus.orchestrator import bootstrap_agent_authority as real_bootstrap
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.task_contract import (
    TASK_CARD_EXPECTED_EVIDENCE_FENCE,
    TASK_CARD_ISSUE_PROMISES_FENCE,
    ExpectedEvidenceUniverse,
    IssuePromiseBinding,
    expected_evidence_universe_identity,
)
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway

FAKE_HEAD = "a" * 40
AUTHORITY_ARGS = {"authority_goal_id": "goal-g9", "authority_coordination_scope_id": "thread-g9"}
OWNER_GRANT = {
    "schema": "nexus.standing_grant_effect_authorization.v1",
    "authorization_hash": "f" * 64,
}
AGENT_AUTHORITY = {"schema": real_bootstrap.AUTHORIZATION_SCHEMA, "record_hash": "e" * 64}
UNIVERSE = {
    "universe_generation": 2,
    "subjects": [
        {
            "logical_subject_id": "git diff --check",
            "evidence_kind": "verifier-run",
            "requirement_mode": "REQUIRED",
            "applicability": "APPLICABLE",
        }
    ],
}
_REAL_RUN = subprocess.run
_REAL_REPLACE = os.replace


def _create_args(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "objective": "Change README.md in one bounded step.",
        "allowed_files": ["README.md", " ", "docs/notes.md"],
        "verifier_commands": ["git diff --check", "  "],
    }
    arguments.update(overrides)
    return arguments


@pytest.fixture
def events() -> list[tuple]:
    return []


@pytest.fixture
def probes(monkeypatch, events, tmp_path):
    """Replace the Controller/path/evidence collaborators and process effects on the facade."""
    root = (tmp_path / "controller").resolve()
    root.mkdir()
    ctx = SimpleNamespace(
        root=root,
        bound_error=None,
        fake_git=True,
        git_hook=None,
        run_hook=None,
        in_git=False,
    )
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", root)
    real_text = gateway_module._text
    real_safe_relative_path = gateway_module._safe_relative_path
    real_protected = gateway_module.protected_path_reason
    real_git = gateway_module._git

    def require_bound_controller(expected_head=None):
        events.append(("_require_bound_controller", expected_head))
        if ctx.bound_error is not None:
            raise ctx.bound_error

    def text(value, field, *, max_length=4096):
        events.append(("_text", field))
        return real_text(value, field, max_length=max_length)

    def safe_relative_path(value, field="path"):
        events.append(("_safe_relative_path", value))
        return real_safe_relative_path(value, field)

    def protected(path):
        events.append(("protected_path_reason", path))
        return real_protected(path)

    def git(*args, **kwargs):
        events.append(("_git",) + args)
        if ctx.git_hook is not None:
            hooked = ctx.git_hook(args)
            if hooked is not None:
                return hooked
        if ctx.fake_git:
            return FAKE_HEAD + "\n"
        ctx.in_git = True
        try:
            return real_git(*args, **kwargs)
        finally:
            ctx.in_git = False

    def run(argv, *args, **kwargs):
        if not ctx.in_git:
            events.append(("subprocess.run",) + tuple(str(item) for item in argv[1:3]))
            if ctx.run_hook is not None:
                hooked = ctx.run_hook(argv)
                if hooked is not None:
                    return hooked
        return _REAL_RUN(argv, *args, **kwargs)

    def replace(source, target):
        events.append(("os.replace", Path(target).name))
        return _REAL_REPLACE(source, target)

    def authority_basis(authorization):
        events.append(("authority_basis",))
        return real_bootstrap.authority_basis(authorization)

    monkeypatch.setattr(gateway_module, "_require_bound_controller", require_bound_controller)
    monkeypatch.setattr(gateway_module, "_text", text)
    monkeypatch.setattr(gateway_module, "_safe_relative_path", safe_relative_path)
    monkeypatch.setattr(gateway_module, "protected_path_reason", protected)
    monkeypatch.setattr(gateway_module, "_git", git)
    monkeypatch.setattr(gateway_module.subprocess, "run", run)
    monkeypatch.setattr(gateway_module.os, "replace", replace)
    monkeypatch.setattr(
        gateway_module,
        "bootstrap_agent_authority",
        SimpleNamespace(
            authority_basis=authority_basis, BASIS_OWNER_GRANT=real_bootstrap.BASIS_OWNER_GRANT
        ),
    )
    return ctx


def _gateway(events: list[tuple], *, authority: Any = None, authority_error: Any = None):
    gateway = UnifiedMCPGateway(service=MagicMock())
    real_key = gateway._owner_effect_key
    real_slug = gateway._safe_slug
    real_exact = gateway._exact_hash
    real_evidence = gateway._task_card_expected_evidence
    real_promises = gateway._task_card_issue_promises

    def owner_effect_key(arguments):
        events.append(("self._owner_effect_key",))
        return real_key(arguments)

    def require_owner_effect_authority(action, effect, *, key):
        events.append((
            "self._require_owner_effect_authority",
            action.value,
            key.goal_id,
            key.coordinator_thread,
        ))
        vars(gateway)["owner_effect"] = dict(effect)
        if authority_error is not None:
            raise authority_error
        return dict(OWNER_GRANT if authority is None else authority)

    def safe_slug(value, field, *, max_length=80):
        events.append(("self._safe_slug", field))
        return real_slug(value, field, max_length=max_length)

    def exact_hash(value, field, length):
        events.append(("self._exact_hash", field, length))
        return real_exact(value, field, length)

    def expected_evidence(arguments):
        events.append(("self._task_card_expected_evidence",))
        return real_evidence(arguments)

    def issue_promises(arguments, universe):
        events.append(("self._task_card_issue_promises",))
        return real_promises(arguments, universe)

    gateway._owner_effect_key = owner_effect_key  # type: ignore[method-assign]
    gateway._require_owner_effect_authority = require_owner_effect_authority  # type: ignore[method-assign]
    gateway._safe_slug = safe_slug  # type: ignore[method-assign]
    gateway._exact_hash = exact_hash  # type: ignore[method-assign]
    gateway._task_card_expected_evidence = expected_evidence  # type: ignore[method-assign]
    gateway._task_card_issue_promises = issue_promises  # type: ignore[method-assign]
    return gateway


def _names(events: list[tuple]) -> list[str]:
    return [event[0] for event in events]


EFFECT_EVENTS = {"os.replace", "_git:add", "_git:commit"}


def _effects(events: list[tuple]) -> list[str]:
    out = []
    for event in events:
        name = event[0] if event[0] != "_git" else f"_git:{event[1]}"
        if name in EFFECT_EVENTS:
            out.append(name)
    return out


def _tree(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root)) for path in root.rglob("*") if ".git" not in path.parts
    )


# --- _safe_slug / _exact_hash ------------------------------------------------------------


@pytest.mark.parametrize("value", ["a", "A9", "a.b_c-d", "x" * 80])
def test_safe_slug_accepts_bounded_slugs(value) -> None:
    assert UnifiedMCPGateway._safe_slug(value, "campaign_id") == value


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "^campaign_id is required$"),
        (None, "^campaign_id is required$"),
        ("x" * 81, "^campaign_id exceeds 80 characters$"),
        ("-lead", "^campaign_id must be a stable bounded slug$"),
        ("a/b", "^campaign_id must be a stable bounded slug$"),
        ("a b", "^campaign_id must be a stable bounded slug$"),
        (".hidden", "^campaign_id must be a stable bounded slug$"),
    ],
)
def test_safe_slug_rejects(value, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        UnifiedMCPGateway._safe_slug(value, "campaign_id")


def test_safe_slug_max_length_is_the_regex_bound_too() -> None:
    assert UnifiedMCPGateway._safe_slug(" ab ", "f", max_length=2) == "ab"
    with pytest.raises(GatewayInputError, match="^f exceeds 2 characters$"):
        UnifiedMCPGateway._safe_slug("abc", "f", max_length=2)


def test_safe_slug_and_exact_hash_read_text_through_the_facade(monkeypatch) -> None:
    seen = []
    real = gateway_module._text

    def text(value, field, *, max_length=4096):
        seen.append((field, max_length))
        return real(value, field, max_length=max_length)

    monkeypatch.setattr(gateway_module, "_text", text)
    UnifiedMCPGateway._safe_slug("ok", "slug", max_length=10)
    UnifiedMCPGateway._exact_hash("a" * 40, "sha", 40)
    assert seen == [("slug", 10), ("sha", 4096)]


@pytest.mark.parametrize(("value", "length"), [("a" * 40, 40), (" " + "0" * 64 + " ", 64)])
def test_exact_hash_accepts_lowercase_hex_of_the_exact_length(value, length) -> None:
    assert UnifiedMCPGateway._exact_hash(value, "h", length) == value.strip()


@pytest.mark.parametrize(
    ("value", "length"),
    [("A" * 40, 40), ("a" * 39, 40), ("a" * 41, 40), ("g" * 40, 40), ("a" * 40, 64)],
)
def test_exact_hash_rejects(value, length) -> None:
    with pytest.raises(GatewayInputError, match="^h must be an exact lowercase Git hash$"):
        UnifiedMCPGateway._exact_hash(value, "h", length)


def test_exact_hash_requires_a_value() -> None:
    with pytest.raises(GatewayInputError, match="^h is required$"):
        UnifiedMCPGateway._exact_hash(None, "h", 40)


# --- _task_card_expected_evidence ---------------------------------------------------------


def test_expected_evidence_absent_is_none() -> None:
    assert UnifiedMCPGateway._task_card_expected_evidence({}) is None
    assert UnifiedMCPGateway._task_card_expected_evidence({"expected_evidence": None}) is None


def test_expected_evidence_is_validated_with_the_reader_model() -> None:
    universe = UnifiedMCPGateway._task_card_expected_evidence({"expected_evidence": UNIVERSE})
    assert isinstance(universe, ExpectedEvidenceUniverse)
    assert universe == ExpectedEvidenceUniverse.model_validate(UNIVERSE)


@pytest.mark.parametrize("raw", [[], "x", 3, False])
def test_expected_evidence_must_be_an_object(raw) -> None:
    with pytest.raises(
        GatewayInputError,
        match="^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:expected_evidence must be an object$",
    ):
        UnifiedMCPGateway._task_card_expected_evidence({"expected_evidence": raw})


def test_expected_evidence_model_errors_are_flattened_and_bounded() -> None:
    with pytest.raises(GatewayInputError) as caught:
        UnifiedMCPGateway._task_card_expected_evidence({
            "expected_evidence": {"universe_generation": "x" * 2000, "subjects": "nope"}
        })
    message = str(caught.value)
    assert message.startswith("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:")
    reason = message.split(":", 1)[1]
    assert "\n" not in reason and len(reason) <= 500


# --- _task_card_create --------------------------------------------------------------------


def test_create_call_order_effect_and_payload(events, probes) -> None:
    gateway = _gateway(events)
    payload = gateway._call_tool("nexus_task_card_create", _create_args())
    HASH_OBJECT = next(event for event in events if event[:2] == ("subprocess.run", "hash-object"))
    assert events == [
        ("_require_bound_controller", None),
        ("self._owner_effect_key",),
        ("_text", "authority_goal_id"),
        ("_text", "authority_coordination_scope_id"),
        ("self._safe_slug", "campaign_id"),
        ("_text", "campaign_id"),
        ("self._safe_slug", "task_id"),
        ("_text", "task_id"),
        ("_text", "objective"),
        ("_safe_relative_path", "README.md"),
        ("_text", "allowed_files"),
        ("protected_path_reason", "README.md"),
        ("protected_path_reason", "README.md"),
        ("_safe_relative_path", "docs/notes.md"),
        ("_text", "allowed_files"),
        ("protected_path_reason", "docs/notes.md"),
        ("protected_path_reason", "docs/notes.md"),
        ("self._task_card_expected_evidence",),
        ("self._task_card_issue_promises",),
        ("_git", "rev-parse", "HEAD"),
        ("self._exact_hash", "expected_head", 40),
        ("_text", "expected_head"),
        ("self._require_owner_effect_authority", "TASK_CARD_CREATE", "goal-g9", "thread-g9"),
        HASH_OBJECT,
        ("os.replace", "g9-campaign"),
        ("authority_basis",),
        ("authority_basis",),
    ]
    assert Path(HASH_OBJECT[2]).name == "00-g9-card.md"
    assert Path(HASH_OBJECT[2]).parent.name.startswith(".g9-campaign.create-")
    objective = "Change README.md in one bounded step."
    assert vars(gateway)["owner_effect"] == {
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "expected_head": FAKE_HEAD,
        "allowed_files": ["README.md", "docs/notes.md"],
        "verifier_commands": ["git diff --check"],
        "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
    }
    root = probes.root
    card = (root / "tasks/g9-campaign/00-g9-card.md").read_bytes()
    index = (root / "tasks/g9-campaign/INDEX.md").read_bytes()
    blob = (
        _REAL_RUN(["git", "hash-object", "--stdin"], input=card, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    assert _tree(root) == [
        "tasks",
        "tasks/g9-campaign",
        "tasks/g9-campaign/00-g9-card.md",
        "tasks/g9-campaign/INDEX.md",
    ]
    assert payload == {
        "schema": "nexus.task_card_create.v1",
        "status": "CREATED_PENDING_COMMIT",
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "index_path": "tasks/g9-campaign/INDEX.md",
        "card_path": "tasks/g9-campaign/00-g9-card.md",
        "card_hash": hashlib.sha256(card).hexdigest(),
        "index_hash": hashlib.sha256(index).hexdigest(),
        "git_blob_sha": blob,
        "exact_card_diff": payload["exact_card_diff"],
        "exact_index_diff": payload["exact_index_diff"],
        "successor_execution": "NOT_STARTED",
        "authority_basis": real_bootstrap.BASIS_OWNER_GRANT,
        "owner_confirmation": True,
        "owner_authority": OWNER_GRANT,
    }
    assert payload["exact_card_diff"].startswith(
        "--- /dev/null\n+++ tasks/g9-campaign/00-g9-card.md\n"
    )
    assert payload["exact_index_diff"].startswith("--- /dev/null\n+++ tasks/g9-campaign/INDEX.md\n")
    assert (
        "".join(line[1:] for line in payload["exact_card_diff"].splitlines(True)[3:])
        == card.decode()
    )
    text = card.decode()
    assert text.startswith(
        "# Task Card: g9-card\n\nartifact_authority: current\ntask_id: `g9-card`\n"
    )
    assert "- `README.md`\n- `docs/notes.md`\n" in text
    assert "```bash\ngit diff --check\n```" in text
    assert TASK_CARD_EXPECTED_EVIDENCE_FENCE not in text
    assert index.decode().startswith("# Campaign Index: g9-campaign\n")
    assert "| 0 | `g9-card` | `00-g9-card.md` | ACTIVE | Owner confirmation |" in index.decode()


def test_create_binds_the_declared_universe_into_effect_and_card(events, probes) -> None:
    gateway = _gateway(events)
    payload = gateway._task_card_create(_create_args(expected_evidence=UNIVERSE))
    universe = ExpectedEvidenceUniverse.model_validate(UNIVERSE)
    assert vars(gateway)["owner_effect"]["expected_evidence_identity"] == universe.universe_identity
    card = (probes.root / payload["card_path"]).read_text(encoding="utf-8")
    assert (
        "## Expected evidence\n\n```"
        + TASK_CARD_EXPECTED_EVIDENCE_FENCE
        + "\n"
        + universe.canonical_json()
        + "\n```\n"
        in card
    )


@pytest.mark.parametrize("value", [None, False, "true", 1, "yes"])
def test_create_requires_literal_true_owner_confirmation_before_anything(
    events, probes, value
) -> None:
    arguments = _create_args(owner_confirmation=value)
    if value is None:
        arguments.pop("owner_confirmation")
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_REQUIRED$"):
        _gateway(events)._task_card_create(arguments)
    assert events == []
    assert _tree(probes.root) == []


def test_create_refuses_an_unbound_controller_first(events, probes) -> None:
    probes.bound_error = GatewayInputError("CONTROLLER_BINDING_INVALID:probe")
    with pytest.raises(GatewayInputError, match="^CONTROLLER_BINDING_INVALID:probe$"):
        _gateway(events)._task_card_create(_create_args())
    assert events == [("_require_bound_controller", None)]


@pytest.mark.parametrize(
    ("overrides", "message", "last"),
    [
        (
            {"authority_goal_id": ""},
            "^OWNER_AUTHORITY_KEY_REQUIRED:authority_goal_id is required$",
            ("_text", "authority_goal_id"),
        ),
        (
            {"authority_coordination_scope_id": "x" * 129},
            "^OWNER_AUTHORITY_KEY_REQUIRED:authority_coordination_scope_id exceeds 128 characters$",
            ("_text", "authority_coordination_scope_id"),
        ),
        (
            {"campaign_id": "bad slug"},
            "^campaign_id must be a stable bounded slug$",
            ("_text", "campaign_id"),
        ),
        ({"task_id": "../x"}, "^task_id must be a stable bounded slug$", ("_text", "task_id")),
        ({"objective": ""}, "^objective is required$", ("_text", "objective")),
        ({"objective": "x" * 4001}, "^objective exceeds 4000 characters$", ("_text", "objective")),
        (
            {"allowed_files": []},
            "^allowed_files must contain 1-10 bounded paths$",
            ("_text", "objective"),
        ),
        (
            {"allowed_files": [" ", ""]},
            "^allowed_files must contain 1-10 bounded paths$",
            ("_text", "objective"),
        ),
        (
            {"allowed_files": None},
            "^allowed_files must contain 1-10 bounded paths$",
            ("_text", "objective"),
        ),
        (
            {"allowed_files": [f"f{i}.md" for i in range(11)]},
            "^allowed_files must contain 1-10 bounded paths$",
            ("_text", "objective"),
        ),
        (
            {"allowed_files": ["/etc/passwd"]},
            "^allowed_files must be a bounded relative path$",
            ("_text", "allowed_files"),
        ),
        (
            {"allowed_files": ["a/../b.md"]},
            "^allowed_files must be a bounded relative path$",
            ("_text", "allowed_files"),
        ),
        (
            {"allowed_files": [".git/config"]},
            "^allowed_files cannot access .git$",
            ("_text", "allowed_files"),
        ),
        (
            {"allowed_files": ["README.md", "AGENTS.md"]},
            "^TASK_CARD_CREATE_PROTECTED_PATH:AUTHORITY_ROOT_FILE:AGENTS.md$",
            ("protected_path_reason", "AGENTS.md"),
        ),
        (
            {"allowed_files": [".github/workflows/x.yml"]},
            "^TASK_CARD_CREATE_PROTECTED_PATH:AUTHORITY_DIRECTORY:.github/workflows/x.yml$",
            ("protected_path_reason", ".github/workflows/x.yml"),
        ),
        (
            {"verifier_commands": []},
            "^verifier_commands is required$",
            ("protected_path_reason", "docs/notes.md"),
        ),
        (
            {"verifier_commands": ["  "]},
            "^verifier_commands is required$",
            ("protected_path_reason", "docs/notes.md"),
        ),
        (
            {"expected_evidence": []},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:expected_evidence must be an object$",
            ("self._task_card_expected_evidence",),
        ),
        (
            {"expected_evidence": {"subjects": 1}},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:",
            ("self._task_card_expected_evidence",),
        ),
    ],
)
def test_create_input_denials_stop_before_authority_and_writes(
    events, probes, overrides, message, last
) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_create(_create_args(**overrides))
    assert events[-1] == last
    assert "self._require_owner_effect_authority" not in _names(events)
    assert _effects(events) == []
    assert _tree(probes.root) == []


def test_create_refuses_a_protected_path_reached_through_a_symlink(events, probes) -> None:
    (probes.root / "alias").symlink_to(probes.root / "AGENTS.md")
    with pytest.raises(
        GatewayInputError, match="^TASK_CARD_CREATE_PROTECTED_PATH:AUTHORITY_ROOT_FILE:alias$"
    ):
        _gateway(events)._task_card_create(_create_args(allowed_files=["alias"]))
    assert events[-2:] == [
        ("protected_path_reason", "alias"),
        ("protected_path_reason", "AGENTS.md"),
    ]
    assert _effects(events) == []


def test_create_refuses_a_symlink_escaping_the_controller(events, probes, tmp_path) -> None:
    (probes.root / "out").symlink_to(tmp_path)
    with pytest.raises(GatewayInputError, match="^allowed_files escapes canonical root$"):
        _gateway(events)._task_card_create(_create_args(allowed_files=["out/x.md"]))
    assert _effects(events) == []


@pytest.mark.parametrize("head", ["", "A" * 40, "a" * 39])
def test_create_requires_an_exact_controller_head(events, probes, head) -> None:
    probes.git_hook = lambda args: head + "\n"
    with pytest.raises(
        GatewayInputError, match="^expected_head (is required|must be an exact lowercase Git hash)$"
    ):
        _gateway(events)._task_card_create(_create_args())
    assert _names(events)[-3:] == ["_git", "self._exact_hash", "_text"]
    assert _effects(events) == []


def test_create_git_failure_propagates_before_authority(events, probes) -> None:
    def fail(args):
        raise RuntimeError("git probe failure")

    probes.git_hook = fail
    with pytest.raises(RuntimeError, match="^git probe failure$"):
        _gateway(events)._task_card_create(_create_args())
    assert _names(events)[-1] == "_git"


def test_create_authority_denial_writes_nothing(events, probes) -> None:
    gateway = _gateway(events, authority_error=GatewayInputError("OWNER_AUTHORITY_REQUIRED:probe"))
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_REQUIRED:probe$"):
        gateway._task_card_create(_create_args())
    assert events[-1] == (
        "self._require_owner_effect_authority",
        "TASK_CARD_CREATE",
        "goal-g9",
        "thread-g9",
    )
    assert _tree(probes.root) == []


def test_create_real_owner_authority_denial_reaches_no_write(events, probes, monkeypatch) -> None:
    from nexus.orchestrator.standing_grant_store import StandingGrantReceiptError

    def deny(**kwargs):
        events.append(("authorize_durable_standing_grant_effect", kwargs["action"].value))
        raise StandingGrantReceiptError("NO_GRANT_PROBE")

    monkeypatch.setattr(gateway_module, "authorize_durable_standing_grant_effect", deny)
    monkeypatch.setattr(gateway_module, "bootstrap_agent_authority", real_bootstrap)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", False)
    monkeypatch.setattr(gateway_module, "CONTROLLER_BINDING_PROBLEM", None)
    gateway = UnifiedMCPGateway(service=MagicMock())
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_REQUIRED:NO_GRANT_PROBE$"):
        gateway._task_card_create(_create_args())
    assert events[-1] == ("authorize_durable_standing_grant_effect", "TASK_CARD_CREATE")
    assert _effects(events) == []
    assert _tree(probes.root) == []


@pytest.mark.parametrize(
    "existing",
    ["tasks/g9-campaign", "tasks/g9-campaign/INDEX.md", "tasks/g9-campaign/00-g9-card.md"],
)
def test_create_never_overwrites(events, probes, existing) -> None:
    target = probes.root / existing
    if target.suffix:
        target.parent.mkdir(parents=True)
        target.write_text("keep\n", encoding="utf-8")
    else:
        target.mkdir(parents=True)
    before = _tree(probes.root)
    with pytest.raises(GatewayInputError, match="^TASK_CARD_CREATE_WOULD_OVERWRITE$"):
        _gateway(events)._task_card_create(_create_args())
    # Refused before the card is rendered and before any owner authority is recorded.
    assert _names(events)[-3:] == ["_git", "self._exact_hash", "_text"]
    assert "self._require_owner_effect_authority" not in _names(events)
    assert _tree(probes.root) == before


SMUGGLED_BLOCK = (
    "```"
    + TASK_CARD_EXPECTED_EVIDENCE_FENCE
    + "\n"
    + ExpectedEvidenceUniverse.model_validate(UNIVERSE).canonical_json()
    + "\n```"
)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"objective": "near miss\n```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "-x\n```"},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text declares a malformed block$",
        ),
        (
            {"objective": "second\n" + SMUGGLED_BLOCK, "expected_evidence": UNIVERSE},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text declares a malformed block$",
        ),
        (
            {"verifier_commands": ["git diff --check", "```", SMUGGLED_BLOCK]},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text does not round-trip$",
        ),
        (
            {"objective": "smuggled\n" + SMUGGLED_BLOCK},
            "^TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text does not round-trip$",
        ),
    ],
)
def test_create_refuses_card_text_that_smuggles_an_evidence_block(
    events, probes, overrides, message
) -> None:
    gateway = _gateway(events)
    with pytest.raises(GatewayInputError, match=message):
        gateway._task_card_create(_create_args(**overrides))
    # The rendered card is refused before any owner authority is recorded or written.
    assert _names(events)[-3:] == ["_git", "self._exact_hash", "_text"]
    assert "self._require_owner_effect_authority" not in _names(events)
    assert _effects(events) == []
    assert _tree(probes.root) == []


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, stdout="b" * 40, stderr="boom"),
        subprocess.CompletedProcess([], 0, stdout="not-a-sha", stderr=""),
        subprocess.CompletedProcess([], 0, stdout="B" * 40, stderr=""),
    ],
)
def test_create_hash_failure_rolls_back_the_temporary_tree(events, probes, result) -> None:
    probes.run_hook = lambda argv: result
    with pytest.raises(RuntimeError, match="^TASK_CARD_CREATE_HASH_FAILED$"):
        _gateway(events)._task_card_create(_create_args())
    assert _names(events)[-1] == "subprocess.run"
    assert _tree(probes.root) == ["tasks"]


def test_create_refuses_a_campaign_that_appears_during_the_write(events, probes) -> None:
    def race(argv):
        (probes.root / "tasks" / "g9-campaign").mkdir()
        return None

    probes.run_hook = race
    with pytest.raises(GatewayInputError, match="^TASK_CARD_CREATE_WOULD_OVERWRITE$"):
        _gateway(events)._task_card_create(_create_args())
    assert "os.replace" not in _names(events)
    assert _tree(probes.root) == ["tasks", "tasks/g9-campaign"]


def test_create_replace_failure_rolls_back(events, probes, monkeypatch) -> None:
    def replace(source, target):
        events.append(("os.replace", Path(target).name))
        raise OSError("replace probe")

    monkeypatch.setattr(gateway_module.os, "replace", replace)
    with pytest.raises(OSError, match="replace probe"):
        _gateway(events)._task_card_create(_create_args())
    assert _tree(probes.root) == ["tasks"]


def test_create_reports_the_bootstrap_agent_basis(events, probes) -> None:
    payload = _gateway(events, authority=AGENT_AUTHORITY)._task_card_create(_create_args())
    assert payload["authority_basis"] == real_bootstrap.BASIS_BOOTSTRAP_AGENT
    assert payload["owner_confirmation"] is False
    assert payload["owner_authority"] == AGENT_AUTHORITY


def test_create_public_tool_reports_denials_as_tool_errors(events, probes) -> None:
    response = _gateway(events).handle({
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_create",
            "arguments": _create_args(owner_confirmation=False),
        },
    })
    assert response is not None
    assert response["result"]["isError"] is True
    assert "OWNER_CONFIRMATION_REQUIRED" in response["result"]["structuredContent"]["error"]
    assert events == []


# --- _task_card_issue_promises (#2532) ----------------------------------------------------


PROMISE_UNIVERSE = {
    "universe_generation": 3,
    "subjects": [
        {
            "logical_subject_id": "verify:entry",
            "evidence_kind": "verifier-run",
            "requirement_mode": "REQUIRED",
            "applicability": "APPLICABLE",
        },
        {
            "logical_subject_id": "review:security",
            "evidence_kind": "review-report",
            "requirement_mode": "CONDITIONALLY_REQUIRED",
            "applicability": "UNRESOLVED",
        },
    ],
}


def _promise(pid: str) -> dict[str, Any]:
    return {
        "promise_id": pid,
        "statement_sha256": hashlib.sha256(pid.encode()).hexdigest(),
        "phase": "PRE_MERGE",
        "risk": "STANDARD",
    }


def _binding(mapping: dict[str, list[str]] | None = None, **overrides: Any) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "repository": "James3014/Nexus-new",
        "issue_number": 2548,
        "issue_contract_hash": "c" * 64,
        "expected_evidence_identity": expected_evidence_universe_identity(PROMISE_UNIVERSE),
        "promise_set": {"promise_set_generation": 1, "promises": [_promise("P1")]},
        "map": [
            {"promise_id": pid, "subject_ids": sids}
            for pid, sids in (mapping or {"P1": ["verify:entry", "review:security"]}).items()
        ],
    }
    binding.update(overrides)
    return binding


def _universe() -> ExpectedEvidenceUniverse:
    return ExpectedEvidenceUniverse.model_validate(PROMISE_UNIVERSE)


def test_issue_promises_absent_is_none() -> None:
    assert UnifiedMCPGateway._task_card_issue_promises({}, None) is None
    assert (
        UnifiedMCPGateway._task_card_issue_promises({"issue_promises": None}, _universe()) is None
    )


def test_issue_promises_valid_binding_is_the_reader_model() -> None:
    binding = UnifiedMCPGateway._task_card_issue_promises(
        {"issue_promises": _binding()}, _universe()
    )
    assert binding == IssuePromiseBinding.model_validate(_binding())


@pytest.mark.parametrize(
    ("raw", "universe", "message"),
    [
        ([], "u", "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:issue_promises must be an object$"),
        ("x", "u", "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:issue_promises must be an object$"),
        (
            _binding(),
            None,
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:issue_promises requires expected_evidence$",
        ),
        ({"repository": "x"}, "u", "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:"),
        (
            _binding(expected_evidence_identity="sha256:" + "0" * 64),
            "u",
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:expected_evidence_identity is not this card's universe$",
        ),
        (
            _binding({"P1": ["never:declared"]}),
            "u",
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:subject not in expected_evidence for P1: never:declared$",
        ),
        (
            _binding({"P1": ["review:security"]}),
            "u",
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:promise has no REQUIRED/APPLICABLE subject: P1$",
        ),
    ],
)
def test_issue_promises_denials(raw, universe, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        UnifiedMCPGateway._task_card_issue_promises(
            {"issue_promises": raw}, _universe() if universe == "u" else universe
        )


def test_issue_promise_model_errors_are_flattened_and_bounded() -> None:
    with pytest.raises(GatewayInputError) as caught:
        UnifiedMCPGateway._task_card_issue_promises(
            {"issue_promises": {"map": "x" * 2000}}, _universe()
        )
    reason = str(caught.value).split(":", 1)[1]
    assert "\n" not in reason and len(reason) <= 500


def test_create_binds_issue_promises_into_effect_and_card(events, probes) -> None:
    gateway = _gateway(events)
    payload = gateway._task_card_create(
        _create_args(expected_evidence=PROMISE_UNIVERSE, issue_promises=_binding())
    )
    canonical = IssuePromiseBinding.model_validate(_binding())
    effect = vars(gateway)["owner_effect"]
    assert effect["issue_promises_identity"] == canonical.binding_identity
    assert effect["expected_evidence_identity"] == _universe().universe_identity
    card = (probes.root / payload["card_path"]).read_text(encoding="utf-8")
    block = (
        "## Issue promises\n\n```"
        + TASK_CARD_ISSUE_PROMISES_FENCE
        + "\n"
        + canonical.canonical_json()
        + "\n```\n\n"
    )
    assert block in card
    assert (
        card.index("## Expected evidence")
        < card.index("## Issue promises")
        < card.index("## Exit criteria")
    )
    assert "self._task_card_issue_promises" in _names(events)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"issue_promises": []},
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:issue_promises must be an object$",
        ),
        (
            {"issue_promises": _binding()},
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:issue_promises requires expected_evidence$",
        ),
    ],
)
def test_create_issue_promise_denials_stop_before_head_and_authority(
    events, probes, overrides, message
) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_create(_create_args(**overrides))
    assert events[-1] == ("self._task_card_issue_promises",)
    assert "_git" not in _names(events)
    assert _tree(probes.root) == []


PROMISE_BLOCK = (
    "```"
    + TASK_CARD_ISSUE_PROMISES_FENCE
    + "\n"
    + IssuePromiseBinding.model_validate(_binding()).canonical_json()
    + "\n```"
)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"objective": "near miss\n```" + TASK_CARD_ISSUE_PROMISES_FENCE + "-x\n```"},
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:card text declares a malformed block$",
        ),
        (
            {"objective": "smuggled\n" + PROMISE_BLOCK},
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:card text does not round-trip$",
        ),
        (
            {
                "objective": "second\n" + PROMISE_BLOCK,
                "expected_evidence": PROMISE_UNIVERSE,
                "issue_promises": _binding(),
            },
            "^TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:card text declares a malformed block$",
        ),
    ],
)
def test_create_refuses_card_text_that_smuggles_a_promise_block(
    events, probes, overrides, message
) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_create(_create_args(**overrides))
    assert "self._require_owner_effect_authority" not in _names(events)
    assert _effects(events) == []
    assert _tree(probes.root) == []


# --- _task_card_commit --------------------------------------------------------------------


def _init_repo(root: Path, *, detach: bool = True) -> str:
    def git(*args: str) -> str:
        return _REAL_RUN(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Nexus Test")
    git("config", "user.email", "nexus-test@example.invalid")
    git("config", "commit.gpgsign", "false")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-qm", "base")
    head = git("rev-parse", "HEAD").strip()
    if detach:
        git("checkout", "-q", "--detach", head)
    return head


def _write_pending_card(
    root: Path, *, card: str | None = None, index: str | None = None
) -> tuple[str, str]:
    campaign = root / "tasks" / "g9-campaign"
    campaign.mkdir(parents=True, exist_ok=True)
    card_text = (
        card
        if card is not None
        else "# Task Card: g9-card\n\ntask_id: `g9-card`\nstatus: ACTIVE\nAUTO_CHAIN: false\n"
    )
    index_text = (
        index if index is not None else "# Campaign Index: g9-campaign\n\nAUTO_CHAIN: false\n"
    )
    (campaign / "00-g9-card.md").write_text(card_text, encoding="utf-8")
    (campaign / "INDEX.md").write_text(index_text, encoding="utf-8")
    return (
        hashlib.sha256(card_text.encode("utf-8")).hexdigest(),
        hashlib.sha256(index_text.encode("utf-8")).hexdigest(),
    )


@pytest.fixture
def repo(probes) -> SimpleNamespace:
    head = _init_repo(probes.root)
    card_hash, index_hash = _write_pending_card(probes.root)
    probes.fake_git = False
    return SimpleNamespace(head=head, card_hash=card_hash, index_hash=index_hash)


def _commit_args(repo: SimpleNamespace, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "expected_head": repo.head,
        "card_hash": repo.card_hash,
        "index_hash": repo.index_hash,
    }
    arguments.update(overrides)
    return arguments


def _git_out(root: Path, *args: str) -> str:
    return _REAL_RUN(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


CARD_REL = "tasks/g9-campaign/00-g9-card.md"
INDEX_REL = "tasks/g9-campaign/INDEX.md"
COMMIT_PREFIX = [
    ("_require_bound_controller", None),
    ("self._owner_effect_key",),
    ("_text", "authority_goal_id"),
    ("_text", "authority_coordination_scope_id"),
    ("self._safe_slug", "campaign_id"),
    ("_text", "campaign_id"),
    ("self._safe_slug", "task_id"),
    ("_text", "task_id"),
]


def test_commit_call_order_effect_and_payload(events, probes, repo) -> None:
    gateway = _gateway(events)
    payload = gateway._call_tool("nexus_task_card_commit", _commit_args(repo))
    assert events == COMMIT_PREFIX + [
        ("_git", "rev-parse", "HEAD"),
        ("_require_bound_controller", repo.head),
        ("self._require_owner_effect_authority", "TASK_CARD_COMMIT", "goal-g9", "thread-g9"),
        ("subprocess.run", "symbolic-ref", "-q"),
        ("subprocess.run", "status", "--porcelain=v1"),
        ("_git", "add", "--", INDEX_REL, CARD_REL),
        ("_git", "diff", "--cached", "--name-only", "--", INDEX_REL, CARD_REL),
        ("subprocess.run", "show", ":" + CARD_REL),
        ("subprocess.run", "show", ":" + INDEX_REL),
        ("_git", "commit", "-m", "chore(tasks): bind g9-card"),
        ("_git", "rev-parse", "HEAD"),
        ("_git", "rev-parse", "HEAD^"),
        ("_git", "rev-parse", "HEAD^{tree}"),
        ("subprocess.run", "status", "--porcelain=v1"),
        ("_git", "diff-tree", "--no-commit-id", "--name-only", "-r", payload["commit_sha"]),
        ("authority_basis",),
        ("authority_basis",),
    ]
    assert vars(gateway)["owner_effect"] == {
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "expected_head": repo.head,
        "card_hash": repo.card_hash,
        "index_hash": repo.index_hash,
    }
    commit = _git_out(probes.root, "rev-parse", "HEAD").strip()
    assert payload == {
        "schema": "nexus.task_card_commit.v1",
        "status": "COMMITTED",
        "campaign_id": "g9-campaign",
        "task_id": "g9-card",
        "previous_head": repo.head,
        "commit_sha": commit,
        "tree_sha": _git_out(probes.root, "rev-parse", "HEAD^{tree}").strip(),
        "index_path": INDEX_REL,
        "card_path": CARD_REL,
        "card_hash": repo.card_hash,
        "index_hash": repo.index_hash,
        "committed_paths": [CARD_REL, INDEX_REL],
        "controller_clean": True,
        "successor_execution": "READY_FOR_GOVERNED_START",
        "authority_basis": real_bootstrap.BASIS_OWNER_GRANT,
        "owner_confirmation": True,
        "owner_authority": OWNER_GRANT,
    }
    assert _git_out(probes.root, "log", "-1", "--format=%s").strip() == "chore(tasks): bind g9-card"
    assert _git_out(probes.root, "status", "--porcelain=v1") == ""


def test_commit_hashes_are_normalised_to_lowercase(events, probes, repo) -> None:
    payload = _gateway(events)._task_card_commit(
        _commit_args(repo, expected_head=" " + repo.head.upper(), card_hash=repo.card_hash.upper())
    )
    assert payload["previous_head"] == repo.head and payload["card_hash"] == repo.card_hash


def test_commit_reports_the_bootstrap_agent_basis(events, probes, repo) -> None:
    payload = _gateway(events, authority=AGENT_AUTHORITY)._task_card_commit(_commit_args(repo))
    assert (payload["authority_basis"], payload["owner_confirmation"]) == (
        real_bootstrap.BASIS_BOOTSTRAP_AGENT,
        False,
    )


@pytest.mark.parametrize("value", [None, False, "true", 1])
def test_commit_requires_literal_true_owner_confirmation_before_anything(
    events, probes, repo, value
) -> None:
    with pytest.raises(GatewayInputError, match="^OWNER_CONFIRMATION_REQUIRED$"):
        _gateway(events)._task_card_commit(_commit_args(repo, owner_confirmation=value))
    assert events == []


def test_commit_refuses_an_unbound_controller_first(events, probes, repo) -> None:
    probes.bound_error = GatewayInputError("CONTROLLER_BINDING_INVALID:probe")
    with pytest.raises(GatewayInputError, match="^CONTROLLER_BINDING_INVALID:probe$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events == [("_require_bound_controller", None)]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"authority_goal_id": None},
            "^OWNER_AUTHORITY_KEY_REQUIRED:authority_goal_id is required$",
        ),
        ({"campaign_id": "a b"}, "^campaign_id must be a stable bounded slug$"),
        ({"task_id": ""}, "^task_id is required$"),
        ({"expected_head": "abc"}, "^expected_head must be a lowercase 40-hex SHA$"),
        ({"expected_head": None}, "^expected_head must be a lowercase 40-hex SHA$"),
        ({"card_hash": "a" * 63}, "^card_hash must be a lowercase 64-hex SHA-256$"),
        ({"index_hash": "z" * 64}, "^index_hash must be a lowercase 64-hex SHA-256$"),
    ],
)
def test_commit_argument_denials(events, probes, repo, overrides, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_commit(_commit_args(repo, **overrides))
    assert "_git" not in _names(events)
    assert "self._require_owner_effect_authority" not in _names(events)


@pytest.mark.parametrize("missing", [CARD_REL, INDEX_REL])
def test_commit_requires_both_pending_files(events, probes, repo, missing) -> None:
    (probes.root / missing).unlink()
    with pytest.raises(GatewayInputError, match="^TASK_CARD_COMMIT_SOURCE_MISSING$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events == COMMIT_PREFIX


@pytest.mark.parametrize("linked", [CARD_REL, INDEX_REL])
def test_commit_refuses_symlinked_pending_files(events, probes, repo, linked, tmp_path) -> None:
    path = probes.root / linked
    outside = tmp_path / "outside.md"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(GatewayInputError, match="^TASK_CARD_COMMIT_SYMLINK_FORBIDDEN$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events == COMMIT_PREFIX


def test_commit_refuses_a_campaign_directory_escaping_the_controller(
    events, probes, repo, tmp_path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    (probes.root / "tasks" / "g9-campaign").rename(elsewhere)
    (probes.root / "tasks" / "g9-campaign").symlink_to(elsewhere)
    with pytest.raises(GatewayInputError, match="^TASK_CARD_COMMIT_PATH_ESCAPE$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events == COMMIT_PREFIX


def test_commit_undecodable_card_fails_before_hash_checks(events, probes, repo) -> None:
    (probes.root / CARD_REL).write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeDecodeError):
        _gateway(events)._task_card_commit(
            _commit_args(repo, card_hash=hashlib.sha256(b"\xff\xfe").hexdigest())
        )
    assert events == COMMIT_PREFIX


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"card_hash": "0" * 64}, "^TASK_CARD_COMMIT_HASH_MISMATCH$"),
        ({"index_hash": "0" * 64}, "^TASK_CARD_COMMIT_INDEX_HASH_MISMATCH$"),
    ],
)
def test_commit_hash_mismatches(events, probes, repo, overrides, message) -> None:
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_commit(_commit_args(repo, **overrides))
    assert events == COMMIT_PREFIX


@pytest.mark.parametrize(
    ("card", "index", "message"),
    [
        (
            "# Task Card: g9-card\n\ntask_id: `other`\nstatus: ACTIVE\nAUTO_CHAIN: false\n",
            None,
            "^TASK_CARD_COMMIT_CARD_NOT_ACTIVE$",
        ),
        (
            "# Task Card: g9-card\n\ntask_id: `g9-card`\nstatus: DONE\nAUTO_CHAIN: false\n",
            None,
            "^TASK_CARD_COMMIT_CARD_NOT_ACTIVE$",
        ),
        (
            "# Task Card: g9-card\n\ntask_id: `g9-card`\nstatus: ACTIVE\nAUTO_CHAIN: true\n",
            None,
            "^TASK_CARD_COMMIT_CARD_NOT_ACTIVE$",
        ),
        (
            None,
            "# Campaign Index: other\n\nAUTO_CHAIN: false\n",
            "^TASK_CARD_COMMIT_INDEX_NOT_BOUND$",
        ),
        (
            None,
            "# Campaign Index: g9-campaign\n\nAUTO_CHAIN: true\n",
            "^TASK_CARD_COMMIT_INDEX_NOT_BOUND$",
        ),
    ],
)
def test_commit_content_binding_denials(events, probes, repo, card, index, message) -> None:
    card_hash, index_hash = _write_pending_card(probes.root, card=card, index=index)
    with pytest.raises(GatewayInputError, match=message):
        _gateway(events)._task_card_commit(
            _commit_args(repo, card_hash=card_hash, index_hash=index_hash)
        )
    assert events == COMMIT_PREFIX


def test_commit_refuses_a_moved_controller_head(events, probes, repo) -> None:
    with pytest.raises(GatewayInputError, match="^TASK_CARD_COMMIT_HEAD_MISMATCH$"):
        _gateway(events)._task_card_commit(_commit_args(repo, expected_head="b" * 40))
    assert events == COMMIT_PREFIX + [("_git", "rev-parse", "HEAD")]


def test_commit_rechecks_the_bound_controller_at_the_expected_head(
    events, probes, repo, monkeypatch
) -> None:
    calls = []

    def bound(expected_head=None):
        events.append(("_require_bound_controller", expected_head))
        calls.append(expected_head)
        if expected_head is not None:
            raise GatewayInputError("CONTROLLER_BINDING_INVALID:HEAD_MOVED_DURING_CHECK")

    monkeypatch.setattr(gateway_module, "_require_bound_controller", bound)
    with pytest.raises(GatewayInputError, match="HEAD_MOVED_DURING_CHECK"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert calls == [None, repo.head]
    assert "self._require_owner_effect_authority" not in _names(events)


def test_commit_authority_denial_stages_nothing(events, probes, repo) -> None:
    gateway = _gateway(events, authority_error=GatewayInputError("OWNER_AUTHORITY_REQUIRED:probe"))
    with pytest.raises(GatewayInputError, match="^OWNER_AUTHORITY_REQUIRED:probe$"):
        gateway._task_card_commit(_commit_args(repo))
    assert _names(events)[-1] == "self._require_owner_effect_authority"
    assert _effects(events) == []
    assert _git_out(probes.root, "rev-parse", "HEAD").strip() == repo.head


def test_commit_requires_a_detached_controller(events, probes) -> None:
    head = _init_repo(probes.root, detach=False)
    card_hash, index_hash = _write_pending_card(probes.root)
    probes.fake_git = False
    repo = SimpleNamespace(head=head, card_hash=card_hash, index_hash=index_hash)
    with pytest.raises(GatewayInputError, match="^TASK_CARD_COMMIT_REQUIRES_DETACHED_CONTROLLER$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("subprocess.run", "symbolic-ref", "-q")
    assert _effects(events) == []


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            subprocess.CompletedProcess([], 128, stdout="", stderr="symbolic probe"),
            "^symbolic probe$",
        ),
        (
            subprocess.CompletedProcess([], 2, stdout="", stderr=""),
            "^failed to inspect controller branch state$",
        ),
    ],
)
def test_commit_branch_inspection_failure(events, probes, repo, result, message) -> None:
    probes.run_hook = lambda argv: result if argv[1] == "symbolic-ref" else None
    with pytest.raises(RuntimeError, match=message):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert _effects(events) == []


def test_commit_status_failure(events, probes, repo) -> None:
    failed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"status probe")
    probes.run_hook = lambda argv: failed if argv[1] == "status" else None
    with pytest.raises(RuntimeError, match="^status probe$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert _effects(events) == []


def test_commit_refuses_unrelated_controller_state(events, probes, repo) -> None:
    (probes.root / "unrelated.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(
        GatewayInputError, match="^TASK_CARD_COMMIT_CONTROLLER_NOT_EXACTLY_PENDING_CARD$"
    ):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("subprocess.run", "status", "--porcelain=v1")
    assert _effects(events) == []


def test_commit_stage_mismatch_resets_the_index(events, probes, repo) -> None:
    probes.git_hook = lambda args: (INDEX_REL + "\n") if args[:2] == ("diff", "--cached") else None
    with pytest.raises(RuntimeError, match="^TASK_CARD_COMMIT_STAGE_MISMATCH$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("_git", "reset", "--", INDEX_REL, CARD_REL)
    assert _git_out(probes.root, "diff", "--cached", "--name-only") == ""
    assert "_git:commit" not in _effects(events)


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            subprocess.CompletedProcess([], 0, stdout=b"other", stderr=b""),
            "^TASK_CARD_COMMIT_STAGED_HASH_MISMATCH$",
        ),
        (subprocess.CompletedProcess([], 128, stdout=b"", stderr=b"show probe"), "^show probe$"),
        (
            subprocess.CompletedProcess([], 128, stdout=b"", stderr=b""),
            "^failed to read staged task-card content$",
        ),
    ],
)
def test_commit_staged_content_must_match(events, probes, repo, result, message) -> None:
    probes.run_hook = lambda argv: result if argv[1] == "show" else None
    with pytest.raises(RuntimeError, match=message):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("_git", "reset", "--", INDEX_REL, CARD_REL)
    assert "_git:commit" not in _effects(events)
    assert _git_out(probes.root, "diff", "--cached", "--name-only") == ""


def test_commit_failure_resets_the_index(events, probes, repo) -> None:
    def hook(args):
        if args[0] == "commit":
            raise RuntimeError("commit probe")
        return None

    probes.git_hook = hook
    with pytest.raises(RuntimeError, match="^commit probe$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-2:] == [
        ("_git", "commit", "-m", "chore(tasks): bind g9-card"),
        ("_git", "reset", "--", INDEX_REL, CARD_REL),
    ]
    assert _git_out(probes.root, "rev-parse", "HEAD").strip() == repo.head


@pytest.mark.parametrize(
    ("hooked", "value"),
    [
        (("rev-parse", "HEAD^"), "b" * 40),
        (("rev-parse", "HEAD"), "nope"),
        (("rev-parse", "HEAD^{tree}"), "nope"),
    ],
)
def test_commit_identity_mismatch_after_commit(events, probes, repo, hooked, value) -> None:
    state = {"seen": 0}

    def hook(args):
        if args == hooked:
            state["seen"] += 1
            if hooked != ("rev-parse", "HEAD") or state["seen"] == 2:
                return value + "\n"
        return None

    probes.git_hook = hook
    with pytest.raises(RuntimeError, match="^TASK_CARD_COMMIT_IDENTITY_MISMATCH$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("_git", "rev-parse", "HEAD^{tree}")


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            subprocess.CompletedProcess([], 0, stdout=b"?? stray\0", stderr=b""),
            "^TASK_CARD_COMMIT_CONTROLLER_NOT_CLEAN_AFTER_COMMIT$",
        ),
        (
            subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"late status probe"),
            "^late status probe$",
        ),
        (subprocess.CompletedProcess([], 1, stdout=b"", stderr=b""), "^git status failed$"),
    ],
)
def test_commit_controller_must_be_clean_after_commit(
    events, probes, repo, result, message
) -> None:
    state = {"status": 0}

    def hook(argv):
        if argv[1] == "status":
            state["status"] += 1
            if state["status"] == 2:
                return result
        return None

    probes.run_hook = hook
    with pytest.raises(RuntimeError, match=message):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert events[-1] == ("subprocess.run", "status", "--porcelain=v1")


def test_commit_scope_must_be_exactly_the_two_files(events, probes, repo) -> None:
    probes.git_hook = lambda args: (
        f"{CARD_REL}\n{INDEX_REL}\nextra.md\n" if args[0] == "diff-tree" else None
    )
    with pytest.raises(RuntimeError, match="^TASK_CARD_COMMIT_SCOPE_MISMATCH$"):
        _gateway(events)._task_card_commit(_commit_args(repo))
    assert _names(events)[-1] == "_git"


def test_commit_public_tool_reports_denials_as_tool_errors(events, probes, repo) -> None:
    response = _gateway(events).handle({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_commit",
            "arguments": _commit_args(repo, card_hash="0" * 64),
        },
    })
    assert response is not None
    assert response["result"]["isError"] is True
    assert "TASK_CARD_COMMIT_HASH_MISMATCH" in response["result"]["structuredContent"]["error"]


def test_create_then_commit_round_trip(events, probes) -> None:
    head = _init_repo(probes.root)
    probes.fake_git = False
    gateway = _gateway(events)
    created = gateway._task_card_create(_create_args())
    events.clear()
    committed = gateway._task_card_commit(
        _commit_args(
            SimpleNamespace(
                head=head, card_hash=created["card_hash"], index_hash=created["index_hash"]
            )
        )
    )
    assert committed["committed_paths"] == [CARD_REL, INDEX_REL]
    blob = _git_out(probes.root, "rev-parse", f"HEAD:{CARD_REL}").strip()
    assert blob == created["git_blob_sha"]
