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
        "workflow_sha": world["base"],
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
        "scripts/ops/owner_attestation.py",
        "tools/owner-signer/Sources/owner-signer/main.swift",
        ".claude/settings.json",
        "src/.claude/settings.json",
        ".mcp.json",
        "AGENTS.md",
        "src/AGENTS.md",
        "src/CLAUDE.md",
        "MUSE_PROTO.md",
        "pyproject.toml",
        "uv.lock",
        "tasks/campaign/card.md",
        "docs/governance/current_operating_mode.yaml",
        "docs/governance/OWNER_REPRESENTATION.md",
        "docs/testing/test_impact_map.md",
        "tests/ops/test_owner_attestation_gate.py",
        "tests/ops/test_trusted_merge_lane_gate.py",
    ],
)
def test_protected_paths_are_never_coverable(world, path):
    head = _head(world, {path: "changed\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PROTECTED_PATH"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=[path]))))


def test_a_broad_grant_does_not_cover_authority_documents_under_it(world):
    # Reproduces the #1817 review: docs/** used to cover docs/governance/.
    head = _head(world, {"docs/governance/current_operating_mode.yaml": "mode: open\n"})
    with pytest.raises(
        LaneBindingError,
        match="ATTESTATION_PROTECTED_PATH:docs/governance/current_operating_mode.yaml",
    ):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=["docs/**"]))))


@pytest.mark.parametrize(
    "actions",
    [
        ["GITHUB_MERGE", 9001],
        ["GITHUB_MERGE", None],
        ["GITHUB_MERGE", ["GITHUB_MERGE"]],
        ["GITHUB_MERGE", "GITHUB_MERGE"],
        ["GITHUB_MERGE", "github merge"],
        "GITHUB_MERGE",
        [],
    ],
)
def test_signed_actions_must_be_a_strict_list_of_action_names(world, actions):
    # Reproduces the #1817 review: a mixed-type list was accepted by the gate
    # while the signer prompt would have shown no actions at all.
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_ACTIONS_INVALID"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_actions=actions))))


@pytest.mark.parametrize("field", ["repository", "owner_id", "agent_login"])
@pytest.mark.parametrize("value", [123, None, ["x"]])
def test_signed_identity_fields_must_be_strings(world, field, value):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="_INVALID"):
        _validate(world, head, _body(_envelope(world, _payload(**{field: value}))))


@pytest.mark.parametrize("pattern", ["**", "*", "**/*.py", "?rc/**", "*/feature.py"])
def test_grants_cannot_start_with_a_wildcard(world, pattern):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PATH_TOO_BROAD"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=[pattern]))))


def test_grant_path_lists_are_bounded(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    patterns = [f"src/p{i}/**" for i in range(13)]
    with pytest.raises(LaneBindingError, match="ATTESTATION_PATHS_INVALID"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=patterns))))


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
    (repo / "governance" / "owner-signing-keys.json").write_text(
        json.dumps({"schema": "nexus.owner_signing_keys.v1", "owner_id": OWNER, "keys": []}),
        encoding="utf-8",
    )
    world["base"] = _commit(repo, "no keys")
    head = _head(world, {"src/feature.py": "value = 2\n"})
    with pytest.raises(LaneBindingError, match="OWNER_SIGNING_KEY_NOT_CONFIGURED"):
        _validate(world, head, _body(_envelope(world, _payload())))


@pytest.mark.parametrize(
    ("missing", "reason"),
    [
        ("governance/agent-identities.json", "AGENT_IDENTITIES_MISSING"),
        ("governance/owner-signing-keys.json", "OWNER_SIGNING_KEYS_MISSING"),
    ],
)
def test_missing_trust_configuration_fails_closed_even_for_owner_prs(world, missing, reason):
    repo = world["repo"]
    (repo / missing).unlink()
    world["base"] = _commit(repo, "drop config")
    head = _head(world, {"src/feature.py": "value = 2\n"})
    author = AGENT if "signing" in missing else OWNER
    body = _body(_envelope(world, _payload())) if author == AGENT else _body()
    with pytest.raises(LaneBindingError, match=reason):
        _validate(world, head, body, author=author, sender=author)


def test_trust_configuration_comes_from_the_gate_revision_not_the_pr_base(world):
    repo = world["repo"]
    stale_base = world["base"]
    (repo / "governance" / "agent-identities.json").write_text(
        json.dumps({"schema": "nexus.agent_identities.v1", "agents": []}), encoding="utf-8"
    )
    _commit(repo, "agent removed later")
    world["base"] = stale_base
    head = _head(world, {"src/feature.py": "value = 2\n"})
    event = _event(world, head, _body())
    event["workflow_sha"] = _git(repo, "rev-parse", "HEAD~1")
    # The PR base still lists the agent, the gate revision does not: no attestation needed.
    assert "owner_attestation" not in validate_event(event, repo_root=repo, now=NOW)
    # And the reverse: gate revision lists the agent although the stale base did not.
    event["workflow_sha"] = stale_base
    with pytest.raises(LaneBindingError, match="AGENT_PR_REQUIRES_OWNER_ATTESTATION"):
        validate_event(event, repo_root=repo, now=NOW)


def test_gate_requires_the_trusted_revision(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    event = _event(world, head, _body(), author=OWNER, sender=OWNER)
    del event["workflow_sha"]
    with pytest.raises(LaneBindingError, match="TRUSTED_CONFIG_REVISION"):
        validate_event(event, repo_root=world["repo"], now=NOW)


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


def _approve(world, head, body, **kwargs):
    from scripts.ops.trusted_merge_lane_gate import approval_decision

    return approval_decision(_event(world, head, body, **kwargs), repo_root=world["repo"], now=NOW)


@pytest.mark.parametrize("sender", [AGENT, OWNER, "someone-else"])
def test_approval_depends_on_content_not_on_who_sent_the_event(world, sender):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    decision = _approve(
        world, head, _body(_envelope(world, _payload())), author=AGENT, sender=sender
    )
    assert decision["approve"] is True
    assert decision["head_sha"] == head


@pytest.mark.parametrize("sender", [AGENT, OWNER])
def test_owner_touching_the_pr_after_an_out_of_scope_push_never_earns_approval(world, sender):
    # Reviewer's F1: an agent pushes outside the grant; a later Owner event must not turn it green.
    head = _head(world, {"src/feature.py": "value = 2\n", ".github/workflows/x.yml": "on: push\n"})
    decision = _approve(
        world, head, _body(_envelope(world, _payload())), author=AGENT, sender=sender
    )
    assert decision["approve"] is False
    assert decision["reason"].startswith("ATTESTATION_PROTECTED_PATH")


def test_no_attestation_means_no_automatic_approval(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    decision = _approve(world, head, _body(), author=OWNER, sender=OWNER)
    assert decision == {**decision, "approve": False, "reason": "NO_OWNER_ATTESTATION"}


def test_grant_for_an_unregistered_agent_is_not_approved(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    decision = _approve(world, head, _body(_envelope(world, _payload(agent_login="unknown-bot"))))
    assert decision["approve"] is False
    assert decision["reason"] == "ATTESTATION_AGENT_NOT_REGISTERED"


@pytest.mark.parametrize(
    ("files", "overrides", "reason"),
    [
        ({"docs/notes.md": "x\n"}, {}, "ATTESTATION_PATH_OUT_OF_SCOPE"),
        (
            {"src/feature.py": "2\n"},
            {"expires_at": (NOW - timedelta(seconds=1)).isoformat()},
            "ATTESTATION_EXPIRED",
        ),
        (
            {"src/feature.py": "2\n"},
            {"allowed_actions": ["REPOSITORY_PUSH"]},
            "ATTESTATION_MERGE_NOT_GRANTED",
        ),
    ],
)
def test_approval_is_withheld_for_anything_the_grant_does_not_cover(
    world, files, overrides, reason
):
    head = _head(world, files)
    decision = _approve(world, head, _body(_envelope(world, _payload(**overrides))))
    assert decision["approve"] is False
    assert decision["reason"].startswith(reason)


def test_approval_cli_never_fails_the_job(world, tmp_path):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    event = _event(world, head, "no markers at all")
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    proc = subprocess.run(
        [
            "python",
            "scripts/ops/trusted_merge_lane_gate.py",
            "--mode",
            "approve",
            "--event-json",
            str(event_file),
            "--repo-root",
            str(world["repo"]),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["approve"] is False


@pytest.mark.parametrize("author", [OWNER, "someone-else"])
def test_a_copied_grant_does_not_approve_someone_elses_pr(world, author):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    decision = _approve(
        world, head, _body(_envelope(world, _payload())), author=author, sender=author
    )
    assert decision["approve"] is False
    assert decision["reason"] == "PR_NOT_AUTHORED_BY_GRANTED_AGENT"


@pytest.mark.parametrize(
    "path",
    [
        "GEMINI.md",
        "src/.vscode/tasks.json",
        ".nexus-core/config.toml",
        "src/conftest.py",
        ".gitattributes",
    ],
)
def test_more_files_that_run_on_the_owner_machine_are_protected(world, path):
    head = _head(world, {path: "x\n"})
    with pytest.raises(LaneBindingError, match="ATTESTATION_PROTECTED_PATH"):
        _validate(world, head, _body(_envelope(world, _payload(allowed_paths=[path]))))


def test_approval_cli_turns_unexpected_errors_into_no_approval(world, tmp_path):
    repo = world["repo"]
    weird = repo / "src" / b"bad-\xff.py".decode("utf-8", "surrogateescape")
    weird.write_bytes(b"x = 1\n")
    head = _commit(repo, "non-utf8 path")
    event = _event(world, head, _body(_envelope(world, _payload())))
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")
    proc = subprocess.run(
        [
            "python",
            "scripts/ops/trusted_merge_lane_gate.py",
            "--mode",
            "approve",
            "--event-json",
            str(event_file),
            "--repo-root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["approve"] is False


def test_a_merge_that_reverts_a_newer_protected_change_is_not_covered(world):
    from scripts.ops.trusted_merge_lane_gate import approval_decision

    repo = world["repo"]
    (repo / "AGENTS.md").write_text("v0\n", encoding="utf-8")
    stale_base = _commit(repo, "AGENTS v0")
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "agent", stale_base], check=True
    )
    (repo / "src" / "feature.py").write_text("value = 2\n", encoding="utf-8")
    _commit(repo, "agent feature")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    (repo / "AGENTS.md").write_text("v1 owner change\n", encoding="utf-8")
    main_tip = _commit(repo, "owner updates AGENTS")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "agent"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "merge", "-q", "--no-commit", "--no-ff", main_tip], check=False
    )
    subprocess.run(["git", "-C", str(repo), "checkout", stale_base, "--", "AGENTS.md"], check=True)
    head = _commit(repo, "merge main, keep old AGENTS")
    # A two-dot diff against the stale base would not show AGENTS.md at all.
    assert "AGENTS.md" not in _git(repo, "diff", "--name-only", stale_base, head).split()
    world["base"] = stale_base
    event = _event(world, head, _body(_envelope(world, _payload())))
    event["workflow_sha"] = main_tip
    decision = approval_decision(event, repo_root=repo, now=NOW)
    assert decision["approve"] is False
    assert decision["reason"] == "ATTESTATION_PROTECTED_PATH:AGENTS.md"


def test_missing_history_for_the_merge_base_fails_closed(world):
    head = _head(world, {"src/feature.py": "value = 2\n"})
    event = _event(world, head, _body(_envelope(world, _payload())))
    event["workflow_sha"] = "f" * 40
    with pytest.raises(LaneBindingError):
        validate_event(event, repo_root=world["repo"], now=NOW)
