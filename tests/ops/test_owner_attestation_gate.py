"""Owner-signed grants gate agent-authored pull requests (#1750 phase 2).

Keys are generated with the system OpenSSL, as the Owner's Secure Enclave key
would be P-256.  Every negative case asserts the gate's refusal for the exact
PR, with trust configuration read from the base revision only.
"""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.ops.trusted_merge_lane_gate import (
    ATTESTATION_SCHEMA,
    BINDING_SCHEMA,
    LaneBindingError,
    canonical_attestation_bytes,
    canonical_hash,
    render_attestation,
    render_binding,
    signing_key_id,
    validate_event,
)

REPOSITORY = "James3014/Nexus-new"
OWNER = "James3014"
AGENT = "nexus-agent-bot"
ISSUE = 1750
PR_NUMBER = 1900
NOW = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _keypair(directory: Path, name: str, curve: str = "prime256v1") -> tuple[Path, str]:
    private = directory / f"{name}.key"
    subprocess.run(
        ["openssl", "ecparam", "-name", curve, "-genkey", "-noout", "-out", str(private)],
        check=True,
        capture_output=True,
    )
    public = subprocess.run(
        ["openssl", "ec", "-in", str(private), "-pubout"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return private, public


def _sign(private: Path, message: bytes, directory: Path) -> str:
    data = directory / "message.bin"
    data.write_bytes(message)
    signature = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private), str(data)],
        check=True,
        capture_output=True,
    ).stdout
    return base64.b64encode(signature).decode("ascii")


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True
    )
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path: Path):
    keys = tmp_path / "keys"
    keys.mkdir()
    owner_key, owner_pub = _keypair(keys, "owner")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True
    )
    (repo / "governance").mkdir()
    (repo / "governance" / "agent-identities.json").write_text(
        json.dumps({"schema": "nexus.agent_identities.v1", "agents": [AGENT]}), encoding="utf-8"
    )
    (repo / "governance" / "owner-signing-keys.json").write_text(
        json.dumps({
            "schema": "nexus.owner_signing_keys.v1",
            "owner_id": OWNER,
            "keys": [{"key_id": signing_key_id(owner_pub), "public_key_pem": owner_pub}],
        }),
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "feature.py").write_text("value = 1\n", encoding="utf-8")
    base = _commit(repo, "base")
    return {
        "repo": repo,
        "base": base,
        "keys": keys,
        "owner_key": owner_key,
        "owner_pub": owner_pub,
    }


def _head(world, files: dict[str, str]) -> str:
    repo = world["repo"]
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return _commit(repo, "head")


def _payload(**overrides):
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "repository": REPOSITORY,
        "owner_id": OWNER,
        "agent_login": AGENT,
        "issue_number": ISSUE,
        "allowed_actions": ["GITHUB_MERGE"],
        "allowed_paths": ["src/**"],
        "issued_at": (NOW - timedelta(hours=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=1)).isoformat(),
        "nonce": "n-2026-10-12-0001",
    }
    payload.update(overrides)
    return payload


def _envelope(world, payload, *, key=None, signed_payload=None):
    key = key or world["owner_key"]
    pub = subprocess.run(
        ["openssl", "ec", "-in", str(key), "-pubout"], check=True, capture_output=True, text=True
    ).stdout
    return {
        "payload": payload,
        "key_id": signing_key_id(pub),
        "signature": _sign(
            key, canonical_attestation_bytes(signed_payload or payload), world["keys"]
        ),
    }


def _binding():
    value = {
        "schema": BINDING_SCHEMA,
        "execution_lane": "DIRECT_CANONICAL",
        "contract_kind": "OWNER_INLINE",
        "owner_id": OWNER,
        "issue_number": None,
        "task_id": None,
        "attempt_id": None,
        "task_card_path": None,
        "task_card_sha256": None,
        "owner_lane_rebind": None,
    }
    value["binding_hash"] = canonical_hash(value)
    return value


def _body(*envelopes, issue: int = ISSUE) -> str:
    parts = [f"Refs #{issue}", f"<!-- NEXUS_CORE_ISSUE: {issue} -->", render_binding(_binding())]
    parts.extend(render_attestation(envelope) for envelope in envelopes)
    return "\n\n".join(parts)


def _event(world, head: str, body: str, *, author: str = AGENT, sender: str = AGENT):
    return {
        "event_name": "pull_request_target",
        "repository": {"full_name": REPOSITORY},
        "sender": {"login": sender},
        "pull_request": {
            "number": PR_NUMBER,
            "body": body,
            "user": {"login": author},
            "base": {"sha": world["base"]},
            "head": {"sha": head},
        },
    }


def _validate(world, head, body, **kwargs):
    return validate_event(_event(world, head, body, **kwargs), repo_root=world["repo"], now=NOW)


def test_agent_pr_with_owner_signed_scope_passes(world):
    head = _head(world, {"src/feature.py": "value = 2\n", "src/new/module.py": "x = 1\n"})
    result = _validate(world, head, _body(_envelope(world, _payload())))
    assert result["status"] == "PASS"
    check = result["owner_attestation"]
    assert check["agent_login"] == AGENT
    assert check["issue_number"] == ISSUE
    assert check["changed_path_count"] == 2


def test_owner_pr_needs_no_attestation(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    result = _validate(world, head, _body(), author=OWNER, sender=OWNER)
    assert result["status"] == "PASS"
    assert "owner_attestation" not in result


@pytest.mark.parametrize(("author", "sender"), [(AGENT, OWNER), (OWNER, AGENT), (AGENT, AGENT)])
def test_any_agent_involvement_requires_attestation(world, author, sender):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="AGENT_PR_REQUIRES_OWNER_ATTESTATION"):
        _validate(world, head, _body(), author=author, sender=sender)


def test_agent_login_match_is_case_insensitive(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    result = _validate(world, head, _body(_envelope(world, _payload())), author="Nexus-Agent-Bot")
    assert result["owner_attestation"]["status"] == "PASS"


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ({"allowed_paths": ["**"]}, "ATTESTATION_SIGNATURE_INVALID"),
        ({"expires_at": (NOW + timedelta(days=6)).isoformat()}, "ATTESTATION_SIGNATURE_INVALID"),
        ({"agent_login": "someone-else"}, "ATTESTATION_SIGNATURE_INVALID"),
    ],
)
def test_payload_changed_after_signing_is_rejected(world, tamper, reason):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    signed = _payload()
    envelope = _envelope(world, {**signed, **tamper}, signed_payload=signed)
    with pytest.raises(LaneBindingError, match=reason):
        _validate(world, head, _body(envelope))


def test_signature_from_an_unpinned_key_is_rejected(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    attacker_key, _ = _keypair(world["keys"], "attacker")
    with pytest.raises(LaneBindingError, match="ATTESTATION_KEY_NOT_PINNED"):
        _validate(world, head, _body(_envelope(world, _payload(), key=attacker_key)))


def test_signature_by_another_key_under_the_pinned_key_id_is_rejected(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    attacker_key, _ = _keypair(world["keys"], "attacker")
    envelope = _envelope(world, _payload(), key=attacker_key)
    envelope["key_id"] = signing_key_id(world["owner_pub"])
    with pytest.raises(LaneBindingError, match="ATTESTATION_SIGNATURE_INVALID"):
        _validate(world, head, _body(envelope))


def test_head_cannot_add_its_own_signing_key(world):
    attacker_key, attacker_pub = _keypair(world["keys"], "attacker")
    keys_file = {
        "schema": "nexus.owner_signing_keys.v1",
        "owner_id": OWNER,
        "keys": [{"key_id": signing_key_id(attacker_pub), "public_key_pem": attacker_pub}],
    }
    head = _head(
        world,
        {
            "src/feature.py": "value = 2\n",
            "governance/owner-signing-keys.json": json.dumps(keys_file),
        },
    )
    envelope = _envelope(world, _payload(allowed_paths=["**"]), key=attacker_key)
    with pytest.raises(LaneBindingError, match="ATTESTATION_KEY_NOT_PINNED"):
        _validate(world, head, _body(envelope))


@pytest.mark.parametrize(
    "path",
    [
        "governance/agent-identities.json",
        ".github/workflows/ci.yml",
        "scripts/ops/trusted_merge_lane_gate.py",
        "AGENTS.md",
    ],
)
def test_protected_paths_are_never_coverable(world, path):
    head = _head(world, {path: "changed\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PROTECTED_PATH"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=["**"]))))


def test_changes_outside_the_signed_paths_are_rejected(world):
    head = _head(world, {"src/feature.py": "value = 2\n", "docs/notes.md": "x\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PATH_OUT_OF_SCOPE:docs/notes.md"):
        _validate(world, head, _body(_envelope(world, _payload())))


def test_single_star_does_not_cross_directories(world):
    head = _head(world, {"src/deep/module.py": "x = 1\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PATH_OUT_OF_SCOPE:src/deep/module.py"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=["src/*"]))))


@pytest.mark.parametrize("pattern", ["../src/**", "/src/**", "src/../governance/**"])
def test_escaping_path_patterns_are_invalid(world, pattern):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PATH_PATTERN_INVALID"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=[pattern]))))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"expires_at": (NOW - timedelta(seconds=1)).isoformat()}, "ATTESTATION_EXPIRED"),
        (
            {
                "issued_at": (NOW + timedelta(hours=1)).isoformat(),
                "expires_at": (NOW + timedelta(days=1)).isoformat(),
            },
            "ATTESTATION_NOT_YET_VALID",
        ),
        ({"expires_at": (NOW + timedelta(days=8)).isoformat()}, "ATTESTATION_LIFETIME_INVALID"),
        ({"agent_login": "another-bot"}, "ATTESTATION_AGENT_MISMATCH"),
        ({"issue_number": 9999}, "ATTESTATION_ISSUE_NOT_BOUND_TO_PR"),
        ({"allowed_actions": ["REPOSITORY_PUSH"]}, "ATTESTATION_MERGE_NOT_GRANTED"),
        ({"repository": "James3014/devspace"}, "ATTESTATION_REPOSITORY_MISMATCH"),
        ({"owner_id": "someone"}, "ATTESTATION_OWNER_MISMATCH"),
        ({"schema": "nexus.other.v1"}, "ATTESTATION_PAYLOAD_SCHEMA_INVALID"),
        ({"extra": True}, "ATTESTATION_PAYLOAD_SCHEMA_INVALID"),
    ],
)
def test_signed_but_out_of_bounds_grants_are_rejected(world, overrides, reason):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match=reason):
        _validate(world, head, _body(_envelope(world, _payload(**overrides))))


def test_two_attestations_are_rejected(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    envelope = _envelope(world, _payload())
    with pytest.raises(LaneBindingError, match="ATTESTATION_MARKER_COUNT_INVALID"):
        _validate(world, head, _body(envelope, envelope))


def test_without_pinned_keys_agent_prs_cannot_pass(world):
    repo = world["repo"]
    (repo / "governance" / "owner-signing-keys.json").unlink()
    world["base"] = _commit(repo, "remove keys")
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="OWNER_SIGNING_KEY_NOT_CONFIGURED"):
        _validate(world, head, _body(_envelope(world, _payload())))


def test_a_non_p256_pinned_key_never_verifies(world):
    repo = world["repo"]
    other_key, other_pub = _keypair(world["keys"], "p384", curve="secp384r1")
    (repo / "governance" / "owner-signing-keys.json").write_text(
        json.dumps({
            "schema": "nexus.owner_signing_keys.v1",
            "owner_id": OWNER,
            "keys": [{"key_id": signing_key_id(other_pub), "public_key_pem": other_pub}],
        }),
        encoding="utf-8",
    )
    world["base"] = _commit(repo, "p384 key")
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_SIGNATURE_INVALID"):
        _validate(world, head, _body(_envelope(world, _payload(), key=other_key)))


def test_pinned_key_id_must_match_its_key(world):
    repo = world["repo"]
    config = json.loads(
        (repo / "governance" / "owner-signing-keys.json").read_text(encoding="utf-8")
    )
    config["keys"][0]["key_id"] = "0" * 64
    (repo / "governance" / "owner-signing-keys.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    world["base"] = _commit(repo, "bad key id")
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="OWNER_SIGNING_KEY_ID_MISMATCH"):
        _validate(world, head, _body(_envelope(world, _payload())))


def test_draft_sign_assemble_round_trip_passes_the_gate(world, capsys):
    from scripts.ops.owner_attestation import main as tool

    head = _head(world, {"src/feature.py": "value = 2\n"})
    keys = world["keys"]
    payload_file = keys / "grant.json"
    assert (
        tool([
            "draft",
            "--agent",
            AGENT,
            "--issue",
            str(ISSUE),
            "--path",
            "src/**",
            "--hours",
            "24",
            "--out",
            str(payload_file),
        ])
        == 0
    )
    signature_file = keys / "grant.sig"
    signature_file.write_text(
        _sign(world["owner_key"], payload_file.read_bytes(), keys), encoding="ascii"
    )
    public_file = keys / "owner.pem"
    public_file.write_text(world["owner_pub"], encoding="ascii")
    capsys.readouterr()
    assert (
        tool([
            "assemble",
            "--payload",
            str(payload_file),
            "--signature",
            str(signature_file),
            "--public-key",
            str(public_file),
        ])
        == 0
    )
    marker = capsys.readouterr().out
    body = _body() + "\n\n" + marker
    result = validate_event(_event(world, head, body), repo_root=world["repo"])
    assert result["owner_attestation"]["status"] == "PASS"


def test_assemble_refuses_a_signature_that_does_not_verify(world):
    from scripts.ops.owner_attestation import main as tool

    keys = world["keys"]
    payload_file = keys / "grant.json"
    tool([
        "draft",
        "--agent",
        AGENT,
        "--issue",
        str(ISSUE),
        "--path",
        "src/**",
        "--out",
        str(payload_file),
    ])
    attacker_key, _ = _keypair(keys, "attacker")
    signature_file = keys / "grant.sig"
    signature_file.write_text(
        _sign(attacker_key, payload_file.read_bytes(), keys), encoding="ascii"
    )
    public_file = keys / "owner.pem"
    public_file.write_text(world["owner_pub"], encoding="ascii")
    with pytest.raises(SystemExit, match="does not verify"):
        tool([
            "assemble",
            "--payload",
            str(payload_file),
            "--signature",
            str(signature_file),
            "--public-key",
            str(public_file),
        ])
