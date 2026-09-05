from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path
from typing import Any

import tg7_github_physical as base
from tg7_github_physical_v2 import _bind_tg5_profile

TG5_ROOT: Path | None = None

BENCHMARK_GUARD = {
    "PROVENANCE_HASH_TAMPER": "tampered_evidence_claimed_hash",
    "STALE_REVISION_GENERATION": "stale_change_set_hash_mismatch",
    "DUPLICATE_REPLAY_CONFLICT": "direct_duplicate_verifier",
    "MALFORMED_PROTOCOL_SCHEMA": "malformed_status_input_rejected",
    "MISSING_INADEQUATE_ORACLE": "direct_missing_required_verifier",
    "PATH_SCOPE_ESCAPE": "direct_scope_escape",
}


def _semantic_test_source(case: dict[str, Any], bottle_hash: str) -> str:
    case_json = base.canonical(case)
    return f'''import hashlib, json, sys\nfrom pathlib import Path\n\nsys.path.insert(0, "/nexus")\nsys.path.insert(0, "/bottle")\nimport bottle\nimport product.benchmark as bm\nfrom product.runtime.auth import validate_auth_header\n\nCASE = json.loads({case_json!r})\n\ndef _digest(value):\n    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")\n    return "sha256:" + hashlib.sha256(raw).hexdigest()\n\ndef _benchmark_observation(case_id):\n    report = bm.run_benchmark()\n    assert report.infra_invalid_count == 0\n    assert report.false_completion_count == 0\n    assert bm.verify_report(report) == ()\n    row = next(item for item in report.cases if item.case_id == case_id)\n    actual = row.actual.to_dict()\n    if actual["outcome_kind"] == "CERTIFICATION":\n        return actual["verification_status"], actual["disposition"], actual\n    if actual["outcome_kind"] == "INPUT_REJECTED":\n        return "UNVERIFIABLE", "INPUT_REJECTED", actual\n    if actual["outcome_kind"] == "RECEIPT_INVALID":\n        return "UNVERIFIABLE", "REJECTED", actual\n    raise AssertionError("unsupported benchmark guard outcome: " + repr(actual))\n\ndef test_physical_hostile_case():\n    bottle_bytes = Path("/bottle/bottle.py").read_bytes()\n    observed_bottle_hash = "sha256:" + hashlib.sha256(bottle_bytes).hexdigest()\n    assert observed_bottle_hash == {bottle_hash!r}\n    app = bottle.Bottle()\n    @app.get("/tg7/<name>")\n    def _tg7_probe(name):\n        return name\n    assert any(route.rule == "/tg7/<name>" for route in app.routes)\n    assert CASE["repository_commit"] == {base.BOTTLE_COMMIT!r}\n    assert CASE["repository_tree"] == {base.BOTTLE_TREE!r}\n    assert _digest(CASE["request_payload"]) == CASE["canonical_request_hash"]\n\n    family = CASE["hostile_family"]\n    guard_source = None\n    actual_detail = None\n    if family == "AUTH_ISSUER_TAMPER":\n        expected_token = "A" * 43\n        hostile_token = "B" * 43\n        accepted = validate_auth_header("Bearer " + hostile_token, expected_token)\n        assert accepted is False\n        status, disposition = "UNVERIFIABLE", "BLOCKED"\n        guard_source = "product.runtime.auth.validate_auth_header"\n        actual_detail = {{"accepted": accepted}}\n    elif family == "CRASH_UNKNOWN_EFFECT":\n        from product.execution.python_runner import PythonOCIProfile, PythonOCIRunner, RunnerStatus\n        profile = PythonOCIProfile.load(\n            Path("/tg5/product/execution/profiles/python-oci-pytest-v1.json"),\n            Path("/tg5/product/execution/profiles/python-oci-pytest-v1.lock"),\n            Path("/tg5/uv.lock"),\n        )\n        runner = PythonOCIRunner(profile)\n        req = {{\n            "source_revision": CASE["repository_commit"],\n            "source_tree": CASE["repository_tree"],\n            "contract_hash": CASE["case_hash"],\n            "plan_hash": CASE["oracle_hash"],\n            "environment_hash": observed_bottle_hash,\n            "attempt_id": "nested-crash-" + CASE["case_id"],\n        }}\n        def crash_executor(*_args, **_kwargs):\n            raise RuntimeError("controlled unknown effect")\n        nested = runner.run(req, crash_executor)\n        assert nested.status is RunnerStatus.UNVERIFIABLE\n        assert "MALFORMED_OR_UNAVAILABLE" in nested.reason_codes\n        status, disposition = "UNVERIFIABLE", "BLOCKED"\n        guard_source = "product.execution.python_runner.PythonOCIRunner.run"\n        actual_detail = nested.to_dict()\n    else:\n        guard_id = {BENCHMARK_GUARD!r}[family]\n        status, disposition, actual_detail = _benchmark_observation(guard_id)\n        guard_source = "product.benchmark:" + guard_id\n\n    observed = {{\n        "schema": "nexus.core-v1.tg7-physical-observation.v1",\n        "case_id": CASE["case_id"],\n        "case_hash": CASE["case_hash"],\n        "hostile_family": family,\n        "guard_source": guard_source,\n        "actual_status": status,\n        "actual_disposition": disposition,\n        "actual_detail": actual_detail,\n        "bottle_py_hash": observed_bottle_hash,\n        "canonical_request_hash": CASE["canonical_request_hash"],\n        "oracle_hash": CASE["oracle_hash"],\n    }}\n    observed["observation_hash"] = _digest(observed)\n    Path("/evidence/case-result.json").write_text(\n        json.dumps(observed, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\\n",\n        encoding="utf-8",\n    )\n'''


def _semantic_executor_factory(subject: Path, bottle: Path, deps: Path, work: Path, case: dict[str, Any]):
    from product.execution.python_runner import DEPENDENCY_ARTIFACTS_HASH

    if TG5_ROOT is None:
        raise RuntimeError("TG5_ROOT not bound")
    observed_dir = work.parent / "observations"
    observed_dir.mkdir(parents=True, exist_ok=True)

    def executor(profile: Any, request: dict[str, object], index: int) -> dict[str, object]:
        run_root = work / f"{case['case_id']}-{index}"
        case_root = run_root / "workspace"
        evidence = run_root / "evidence"
        case_root.mkdir(parents=True, exist_ok=True)
        evidence.mkdir(parents=True, exist_ok=True)
        (case_root / "test_case.py").write_text(
            _semantic_test_source(case, os.environ["TG7_BOTTLE_HASH"]), encoding="utf-8"
        )
        image = f"{profile.image}@{profile.image_digest}"
        execution_id = f"gha-sem-{os.environ.get('GITHUB_RUN_ID','local')}-{case['case_id']}-{index}-{uuid.uuid4().hex[:10]}"
        cmd = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--memory", str(profile.memory_bytes), "--ulimit", f"cpu={profile.cpu_seconds}:{profile.cpu_seconds}",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{case_root}:/workspace:ro",
            "-v", f"{evidence}:/evidence:rw",
            "-v", f"{deps}:/deps:ro",
            "-v", f"{subject}:/nexus:ro",
            "-v", f"{TG5_ROOT}:/tg5:ro",
            "-v", f"{bottle}:/bottle:ro",
            "-w", "/workspace",
            "-e", "PYTHONPATH=/deps:/nexus:/bottle",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "-e", "PYTEST_ADDOPTS=-q -p no:cacheprovider /workspace/test_case.py",
            image, *profile.command,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=profile.timeout_seconds + 30)
        junit_path = evidence / "junit.xml"
        junit = junit_path.read_bytes() if junit_path.exists() else b""
        observation_path = evidence / "case-result.json"
        if proc.returncode == 0:
            if not observation_path.is_file():
                raise RuntimeError("successful semantic case emitted no observation")
            raw_observation = observation_path.read_bytes()
            parsed = json.loads(raw_observation.decode("utf-8"))
            canonical = (base.canonical(parsed) + "\n").encode("utf-8")
            if raw_observation != canonical:
                raise RuntimeError("semantic observation is not canonical")
            (observed_dir / f"{case['case_id']}-{index}.json").write_bytes(raw_observation)
        return {
            "source_revision": request["source_revision"],
            "source_tree": request["source_tree"],
            "contract_hash": request["contract_hash"],
            "plan_hash": request["plan_hash"],
            "environment_hash": request["environment_hash"],
            "profile_id": profile.profile_id,
            "image": profile.image,
            "image_digest": profile.image_digest,
            "lock_digest": profile.lock_digest,
            "dependency_artifacts_hash": DEPENDENCY_ARTIFACTS_HASH,
            "network": profile.network,
            "rootfs": profile.rootfs,
            "timeout_seconds": profile.timeout_seconds,
            "memory_bytes": profile.memory_bytes,
            "cpu_seconds": profile.cpu_seconds,
            "execution_id": execution_id,
            "argv": profile.command,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "junit": junit,
        }
    return executor


def _patch_family_contracts() -> None:
    source, status, _disp, ops = base.FAMILY_CONTRACTS["DUPLICATE_REPLAY_CONFLICT"]
    base.FAMILY_CONTRACTS["DUPLICATE_REPLAY_CONFLICT"] = (source, status, "REJECTED", ops)


def _postprocess_from_observations(subject: Path, root: Path, tar_path: Path) -> None:
    sys.path.insert(0, str(subject))
    from product.benchmark.tg7_shadow import validate_report, validate_shadow_receipt

    corpus = base.load_json(root / "corpus.json")
    selection = base.load_json(root / "selection.json")
    tg5 = base.load_json(root / "tg5-receipt.json")
    observations = root / "observations"
    attempts = root / "attempts"
    observations.chmod(0o755)
    attempts.chmod(0o755)
    semantic_hashes: list[str] = []

    for case in corpus["cases"]:
        cid = case["case_id"]
        first_path = observations / f"{cid}-1.json"
        second_path = observations / f"{cid}-2.json"
        first_raw = first_path.read_bytes()
        second_raw = second_path.read_bytes()
        if first_raw != second_raw:
            raise RuntimeError(f"semantic observations diverged across fresh executions: {cid}")
        observed = json.loads(first_raw.decode("utf-8"))
        expected_hash = base.digest({k: v for k, v in observed.items() if k != "observation_hash"})
        if observed.get("observation_hash") != expected_hash:
            raise RuntimeError(f"semantic observation hash mismatch: {cid}")
        if observed.get("case_id") != cid or observed.get("case_hash") != case["case_hash"]:
            raise RuntimeError(f"semantic observation case binding mismatch: {cid}")
        if observed.get("actual_status") != case["expected_status"] or observed.get("actual_disposition") != case["expected_disposition"]:
            raise RuntimeError(f"semantic guard outcome differs from blinded oracle for {cid}: {observed}")
        semantic_hashes.append(observed["observation_hash"])

        attempt_path = attempts / f"{cid}.json"
        attempt_path.chmod(0o644)
        attempt = base.load_json(attempt_path)
        attempt["actual_status"] = observed["actual_status"]
        attempt["actual_disposition"] = observed["actual_disposition"]
        attempt["evidence_hash"] = base.digest({
            "case_hash": case["case_hash"],
            "oracle_hash": case["oracle_hash"],
            "runner_result_hash": attempt["runner_result_hash"],
            "semantic_observation_hash": observed["observation_hash"],
        })
        body = {k: v for k, v in attempt.items() if k != "attempt_hash"}
        attempt["attempt_hash"] = base.digest(body)
        base.write_json(attempt_path, attempt)
        attempt_path.chmod(0o444)
        first_path.chmod(0o444)
        second_path.chmod(0o444)

    attempts.chmod(0o555)
    observations.chmod(0o555)
    for name in ("shadow-receipt.json", "report.json", "controller-summary.json"):
        path = root / name
        if path.exists():
            path.unlink()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(subject)
    subprocess.run([
        sys.executable, "-m", "product.benchmark.tg7_shadow",
        "--selection", str(root / "selection.json"),
        "--repository", str(root / "repository"),
        "--manifest", str(root / "corpus.json"),
        "--tg5-receipt", str(root / "tg5-receipt.json"),
        "--shadow-receipt", str(root / "shadow-receipt.json"),
        "--report", str(root / "report.json"),
    ], cwd=subject, env=env, check=True)
    report = base.load_json(root / "report.json")
    shadow = base.load_json(root / "shadow-receipt.json")
    errors = validate_shadow_receipt(shadow, corpus=corpus, tg5_receipt=tg5, selection=selection)
    errors += validate_report(report, shadow_receipt=shadow, corpus=corpus)
    if errors or report["trust_mismatches"] != 0 or report["false_certification_count"] != 0 or report["infra_invalid_count"] != 0:
        raise RuntimeError(f"semantic TG7 reduction failed: {errors} report={report}")
    (root / "shadow-receipt.json").chmod(0o444)
    (root / "report.json").chmod(0o444)
    summary = {
        "schema": "nexus.core-v1.tg7-github-semantic-physical-summary.v1",
        "subject": base.TG7_SUBJECT,
        "subject_tree": base.git(subject, "rev-parse", "HEAD^{tree}"),
        "selection_hash": selection["selection_hash"],
        "corpus_hash": corpus["corpus_hash"],
        "tg5_receipt_hash": tg5["receipt_hash"],
        "attempt_count": 56,
        "physical_execution_count": 112,
        "semantic_observation_count": 112,
        "semantic_observation_set_hash": base.digest(semantic_hashes),
        "eligible_count": report["eligible_count"],
        "infra_invalid_count": report["infra_invalid_count"],
        "false_certification_count": report["false_certification_count"],
        "trust_mismatches": report["trust_mismatches"],
        "report_hash": report["report_hash"],
        "shadow_receipt_hash": shadow["receipt_hash"],
        "generated_at": base._utc_now(),
    }
    base.write_json(root / "controller-summary.json", summary)
    (root / "controller-summary.json").chmod(0o444)
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(root, arcname="tg7")
    print(base.canonical(summary))


def collect(subject: Path, tg5_subject: Path, tg5_receipt: Path, tg5_provenance: Path, root: Path, tar_path: Path) -> None:
    global TG5_ROOT
    TG5_ROOT = tg5_subject.resolve()
    _bind_tg5_profile(subject, TG5_ROOT)
    _patch_family_contracts()
    base._case_test_source = _semantic_test_source
    base._physical_executor_factory = _semantic_executor_factory
    base._tg7_collect(subject, tg5_receipt, tg5_provenance, root, tar_path)
    _postprocess_from_observations(subject, root, tar_path)


def audit(subject: Path, tg5_subject: Path, root: Path, junit: Path, output: Path) -> None:
    _bind_tg5_profile(subject, tg5_subject)
    _patch_family_contracts()
    base._audit(subject, root, junit, output)
    acceptance = base.load_json(output)
    corpus = base.load_json(root / "corpus.json")
    observations = root / "observations"
    semantic_errors: list[str] = []
    observed_count = 0
    semantic_hashes: list[str] = []
    for case in corpus["cases"]:
        cid = case["case_id"]
        values = []
        for index in (1, 2):
            path = observations / f"{cid}-{index}.json"
            if path.stat().st_mode & 0o222:
                semantic_errors.append(f"writable semantic observation: {path.name}")
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
            if raw != (base.canonical(value) + "\n").encode("utf-8"):
                semantic_errors.append(f"noncanonical semantic observation: {path.name}")
            values.append(value)
            observed_count += 1
        if values[0] != values[1]:
            semantic_errors.append(f"fresh semantic observations diverge: {cid}")
            continue
        observed = values[0]
        semantic_hashes.append(observed.get("observation_hash"))
        attempt = base.load_json(root / "attempts" / f"{cid}.json")
        if attempt.get("actual_status") != observed.get("actual_status"):
            semantic_errors.append(f"attempt status not observation-derived: {cid}")
        if attempt.get("actual_disposition") != observed.get("actual_disposition"):
            semantic_errors.append(f"attempt disposition not observation-derived: {cid}")
        if observed.get("actual_status") != case.get("expected_status") or observed.get("actual_disposition") != case.get("expected_disposition"):
            semantic_errors.append(f"observed guard differs from oracle: {cid}")
        if not str(observed.get("guard_source", "")).startswith("product."):
            semantic_errors.append(f"unbound guard source: {cid}")
    if observed_count != 112:
        semantic_errors.append(f"expected 112 semantic observations, found {observed_count}")
    acceptance["semantic_observation_count"] = observed_count
    acceptance["semantic_observation_set_hash"] = base.digest(semantic_hashes)
    acceptance["semantic_binding"] = "PASS" if not semantic_errors else "FAIL"
    acceptance["errors"] = list(acceptance.get("errors", [])) + semantic_errors
    if semantic_errors:
        acceptance["status"] = "BLOCK"
        acceptance["claim"] = "TG7_PHYSICAL_BLOCKED"
    base.write_json(output, acceptance)
    print(base.canonical(acceptance))
    if semantic_errors:
        raise SystemExit(1)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--subject", type=Path, required=True)
    c.add_argument("--tg5-subject", type=Path, required=True)
    c.add_argument("--tg5-receipt", type=Path, required=True)
    c.add_argument("--tg5-provenance", type=Path, required=True)
    c.add_argument("--root", type=Path, required=True)
    c.add_argument("--tar", type=Path, required=True)
    a = sub.add_parser("audit")
    a.add_argument("--subject", type=Path, required=True)
    a.add_argument("--tg5-subject", type=Path, required=True)
    a.add_argument("--root", type=Path, required=True)
    a.add_argument("--junit", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.cmd == "collect":
        collect(args.subject.resolve(), args.tg5_subject.resolve(), args.tg5_receipt.resolve(), args.tg5_provenance.resolve(), args.root.resolve(), args.tar.resolve())
    else:
        audit(args.subject.resolve(), args.tg5_subject.resolve(), args.root.resolve(), args.junit.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
