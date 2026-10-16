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

# In-process seam units compute the card identity with the test reference of
# Core's formula (the in-tree ``product`` shadows Core here); the live driver
# uses the real pinned Core, and the two are proven equal below (#2246).
pytestmark = pytest.mark.usefixtures("reference_core_universe_identity")

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
    work: Path,
    scenarios: list[dict[str, Any]],
    core_root: Path | None,
    core_digest: tuple[str, str] | None = None,
) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    spec = {"work": str(work / "run"), "out": str(work / "out.json"), "scenarios": scenarios}
    (work / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "NEXUS_CORE_REPO_ROOT",
            "NEXUS_CORE_SOURCE_DIGEST",
            "NEXUS_CORE_SOURCE_DIGEST_REVISION",
        )
    }
    # Same import environment as this test process (CI executors provide
    # dependencies such as nexus_runtime through sys.path), repo first.
    inherited = [entry for entry in sys.path if entry and Path(entry).exists()]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([str(REPO_ROOT), *inherited]))
    # Like the deployed Gateway: no bytecode lands in the Core checkout, which
    # would make it dirty and therefore not pinned.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if core_root is not None:
        env["NEXUS_CORE_REPO_ROOT"] = str(core_root)
    if core_digest is not None:
        # What the Gateway auto-deployer exports for its pinned Core (#2246).
        env["NEXUS_CORE_SOURCE_DIGEST_REVISION"], env["NEXUS_CORE_SOURCE_DIGEST"] = core_digest
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
def pinned_core_digest(pinned_core) -> tuple[str, str]:
    """The deployer's expected source digest of the pinned checkout (#2246)."""
    from scripts.ops import nexus_gateway_auto_deploy as ad

    revision = _pinned_core_revision()
    computed = ad.core_source_digest(ad.Host(), pinned_core, revision)
    assert computed["source_digest_status"] == "COMPUTED", computed
    return revision, computed["source_digest"]


def test_deployer_source_digest_equals_pinned_core_identity(pinned_core, pinned_core_digest):
    """The Gateway auto-deployer's digest is what real Core's core_identity() reports."""
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import json, sys; sys.path.insert(0, sys.argv[1]);"
            "from product.protocol import core_identity; print(json.dumps(core_identity()))",
            str(pinned_core),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    identity = json.loads(proc.stdout.strip().splitlines()[-1])
    assert identity["build_identity"] == "UNSTAMPED"
    assert identity["source_digest"] == pinned_core_digest[1]
    assert pinned_core_digest[0] == _pinned_core_revision()


@pytest.fixture(scope="module")
def live(pinned_core, pinned_core_digest, tmp_path_factory) -> dict[str, Any]:
    results = _run_driver(
        tmp_path_factory.mktemp("live"), SCENARIOS, pinned_core, pinned_core_digest
    )
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


def test_live_core_revision_mismatch_fails_closed(pinned_core, pinned_core_digest, tmp_path):
    drifted = tmp_path / "drifted-core"
    assert _git(tmp_path, "clone", "-q", str(pinned_core), str(drifted)).returncode == 0
    # A drifted Core runs different source than the digest pinned for the
    # revision (#2246: identity is the source digest, not git HEAD).
    init = drifted / "product" / "__init__.py"
    init.write_text(init.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    commit = _git(
        drifted,
        "-c",
        "user.name=Drift",
        "-c",
        "user.email=drift@example.com",
        "commit",
        "-q",
        "-a",
        "-m",
        "drift",
    )
    assert commit.returncode == 0, commit.stderr
    results = _run_driver(tmp_path / "work", [SCENARIOS[0]], drifted, pinned_core_digest)
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
    assert results["gateway_core_provenance"]["reason"] == "CORE_SOURCE_DIGEST_MISMATCH"


def test_live_gateway_pins_core_by_source_digest(live, pinned_core_digest):
    provenance = live["gateway_core_provenance"]
    assert provenance["identity_source"] == "source_digest"
    assert provenance["build_identity"] == "UNSTAMPED"
    assert provenance["observed_source_digest"] == pinned_core_digest[1]
    assert provenance["expected_source_digest"] == pinned_core_digest[1]
    assert live["public_core_provenance"]["identity_source"] == "source_digest"


def test_live_stray_pycache_keeps_core_pinned(pinned_core, pinned_core_digest, tmp_path):
    """Regression for 2026-10-15: bytecode in the in-use Core checkout no longer
    flips provenance to unavailable."""
    checkout = tmp_path / "core-with-pycache"
    assert _git(tmp_path, "clone", "-q", str(pinned_core), str(checkout)).returncode == 0
    for package in ("product", "product/protocol", "product/adapters"):
        cache = checkout / package / "__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "stray.cpython-312.pyc").write_bytes(b"\x00stray")
    results = _run_driver(tmp_path / "work", [SCENARIOS[0]], checkout, pinned_core_digest)
    provenance = results["gateway_core_provenance"]
    assert provenance["status"] == "CORE_REVISION_PINNED", provenance
    assert provenance["observed_commit"] == _pinned_core_revision()
    verdict = _verdict(results["complete"])
    assert verdict["blocking"] is False
    assert verdict["core_provenance"]["status"] == "CORE_REVISION_PINNED"


def test_live_checkout_without_source_digest_pin_fails_closed(pinned_core, tmp_path):
    results = _run_driver(tmp_path / "work", [SCENARIOS[0]], pinned_core)
    provenance = results["gateway_core_provenance"]
    assert provenance["status"] == "CORE_IDENTITY_UNAVAILABLE"
    assert provenance["reason"] == "CORE_SOURCE_DIGEST_UNPINNED"
    assert provenance["fail_closed"] is True
    result = results["complete"]
    _assert_blocked(result)
    assert (
        "CORE_PROVENANCE_NOT_PINNED:CORE_IDENTITY_UNAVAILABLE"
        in (_verdict(result)["host_reason_codes"])
    )


def _stamp_core_copy(pinned_core: Path, dest: Path, *, dirty: bool = False) -> Path:
    """A copy of the pinned Core stamped exactly as Core's setup.py would stamp a wheel."""
    shutil.copytree(pinned_core / "product", dest / "product")
    tree = _git(pinned_core, "rev-parse", "HEAD^{tree}").stdout.strip()
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from product.protocol.build_identity import make_build_identity, source_digest\n"
        "stamp = make_build_identity(version='0-test', git_commit=sys.argv[2],"
        " git_tree=sys.argv[3], git_dirty=sys.argv[4] == '1',"
        " source_digest_value=source_digest(Path(sys.argv[1]) / 'product'))\n"
        "Path(sys.argv[1], 'product', '_build_identity.json').write_text(json.dumps(stamp))\n"
    )
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(dest),
            _pinned_core_revision(),
            tree,
            "1" if dirty else "0",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return dest


def test_live_embedded_build_stamp_is_pinned_without_digest_env(pinned_core, tmp_path):
    """Installed-wheel path: Core's EMBEDDED stamp at the pin, no deployer digest."""
    stamped = _stamp_core_copy(pinned_core, tmp_path / "stamped")
    results = _run_driver(tmp_path / "work", [SCENARIOS[0]], stamped)
    provenance = results["gateway_core_provenance"]
    assert provenance["status"] == "CORE_REVISION_PINNED", provenance
    assert provenance["identity_source"] == "build_stamp"
    assert provenance["build_identity"] == "EMBEDDED"
    assert _verdict(results["complete"])["blocking"] is False
    # A stamp made from a dirty tree is never pinned.
    dirty = _stamp_core_copy(pinned_core, tmp_path / "dirty", dirty=True)
    results = _run_driver(tmp_path / "work-dirty", [SCENARIOS[0]], dirty)
    assert results["gateway_core_provenance"]["reason"] == "CORE_BUILD_DIRTY"
    assert results["gateway_core_provenance"]["fail_closed"] is True


def test_core_build_identity_fixture_matches_pinned_core(pinned_core, tmp_path):
    """The vendored test fixture behaves exactly like the pinned Core's module."""
    fixture = Path(__file__).with_name("_core_build_identity_fixture.py")
    code = (
        "import importlib.util, json, sys\n"
        "def load(name, path):\n"
        "    spec = importlib.util.spec_from_file_location(name, path)\n"
        "    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "    return module\n"
        "real = load('real_bi', sys.argv[1] + '/product/protocol/build_identity.py')\n"
        "copy = load('copy_bi', sys.argv[2])\n"
        "out = {}\n"
        "for name, module in (('real', real), ('copy', copy)):\n"
        "    vector = module.SOURCE_DIGEST_CONFORMANCE_VECTOR\n"
        "    files = [(f['path'], f['content_utf8'].encode()) for f in vector['files']]\n"
        "    out[name] = {\n"
        "        'identity': module.core_identity(sys.argv[3] + '/product'),\n"
        "        'vector': module.source_digest_of_files(files) == vector['expected_digest'],\n"
        "        'rule': module.SOURCE_DIGEST_RULE,\n"
        "        'schema': module.CORE_IDENTITY_SCHEMA,\n"
        "    }\n"
        "print(json.dumps(out))\n"
    )
    stamped = _stamp_core_copy(pinned_core, tmp_path / "stamped")
    for target in (pinned_core, stamped):
        proc = subprocess.run(
            [sys.executable, "-B", "-c", code, str(pinned_core), str(fixture), str(target)],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        out = json.loads(proc.stdout)
        assert out["real"]["vector"] is True
        assert out["copy"] == out["real"], "refresh _core_build_identity_fixture.py"


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
        "identity_source",
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
    # Computed in the Gateway process by Core's public expected_universe_identity.
    host_identity = live["host_core_universe_identities"]["complete"]
    assert host_identity.startswith("sha256:"), host_identity
    assert verdict["coverage"]["universe_identity"] == host_identity
    assert verdict["core_universe_identity"] == host_identity


def test_reference_universe_identity_matches_pinned_core(live):
    """The in-process test reference equals real Core on every declared universe."""
    identities = live["host_core_universe_identities"]
    declared = [s for s in SCENARIOS if s["universe"] is not None]
    assert sorted(identities) == sorted(s["name"] for s in declared)
    for scenario in declared:
        assert identities[scenario["name"]] == core_universe_identity(scenario["universe"])
    conformance = live["core_conformance_universe_identity"]
    assert conformance["ok"] is True, conformance


def test_verdict_blocks_when_core_response_universe_identity_differs(tmp_path):
    contract = _universe_contract(tmp_path)
    projection = _verified_projection(1)
    declared = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    projection["core_response"]["hashes"] = {"universe_identity": core_universe_identity(declared)}
    ok = build_core_verdict(contract=contract, projection=projection)
    assert ok["blocking"] is False, ok["host_reason_codes"]
    projection["core_response"]["hashes"] = {"universe_identity": "sha256:" + "2" * 64}
    verdict = build_core_verdict(contract=contract, projection=projection)
    assert verdict["blocking"] is True
    assert verdict["host_reason_codes"] == ["CORE_RESPONSE_UNIVERSE_IDENTITY_MISMATCH"]
    # A legacy task never carries a universe identity in Core's response.
    legacy = build_core_verdict(contract=SimpleNamespace(task_id="legacy"), projection=projection)
    assert legacy["blocking"] is True
    assert "CORE_RESPONSE_UNIVERSE_IDENTITY_MISMATCH" in legacy["host_reason_codes"]


def test_verdict_blocks_when_core_cannot_compute_universe_identity(tmp_path, monkeypatch):
    from nexus.orchestrator import ambient_core

    def unavailable():
        raise RuntimeError("CORE_UNIVERSE_IDENTITY_UNAVAILABLE")

    monkeypatch.setattr(ambient_core, "_core_expected_universe_identity", unavailable)
    contract = _universe_contract(tmp_path)
    verdict = build_core_verdict(
        contract=contract, projection=_verified_projection(1, identity="sha256:" + "3" * 64)
    )
    assert verdict["blocking"] is True
    assert "CORE_UNIVERSE_IDENTITY_UNAVAILABLE" in verdict["host_reason_codes"]
    assert "CORE_COVERAGE_IDENTITY_MISMATCH" in verdict["host_reason_codes"]
    assert verdict["core_universe_identity"] is None
    # Core returning a non-hash is never accepted as an identity.
    monkeypatch.setattr(ambient_core, "_core_expected_universe_identity", lambda: lambda _c: None)
    with pytest.raises(RuntimeError, match="CORE_UNIVERSE_IDENTITY_INVALID"):
        core_universe_identity({"universe_generation": 1, "subjects": [DIFF_CHECK]})


def test_host_has_no_copy_of_the_universe_identity_formula():
    """Without Core the host cannot compute the identity (no fallback formula)."""
    import inspect

    from nexus.orchestrator import ambient_core

    source = inspect.getsource(ambient_core.core_universe_identity)
    assert "hashlib" not in source and "json.dumps" not in source
    assert "_core_expected_universe_identity()" in source


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
    """Since #2246 the identity runs no git (or other) subprocess at all."""
    import nexus.orchestrator.canonical_core_transport as transport

    seen = []

    def fake_subprocess(args, **kwargs):
        seen.append(args)
        raise AssertionError("no subprocess on the provenance path")

    monkeypatch.setattr(transport.subprocess, "check_output", fake_subprocess)
    monkeypatch.setattr(transport.subprocess, "run", fake_subprocess)
    monkeypatch.setattr(transport.subprocess, "Popen", fake_subprocess)
    identity = transport.read_observed_core_identity(tmp_path)
    assert identity["available"] is False
    assert seen == []


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


def test_gateway_startup_binds_product_to_core_before_eia(
    pinned_core, pinned_core_digest, tmp_path
):
    def probe(mode: str) -> dict[str, Any]:
        env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_REPO_ROOT"}
        inherited = [entry for entry in sys.path if entry and Path(entry).exists()]
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys([str(REPO_ROOT), *inherited]))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["NEXUS_CORE_REPO_ROOT"] = str(pinned_core)
        env["NEXUS_CORE_SOURCE_DIGEST_REVISION"], env["NEXUS_CORE_SOURCE_DIGEST"] = (
            pinned_core_digest
        )
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


# --- cards created by nexus_task_card_create (#2218) ------------------------

_CREATED_UNIVERSES = {
    "created_complete": {
        "universe_generation": 1,
        "subjects": [
            _subject("lint:ruff", "lint-report", "CONDITIONALLY_REQUIRED", "NOT_APPLICABLE"),
            DIFF_CHECK,
        ],
    },
    "created_missing": {"universe_generation": 1, "subjects": [SECURITY_REVIEW, DIFF_CHECK]},
}
CREATED_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": name,
        "task_id": name.replace("_", "-"),
        "verifiers": ["git diff --check"],
        "create_card": {
            "authority_goal_id": "goal-test",
            "authority_coordination_scope_id": "thread-test",
            "owner_confirmation": True,
            "campaign_id": f"cov-{name.replace('_', '-')}",
            "task_id": name.replace("_", "-"),
            "objective": "Change README.md in one bounded step.",
            "allowed_files": ["README.md"],
            "verifier_commands": ["git diff --check"],
            "expected_evidence": universe,
        },
    }
    for name, universe in _CREATED_UNIVERSES.items()
]


@pytest.fixture(scope="module")
def live_created(pinned_core, pinned_core_digest, tmp_path_factory) -> dict[str, Any]:
    results = _run_driver(
        tmp_path_factory.mktemp("live-created"), CREATED_SCENARIOS, pinned_core, pinned_core_digest
    )
    assert results["core_available"] is True, results["core_import_error"]
    return results


def _assert_created_card_drives_the_declared_universe(result: dict[str, Any], name: str) -> None:
    created = result["created_card"]
    declared = parse_task_card_expected_evidence(created["card_text"])
    assert declared is not None
    assert core_universe_identity(declared) == core_universe_identity(_CREATED_UNIVERSES[name])
    assert hashlib.sha256(created["card_text"].encode("utf-8")).hexdigest() == created["card_hash"]
    # The Gateway read the universe from the created, hashed card.
    assert result["request_expected_evidence"] == declared
    assert result["request_core_envelope_required"] is True
    verdict = _verdict(result)
    assert verdict["coverage"]["universe_identity"] == core_universe_identity(declared)
    assert verdict["core_provenance"]["status"] == "CORE_REVISION_PINNED"
    assert result["reloaded_core_verdict"] == verdict


def test_live_created_card_with_complete_coverage_reaches_core_verdict(live_created):
    result = live_created["created_complete"]
    _assert_created_card_drives_the_declared_universe(result, "created_complete")
    verdict = _verdict(result)
    assert verdict["blocking"] is False
    assert verdict["coverage_complete"] is True
    assert _categories(verdict) == {
        "git diff --check": "COVERED",
        "lint:ruff": "CONDITIONALLY_NOT_APPLICABLE",
    }
    assert result["receipt_verified"] is True
    assert result["receipt_commit_allowed"] is True


def test_live_created_card_with_missing_evidence_blocks(live_created):
    result = live_created["created_missing"]
    _assert_created_card_drives_the_declared_universe(result, "created_missing")
    _assert_blocked(result)
    verdict = _verdict(result)
    assert verdict["core_status"] == "UNVERIFIABLE"
    assert _categories(verdict) == {
        "git diff --check": "COVERED",
        "review:security": "NOT_COVERED",
    }


# --- #2346: a declared-universe task that ends before a worker runs ---------

TERMINAL_UNIVERSE = {
    "universe_generation": 1,
    "subjects": [
        DIFF_CHECK,
        SECURITY_REVIEW,
        _subject("lint:ruff", "lint-report", "CONDITIONALLY_REQUIRED", "NOT_APPLICABLE"),
    ],
}
TERMINAL_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "preflight_universe",
        "task_id": "term-universe",
        "verifiers": ["git diff --check"],
        "universe": TERMINAL_UNIVERSE,
        "worker_preflight_ready": False,
    },
    {
        "name": "preflight_legacy",
        "task_id": "term-legacy",
        "verifiers": ["git diff --check"],
        "universe": None,
        "worker_preflight_ready": False,
    },
]


@pytest.fixture(scope="module")
def live_terminal(pinned_core, pinned_core_digest, tmp_path_factory) -> dict[str, Any]:
    results = _run_driver(
        tmp_path_factory.mktemp("live-terminal"),
        TERMINAL_SCENARIOS,
        pinned_core,
        pinned_core_digest,
    )
    assert results["core_available"] is True, results["core_import_error"]
    return results


def _assert_ended_before_any_worker(result: dict[str, Any]) -> None:
    assert result["status"] == "FINAL_BLOCK"
    assert "worker preflight failed" in str(result["error"])
    assert result["worker_invocations"] == []
    assert result["verified_receipt_present"] is False
    assert result["candidate_commit_sha"] is None
    assert result["promotion_status"] == "NOT_CREATED"


def test_live_preflight_final_block_records_core_not_covered(live_terminal):
    result = live_terminal["preflight_universe"]
    _assert_ended_before_any_worker(result)
    record = result["terminal_core_record"]
    assert record["record_status"] == "RECORDED", record
    assert record["failure_reason"] is None
    assert record["attempt_id"] == result["attempt_id"]
    assert record["terminal_status"] == "FINAL_BLOCK"
    assert record["verified"] is False
    assert record["candidate_commit_allowed"] is False
    verdict = record["core_verdict"]
    assert verdict["schema"] == CORE_VERDICT_SCHEMA
    assert verdict["core_status"] == "UNVERIFIABLE"
    assert verdict["integrity"] == "MISSING"
    assert "MISSING" in verdict["reason_codes"]
    assert verdict["blocking"] is True
    assert verdict["coverage_complete"] is False
    # Every REQUIRED subject is NOT_COVERED; Core's own category otherwise.
    assert _categories(verdict) == {
        "git diff --check": "NOT_COVERED",
        "lint:ruff": "CONDITIONALLY_NOT_APPLICABLE",
        "review:security": "NOT_COVERED",
    }
    # The coverage is bound to exactly the declared universe and pinned Core.
    host_identity = live_terminal["host_core_universe_identities"]["preflight_universe"]
    assert verdict["core_universe_identity"] == host_identity
    assert verdict["coverage"]["universe_identity"] == host_identity
    assert verdict["universe_generation"] == 1
    assert verdict["core_provenance"]["status"] == "CORE_REVISION_PINNED"
    assert "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE" in verdict["host_reason_codes"]
    assert "CORE_COVERAGE_INCOMPLETE" in verdict["host_reason_codes"]
    assert not [code for code in verdict["host_reason_codes"] if "MISMATCH" in code]
    # Durable: the same record after reload, and one Core provenance row.
    assert result["reloaded_terminal_core_record"] == record
    row = result["db_terminal_row"]
    assert row is not None
    assert row["task_id"] == "term-universe"
    assert row["attempt_id"] == result["attempt_id"]
    assert row["terminal_status"] == "FINAL_BLOCK"
    assert row["core_status"] == "UNVERIFIABLE"
    assert row["integrity"] == "MISSING"
    assert row["universe_identity"] == host_identity
    assert row["universe_generation"] == 1
    assert row["core_provenance_status"] == "CORE_REVISION_PINNED"
    assert row["projection_hash"] == verdict["projection_hash"]


def test_live_preflight_final_block_of_legacy_task_records_nothing(live_terminal):
    result = live_terminal["preflight_legacy"]
    _assert_ended_before_any_worker(result)
    assert result["terminal_core_record"] is None
    assert result["core_db_exists"] is False
    assert result["db_terminal_row"] is None


def test_live_terminal_record_carries_no_authority(live_terminal):
    record = live_terminal["preflight_universe"]["terminal_core_record"]

    def keys(value: Any) -> list[str]:
        if isinstance(value, dict):
            return [*value, *(k for item in value.values() for k in keys(item))]
        if isinstance(value, list):
            return [k for item in value for k in keys(item)]
        return []

    allowed = {"candidate_commit_allowed"}
    for key in keys(record):
        if key in allowed:
            continue
        assert not any(word in key.lower() for word in _AUTHORITY_WORDS), key
    # The record never becomes the receipt that gates commit or approval.
    assert live_terminal["preflight_universe"]["verified_receipt_present"] is False


def test_live_terminal_record_without_core_fails_closed(tmp_path):
    results = _run_driver(tmp_path / "work", TERMINAL_SCENARIOS, None)
    assert results["core_available"] is False
    result = results["preflight_universe"]
    _assert_ended_before_any_worker(result)
    record = result["terminal_core_record"]
    assert record["record_status"] == "FAILED"
    assert record["failure_reason"] == (
        "CORE_TERMINAL_RECORD_FAILED:CANONICAL_NEXUS_CORE_UNAVAILABLE"
    )
    assert record["candidate_commit_allowed"] is False
    assert record["core_verdict"]["blocking"] is True
    assert record["core_verdict"]["coverage"] is None
    assert result["reloaded_terminal_core_record"] == record
    legacy = results["preflight_legacy"]
    _assert_ended_before_any_worker(legacy)
    assert legacy["terminal_core_record"] is None


def test_live_receipt_paths_get_no_terminal_record(live):
    # A verified receipt (passing or blocked) keeps its own Core verdict only.
    for name in ("complete", "missing", "fail", "legacy"):
        assert live[name]["terminal_core_record"] is None, name
        assert live[name]["db_terminal_row"] is None, name


def _terminal_state(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    universe = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    state: dict[str, Any] = {
        "task_id": "verdict-unit",
        "attempt_id": "attempt-1",
        "status": "FINAL_BLOCK",
        "verified_receipt": None,
        "request": {
            "task_id": "verdict-unit",
            "core_envelope_required": True,
            "expected_evidence": universe,
            **_card(tmp_path, universe),
        },
    }
    state.update(overrides)
    return state


class _CountingPort:
    def __init__(self, answer: Any = None, error: Exception | None = None):
        self.calls: list[dict[str, Any]] = []
        self.answer, self.error = answer, error

    def record_terminal_not_covered(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.answer


def test_terminal_record_core_failure_is_recorded_not_raised(tmp_path):
    port = _CountingPort(error=RuntimeError("BOOM: core exploded"))
    record = _host_service(tmp_path, port)._build_terminal_core_record(
        _terminal_state(tmp_path), contract=_universe_contract(tmp_path)
    )
    assert record is not None and len(port.calls) == 1
    assert port.calls[0]["terminal_status"] == "FINAL_BLOCK"
    assert port.calls[0]["attempt_id"] == "attempt-1"
    assert record["record_status"] == "FAILED"
    assert record["failure_reason"] == "CORE_TERMINAL_RECORD_FAILED:BOOM"
    assert record["candidate_commit_allowed"] is False
    assert record["core_verdict"]["blocking"] is True
    assert record["core_verdict"]["host_reason_codes"] == ["CORE_TERMINAL_RECORD_FAILED:BOOM"]


def test_terminal_record_refuses_a_non_blocking_core_answer(tmp_path):
    # Even a pinned, fully covered VERIFIED answer cannot pass a task that
    # produced nothing: the record fails closed.
    port = _CountingPort(answer=_verified_projection(1))
    record = _host_service(tmp_path, port)._build_terminal_core_record(
        _terminal_state(tmp_path), contract=_universe_contract(tmp_path)
    )
    assert record["record_status"] == "FAILED"
    assert (
        record["failure_reason"] == "CORE_TERMINAL_RECORD_FAILED:CORE_TERMINAL_RECORD_NOT_BLOCKING"
    )
    assert record["candidate_commit_allowed"] is False
    assert record["core_verdict"]["blocking"] is True


@pytest.mark.parametrize("port", [None, object()], ids=["no-port", "port-without-recorder"])
def test_terminal_record_without_a_recording_port_fails_closed(tmp_path, port):
    record = _host_service(tmp_path, port)._build_terminal_core_record(
        _terminal_state(tmp_path), contract=_universe_contract(tmp_path)
    )
    expected = (
        "AMBIENT_CORE_CONTROL_PORT_REQUIRED"
        if port is None
        else "AMBIENT_CORE_TERMINAL_RECORD_UNSUPPORTED"
    )
    assert record["record_status"] == "FAILED"
    assert record["failure_reason"] == f"CORE_TERMINAL_RECORD_FAILED:{expected}"


def test_terminal_record_card_edited_after_intake_fails_closed(tmp_path):
    state = _terminal_state(tmp_path)
    Path(state["request"]["task_card_path"]).write_text("edited\n", encoding="utf-8")
    port = _CountingPort(answer={})
    record = _host_service(tmp_path, port)._build_terminal_core_record(
        state, contract=_universe_contract(tmp_path)
    )
    assert port.calls == []
    assert record["failure_reason"] == (
        "CORE_TERMINAL_RECORD_FAILED:EXPECTED_EVIDENCE_TASK_CARD_HASH_MISMATCH"
    )


def test_terminal_record_leaves_receipt_nonterminal_and_legacy_paths_alone(tmp_path):
    port = _CountingPort(answer={})
    service = _host_service(tmp_path, port)
    contract = _universe_contract(tmp_path)
    with_receipt = _terminal_state(tmp_path, verified_receipt={"verified": False})
    assert service._build_terminal_core_record(with_receipt, contract=contract) is None
    running = _terminal_state(tmp_path, status="WORKER_RUNNING")
    assert service._build_terminal_core_record(running, contract=contract) is None
    legacy = _terminal_state(tmp_path)
    legacy["request"] = {"task_id": "verdict-unit", **_card(tmp_path, None)}
    assert service._build_terminal_core_record(legacy) is None
    assert service._build_terminal_core_record(legacy, contract=_legacy_contract(tmp_path)) is None
    assert port.calls == []


def test_terminal_record_hook_never_raises_into_the_terminal_write(tmp_path, monkeypatch):
    service = _host_service(tmp_path, _CountingPort(answer={}))

    def explode(*args, **kwargs):
        raise RuntimeError("recorder bug")

    monkeypatch.setattr(service, "_build_terminal_core_record", explode)
    assert (
        service._record_terminal_core_not_covered("verdict-unit", _terminal_state(tmp_path)) is None
    )


def test_transport_terminal_record_requires_core(tmp_path):
    from nexus.orchestrator.canonical_core_transport import CanonicalNexusCoreTransportPort

    port = CanonicalNexusCoreTransportPort(tmp_path / "core.sqlite", simulate_core_unavailable=True)
    with pytest.raises(RuntimeError, match="CANONICAL_NEXUS_CORE_UNAVAILABLE"):
        port.record_terminal_not_covered(
            contract=_universe_contract(tmp_path),
            request={},
            task_id="verdict-unit",
            attempt_id="attempt-1",
            terminal_status="FINAL_BLOCK",
        )
    assert not (tmp_path / "core.sqlite").exists()


def _not_covered_projection(provenance: str, tmp_path: Path) -> dict[str, Any]:
    declared = {"universe_generation": 1, "subjects": [DIFF_CHECK]}
    return {
        "terminal_status": "FINAL_BLOCK",
        "core_response": {
            "verification": {
                "status": "UNVERIFIABLE",
                "reason_codes": ["CANDIDATE_MISSING", "MISSING"],
                "integrity": "MISSING",
                "coverage": {
                    "universe_generation": 1,
                    "universe_identity": core_universe_identity(declared),
                    "entries": [{**DIFF_CHECK, "category": "NOT_COVERED"}],
                    "unexpected_subjects": [],
                },
            }
        },
        "core_provenance": {"status": provenance},
    }


def test_terminal_record_recorded_only_from_pinned_core(tmp_path):
    pinned = _host_service(
        tmp_path, _CountingPort(answer=_not_covered_projection("CORE_REVISION_PINNED", tmp_path))
    )._build_terminal_core_record(_terminal_state(tmp_path), contract=_universe_contract(tmp_path))
    assert pinned["record_status"] == "RECORDED"
    assert pinned["core_verdict"]["host_reason_codes"] == [
        "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE",
        "CORE_COVERAGE_INCOMPLETE",
    ]
    drifted = _host_service(
        tmp_path,
        _CountingPort(answer=_not_covered_projection("CORE_REVISION_MISMATCH", tmp_path)),
    )._build_terminal_core_record(_terminal_state(tmp_path), contract=_universe_contract(tmp_path))
    assert drifted["record_status"] == "FAILED"
    assert drifted["failure_reason"] == "CORE_TERMINAL_RECORD_FAILED:CORE_PROVENANCE_NOT_PINNED"
    assert drifted["candidate_commit_allowed"] is False
    assert drifted["core_verdict"]["blocking"] is True


@pytest.mark.parametrize("existing_status, rebuilt", [("RECORDED", False), ("FAILED", True)])
def test_terminal_record_is_retried_only_after_a_failure(
    tmp_path, monkeypatch, existing_status, rebuilt
):
    service = _host_service(tmp_path, _CountingPort(answer={}))
    built: list[Any] = []
    monkeypatch.setattr(service, "_build_terminal_core_record", lambda state: built.append(1))
    state = _terminal_state(
        tmp_path,
        terminal_core_record={"attempt_id": "attempt-1", "record_status": existing_status},
    )
    service._record_terminal_core_not_covered("verdict-unit", state)
    assert bool(built) is rebuilt
