"""Golden replay corpus: real valid input must stay accepted (#2455).

Every fixture under ``corpus/`` is a frozen, redacted copy of a real artifact that a
production evaluator, parser or controller accepted in real use. ``MANIFEST.json``
records where each one came from. The replays below feed those artifacts to the
current consumer code and assert the valid input is still accepted ("fail-broken"
regressions: a new or tightened check that rejects real valid input).

Each family also has a negative control: a deliberately broken consumer variant
(the historical defect) must make the same replay fail, so the oracle cannot go
green by checking nothing.

The replays are written against entry points that exist both on main and at the
historical defect revisions, so the file can be copied into an old checkout for
the #2455 backtest.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
ROOT = HERE.parents[1]
MANIFEST = json.loads((CORPUS / "MANIFEST.json").read_text(encoding="utf-8"))
FIXTURES = {entry["path"]: entry for entry in MANIFEST["fixtures"]}


def _family(name: str) -> list[str]:
    return sorted(path for path, entry in FIXTURES.items() if entry["family"] == name)


def _load(path: str) -> Any:
    return json.loads((CORPUS / path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- corpus integrity

_SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)authorization:\s*(basic|bearer)\s+[A-Za-z0-9+/=._-]{8,}"),
    re.compile(r"/Users/(?!REDACTED\b)[A-Za-z0-9._-]+"),
    re.compile(r"/home/(?!runner\b)[A-Za-z0-9._-]+"),
)


def test_manifest_lists_exactly_the_corpus_files_with_matching_hashes():
    on_disk = sorted(
        str(path.relative_to(CORPUS))
        for path in CORPUS.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    )
    assert on_disk == sorted(FIXTURES)
    for path, entry in FIXTURES.items():
        digest = hashlib.sha256((CORPUS / path).read_bytes()).hexdigest()
        assert digest == entry["fixture_sha256"], f"{path} changed; fixtures are immutable"


def test_every_fixture_is_a_real_capture_with_provenance():
    for path, entry in FIXTURES.items():
        assert entry["real"] is True, path
        assert entry["source"] and entry["redaction"], path
        assert re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"]), path
    # The corpus is small and frozen (~15 real artifacts, #2455).
    assert 10 <= len(FIXTURES) <= 20


def test_fixtures_carry_no_secrets_or_unredacted_home_paths():
    for path in FIXTURES:
        text = (CORPUS / path).read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            assert not pattern.search(text), f"{path} matches {pattern.pattern}"


def test_secret_scan_is_not_vacuous():
    leaked = "token ghp_" + "a" * 36 + " under /Users/someone/x"
    assert sum(bool(p.search(leaked)) for p in _SECRET_PATTERNS) == 2


# --------------------------------------------------------------------------- family 1: git modes (#1901)

_ACQUIRE = "Acquire exact trusted source"


def _acquisition_script() -> str:
    yaml = importlib.import_module("yaml")
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/trusted-impact-gate.yml").read_text(encoding="utf-8")
    )
    for step in workflow["jobs"]["trusted-controller"]["steps"]:
        if str(step.get("name", "")).startswith(_ACQUIRE):
            # Cut before the Python controller: only the trusted-source acquisition runs.
            return step["run"].split("\npython -c", 1)[0]
    raise AssertionError("trusted-controller acquisition step not found")


def _lstree_entries(path: str) -> list[tuple[str, str]]:
    entries = []
    for line in (CORPUS / path).read_text(encoding="utf-8").splitlines():
        meta, _, name = line.partition("\t")
        mode, kind, _blob = meta.split()
        assert kind == "blob"
        entries.append((mode, name))
    return entries


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _replay_tree_acquisition(tmp_path: Path, entries: list[tuple[str, str]], script: str):
    """Rebuild a repo with the real file modes and run the production acquisition block."""

    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.name", "Golden Replay")
    _git(origin, "config", "user.email", "golden-replay@example.invalid")
    for mode, name in entries:
        target = origin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / name
        target.write_bytes(source.read_bytes() if source.is_file() else b"# placeholder\n")
        _git(origin, "add", name)
        if mode == "100755":
            _git(origin, "update-index", "--chmod=+x", name)
    _git(origin, "commit", "-q", "-m", "trusted sources with real modes")
    sha = _git(origin, "rev-parse", "HEAD")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    repository = "James3014/Nexus-new"
    env = {
        **os.environ,
        "EVENT_NAME": "pull_request_target",
        "REPOSITORY": repository,
        "DEFAULT_BRANCH": "main",
        "WORKFLOW_REF": f"{repository}/.github/workflows/trusted-impact-gate.yml@refs/heads/main",
        "WORKFLOW_SHA": sha,
        "TRUSTED_TOKEN": "golden-replay",
        "RUNNER_TEMP": str(runner_temp),
    }
    remote = "https://github.com/$REPOSITORY.git"
    # Never let the replay reach GitHub: the remote must be swapped for the local origin.
    assert script.count(remote) == 1, "acquisition remote URL changed; update the replay"
    script = script.replace(remote, origin.resolve().as_uri())
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


def test_family_git_tree_corpus_contains_a_real_executable_blob():
    (path,) = _family("git_executable_mode")
    modes = dict((name, mode) for mode, name in _lstree_entries(path))
    assert modes["scripts/ops/pr_impact_gate.py"] == "100755"


def test_replay_real_executable_mode_tree_through_trusted_acquisition(tmp_path):
    (path,) = _family("git_executable_mode")
    completed = _replay_tree_acquisition(tmp_path, _lstree_entries(path), _acquisition_script())
    assert completed.returncode == 0, completed.stderr[-2000:]


def test_negative_control_regular_file_only_100644_acquisition_is_caught(tmp_path):
    # The #1901 defect: only mode 100644 counted as a regular file.
    script = _acquisition_script()
    broken = re.sub(r"\[ \"\$entry\" = \"100755 blob[^\]]*\] \|\| ", "", script)
    assert broken != script, "negative control mutation did not apply"
    (path,) = _family("git_executable_mode")
    completed = _replay_tree_acquisition(tmp_path, _lstree_entries(path), broken)
    assert completed.returncode != 0


# --------------------------------------------------------------------------- family 2: Agy probe JSON (#1472)


def _probe_decoder() -> Callable[[str, str, str], tuple[Any, Any]]:
    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

    return UnifiedMCPGateway._decode_model_probe_payload


def _expected_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    text = envelope["response"].strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[len("```json\n") : -len("\n```")]
    return json.loads(text)


def _replay_probe(path: str, decode: Callable[[str, str, str], tuple[Any, Any]]) -> list[str]:
    envelope = _load(path)
    raw = json.dumps(envelope)
    payload, provenance = decode(raw, "agy", FIXTURES[path]["resolved_model"])
    if payload != _expected_payload(envelope) or provenance is None:
        return [f"{path}: real valid probe reply rejected ({payload!r}, {provenance!r})"]
    return []


_PROBES = _family("agy_fenced_json_reply") + _family("agy_plain_json_reply")


def test_family_agy_corpus_has_real_fenced_and_plain_replies():
    assert len(_family("agy_fenced_json_reply")) >= 3
    assert len(_family("agy_plain_json_reply")) >= 1


@pytest.mark.parametrize("path", _PROBES)
def test_replay_real_agy_probe_reply_is_accepted(path):
    assert _replay_probe(path, _probe_decoder()) == []


def test_negative_control_fence_blind_probe_decoder_is_caught():
    # The #1472 defect: the model-originated response was json.loads'ed as-is.
    def fence_blind(raw: str, _provider: str, _model: str):
        envelope = json.loads(raw)
        try:
            value = json.loads(envelope["response"].strip())
        except json.JSONDecodeError:
            return None, None
        return (value, "agy_json_envelope") if isinstance(value, dict) else (None, None)

    caught = [path for path in _PROBES if _replay_probe(path, fence_blind)]
    assert caught == _family("agy_fenced_json_reply")


# --------------------------------------------------------------------------- family 3: readiness state (#1514)


def _readiness_store(tmp_path: Path):
    from nexus.research.hybrid_replication_pipeline import AutomaticReplicationStore

    root = tmp_path / "store"
    for path in _family("hybrid_readiness_state"):
        if path.startswith("readiness/v6_store/"):
            target = root / Path(path).relative_to("readiness/v6_store")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((CORPUS / path).read_bytes())
    return AutomaticReplicationStore(root)


def _replay_readiness(tmp_path: Path, evaluate: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    reports = _load("readiness/v6_stage1_reports.json")
    return evaluate(
        store=_readiness_store(tmp_path),
        ingest_report=reports["ingest_report"],
        advance_report=reports["advance_report"],
        control_task_key=reports["control_task_key"],
        launchd_label="com.nexus.hybrid-replication",
        service_observation=reports["service_observation"],
    )


def test_family_readiness_corpus_is_a_deferred_non_control_admission():
    reports = _load("readiness/v6_stage1_reports.json")
    control = reports["control_task_key"]
    deferred = [key for key in reports["ingest_report"]["missing_admission"] if key != control]
    assert deferred == ["James3014/repository-intelligence-engine#45"]
    state = _load(
        "readiness/v6_store/tasks/James3014__repository-intelligence-engine--45/state.json"
    )
    assert state["admission_disposition"] == "PRE_AUTOMATION_PROVISIONAL_CAPTURE"


def test_replay_real_pre_ready_state_does_not_block_on_deferred_admission(tmp_path):
    from scripts.ops.hybrid_replication_daemon import evaluate_readiness_from_store

    result = _replay_readiness(tmp_path, evaluate_readiness_from_store)
    assert "MISSING_ADMISSION" not in result["blockers"]
    assert result.get("deferred_non_control_missing_admission") == [
        "James3014/repository-intelligence-engine#45"
    ]


def test_negative_control_unscoped_admission_readiness_is_caught(tmp_path):
    # The #1514 defect: every missing admission blocked readiness, including
    # non-control captures that are only admitted after readiness (circular).
    from scripts.ops import hybrid_replication_daemon as daemon

    def unscoped(**kwargs: Any) -> dict[str, Any]:
        ingest = kwargs["ingest_report"]
        result = daemon._evaluate_automatic_capture_readiness(
            ingest_report=ingest,
            advance_report=kwargs["advance_report"],
            launchd_loaded=True,
            control_phase="SCORED",
        )
        return result

    result = _replay_readiness(tmp_path, unscoped)
    assert "MISSING_ADMISSION" in result["blockers"]


# --------------------------------------------------------------------------- family 4: doctor state (#1605)


def _replay_doctor(path: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Run the real doctor entry point with collectors replaying a captured live state."""

    from nexus.services import workflow_doctor as doctor

    captured = _load(path)
    runtime = {k: v for k, v in captured["runtime"].items() if k != "current_main_alignment"}
    source = captured["source"]
    monkeypatch.setattr(
        doctor, "_collect_source", lambda *a, **k: (dict(source), source["repository"])
    )
    monkeypatch.setattr(doctor, "_collect_task", lambda *a, **k: dict(captured["task"]))
    monkeypatch.setattr(
        doctor,
        "_collect_pr",
        lambda *a, **k: (
            dict(captured["pr"]),
            list(captured["required_gates"]),
            list(captured["advisory_observers"]),
            list(captured["unknown_policy_checks"]),
        ),
    )
    monkeypatch.setattr(doctor, "_collect_runtime", lambda *a, **k: json.loads(json.dumps(runtime)))
    monkeypatch.setattr(doctor, "_collect_quota_snapshot", lambda *a, **k: dict(captured["quota"]))
    monkeypatch.setattr(doctor, "_collect_operations", lambda *a, **k: dict(captured["operation"]))
    monkeypatch.setattr(doctor, "_collect_leases", lambda *a, **k: dict(captured["leases"]))
    return doctor.collect_workflow_doctor(
        repo_root=tmp_path,
        repository=source["repository"],
        issue_number=captured["task"].get("issue_number"),
        home=tmp_path,
    )


def _doctor_failures(captured: dict[str, Any], replayed: dict[str, Any]) -> list[str]:
    failures = []
    if replayed["resume_disposition"] != captured["resume_disposition"]:
        failures.append(
            f"resume {replayed['resume_disposition']} != live {captured['resume_disposition']}"
        )
    if replayed["next_gate"]["code"] != captured["next_gate"]["code"]:
        failures.append(
            f"next_gate {replayed['next_gate']['code']} != live {captured['next_gate']['code']}"
        )
    live = captured["runtime"]["current_main_alignment"]
    got = replayed["runtime"]["current_main_alignment"]
    if (got.get("status"), got.get("basis")) != (live["status"], live["basis"]):
        failures.append(
            f"alignment {got.get('status')}/{got.get('basis')} != live {live['status']}/{live['basis']}"
        )
    return failures


_DOCTORS = _family("cross_repo_doctor_state") + _family("same_repo_doctor_state")


def test_family_doctor_corpus_has_a_real_cross_repo_state():
    (path,) = _family("cross_repo_doctor_state")
    captured = _load(path)
    target = captured["source"]["repository"]
    runtime_repo = captured["runtime"]["components"]["workflow_source_binding"]["repository"]
    assert target.casefold() != runtime_repo.casefold()
    assert captured["resume_disposition"] == "SAFE"


@pytest.mark.parametrize("path", _DOCTORS)
def test_replay_real_doctor_state_reproduces_the_live_verdict(path, monkeypatch, tmp_path):
    replayed = _replay_doctor(path, monkeypatch, tmp_path)
    assert _doctor_failures(_load(path), replayed) == []


def test_negative_control_target_main_alignment_is_caught(monkeypatch, tmp_path):
    # The #1605 defect: the target repository's main SHA was compared with the
    # Nexus host-runtime revision, so a valid cross-repo state read as DRIFT.
    from nexus.services import workflow_doctor as doctor

    monkeypatch.setattr(
        doctor,
        "_runtime_alignment_projection",
        lambda runtime, source: doctor._runtime_main_alignment(runtime, source.get("github_main")),
    )
    (path,) = _family("cross_repo_doctor_state")
    replayed = _replay_doctor(path, monkeypatch, tmp_path)
    assert _doctor_failures(_load(path), replayed) != []


# --------------------------------------------------------------------------- family 5: Task Cards


_CARDS = _family("task_card_bundle")


@pytest.mark.parametrize("path", _CARDS)
def test_replay_real_task_card_identity_is_accepted(path):
    from nexus.orchestrator.github_orchestration import _parse_task_card

    text = (CORPUS / path).read_text(encoding="utf-8")
    task_id, allowed, _ = _parse_task_card(text.encode("utf-8"))
    assert f"task_id: `{task_id}`" in text
    assert allowed and all(f"- `{item}`" in text for item in allowed)


@pytest.mark.parametrize("path", _CARDS)
def test_replay_real_task_card_expected_evidence_is_accepted(path):
    from nexus.orchestrator.task_contract import parse_task_card_expected_evidence

    text = (CORPUS / path).read_text(encoding="utf-8")
    declared = parse_task_card_expected_evidence(text)
    if "```nexus-expected-evidence" in text:
        assert isinstance(declared, dict) and declared
    else:
        assert declared is None


def test_negative_control_strict_allowed_files_parser_is_caught(monkeypatch):
    # A tightened parser that demands a lower-case "allowed_files:" block would
    # reject every real gateway-rendered card ("## Allowed files" section).
    from nexus.orchestrator import github_orchestration as orchestration

    original = orchestration._parse_task_card

    def strict(card: bytes):
        if b"\nallowed_files:" not in card:
            raise orchestration._projection_error("TASK_CARD_IDENTITY_MISSING")
        return original(card)

    rejected = []
    for path in _CARDS:
        try:
            strict((CORPUS / path).read_bytes())
        except Exception:  # noqa: BLE001 - any rejection counts as caught
            rejected.append(path)
    assert rejected == _CARDS
