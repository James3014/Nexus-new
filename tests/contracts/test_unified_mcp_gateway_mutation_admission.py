"""Characterization tests for the gateway's mutation-admission helpers (Issue #2507).

Big-file split G8 pins two helpers before they move out of ``UnifiedMCPGateway`` into a
mixin:

* ``_mutation_admission_status``, driven through the public
  ``nexus_mutation_admission_status`` tool.
* ``_mutation_task_card_authority``, called on the class. It is a staticmethod reached only
  from the GOVERNED lane of ``_mutation_admit``.

``CANONICAL_SOURCE_ROOT`` and ``_git`` are patched on the gateway facade, so these tests
also prove that facade patches keep reaching the moved code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.mutation_admission import MutationAdmissionError
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway

HEAD = "0123456789abcdef0123456789abcdef01234567"


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


@pytest.fixture
def gateway(tmp_path: Path) -> UnifiedMCPGateway:
    return UnifiedMCPGateway(service=_Service(tmp_path / "state"))


def _call(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


# --- _mutation_admission_status via nexus_mutation_admission_status -----------------


class _Store:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []

    def status(self, admission_id: str, *, expected_receipt_hash: str) -> dict:
        self.calls.append((admission_id, expected_receipt_hash))
        if self.error:
            raise MutationAdmissionError(self.error)
        return {
            "admission_id": admission_id,
            "receipt_hash": expected_receipt_hash,
            "status": "ACTIVE",
        }


def test_admission_status_reads_the_store_with_the_expected_receipt(gateway) -> None:
    gateway._mutation_admissions = _Store()
    result = _call(
        gateway,
        "nexus_mutation_admission_status",
        {"admission_id": " adm-1 ", "receipt_hash": "r" * 64},
    )
    assert not result.get("isError"), result
    assert result["structuredContent"] == {
        "admission_id": "adm-1",
        "receipt_hash": "r" * 64,
        "status": "ACTIVE",
    }
    assert gateway._mutation_admissions.calls == [("adm-1", "r" * 64)]


def test_admission_status_maps_store_errors_to_gateway_input_errors(gateway) -> None:
    gateway._mutation_admissions = _Store(error="MUTATION_ADMISSION_RECEIPT_MISMATCH")
    with pytest.raises(GatewayInputError, match="^MUTATION_ADMISSION_RECEIPT_MISMATCH$") as raised:
        gateway._mutation_admission_status({"admission_id": "adm-1", "receipt_hash": "x"})
    assert isinstance(raised.value.__cause__, MutationAdmissionError)
    result = _call(
        gateway, "nexus_mutation_admission_status", {"admission_id": "adm-1", "receipt_hash": "x"}
    )
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "MUTATION_ADMISSION_RECEIPT_MISMATCH"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"receipt_hash": "r"}, "admission_id is required"),
        ({"admission_id": "a"}, "receipt_hash is required"),
    ],
)
def test_admission_status_requires_both_identifiers(gateway, arguments, message) -> None:
    gateway._mutation_admissions = _Store()
    with pytest.raises(GatewayInputError, match=f"^{message}$"):
        gateway._mutation_admission_status(arguments)
    assert gateway._mutation_admissions.calls == []


# --- _mutation_task_card_authority ---------------------------------------------------

CARD = (
    "# Task card\n"
    "artifact_authority: `current`\n"
    "status: ACTIVE\n"
    "task_id: `task-1`\n"
    "attempt_id: attempt-1\n"
    "Tracks James3014/Nexus-new#42.\n"
)
# #2766: a GOVERNED card must declare its scope; added when the card is written so the
# parametrized ids built from CARD stay the same as before.
CARD_SCOPE = "\n## Allowed files\n\n- `docs/a.md`\n"


@pytest.fixture
def card_root(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tasks").mkdir(parents=True)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", root)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: HEAD + "\n")
    return root


def _write_card(root: Path, text: str | bytes = CARD, name: str = "card.md") -> tuple[str, str]:
    path = root / "tasks" / name
    path.write_bytes((text + CARD_SCOPE).encode("utf-8") if isinstance(text, str) else text)
    return f"tasks/{name}", hashlib.sha256(path.read_bytes()).hexdigest()


def _authority(**overrides: Any) -> dict[str, str]:
    values: dict[str, Any] = {
        "issue_number": 42,
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "allowed_paths": ["docs/a.md"],
    }
    values.update(overrides)
    return UnifiedMCPGateway._mutation_task_card_authority(**values)


def test_task_card_authority_binds_an_active_current_card(card_root) -> None:
    path, digest = _write_card(card_root)
    assert _authority(task_card_path=path, task_card_hash=digest) == {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "task_card_path": path,
        "task_card_hash": digest,
        "governance_source_head": HEAD,
    }


@pytest.mark.parametrize("path", ["docs/card.md", "tasks/card.txt", "tasks/../tasks/card.md"])
def test_task_card_authority_rejects_paths_outside_tasks_markdown(card_root, path) -> None:
    _write_card(card_root)
    with pytest.raises(GatewayInputError):
        _authority(task_card_path=path, task_card_hash="0" * 64)


def test_task_card_authority_rejects_symlink_escape(card_root, tmp_path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text(CARD, encoding="utf-8")
    (card_root / "tasks" / "link.md").symlink_to(outside)
    # _safe_relative_path refuses the escaping symlink before the card is read.
    with pytest.raises(GatewayInputError, match="^task_card_path escapes canonical root$"):
        _authority(
            task_card_path="tasks/link.md",
            task_card_hash=hashlib.sha256(outside.read_bytes()).hexdigest(),
        )


def test_task_card_authority_requires_an_existing_card(card_root) -> None:
    with pytest.raises(GatewayInputError, match="^MUTATION_ADMISSION_TASK_CARD_NOT_FOUND$"):
        _authority(task_card_path="tasks/missing.md", task_card_hash="0" * 64)


def test_task_card_authority_rejects_undecodable_cards(card_root) -> None:
    path, digest = _write_card(card_root, b"\xff\xfe not utf-8")
    with pytest.raises(GatewayInputError, match="^MUTATION_ADMISSION_TASK_CARD_UNREADABLE$"):
        _authority(task_card_path=path, task_card_hash=digest)


def test_task_card_authority_rejects_hash_mismatch(card_root) -> None:
    path, _ = _write_card(card_root)
    with pytest.raises(GatewayInputError, match="^MUTATION_ADMISSION_TASK_CARD_HASH_MISMATCH$"):
        _authority(task_card_path=path, task_card_hash="0" * 64)


@pytest.mark.parametrize(
    ("text", "overrides", "code"),
    [
        (CARD.replace("`current`", "`historical`"), {}, "MUTATION_ADMISSION_TASK_CARD_NOT_ACTIVE"),
        (
            CARD.replace("status: ACTIVE", "status: CLOSED"),
            {},
            "MUTATION_ADMISSION_TASK_CARD_NOT_ACTIVE",
        ),
        (CARD, {"task_id": "task-2"}, "MUTATION_ADMISSION_TASK_CARD_IDENTITY_MISMATCH"),
        (CARD, {"attempt_id": "attempt-2"}, "MUTATION_ADMISSION_TASK_CARD_IDENTITY_MISMATCH"),
        (CARD, {"issue_number": 43}, "MUTATION_ADMISSION_TASK_CARD_ISSUE_MISMATCH"),
    ],
)
def test_task_card_authority_checks_card_fields(card_root, text, overrides, code) -> None:
    path, digest = _write_card(card_root, text)
    with pytest.raises(GatewayInputError, match=f"^{code}$"):
        _authority(task_card_path=path, task_card_hash=digest, **overrides)


def test_task_card_authority_requires_a_full_governance_head(card_root, monkeypatch) -> None:
    path, digest = _write_card(card_root)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "not-a-sha")
    with pytest.raises(GatewayInputError, match="^MUTATION_ADMISSION_GOVERNANCE_SOURCE_INVALID$"):
        _authority(task_card_path=path, task_card_hash=digest)
