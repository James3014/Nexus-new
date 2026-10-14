"""Evidence Coverage on the live self-hosted task path (#2181, Step 2).

Owner decisions under test:
- the expected-evidence universe comes only from the hashed task card;
- only a card that declares a universe sets ``core_envelope_required``, and an
  incomplete or failed Core coverage verdict then blocks the candidate commit;
- legacy cards behave as before and claim no coverage;
- complete coverage grants no approval, merge or release authority.

The ``test_live_*`` witnesses drive the real chain (card -> Gateway
``nexus_worker_candidate`` -> real service runtime -> CandidateVerifier ->
Core seam -> durable receipt -> reload) in a subprocess with
``NEXUS_CORE_REPO_ROOT`` at a clean checkout of the pinned
``CANONICAL_CORE_REVISION``. The subprocess is required because the in-tree
``product`` package shadows Core. The checkout is materialized from
``NEXUS_CORE_REPO_ROOT`` when that names a nexus-core clone containing the pin,
else fetched (depth 1) from the public GitHub repository; without either the
Core-backed witnesses skip with an explicit reason. The Core-unavailable
witness needs no Core and always runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.orchestrator.ambient_core import (
    CORE_VERDICT_SCHEMA,
    LazyCanonicalCoreControlPort,
    build_core_verdict,
    core_universe_identity,
    live_core_db_path,
)
from nexus.orchestrator.task_contract import (
    TASK_CARD_EXPECTED_EVIDENCE_FENCE,
    SelfHostedTaskContract,
    parse_task_card_expected_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DRIVER = Path(__file__).with_name("_evidence_coverage_live_driver.py")
CORE_GITHUB_URL = "https://github.com/James3014/nexus-core.git"
_AUTHORITY_WORDS = ("approv", "merge", "release", "authority", "promot", "integrat")


def _pinned_core_revision() -> str:
    source = (REPO_ROOT / "nexus/orchestrator/canonical_core_transport.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^CANONICAL_CORE_REVISION = "([0-9a-f]{40})"$', source, re.MULTILINE)
    assert match, "CANONICAL_CORE_REVISION must be an exact 40-hex pin"
    return match.group(1)


def _subject(sid: str, kind: str, mode: str = "REQUIRED", applicability: str = "APPLICABLE"):
    return {
        "logical_subject_id": sid,
        "evidence_kind": kind,
        "requirement_mode": mode,
        "applicability": applicability,
    }


DIFF_CHECK = _subject("git diff --check", "verifier-run")
SECURITY_REVIEW = _subject("review:security", "review-report")

SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "complete",
        "task_id": "cov-complete",
        "verifiers": ["git diff --check"],
        "universe": {
            "universe_generation": 1,
            "subjects": [
                DIFF_CHECK,
                _subject("lint:ruff", "lint-report", "CONDITIONALLY_REQUIRED", "NOT_APPLICABLE"),
            ],
        },
    },
    {
        "name": "missing",
        "task_id": "cov-missing",
        "verifiers": ["git diff --check"],
        "universe": {"universe_generation": 1, "subjects": [DIFF_CHECK, SECURITY_REVIEW]},
    },
    {
        "name": "fail",
        "task_id": "cov-fail",
        "verifiers": ["git diff --check", "git diff --exit-code"],
        "universe": {
            "universe_generation": 1,
            "subjects": [_subject("git diff --exit-code", "verifier-run")],
        },
    },
    {
        "name": "cond_missing",
        "task_id": "cov-cond-missing",
        "verifiers": ["git diff --check"],
        "universe": {
            "universe_generation": 1,
            "subjects": [
                DIFF_CHECK,
                _subject("lint:ruff", "lint-report", "CONDITIONALLY_REQUIRED", "APPLICABLE"),
            ],
        },
    },
    {
        "name": "duplicate",
        "task_id": "cov-duplicate",
        "verifiers": ["git diff --check", "git diff --check"],
        "universe": {"universe_generation": 1, "subjects": [DIFF_CHECK, SECURITY_REVIEW]},
    },
    {
        "name": "wrong_generation",
        "task_id": "cov-wrong-gen",
        "verifiers": ["git diff --check"],
        "remint_generation": 3,
        "universe": {"universe_generation": 2, "subjects": [DIFF_CHECK]},
    },
    {
        "name": "drop_universe",
        "task_id": "cov-drop",
        "verifiers": ["git diff --check"],
        "drop_universe": True,
        "universe": {"universe_generation": 1, "subjects": [DIFF_CHECK, SECURITY_REVIEW]},
    },
    {
        "name": "legacy",
        "task_id": "cov-legacy",
        "verifiers": ["git diff --check"],
        "universe": None,
    },
]


def _git(cwd: Path, *args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _materialize_core(dest: Path, revision: str) -> str | None:
    """Clean detached Core checkout at ``revision``; returns a skip reason on failure."""
    errors = []
    source = os.environ.get("NEXUS_CORE_REPO_ROOT", "").strip()
    if source and (Path(source) / ".git").exists():
        shutil.rmtree(dest, ignore_errors=True)
        cloned = _git(dest.parent, "clone", "-q", "--no-checkout", source, str(dest))
        if (
            cloned.returncode == 0
            and _git(dest, "checkout", "-q", "--detach", revision).returncode == 0
        ):
            return None
        errors.append(f"local clone of {source} lacks {revision}")
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    _git(dest, "init", "-q")
    fetched = _git(dest, "fetch", "-q", "--depth", "1", CORE_GITHUB_URL, revision)
    if (
        fetched.returncode == 0
        and _git(dest, "checkout", "-q", "--detach", "FETCH_HEAD").returncode == 0
    ):
        return None
    errors.append(f"fetch from {CORE_GITHUB_URL} failed: {fetched.stderr.strip()[:200]}")
    return "; ".join(errors)


def _run_driver(
    work: Path, scenarios: list[dict[str, Any]], core_root: Path | None
) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    spec = {"work": str(work / "run"), "out": str(work / "out.json"), "scenarios": scenarios}
    (work / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_REPO_ROOT"}
    # Same import environment as this test process (CI executors provide
    # dependencies such as nexus_runtime through sys.path), repo first.
    inherited = [entry for entry in sys.path if entry and Path(entry).exists()]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([str(REPO_ROOT), *inherited]))
    # Like the deployed Gateway: no bytecode lands in the Core checkout, which
    # would make it dirty and therefore not pinned.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if core_root is not None:
        env["NEXUS_CORE_REPO_ROOT"] = str(core_root)
    proc = subprocess.run(
        [sys.executable, "-W", "ignore", str(DRIVER), str(work / "spec.json")],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    results = json.loads((work / "out.json").read_text(encoding="utf-8"))
    for name in (scenario["name"] for scenario in scenarios):
        value = results[name]
        if isinstance(value, dict):
            assert "driver_error" not in value, f"{name}: {value.get('trace')}"
            assert value.get("gateway_is_error") is False, f"{name}: {value.get('gateway_error')}"
    return results


def _core_unobtainable(message: str) -> None:
    """Skip locally, but never let CI pass these enforcement witnesses by skipping."""
    if os.environ.get("CI", "").strip():
        pytest.fail(f"{message} (CI forbids skipping the Evidence Coverage witnesses)")
    pytest.skip(message)


@pytest.fixture(scope="module")
def pinned_core(tmp_path_factory) -> Path:
    revision = _pinned_core_revision()
    dest = tmp_path_factory.mktemp("core") / "nexus-core"
    reason = _materialize_core(dest, revision)
    if reason is not None:
        _core_unobtainable(f"pinned nexus-core {revision} not obtainable: {reason}")
    head = _git(dest, "rev-parse", "HEAD").stdout.strip()
    assert head == revision
    return dest


@pytest.fixture(scope="module")
def live(pinned_core, tmp_path_factory) -> dict[str, Any]:
    results = _run_driver(tmp_path_factory.mktemp("live"), SCENARIOS, pinned_core)
    assert results["core_available"] is True, results["core_import_error"]
    return results


def _verdict(result: dict[str, Any]) -> dict[str, Any]:
    verdict = result["core_verdict"]
    assert isinstance(verdict, dict) and verdict["schema"] == CORE_VERDICT_SCHEMA
    return verdict


def _categories(verdict: dict[str, Any]) -> dict[str, str]:
    return {e["logical_subject_id"]: e["category"] for e in verdict["coverage"]["entries"]}


def _assert_blocked(result: dict[str, Any]) -> None:
    assert result["status"] == "FINAL_BLOCK"
    assert result["receipt_verified"] is False
    assert result["receipt_commit_allowed"] is False
    assert result["candidate_commit_sha"] is None
    assert _verdict(result)["blocking"] is True
    assert _verdict(result)["coverage_complete"] is False
    # A blocked receipt never reads as Core-verified downstream.
    assert result["core_verification_status"].startswith("HOST_BLOCKED:")


# --- live chain witnesses (real Core) ---------------------------------------


def test_live_card_universe_reaches_request_from_card_only(live):
    complete = live["complete"]
    assert complete["request_expected_evidence"] == parse_task_card_expected_evidence(
        "```"
        + TASK_CARD_EXPECTED_EVIDENCE_FENCE
        + "\n"
        + json.dumps(SCENARIOS[0]["universe"])
        + "\n```\n"
    )
    assert complete["request_core_envelope_required"] is True


def test_live_missing_evidence_blocks_unverifiable_missing(live):
    result = live["missing"]
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["core_status"] == "UNVERIFIABLE"
    assert verdict["integrity"] == "MISSING"
    assert "MISSING" in verdict["reason_codes"]
    assert _categories(verdict)["review:security"] == "NOT_COVERED"
    assert verdict["core_provenance"]["status"] == "CORE_REVISION_PINNED"


def test_live_present_fail_blocks_failed_verification(live):
    result = live["fail"]
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["core_status"] == "FAILED_VERIFICATION"
    entry = verdict["coverage"]["entries"][0]
    assert entry["category"] == "COVERED" and entry["observed_status"] == "FAIL"
    assert result["db_verification_row"]["core_status"] == "FAILED_VERIFICATION"


def test_live_conditional_not_applicable_does_not_block(live):
    result = live["complete"]
    verdict = _verdict(result)
    assert verdict["blocking"] is False
    assert _categories(verdict) == {
        "git diff --check": "COVERED",
        "lint:ruff": "CONDITIONALLY_NOT_APPLICABLE",
    }
    assert result["receipt_verified"] is True
    assert result["receipt_commit_allowed"] is True


def test_live_conditional_required_but_missing_does_not_pass(live):
    result = live["cond_missing"]
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["core_status"] == "UNVERIFIABLE"
    assert _categories(verdict)["lint:ruff"] == "NOT_COVERED"


def test_live_duplicate_evidence_gives_no_coverage_gain(live):
    result = live["duplicate"]
    _assert_blocked(result)
    categories = _categories(_verdict(result))
    assert list(categories.values()).count("COVERED") == 1
    assert categories["review:security"] == "NOT_COVERED"


def _assert_rejected_at_intake(result: dict[str, Any], code: str) -> None:
    assert f"TASK_CARD_EVIDENCE_BINDING_INVALID:{code}" in result["submit_error"]
    # Nothing ran: no state, no candidate, no Core session.
    assert result["status"] is None
    assert result["candidate_commit_sha"] is None
    assert result["core_session_id"] is None


def test_live_wrong_generation_is_rejected(live):
    _assert_rejected_at_intake(live["wrong_generation"], "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH")


def test_live_dropped_universe_is_rejected(live):
    result = live["drop_universe"]
    assert result["request_has_evidence_keys"] == ["core_envelope_required", "expected_evidence"]
    _assert_rejected_at_intake(result, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH")


def test_live_legacy_task_unchanged_and_claims_no_coverage(live):
    result = live["legacy"]
    assert result["request_has_evidence_keys"] == []
    assert result["receipt_verified"] is True
    assert result["receipt_commit_allowed"] is True
    assert result["core_verdict"] is None
    assert result["core_verification_status"] == ""
    assert result["core_session_id"] is None
    assert result["core_db_exists"] is False


def test_live_complete_coverage_carries_no_authority(live):
    result = live["complete"]
    verdict = _verdict(result)
    assert verdict["coverage_complete"] is True
    assert result["core_verification_status"] == "VERIFIED"

    def keys(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [*value, *(k for item in value.values() for k in keys(item))]
        if isinstance(value, list):
            return [k for item in value for k in keys(item)]
        return []

    for key in keys(verdict):
        assert not any(word in key.lower() for word in _AUTHORITY_WORDS), key
    # Commit permission stays tied to the verified result; nothing is approved.
    assert result["receipt_commit_allowed"] is result["receipt_verified"]
    assert result["promotion_status"] != "APPROVED"


def test_live_gateway_process_reports_pinned_core_provenance(live):
    provenance = live["gateway_core_provenance"]
    assert provenance["status"] == "CORE_REVISION_PINNED"
    assert provenance["fail_closed"] is False
    assert provenance["observed_commit"] == _pinned_core_revision()
    assert provenance["observed_in_pid"] == live["driver_pid"]


def test_live_receipt_survives_reload_from_state_dir(live):
    for name in ("complete", "missing", "fail", "cond_missing", "duplicate"):
        result = live[name]
        assert result["reloaded_core_verdict"] == result["core_verdict"], name
    assert live["complete"]["db_verification_row"]["core_status"] == "VERIFIED"
    assert live["missing"]["db_verification_row"]["core_status"] == "UNVERIFIABLE"


def test_live_core_revision_mismatch_fails_closed(pinned_core, tmp_path):
    drifted = tmp_path / "drifted-core"
    assert _git(tmp_path, "clone", "-q", str(pinned_core), str(drifted)).returncode == 0
    commit = _git(
        drifted,
        "-c",
        "user.name=Drift",
        "-c",
        "user.email=drift@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "drift",
    )
    assert commit.returncode == 0, commit.stderr
    results = _run_driver(tmp_path / "work", [SCENARIOS[0]], drifted)
    result = results["complete"]
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["core_provenance"]["status"] == "CORE_REVISION_MISMATCH"
    assert "CORE_PROVENANCE_NOT_PINNED:CORE_REVISION_MISMATCH" in verdict["host_reason_codes"]
    assert results["gateway_core_provenance"]["status"] == "CORE_REVISION_MISMATCH"
    # Core itself VERIFIED this candidate; only the host refused it.
    assert verdict["core_status"] == "VERIFIED"
    assert result["core_verification_status"] == "HOST_BLOCKED:VERIFIED"
    assert results["gateway_core_provenance"]["fail_closed"] is True


def test_live_core_unavailable_fails_closed_for_universe_task(tmp_path):
    results = _run_driver(tmp_path / "work", [SCENARIOS[0], SCENARIOS[-1]], None)
    assert results["core_available"] is False
    result = results["complete"]
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["host_reason_codes"] == [
        "CORE_TRANSPORT_FAILED:CANONICAL_NEXUS_CORE_UNAVAILABLE"
    ]
    assert result["reloaded_core_verdict"] == verdict
    # A legacy task in the same process is untouched by Core being absent.
    legacy = results["legacy"]
    assert legacy["receipt_verified"] is True and legacy["core_verdict"] is None


# --- seam units (no Core needed) --------------------------------------------


def test_card_parser_legacy_valid_and_fail_closed():
    assert parse_task_card_expected_evidence("task_id: `x`\nAUTO_CHAIN: false\n") is None
    block = "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "\n{}\n```\n"
    universe = {"universe_generation": 4, "subjects": [SECURITY_REVIEW, DIFF_CHECK]}
    good = block.replace("{}", json.dumps(universe))
    parsed = parse_task_card_expected_evidence(good)
    assert parsed is not None
    assert [s["logical_subject_id"] for s in parsed["subjects"]] == [
        "git diff --check",
        "review:security",
    ]
    for bad in (
        good + good,
        good.replace(
            "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE,
            "```json " + TASK_CARD_EXPECTED_EVIDENCE_FENCE,
        ),
        "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "\n{}\n",
        block.replace("{}", "{not json"),
        block.replace("{}", json.dumps({"universe_generation": 1, "subjects": []})),
    ):
        with pytest.raises(ValueError, match="TASK_CARD_EXPECTED_EVIDENCE_INVALID"):
            parse_task_card_expected_evidence(bad)


def _universe_contract(tmp_path: Path, generation: int = 1) -> SelfHostedTaskContract:
    return SelfHostedTaskContract(
        task_id="verdict-unit",
        objective="unit",
        controller_revision="a" * 40,
        target_base_revision="a" * 40,
        controller_repo_root=str(tmp_path),
        target_repo_root=str(tmp_path / "t"),
        target_worktree_root=str(tmp_path),
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_evidence={"universe_generation": generation, "subjects": [DIFF_CHECK]},
    )


def _verified_projection(
    generation: int,
    provenance: str = "CORE_REVISION_PINNED",
    *,
    identity: str | None = None,
    entries: list[dict[str, Any]] | None = None,
    unexpected: list[dict[str, Any]] | None = None,
):
    declared = {"universe_generation": generation, "subjects": [DIFF_CHECK]}
    return {
        "core_response": {
            "verification": {
                "status": "VERIFIED",
                "reason_codes": [],
                "integrity": "VALID",
                "coverage": {
                    "universe_generation": generation,
                    "universe_identity": identity or core_universe_identity(declared),
                    "entries": entries
                    if entries is not None
                    else [{**DIFF_CHECK, "category": "COVERED", "observed_status": "PASS"}],
                    "unexpected_subjects": unexpected or [],
                },
            }
        },
        "core_provenance": {"status": provenance},
    }


def test_verdict_rejects_coverage_for_wrong_generation(tmp_path):
    contract = _universe_contract(tmp_path, generation=1)
    verdict = build_core_verdict(contract=contract, projection=_verified_projection(2))
    assert verdict["blocking"] is True
    assert "CORE_COVERAGE_GENERATION_MISMATCH" in verdict["host_reason_codes"]
    ok = build_core_verdict(contract=contract, projection=_verified_projection(1))
    assert ok["blocking"] is False and ok["coverage_complete"] is True


def test_verdict_requires_pinned_core_provenance(tmp_path):
    contract = _universe_contract(tmp_path)
    for status in ("CORE_REVISION_MISMATCH", "CORE_IDENTITY_UNAVAILABLE"):
        verdict = build_core_verdict(contract=contract, projection=_verified_projection(1, status))
        assert verdict["blocking"] is True
        assert f"CORE_PROVENANCE_NOT_PINNED:{status}" in verdict["host_reason_codes"]


def test_verdict_for_legacy_contract_claims_no_coverage():
    verdict = build_core_verdict(
        contract=SimpleNamespace(task_id="legacy"), projection=_verified_projection(1)
    )
    assert verdict["universe_declared"] is False
    assert verdict["coverage"] is None
    assert verdict["coverage_complete"] is False
    assert verdict["blocking"] is False


def test_lazy_port_creates_nothing_until_used(tmp_path):
    port = LazyCanonicalCoreControlPort(tmp_path / "state")
    assert port.db_path == live_core_db_path(tmp_path / "state")
    assert port.db_path.startswith(str((tmp_path / "state").resolve()))
    assert not (tmp_path / "state").exists()
    assert port._port is None


def test_default_gateway_injects_lazy_core_port_under_canonical_state(monkeypatch, tmp_path):
    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

    canonical = tmp_path / "canonical-state"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    gateway = UnifiedMCPGateway()
    port = gateway.service.ambient_core_port
    assert isinstance(port, LazyCanonicalCoreControlPort)
    assert port.db_path == live_core_db_path(canonical)
    assert "/tmp/nexus_canary" not in port.db_path
    assert not Path(port.db_path).exists()


def test_detached_worker_injects_lazy_core_port(monkeypatch, tmp_path):
    import nexus.orchestrator.self_hosted_task_worker as worker

    captured: dict[str, Any] = {}

    class Capture:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def _wait_for_owner(self, *args):
            return False

    monkeypatch.setattr(worker, "SelfHostedTaskService", Capture)
    monkeypatch.setattr(
        sys, "argv", ["worker", "--state-dir", str(tmp_path), "--task-id", "t", "--attempt-id", "a"]
    )
    assert worker.main() == 2
    port = captured["ambient_core_port"]
    assert isinstance(port, LazyCanonicalCoreControlPort)
    assert port.db_path == live_core_db_path(tmp_path)


def _core_available_transport(monkeypatch):
    import nexus.orchestrator.canonical_core_transport as transport

    def fake_hash(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    monkeypatch.setattr(transport, "CORE_AVAILABLE", True, raising=False)
    for name in (
        "acceptance_contract_hash",
        "change_set_hash",
        "verification_plan_hash",
        "evidence_bundle_hash",
        "change_manifest_hash",
    ):
        monkeypatch.setattr(transport, name, fake_hash, raising=False)
    captured: dict[str, Any] = {}

    def fake_verify(request):
        captured["request"] = request
        return 200, {
            "schema": transport.GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
            "verification": {"status": "UNVERIFIABLE", "reason_codes": ["MISSING"]},
            "hashes": {},
        }

    monkeypatch.setattr(transport, "verify_generic_changeset", fake_verify, raising=False)
    return transport, captured


def test_transport_has_no_canary_defaults(monkeypatch, tmp_path):
    transport, captured = _core_available_transport(monkeypatch)
    port = transport.CanonicalNexusCoreTransportPort(db_path=tmp_path / "core.sqlite")
    prep = {
        "session_id": "cms_" + "1" * 32,
        "binding_hash": "sha256:" + "2" * 64,
        "source_revision": "git-commit:" + "3" * 40,
    }
    request = {"task_id": "no-canary", "allowed_files": ["README.md"], "verifier_commands": ["v"]}
    # Missing candidate worktree: no synthetic change list, fail closed.
    with pytest.raises(RuntimeError, match="CANONICAL_CORE_CANDIDATE_WORKTREE_MISSING"):
        port.verify_candidate(preparation=prep, request=request, candidate_state_hash="s")
    # Missing contract identity / scope / verifier set: nothing is defaulted.
    manifest = {
        "source_tree": "git-tree:" + "0" * 40,
        "target_tree": "git-tree:" + "1" * 40,
        "entries": [
            {
                "path": "README.md",
                "change_type": "MODIFY",
                "before_oid": "a" * 40,
                "after_oid": "b" * 40,
                "before_mode": "100644",
                "after_mode": "100644",
            }
        ],
    }
    for field, code in (
        ("task_id", "CANONICAL_CORE_CONTRACT_IDENTITY_MISSING"),
        ("allowed_files", "CANONICAL_CORE_ALLOWED_PATHS_MISSING"),
        ("verifier_commands", "CANONICAL_CORE_VERIFIERS_MISSING"),
    ):
        partial = {k: v for k, v in request.items() if k != field}
        with pytest.raises(RuntimeError, match=code):
            port.verify_candidate(
                preparation=prep,
                request=partial,
                candidate_state_hash="s",
                change_manifest=manifest,
            )
    # Absent verifier evidence is sent as absent, never as a synthetic PASS,
    # and the removed canary knobs no longer change the request.
    port.verify_candidate(
        preparation=prep,
        request=request,
        candidate_state_hash="s",
        change_manifest=manifest,
        force_scope_escape=True,
        force_fail=True,
    )
    assert captured["request"]["evidence_bundle"]["observations"] == []
    assert [e["path"] for e in captured["request"]["change_manifest"]["entries"]] == ["README.md"]
    assert captured["request"]["acceptance_contract"]["contract_id"] == "no-canary"
    # The session DB is created only on use, at the caller's path.
    assert (tmp_path / "core.sqlite").exists()


def test_transport_binding_requires_exact_source_revision(monkeypatch, tmp_path):
    transport, _ = _core_available_transport(monkeypatch)
    port = transport.CanonicalNexusCoreTransportPort(db_path=tmp_path / "core.sqlite")
    with pytest.raises(RuntimeError, match="CANONICAL_CORE_SOURCE_REVISION_MISSING"):
        port.open_or_reuse_mutation_binding(
            task_id="t",
            attempt_id="a",
            request={"allowed_files": ["README.md"], "verifier_commands": ["v"]},
        )
    with pytest.raises(RuntimeError, match="CANONICAL_CORE_ATTEMPT_IDENTITY_MISSING"):
        port.open_or_reuse_mutation_binding(task_id="t", request={"controller_revision": "a" * 40})
    assert not (tmp_path / "core.sqlite").exists()


def test_gateway_status_and_health_report_in_process_core_provenance(monkeypatch, tmp_path):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    from scripts.ops import nexus_mcp_gateway_http

    status = gateway_module.gateway_core_provenance()
    assert status["observed_in_pid"] == os.getpid()
    assert status["server_instance_id"] == gateway_module.SERVER_INSTANCE_ID
    assert isinstance(status["fail_closed"], bool)
    assert status["fail_closed"] is (status["status"] != "CORE_REVISION_PINNED")
    health = nexus_mcp_gateway_http.runtime_identity()
    assert set(health["core_provenance"]) == {
        "status",
        "expected_revision",
        "observed_commit",
        "fail_closed",
    }

    import nexus.orchestrator.canonical_core_transport as transport

    def explode():
        raise RuntimeError("probe broke")

    monkeypatch.setattr(transport, "core_provenance_status", explode)
    failed = gateway_module.gateway_core_provenance(refresh=True)
    assert failed["status"] == "CORE_PROVENANCE_PROBE_FAILED"
    assert failed["fail_closed"] is True
    monkeypatch.undo()
    gateway_module.gateway_core_provenance(refresh=True)


def test_gateway_status_tool_carries_core_provenance(monkeypatch, tmp_path):
    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(tmp_path / "state"))
    gateway = UnifiedMCPGateway()
    monkeypatch.setattr(gateway, "_observe_upstream_freshness", lambda **kwargs: {})
    status = gateway._gateway_status()
    assert status["core_provenance"]["observed_in_pid"] == os.getpid()
    assert "status" in status["core_provenance"]


# --- review fixes (#2201): witnesses ----------------------------------------


def test_live_coverage_identity_is_the_host_computed_card_identity(live):
    verdict = _verdict(live["complete"])
    assert verdict["coverage"]["universe_identity"] == core_universe_identity(
        SCENARIOS[0]["universe"]
    )


@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"identity": "sha256:" + "1" * 64}, "CORE_COVERAGE_IDENTITY_MISMATCH"),
        (
            {
                "entries": [
                    {
                        **DIFF_CHECK,
                        "evidence_kind": "other-kind",
                        "category": "COVERED",
                        "observed_status": "PASS",
                    }
                ]
            },
            "CORE_COVERAGE_UNIVERSE_MISMATCH",
        ),
        (
            {
                "entries": [
                    {
                        **DIFF_CHECK,
                        "requirement_mode": "CONDITIONALLY_REQUIRED",
                        "category": "COVERED",
                        "observed_status": "PASS",
                    }
                ]
            },
            "CORE_COVERAGE_UNIVERSE_MISMATCH",
        ),
        (
            {"unexpected": [{"logical_subject_id": "x:y", "evidence_kind": "k"}]},
            "CORE_COVERAGE_UNEXPECTED_SUBJECTS",
        ),
        (
            {
                "entries": [
                    {**DIFF_CHECK, "category": "COVERED", "observed_status": "PASS"},
                    {**DIFF_CHECK, "category": "COVERED", "observed_status": "PASS"},
                ]
            },
            "CORE_COVERAGE_UNIVERSE_MISMATCH",
        ),
    ],
)
def test_verdict_binds_coverage_exactly_to_the_card(tmp_path, overrides, code):
    verdict = build_core_verdict(
        contract=_universe_contract(tmp_path), projection=_verified_projection(1, **overrides)
    )
    assert verdict["blocking"] is True
    assert verdict["coverage_complete"] is False
    assert code in verdict["host_reason_codes"]


def test_card_parser_rejects_duplicate_subjects():
    block = "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "\n{}\n```\n"
    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK, DIFF_CHECK]}
    with pytest.raises(ValueError, match="TASK_CARD_EXPECTED_EVIDENCE_INVALID"):
        parse_task_card_expected_evidence(block.replace("{}", json.dumps(universe)))


def _card(tmp_path: Path, universe: dict[str, Any] | None) -> dict[str, str]:
    text = "task_id: `verdict-unit`\nAUTO_CHAIN: false\n"
    if universe is not None:
        text += "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "\n" + json.dumps(universe) + "\n```\n"
    card = tmp_path / "card.md"
    card.write_text(text, encoding="utf-8")
    return {
        "task_card_path": str(card),
        "task_card_hash": hashlib.sha256(card.read_bytes()).hexdigest(),
    }


def _legacy_contract(tmp_path: Path) -> SelfHostedTaskContract:
    return _universe_contract(tmp_path).model_copy(update={"expected_evidence": None})


def _host_service(tmp_path: Path, port: Any = None):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    return SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False, ambient_core_port=port
    )


def _local_receipt():
    from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt

    return VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id="verdict-unit",
        contract_hash="c" * 64,
        lease_id="lease",
        candidate_state_hash="candidate-state",
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        verified=True,
        candidate_commit_allowed=True,
        public_claim_allowed=False,
        production_ready=False,
        failure_reasons=[],
        verifier_evidence=(),
        candidate_commit_created=False,
        merge_performed=False,
    )


@pytest.mark.parametrize(
    "contract_kind, card_universe, request_extra, code",
    [
        # The universe and the Core flag were dropped from a universe card's task.
        ("legacy", "card", {}, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"),
        # A universe that no card declares.
        (
            "universe",
            None,
            {"core_envelope_required": True},
            "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH",
        ),
        # A universe task with no card binding at all.
        (
            "universe",
            "none",
            {"core_envelope_required": True},
            "EXPECTED_EVIDENCE_UNIVERSE_NOT_CARD_BOUND",
        ),
        # The universe kept but the Core requirement dropped.
        ("universe", "card", {}, "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"),
    ],
)
def test_finalize_binds_universe_and_core_flag_to_the_card(
    tmp_path, contract_kind, card_universe, request_extra, code
):
    from nexus.orchestrator.ambient_core import AmbientCoreVerdictBlocked

    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    contract = (
        _universe_contract(tmp_path) if contract_kind == "universe" else _legacy_contract(tmp_path)
    )
    request: dict[str, Any] = dict(request_extra)
    if card_universe != "none":
        request.update(_card(tmp_path, universe if card_universe == "card" else None))

    class NeverCalled:
        def verify_candidate(self, **kwargs):
            raise AssertionError("Core must not be reached")

    service = _host_service(tmp_path, NeverCalled())
    with pytest.raises(AmbientCoreVerdictBlocked) as blocked:
        service._verify_ambient_core_candidate(
            contract=contract,
            request=request,
            lease=SimpleNamespace(target_worktree=str(tmp_path)),
            state={"attempt_id": "attempt"},
            candidate=SimpleNamespace(candidate_state_hash="candidate-state"),
            verified=_local_receipt(),
        )
    receipt = blocked.value.receipt
    assert receipt.verified is False and receipt.candidate_commit_allowed is False
    assert receipt.core_verdict["host_reason_codes"] == [code]


def test_finalize_card_edited_after_intake_blocks(tmp_path):
    from nexus.orchestrator.ambient_core import AmbientCoreVerdictBlocked

    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    request = {"core_envelope_required": True, **_card(tmp_path, universe)}
    (tmp_path / "card.md").write_text("edited", encoding="utf-8")
    with pytest.raises(AmbientCoreVerdictBlocked) as blocked:
        _host_service(tmp_path, object())._verify_ambient_core_candidate(
            contract=_universe_contract(tmp_path),
            request=request,
            lease=None,
            state={},
            candidate=None,
            verified=_local_receipt(),
        )
    assert blocked.value.verdict["host_reason_codes"] == [
        "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISMATCH"
    ]


def test_legacy_card_task_without_universe_is_unchanged(tmp_path):
    request = _card(tmp_path, None)
    receipt = _local_receipt()
    out = _host_service(tmp_path)._verify_ambient_core_candidate(
        contract=_legacy_contract(tmp_path),
        request=request,
        lease=None,
        state={},
        candidate=None,
        verified=receipt,
    )
    assert out is receipt


def test_core_verified_but_host_blocked_never_reads_as_verified(tmp_path):
    from nexus.orchestrator.ambient_core import AmbientCoreVerdictBlocked

    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    projection = {
        **_verified_projection(1, "CORE_REVISION_MISMATCH"),
        "session_id": "cms_" + "1" * 32,
        "binding_hash": "sha256:" + "2" * 64,
        "candidate_state_hash": "candidate-state",
    }

    class VerifiedCore:
        def verify_candidate(self, **kwargs):
            return projection

    state = {
        "attempt_id": "attempt",
        "host_preparation": {
            "schema": "nexus.ambient-core-preparation.v1",
            "session_id": "cms_" + "1" * 32,
            "binding_id": "binding-1",
            "binding_hash": "sha256:" + "2" * 64,
            "operation_id": "operation-1",
            "attempt_id": "attempt",
            "acceptance_contract_hash": "sha256:" + "3" * 64,
            "source_revision": "git-commit:" + "8" * 40,
            "source_tree": "git-tree:" + "9" * 40,
        },
    }
    with pytest.raises(AmbientCoreVerdictBlocked) as blocked:
        _host_service(tmp_path, VerifiedCore())._verify_ambient_core_candidate(
            contract=_universe_contract(tmp_path),
            request={"core_envelope_required": True, **_card(tmp_path, universe)},
            lease=None,
            state=state,
            candidate=SimpleNamespace(candidate_state_hash="candidate-state"),
            verified=_local_receipt(),
        )
    receipt = blocked.value.receipt
    assert receipt.core_verdict["core_status"] == "VERIFIED"
    assert receipt.core_verification_status == "HOST_BLOCKED:VERIFIED"
    assert receipt.candidate_commit_allowed is False


def test_direct_lane_refuses_evidence_tasks(tmp_path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    claims = SelfHostedTaskService._direct_lane_claims_evidence
    assert claims(_card(tmp_path, universe)) is True
    assert claims({"core_envelope_required": True}) is True
    assert claims({"expected_evidence": universe}) is True
    assert claims(_card(tmp_path, None)) is False
    assert claims({}) is False


def test_core_provenance_is_cached_per_process(monkeypatch):
    import nexus.orchestrator.canonical_core_transport as transport
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    calls = []

    def counted():
        calls.append(1)
        return {"status": "CORE_UNAVAILABLE", "fail_closed": True}

    monkeypatch.setattr(transport, "core_provenance_status", counted)
    gateway_module.gateway_core_provenance(refresh=True)
    for _ in range(5):
        gateway_module.gateway_core_provenance()
        gateway_module.public_core_provenance()
    assert len(calls) == 1
    monkeypatch.undo()
    gateway_module.gateway_core_provenance(refresh=True)


def test_core_identity_git_probes_are_time_bounded(monkeypatch, tmp_path):
    import nexus.orchestrator.canonical_core_transport as transport

    seen = []

    def fake_check_output(args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return "" if args[1] == "status" else "a" * 40

    monkeypatch.setattr(transport.subprocess, "check_output", fake_check_output)
    transport.read_observed_core_identity(tmp_path)
    assert seen and all(isinstance(value, (int, float)) and value > 0 for value in seen)


def test_core_unobtainable_fails_in_ci_and_skips_locally(monkeypatch):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception):
        _core_unobtainable("no core")
    monkeypatch.delenv("CI")
    with pytest.raises(pytest.skip.Exception):
        _core_unobtainable("no core")


_PRELOAD_PROBE = """
import json, sys
from pathlib import Path
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway, gateway_core_provenance
if sys.argv[1] == "gateway-first":
    UnifiedMCPGateway(service=SelfHostedTaskService(
        state_dir=Path(sys.argv[2]), ephemeral=True, auto_reconcile=False))
from nexus.services.external_intelligence_core_binding import acceptance_contract_hash
contract = {"contract_id": "c", "requirements_hash": "sha256:" + "0" * 64,
            "required_verifier_ids": ["v"], "allowed_paths": ["a"], "deletion_policy": "FORBID"}
acceptance_contract_hash(contract)  # an EIA call that imports ``product``
print(json.dumps(gateway_core_provenance(refresh=True)))
"""


def test_gateway_startup_binds_product_to_core_before_eia(pinned_core, tmp_path):
    def probe(mode: str) -> dict[str, Any]:
        env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_REPO_ROOT"}
        inherited = [entry for entry in sys.path if entry and Path(entry).exists()]
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([str(REPO_ROOT), *inherited]))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["NEXUS_CORE_REPO_ROOT"] = str(pinned_core)
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", _PRELOAD_PROBE, mode, str(tmp_path / mode)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr[-3000:]
        return json.loads(proc.stdout.strip().splitlines()[-1])

    # Gateway startup first: Core owns ``product`` for the whole process.
    assert probe("gateway-first")["status"] == "CORE_REVISION_PINNED"
    # The hazard the preload removes: an EIA import first shadows Core.
    shadowed = probe("eia-first")
    assert shadowed["fail_closed"] is True
    assert "CORE_PRODUCT_SHADOWED" in str(shadowed.get("reason"))


# --- Codex re-review (#2201 at d9fb707a3): witnesses -------------------------


def _path_only(tmp_path: Path, universe: dict[str, Any] | None) -> dict[str, str]:
    return {"task_card_path": _card(tmp_path, universe)["task_card_path"]}


def test_direct_lane_reads_a_card_supplied_without_hash(tmp_path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    claims = SelfHostedTaskService._direct_lane_claims_evidence
    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    assert claims(_path_only(tmp_path, universe)) is True
    assert claims(_path_only(tmp_path, None)) is False
    # Unreadable or malformed cards fail closed for the direct lane.
    assert claims({"task_card_path": str(tmp_path / "missing.md")}) is True
    bad = tmp_path / "bad.md"
    bad.write_text(
        "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE + "\n{not json\n```\n", encoding="utf-8"
    )
    assert claims({"task_card_path": str(bad)}) is True


@pytest.mark.parametrize(
    "contract_kind, request_extra, code",
    [
        # A universe card supplied without its hash cannot be skipped.
        ("legacy", {}, "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"),
        # A universe is honoured only from a hash-bound card.
        ("universe", {"core_envelope_required": True}, "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISSING"),
    ],
)
def test_card_binding_reads_a_card_supplied_without_hash(
    tmp_path, contract_kind, request_extra, code
):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    contract = (
        _universe_contract(tmp_path) if contract_kind == "universe" else _legacy_contract(tmp_path)
    )
    request = {**request_extra, **_path_only(tmp_path, universe)}
    assert SelfHostedTaskService._card_evidence_binding_error(contract, request) == code


def test_verdict_names_both_universe_identities(tmp_path):
    contract = _universe_contract(tmp_path)
    verdict = build_core_verdict(contract=contract, projection=_verified_projection(1))
    assert "universe_identity" not in verdict
    assert verdict["contract_universe_identity"] == contract.universe_identity
    declared = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    assert verdict["core_universe_identity"] == core_universe_identity(declared)
    assert verdict["core_universe_identity"] == verdict["coverage"]["universe_identity"]
    assert verdict["contract_universe_identity"] != verdict["core_universe_identity"]
    legacy = build_core_verdict(
        contract=SimpleNamespace(task_id="legacy"), projection=_verified_projection(1)
    )
    assert legacy["contract_universe_identity"] is None
    assert legacy["core_universe_identity"] is None


def test_live_verdict_core_identity_matches_real_core(live):
    verdict = _verdict(live["complete"])
    assert verdict["core_universe_identity"] == verdict["coverage"]["universe_identity"]
    assert verdict["contract_universe_identity"].startswith("sha256:")
