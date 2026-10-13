"""Issue #29 governed canary harness: fake transports only, no model calls.

The happy path runs the real canonical product seam (CapabilityPlanner,
Workforce Admission, UnifiedRuntime, World C, VAP, consumption mint,
RootReceipt).  Only the two physical edges are replaced: Ollama by a loopback
HTTP fake and the Agy CLI by a fake executable resolved through
``NEXUS_AGY_BIN``.  Negative controls mutate a copy of the real runtime
receipt or refuse before any provider edge.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from scripts.ops import issue29_governed_canary as canary

REPO_ROOT = Path(__file__).resolve().parents[2]
GOOD_DIFF = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add_one(x):\n-    return x\n+    return x + 1\n"
FAKE_AGY = """#!{python}
import json, os, sys
with open(os.environ["FAKE_AGY_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd()}}) + "\\n")
print(json.dumps({{"status": "APPROVED", "summary": "consumed inline local evidence", "patch": ""}}))
"""


class _FakeOllama:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.calls.append({"path": self.path, "model": body.get("model")})
                text = fake.content
                payload = json.dumps({
                    "model": body.get("model"),
                    "message": {"role": "assistant", "content": text},
                    "response": text,
                    "done": True,
                    "eval_count": 7,
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/api/chat"

    def __enter__(self) -> "_FakeOllama":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()


def _ok_probes(**overrides: Any) -> canary.HostProbes:
    responses = {
        canary.OLLAMA_SERVICE_PS_URL: (200, json.dumps({"models": []})),
        canary.OLLAMA_GATEWAY_TAGS_URL: (200, "{}"),
        canary.SPLASH_MODELS_URL: (200, "{}"),
        **overrides.pop("http", {}),
    }
    return canary.HostProbes(
        http_get=lambda url: responses[url],
        unused_memory_bytes=overrides.pop("unused_memory_bytes", lambda: 20 * 1024**3),
        agy_path=overrides.pop("agy_path", lambda: "/fake/bin/agy"),
    )


def _card_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "card-repo"
    card = repo / canary.TASK_CARD_PATH
    card.parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / canary.TASK_CARD_PATH, card)
    env_args = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", *env_args, "commit", "-qm", "card"], cwd=repo, check=True)
    return repo


def _fake_agy(tmp_path: Path) -> tuple[Path, Path]:
    binary = tmp_path / "bin" / "agy"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(FAKE_AGY.format(python=sys.executable), encoding="utf-8")
    binary.chmod(0o755)
    return binary, tmp_path / "agy.log"


def _agy_calls(log: Path) -> list[dict[str, Any]]:
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    ollama_content: str = GOOD_DIFF,
    physical: bool = True,
    **kwargs: Any,
) -> tuple[dict[str, Any], _FakeOllama, Path]:
    import nexus.services.local_heal.armor_artifact_storage as storage

    # pytest's tmp_path is an OS temp dir; the physical CLI uses a durable state root.
    monkeypatch.setattr(storage, "is_ephemeral_path", lambda _path: False)
    monkeypatch.delenv("NEXUS_AGY_EXECUTABLE", raising=False)
    monkeypatch.delenv("NEXUS_AGY_BIN", raising=False)
    binary, log = _fake_agy(tmp_path)
    repo = kwargs.pop("repo_root", None) or _card_repo(tmp_path)
    with _FakeOllama(ollama_content) as ollama:
        receipt = canary.run_canary(
            physical=physical,
            state_root=tmp_path / "state",
            run_id="r-test",
            repo_root=repo,
            confirm_task_id=kwargs.pop("confirm_task_id", canary.TASK_ID),
            host_probes=kwargs.pop("host_probes", _ok_probes()),
            runtime_env={
                "NEXUS_OLLAMA_URL": ollama.url,
                "NEXUS_AGY_BIN": str(binary),
                "FAKE_AGY_LOG": str(log),
                "NEXUS_ARMOR_ALLOW_EPHEMERAL": "1",
            },
            **kwargs,
        )
    return receipt, ollama, log


@pytest.fixture(scope="module")
def happy(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp_path = tmp_path_factory.mktemp("issue29-happy")
    with pytest.MonkeyPatch.context() as monkeypatch:
        receipt, ollama, log = _run(tmp_path, monkeypatch)
    runtime = json.loads(Path(receipt["runtime_receipt"]["path"]).read_text(encoding="utf-8"))
    _AGY_EXECUTABLE["path"] = receipt["agy_executable"]
    return {
        "receipt": receipt,
        "ollama_calls": ollama.calls,
        "agy_calls": _agy_calls(log),
        "runtime": runtime,
    }


_AGY_EXECUTABLE: dict[str, str] = {}


def _evaluate(runtime: dict[str, Any], **kwargs: Any) -> canary.Evaluation:
    return canary.evaluate_runtime_evidence(
        runtime,
        task_id=canary.TASK_ID,
        agy_executable=kwargs.pop("agy_executable", _AGY_EXECUTABLE.get("path", "")),
        root_receipt_valid=kwargs.pop("root_receipt_valid", True),
        root_receipt_blockers=kwargs.pop("root_receipt_blockers", ()),
    )


# --------------------------------------------------------------------------
# Happy path through the real canonical seam
# --------------------------------------------------------------------------


def test_happy_path_records_consumption_and_contribution(happy: dict[str, Any]) -> None:
    receipt = happy["receipt"]
    assert receipt["status"] == canary.STATUS_PASS, receipt["reasons"]
    assert receipt["online_consumed"] is True
    assert receipt["final_outcome_contributed"] is True
    evidence = receipt["evidence"]
    assert evidence["local_admission"]["worker_id"] == "local_coder_7b"
    assert evidence["online_admission"]["worker_id"] == "agy_flash_38"
    assert evidence["online_admission"]["model"] == "gemini-3.8-flash-medium"
    assert evidence["consumption"]["status"] == "consumed"
    assert (
        evidence["consumption"]["final_prompt_hash"] == evidence["online"]["provider_input_sha256"]
    )
    assert evidence["contribution"]["claim_boundary_outcome_contributed"] is True
    assert evidence["root_receipt"]["valid"] is True
    assert all(check["ok"] for check in receipt["checks"])
    # Fake transports never make a receipt marker-eligible.
    assert receipt["durable_marker_eligible"] is False
    assert receipt["transport_overrides"]


def test_happy_path_physical_edges_are_admitted_identities(happy: dict[str, Any]) -> None:
    assert happy["ollama_calls"]
    assert {call["model"] for call in happy["ollama_calls"]} == {"qwen2.5-coder:7b-instruct"}
    assert len(happy["agy_calls"]) == 1
    argv = happy["agy_calls"][0]["argv"]
    assert argv[:6] == ["--mode", "plan", "--sandbox", "--model", "gemini-3.8-flash-medium", "-p"]
    assert not any("dangerously" in token for token in argv)
    fragment = happy["runtime"]["verified_assist"]["injection_fragment"]
    assert fragment.startswith("[VAP]")
    assert fragment in argv[-1]
    task_card = happy["receipt"]["task_card"]
    assert task_card["path"] == canary.TASK_CARD_PATH
    assert len(task_card["sha256"]) == 64


def test_canonical_workspace_is_not_the_execution_root(happy: dict[str, Any]) -> None:
    fixture = Path(happy["receipt"]["fixture"]["workspace"])
    assert REPO_ROOT not in fixture.parents
    assert (fixture / "calc.py").read_text(encoding="utf-8") == canary.FIXTURE_FILES["calc.py"]


# --------------------------------------------------------------------------
# Negative controls
# --------------------------------------------------------------------------


def test_missing_local_evidence_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, _, _ = _run(tmp_path, monkeypatch, ollama_content="")
    assert receipt["status"] == canary.STATUS_FAILED
    assert "check_failed:local_physical_call" in receipt["reasons"]
    assert "check_failed:consumption_proof_verified" in receipt["reasons"]
    assert receipt["online_consumed"] is False
    assert receipt["final_outcome_contributed"] is False


def test_missing_vap_in_receipt_fails_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["verified_assist"] = {}
    failed = set(_evaluate(runtime).failed)
    assert {"vap_integrity", "vap_runtime_binding", "consumption_proof_verified"} <= failed


def test_stale_local_evidence_wrong_attempt_fails_closed(happy: dict[str, Any]) -> None:
    from nexus.services.verified_assist_contract import _rebuild_verified_assist_packet

    runtime = copy.deepcopy(happy["runtime"])
    packet = runtime["verified_assist"]["packet"]
    stale_attempt = {**packet["execution_attempt"], "attempt_id": "sha256:" + "0" * 64}
    stale = _rebuild_verified_assist_packet({
        **packet,
        "execution_attempt": stale_attempt,
        "packet_id": "",
    }).to_dict()
    runtime["verified_assist"]["packet"] = stale
    failed = set(_evaluate(runtime).failed)
    assert "vap_integrity" not in failed  # a self-consistent packet ...
    assert "vap_runtime_binding" in failed  # ... still cannot bind to this attempt
    assert "vap_matches_local_stage" in failed


def test_stale_local_evidence_wrong_task_fails_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["local"]["response"]["task_id"] = "some-other-task"
    world_c = runtime["local"]["response"]["local_outputs"]["world_c_receipt"]
    world_c["task_id"] = "some-other-task"
    failed = set(_evaluate(runtime).failed)
    assert {"local_response_same_task", "world_c_same_task_and_source"} <= failed


def test_substituted_local_result_hash_mismatch_fails_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    summary = runtime["local"]["response"]["candidate_summary"]
    substitute = "f" * 64
    summary["selected_candidate_hash"] = substitute
    summary["applied_patch_hash"] = substitute
    failed = set(_evaluate(runtime).failed)
    assert "vap_derived_from_selected_local_candidate" in failed


def test_substituted_vap_packet_fails_closed(happy: dict[str, Any]) -> None:
    from nexus.services.verified_assist_contract import _rebuild_verified_assist_packet

    runtime = copy.deepcopy(happy["runtime"])
    packet = runtime["verified_assist"]["packet"]
    swapped = _rebuild_verified_assist_packet({
        **packet,
        "bounded_diagnosis": "substituted diagnosis",
        "packet_id": "",
    }).to_dict()
    runtime["verified_assist"]["packet"] = swapped
    failed = set(_evaluate(runtime).failed)
    assert "vap_integrity" not in failed
    assert {
        "vap_matches_local_stage",
        "vap_inline_in_online_input",
        "consumption_proof_verified",
    } <= failed


def test_tampered_vap_bytes_in_online_input_fail_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    fragment = runtime["verified_assist"]["injection_fragment"]
    tampered = fragment.replace("[VAP]", "[VAP]0", 1)
    online = runtime["online"]["response"]
    online["assembled_online_prompt"] = online["assembled_online_prompt"].replace(
        fragment, tampered
    )
    failed = set(_evaluate(runtime).failed)
    assert {"online_input_is_assembled_prompt", "vap_inline_in_online_input"} <= failed


def test_tampered_vap_packet_field_fails_integrity(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["verified_assist"]["packet"]["bounded_diagnosis"] = "tampered"
    assert "vap_integrity" in _evaluate(runtime).failed


def test_forged_contribution_flags_without_proof_fail_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["verified_assist"]["consumption"]["final_prompt_hash"] = "0" * 64
    failed = set(_evaluate(runtime).failed)
    assert {"consumption_proof_verified", "consumption_bound_to_provider_input"} <= failed


def test_online_model_not_admitted_is_blocked_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services.model_workforce_policy import (
        WorkforcePolicyLoader,  # pyright: ignore[reportAttributeAccessIssue]
    )

    original_load = WorkforcePolicyLoader.load

    def load_with_37_route(self: Any, *args: Any, **kwargs: Any) -> Any:
        snapshot = original_load(self, *args, **kwargs)
        routing = copy.deepcopy(dict(snapshot.routing))
        routing["online"] = {
            **routing["online"],
            "fast_bounded_implementation": "agy_flash_37_medium",
        }
        try:
            object.__setattr__(snapshot, "routing", routing)
        except AttributeError:
            snapshot = copy.copy(snapshot)
            object.__setattr__(snapshot, "routing", routing)
        return snapshot

    monkeypatch.setattr(WorkforcePolicyLoader, "load", load_with_37_route)
    receipt, ollama, log = _run(tmp_path, monkeypatch)
    assert receipt["status"] == canary.STATUS_BLOCKED
    assert receipt["reasons"][0].startswith("online_route_not_agy_flash_38:agy_flash_37_medium")
    assert ollama.calls == []
    assert _agy_calls(log) == []


def test_runtime_online_admission_block_returns_to_owner(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    for record in runtime["workforce_admission"]["records"]:
        if record["demand"]["execution_channel"] == "online":
            record["decision"].update({
                "decision": "BLOCK",
                "resolved_worker_id": "agy_flash_37_medium",
                "resolved_model": "gemini-3.7-flash-medium",
                "decision_reasons": ["Worker unavailable"],
            })
    evaluation = _evaluate(runtime)
    reason = canary._online_blocked_reason(evaluation)
    assert reason.startswith(
        "online_model_not_lawfully_admitted:agy_flash_37_medium:gemini-3.7-flash-medium:BLOCK"
    )


def test_caller_route_override_is_rejected_before_any_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, ollama, log = _run(tmp_path, monkeypatch, extra_context={"provider": "gemini"})
    assert receipt["status"] == canary.STATUS_BLOCKED
    assert receipt["reasons"] == [
        "canonical_seam_rejected:canonical_product_caller_override_forbidden:provider"
    ]
    assert ollama.calls == []
    assert _agy_calls(log) == []


def test_online_command_fingerprint_proves_admitted_argv(happy: dict[str, Any]) -> None:
    evaluation = _evaluate(copy.deepcopy(happy["runtime"]))
    assert "online_command_fingerprint_matches_admitted_argv" not in evaluation.failed


def test_online_command_fingerprint_mismatch_fails_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["online"]["response"]["process_evidence"]["command_fingerprint"] = "0" * 64
    assert "online_command_fingerprint_matches_admitted_argv" in _evaluate(runtime).failed


def test_online_command_ran_other_model_fails_closed(happy: dict[str, Any]) -> None:
    import hashlib

    runtime = copy.deepcopy(happy["runtime"])
    response = runtime["online"]["response"]
    argv = [
        _AGY_EXECUTABLE["path"],
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        "gemini-3.7-flash-medium",
        "-p",
        response["assembled_online_prompt"],
    ]
    response["process_evidence"]["command_fingerprint"] = hashlib.sha256(
        json.dumps(argv, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert "online_command_fingerprint_matches_admitted_argv" in _evaluate(runtime).failed


def test_online_command_fingerprint_unknown_executable_fails_closed(
    happy: dict[str, Any],
) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    evaluation = _evaluate(runtime, agy_executable="")
    assert "online_command_fingerprint_matches_admitted_argv" in evaluation.failed


def test_receipt_discloses_online_model_attestation_limits(happy: dict[str, Any]) -> None:
    limits = " ".join(happy["receipt"]["limitations"])
    assert "provider-side served model is not observed" in limits
    assert "does not bind the Task Card hash" in limits


def test_planner_authority_bypass_in_receipt_fails_closed(happy: dict[str, Any]) -> None:
    runtime = copy.deepcopy(happy["runtime"])
    runtime["canonical_execution"]["execution_decision_authority"] = "caller"
    assert "planner_sole_authority" in _evaluate(runtime).failed


def test_preflight_memory_below_threshold_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _ok_probes(unused_memory_bytes=lambda: 5 * 1024**3)
    receipt, ollama, log = _run(tmp_path, monkeypatch, host_probes=probes)
    assert receipt["status"] == canary.STATUS_ABORTED
    assert receipt["reasons"] == ["host_preflight_failed:unused_memory_at_least_threshold"]
    assert "fixture" not in receipt
    assert ollama.calls == []
    assert _agy_calls(log) == []


def test_preflight_other_model_loaded_or_splash_down_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _ok_probes(
        http={
            canary.OLLAMA_SERVICE_PS_URL: (200, json.dumps({"models": [{"name": "qwen3.5:9b"}]})),
            canary.SPLASH_MODELS_URL: (0, "unreachable"),
        },
    )
    receipt, ollama, _ = _run(tmp_path, monkeypatch, host_probes=probes)
    assert receipt["status"] == canary.STATUS_ABORTED
    assert set(receipt["reasons"]) == {
        "host_preflight_failed:ollama_ps_empty_or_only_target",
        "host_preflight_failed:splash_8000_answers",
    }
    assert ollama.calls == []


def test_preflight_ollama_service_down_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _ok_probes(http={canary.OLLAMA_SERVICE_PS_URL: (0, "unreachable")})
    receipt, ollama, _ = _run(tmp_path, monkeypatch, host_probes=probes)
    assert receipt["status"] == canary.STATUS_ABORTED
    assert set(receipt["reasons"]) == {
        "host_preflight_failed:ollama_service_answers",
        "host_preflight_failed:ollama_ps_empty_or_only_target",
    }
    assert ollama.calls == []


def test_dry_mode_calls_no_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt, ollama, log = _run(tmp_path, monkeypatch, physical=False)
    assert receipt["status"] == canary.STATUS_DRY
    assert "host_preflight" not in receipt
    assert (
        receipt["workforce_route_preflight"]["online_fast_bounded_implementation"]["worker_id"]
        == "agy_flash_38"
    )
    assert receipt["workforce_route_preflight"]["online_fallback"] is None
    assert ollama.calls == []
    assert _agy_calls(log) == []
    assert Path(receipt["receipt_path"]).is_file()


def test_physical_requires_confirmed_task_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, ollama, _ = _run(tmp_path, monkeypatch, confirm_task_id="")
    assert receipt["status"] == canary.STATUS_BLOCKED
    assert receipt["reasons"] == ["physical_run_requires_confirm_task_id"]
    assert ollama.calls == []


def test_task_card_drift_from_head_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _card_repo(tmp_path)
    card = repo / canary.TASK_CARD_PATH
    card.write_text(card.read_text(encoding="utf-8") + "\nunreviewed edit\n", encoding="utf-8")
    receipt, ollama, _ = _run(tmp_path, monkeypatch, repo_root=repo)
    assert receipt["status"] == canary.STATUS_BLOCKED
    assert receipt["reasons"] == ["task_card_working_copy_differs_from_head"]
    assert ollama.calls == []


def _capture_route_and_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **seam_kwargs: Any
) -> dict[str, Any]:
    """Run the real seam up to the gateway; evaluate Workforce Admission on its bindings."""
    import nexus.services.gateway as gateway
    from nexus.engine.canonical_task_seam import execute_canonical_product_task
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader
    from nexus.services.runtime_workforce_admission import evaluate_runtime_workforce_admission

    captured: dict[str, Any] = {}

    def capture(self: Any, request: Any, **kwargs: Any) -> Any:
        captured["route"] = request.route
        demands = request.canonical_planning_bundle.to_dict()["plan_payload"]["signal_snapshot"][
            "workforce_demands"
        ]
        captured["admission"] = evaluate_runtime_workforce_admission(
            demands, request.route["workforce_bindings"], WorkforcePolicyLoader()
        ).to_dict()
        raise RuntimeError("stop_before_runtime")

    monkeypatch.setattr(gateway.BattlesuitGateway, "ask_unified", capture)
    (tmp_path / "calc.py").write_text(canary.FIXTURE_FILES["calc.py"], encoding="utf-8")
    with pytest.raises(RuntimeError, match="stop_before_runtime"):
        execute_canonical_product_task(
            canary.TASK_STATEMENT,
            tmp_path,
            execution_context=canary.build_execution_context(canary.TASK_ID, "rev"),
            **seam_kwargs,
        )
    return captured


def _online_admission_decision(captured: dict[str, Any]) -> dict[str, Any]:
    for record in captured["admission"]["records"]:
        if record["demand"]["execution_channel"] == "online":
            return dict(record["decision"])
    raise AssertionError("no online admission record")


def test_task_card_identity_is_required_for_online_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without the verified card, the canonical seam supplies no task_card control."""
    captured = _capture_route_and_admission(monkeypatch, tmp_path)
    online = captured["route"]["workforce_bindings"]["online"]
    assert online["worker_id"] == "agy_flash_38"
    assert "task_card" not in online["controls"]
    decision = _online_admission_decision(captured)
    assert decision["decision"] == "BLOCK"
    assert any("Missing required controls: task_card" in r for r in decision["decision_reasons"])


def test_valid_task_card_identity_supplies_task_card_control(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hashlib

    from nexus.engine.canonical_task_seam import VerifiedTaskCardIdentity

    card = REPO_ROOT / canary.TASK_CARD_PATH
    identity = VerifiedTaskCardIdentity(
        task_id=canary.TASK_ID,
        task_card_path=canary.TASK_CARD_PATH,
        canonical_task_card_path=str(card),
        task_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(),
    )
    captured = _capture_route_and_admission(monkeypatch, tmp_path, task_card_identity=identity)
    online = captured["route"]["workforce_bindings"]["online"]
    assert online["worker_id"] == "agy_flash_38"
    assert "task_card" in online["controls"]
    decision = _online_admission_decision(captured)
    assert decision["decision"] == "ALLOW"
    assert decision["resolved_model"] == "gemini-3.8-flash-medium"


def test_task_card_identity_with_wrong_hash_is_refused_at_seam(tmp_path: Path) -> None:
    from nexus.engine.canonical_task_seam import (
        VerifiedTaskCardIdentity,
        execute_canonical_product_task,
    )

    identity = VerifiedTaskCardIdentity(
        task_id=canary.TASK_ID,
        task_card_path=canary.TASK_CARD_PATH,
        canonical_task_card_path=str(REPO_ROOT / canary.TASK_CARD_PATH),
        task_card_hash="0" * 64,
    )
    (tmp_path / "calc.py").write_text(canary.FIXTURE_FILES["calc.py"], encoding="utf-8")
    with pytest.raises(ValueError, match="verified_task_card_hash_mismatch"):
        execute_canonical_product_task(
            canary.TASK_STATEMENT,
            tmp_path,
            execution_context=canary.build_execution_context(canary.TASK_ID, "rev"),
            task_card_identity=identity,
        )


def test_task_card_identity_for_other_task_is_rejected(tmp_path: Path) -> None:
    import hashlib

    from nexus.engine.canonical_task_seam import (
        VerifiedTaskCardIdentity,
        execute_canonical_product_task,
    )

    card = REPO_ROOT / canary.TASK_CARD_PATH
    identity = VerifiedTaskCardIdentity(
        task_id="another-task",
        task_card_path=canary.TASK_CARD_PATH,
        canonical_task_card_path=str(card),
        task_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(),
    )
    (tmp_path / "calc.py").write_text(canary.FIXTURE_FILES["calc.py"], encoding="utf-8")
    with pytest.raises(ValueError, match="canonical_task_card_task_mismatch"):
        execute_canonical_product_task(
            canary.TASK_STATEMENT,
            tmp_path,
            execution_context=canary.build_execution_context(canary.TASK_ID, "rev"),
            task_card_identity=identity,
        )


def test_world_c_verifier_projection_carries_runtime_attempt_only() -> None:
    from nexus.contracts.root_receipt import build_world_c_verifier_projection

    bound = build_world_c_verifier_projection({
        "task_id": "t",
        "execution_attempt": {"attempt_id": "sha256:abc"},
    })
    unbound = build_world_c_verifier_projection({"task_id": "t", "attempt_id": "caller-supplied"})
    assert bound["attempt_id"] == "sha256:abc"
    assert unbound["attempt_id"] == ""
    assert bound["verifier_status"] == "failed"  # no World C receipt -> never a pass
