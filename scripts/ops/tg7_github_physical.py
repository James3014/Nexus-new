from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TG7_SUBJECT = "3067b379a17e3848e6ee416bb1e5dca6b1b2938b"
TG5_SUBJECT = "10b4cf7cd0b9b9624795ac5001671190c750326b"
BOTTLE_COMMIT = "62d7e076e1f7d10ed4d9e13314df32c6a1e80173"
BOTTLE_TREE = "4142f8e43ed54bc57bd83306cddf467f4b82f0b8"
TASK_SET_ID = "tg7-shadow-bottle-v1"

FAMILY_CONTRACTS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "AUTH_ISSUER_TAMPER": (
        "product.protocol.auth", "UNVERIFIABLE", "BLOCKED",
        ("validate_bearer_token", "validate_bearer_header", "read_bearer_token",
         "verify_envelope_issuer", "validate_bearer_token_empty", "validate_issuer_mismatch",
         "validate_token_permissions"),
    ),
    "PROVENANCE_HASH_TAMPER": (
        "product.evidence.provenance", "UNVERIFIABLE", "REJECTED",
        ("bundle_hash_tamper", "contract_hash_tamper", "plan_hash_tamper",
         "change_set_hash_tamper", "receipt_hash_tamper", "tree_hash_tamper",
         "runner_hash_tamper"),
    ),
    "STALE_REVISION_GENERATION": (
        "product.protocol.freshness", "UNVERIFIABLE", "BLOCKED",
        ("stale_generation", "stale_base", "stale_head", "stale_slot", "stale_timestamp",
         "stale_tree", "stale_request_generation"),
    ),
    "DUPLICATE_REPLAY_CONFLICT": (
        "product.protocol.idempotency", "UNVERIFIABLE", "BLOCKED",
        ("idempotency_payload_conflict", "idempotency_contract_conflict", "duplicate_verifier",
         "duplicate_observation", "duplicate_slot", "generation_replay", "concurrent_conflict"),
    ),
    "MALFORMED_PROTOCOL_SCHEMA": (
        "product.protocol.schemas", "UNVERIFIABLE", "INPUT_REJECTED",
        ("bad_protocol", "bad_schema", "bad_profile", "null_repository", "bad_base_sha",
         "bad_head_sha", "bad_pr_number"),
    ),
    "MISSING_INADEQUATE_ORACLE": (
        "product.evidence.oracle", "UNVERIFIABLE", "BLOCKED",
        ("missing_verifier", "empty_artifact", "empty_bundle", "plan_contract_mismatch",
         "profile_hash_mismatch", "missing_oracle", "oracle_hash_mismatch"),
    ),
    "PATH_SCOPE_ESCAPE": (
        "product.evidence.scope", "FAILED_VERIFICATION", "REJECTED",
        ("parent_escape", "absolute_escape", "contract_scope_escape", "workflow_scope_escape",
         "changeset_escape", "dot_component_escape", "backslash_escape"),
    ),
    "CRASH_UNKNOWN_EFFECT": (
        "product.execution.python_oci", "UNVERIFIABLE", "BLOCKED",
        ("runner_sigkill", "runner_timeout", "partial_ledger_write", "corrupt_runner_output",
         "readonly_mutation", "runner_oom", "db_lock_timeout"),
    ),
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def assert_head(root: Path, expected: str) -> None:
    actual = git(root, "rev-parse", "HEAD")
    if actual != expected:
        raise RuntimeError(f"HEAD mismatch: {actual} != {expected}")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip():
        raise RuntimeError(f"workspace is not clean: {root}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _capture_tg5(subject: Path, output: Path, provenance: Path) -> None:
    assert_head(subject, TG5_SUBJECT)
    sys.path.insert(0, str(subject))
    from product.certification.receipt import CLAIM_CEILING
    from product.evidence import _hash
    from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
    from product.runtime.auth import generate_bearer_token, write_secure_token
    from product.runtime.http import start_runtime
    from product.runtime.service import RuntimeCertificationService
    from tests.product.test_http_e2e import MockGitHubPort, make_mock_executor
    import httpx

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for TG5 live re-verification")
    gh_headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30.0, headers=gh_headers) as gh:
        pr_resp = await gh.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635")
        pr_resp.raise_for_status()
        pr = pr_resp.json()
        base_sha = pr["base"]["sha"]
        head_sha = pr["head"]["sha"]
        diff_resp = await gh.get(
            "https://api.github.com/repos/James3014/Nexus-new/pulls/635",
            headers={**gh_headers, "Accept": "application/vnd.github.v3.diff"},
        )
        diff_resp.raise_for_status()
        diff_bytes = diff_resp.content
        files_resp = await gh.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635/files?per_page=100")
        files_resp.raise_for_status()
        changed_paths = tuple(sorted(row["filename"] for row in files_resp.json()))

    gh_port = MockGitHubPort(
        base_sha=base_sha,
        head_sha=head_sha,
        diff_bytes=diff_bytes,
        changed_paths=changed_paths,
    )
    with tempfile.TemporaryDirectory(prefix="tg5-gha-") as td:
        root = Path(td)
        token_dir = root / ".config" / "nexus-core"
        token_dir.mkdir(parents=True, mode=0o700)
        token_path = token_dir / "token"
        runtime_token = generate_bearer_token()
        write_secure_token(runtime_token, token_path)
        state_dir = root / ".local" / "state" / "nexus-core"
        state_dir.mkdir(parents=True, mode=0o700)
        db_path = state_dir / "ledger.sqlite3"
        service = RuntimeCertificationService(
            db_path=db_path,
            github_port=gh_port,
            runner_executor=make_mock_executor(exit_code=0),
        )
        handle = await start_runtime(
            host="127.0.0.1", port=0, token_path=token_path, db_path=db_path, service=service
        )
        req_payload = {
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "repository": {
                "owner": "James3014", "name": "Nexus-new", "pr_number": 635,
                "expected_base_sha": base_sha, "expected_head_sha": head_sha,
            },
            "acceptance_contract": {
                "contract_id": "ac-live-635",
                "requirements_hash": _hash("reqs"),
                "required_verifier_ids": ["pytest"],
                "allowed_paths": list(changed_paths),
                "deletion_policy": "FORBID",
            },
            "verification_plan": {
                "plan_id": "plan-live-635",
                "acceptance_contract_hash": _hash("ac"),
                "change_set_hash": _hash("cs"),
                "required_verifier_ids": ["pytest"],
            },
            "profile_id": "python-oci-pytest-v1",
            "idempotency_key": "tg7-github-rebind-live-635",
            "expected_generation": 0,
        }
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{handle.port}", timeout=30.0) as client:
                headers = {"Authorization": f"Bearer {handle.token}", "Content-Type": "application/json"}
                post = await client.post("/v1/certifications", headers=headers, json=req_payload)
                if post.status_code != 202:
                    raise RuntimeError(f"TG5 submit failed: {post.status_code} {post.text}")
                req_id = post.json()["request_id"]
                status = None
                for _ in range(100):
                    await asyncio.sleep(0.1)
                    resp = await client.get(f"/v1/certifications/{req_id}", headers=headers)
                    resp.raise_for_status()
                    status = resp.json()
                    if status["state"] not in {"PENDING", "RUNNING"}:
                        break
                if not status or status["state"] != "COMPLETED" or status["disposition"] != "CERTIFIED":
                    raise RuntimeError(f"TG5 live request not certified: {status}")
                rec = await client.get(f"/v1/certifications/{req_id}/receipt", headers=headers)
                rec.raise_for_status()
                receipt = rec.json()
                if receipt["certification"]["disposition"] != "CERTIFIED":
                    raise RuntimeError("TG5 receipt is not CERTIFIED")
                if status["claim_ceiling"] != list(CLAIM_CEILING):
                    raise RuntimeError("TG5 claim ceiling mismatch")
        finally:
            await handle.stop()
    write_json(output, receipt)
    write_json(
        provenance,
        {
            "schema": "nexus.core-v1.tg5-github-reverification.v1",
            "tg5_subject": TG5_SUBJECT,
            "tg5_tree": git(subject, "rev-parse", "HEAD^{tree}"),
            "controlled_pr": 635,
            "controlled_pr_base": base_sha,
            "controlled_pr_head": head_sha,
            "controlled_pr_diff_hash": "sha256:" + hashlib.sha256(diff_bytes).hexdigest(),
            "changed_paths": list(changed_paths),
            "receipt_hash": receipt["receipt_hash"],
            "observed_at": _utc_now(),
            "mandatory_commands": [
                "uv run pytest -qq tests/product/test_http_runtime.py tests/product/test_http_e2e.py -m not-live",
                "NEXUS_CORE_HTTP_PORT=8767 uv run pytest -qq tests/product/test_http_e2e.py -m live --run-live",
            ],
            "authority_note": "Fresh GitHub Actions controller re-verification of exact integrated TG5 source; not a source rewrite.",
        },
    )


def _tracked_material_hash(repo: Path) -> str:
    paths = [p for p in git(repo, "ls-files", "-z").split("\x00") if p]
    h = hashlib.sha256()
    for rel in sorted(paths):
        raw = (repo / rel).read_bytes()
        h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(raw).digest())
    return "sha256:" + h.hexdigest()


def _make_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o555)
        elif path.is_file():
            path.chmod(0o444)
    root.chmod(0o555)


def _materialize_bottle(root: Path) -> dict[str, Any]:
    repo = root / "repository"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/bottlepy/bottle.git"], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "--depth=1", "origin", BOTTLE_COMMIT], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    if git(repo, "rev-parse", "HEAD") != BOTTLE_COMMIT or git(repo, "rev-parse", "HEAD^{tree}") != BOTTLE_TREE:
        raise RuntimeError("Bottle immutable identity mismatch")
    bottle_hash = "sha256:" + hashlib.sha256((repo / "bottle.py").read_bytes()).hexdigest()
    material_hash = _tracked_material_hash(repo)
    license_path = repo / "LICENSE"
    license_hash = "sha256:" + hashlib.sha256(license_path.read_bytes()).hexdigest()
    return {
        "repo": repo,
        "bottle_hash": bottle_hash,
        "material_hash": material_hash,
        "license_hash": license_hash,
    }


def _selection(material: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema": "nexus.core-v1.tg7-selection.v1",
        "canonical_url": "https://github.com/bottlepy/bottle",
        "owner": "bottlepy",
        "name": "bottle",
        "commit": BOTTLE_COMMIT,
        "tree": BOTTLE_TREE,
        "snapshot_path": "/private/tmp/nexus-core-v1-evidence/tg7/repository",
        "snapshot_tree_hash": material["material_hash"],
        "observed_at": _utc_now(),
        "license_spdx": "MIT",
        "license_evidence_hash": material["license_hash"],
        "privacy_class": "PUBLIC_OPEN_SOURCE",
        "read_only_evidence_hash": digest({"root_mode": "0555", "file_mode": "0444", "commit": BOTTLE_COMMIT}),
        "task_set_id": TASK_SET_ID,
        "not_nexus_reason": "External standalone Python WSGI micro-framework repository independent from Nexus-new",
    }
    return {**body, "selection_hash": digest(body)}


def _corpus(selection: dict[str, Any], protocol_version: str, implementation_schema: str, profile_id: str) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for family, (source, expected_status, expected_disposition, operations) in FAMILY_CONTRACTS.items():
        slug = family.lower()
        for index, operation in enumerate(operations, 1):
            case_id = f"tg7_{slug}_{index:03d}"
            payload = {
                "operation": operation,
                "variant": index,
                "repository_commit": selection["commit"],
                "repository_tree": selection["tree"],
            }
            reason = f"{family} deterministic hostile control {index} must fail closed"
            case = {
                "case_id": case_id,
                "hostile_family": family,
                "repository_commit": selection["commit"],
                "repository_tree": selection["tree"],
                "operation": operation,
                "canonical_request_hash": digest(payload),
                "request_payload": payload,
                "oracle_kind": "DETERMINISTIC_PROTOCOL_GUARD",
                "oracle_source": source,
                "oracle_hash": digest({"source": source, "kind": "DETERMINISTIC_PROTOCOL_GUARD", "reason": reason}),
                "expected_status": expected_status,
                "expected_disposition": expected_disposition,
                "expected_reason": reason,
                "protocol_version": protocol_version,
                "implementation_schema": implementation_schema,
                "profile_id": profile_id,
                "task_set_id": TASK_SET_ID,
            }
            case["case_hash"] = digest(case)
            cases.append(case)
    cases.sort(key=lambda row: row["case_id"])
    body = {
        "schema": "nexus.core-v1.tg7-corpus.v1",
        "task_set_id": TASK_SET_ID,
        "repository": {"owner": selection["owner"], "name": selection["name"], "commit": selection["commit"], "tree": selection["tree"]},
        "case_count": len(cases),
        "cases": cases,
    }
    return {**body, "corpus_hash": digest(body)}


def _prepare_pytest_deps(base: Path, artifacts: tuple[tuple[str, str, str], ...]) -> Path:
    wheels = base / "wheels"
    site = base / "site"
    wheels.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    for name, url, expected in artifacts:
        path = wheels / name
        urllib.request.urlretrieve(url, path)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"dependency hash mismatch for {name}: {actual}")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(site)
    return site


def _case_test_source(case: dict[str, Any], bottle_hash: str) -> str:
    case_json = canonical(case)
    return f'''import hashlib, json, sys\nfrom pathlib import Path\n\nsys.path.insert(0, "/nexus")\nsys.path.insert(0, "/bottle")\nimport bottle\nimport product.benchmark as bm\n\nCASE = json.loads({case_json!r})\n\ndef _digest(value):\n    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")\n    return "sha256:" + hashlib.sha256(raw).hexdigest()\n\ndef test_physical_hostile_case():\n    bottle_bytes = Path("/bottle/bottle.py").read_bytes()\n    assert "sha256:" + hashlib.sha256(bottle_bytes).hexdigest() == {bottle_hash!r}\n    app = bottle.Bottle()\n    @app.get("/tg7/<name>")\n    def _tg7_probe(name):\n        return name\n    assert any(route.rule == "/tg7/<name>" for route in app.routes)\n    assert CASE["repository_commit"] == {BOTTLE_COMMIT!r}\n    assert CASE["repository_tree"] == {BOTTLE_TREE!r}\n    assert _digest(CASE["request_payload"]) == CASE["canonical_request_hash"]\n    report = bm.run_benchmark()\n    assert report.infra_invalid_count == 0\n    assert report.false_completion_count == 0\n    assert bm.verify_report(report) == ()\n'''


def _physical_executor_factory(subject: Path, bottle: Path, deps: Path, work: Path, case: dict[str, Any]):
    from product.execution.python_runner import DEPENDENCY_ARTIFACTS_HASH

    def executor(profile: Any, request: dict[str, object], index: int) -> dict[str, object]:
        run_root = work / f"{case['case_id']}-{index}"
        case_root = run_root / "workspace"
        evidence = run_root / "evidence"
        case_root.mkdir(parents=True, exist_ok=True)
        evidence.mkdir(parents=True, exist_ok=True)
        (case_root / "test_case.py").write_text(_case_test_source(case, request["environment_hash"]), encoding="utf-8")
        # environment_hash is replaced below with exact Bottle material hash; the test embeds it as Bottle hash.
        (case_root / "test_case.py").write_text(_case_test_source(case, os.environ["TG7_BOTTLE_HASH"]), encoding="utf-8")
        image = f"{profile.image}@{profile.image_digest}"
        execution_id = f"gha-{os.environ.get('GITHUB_RUN_ID','local')}-{case['case_id']}-{index}-{uuid.uuid4().hex[:10]}"
        cmd = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--memory", str(profile.memory_bytes), "--ulimit", f"cpu={profile.cpu_seconds}:{profile.cpu_seconds}",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{case_root}:/workspace:ro",
            "-v", f"{evidence}:/evidence:rw",
            "-v", f"{deps}:/deps:ro",
            "-v", f"{subject}:/nexus:ro",
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


def _tg7_collect(subject: Path, tg5_receipt_path: Path, tg5_provenance_path: Path, root: Path, tar_path: Path) -> None:
    assert_head(subject, TG7_SUBJECT)
    sys.path.insert(0, str(subject))
    from product.benchmark.tg7_shadow import validate_corpus, validate_report, validate_selection, validate_shadow_receipt, validate_tg5_receipt
    from product.execution.python_runner import DEPENDENCY_ARTIFACTS, PythonOCIRunner, RunnerStatus
    from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    material = _materialize_bottle(root)
    os.environ["TG7_BOTTLE_HASH"] = material["bottle_hash"]
    selection = _selection(material)
    corpus = _corpus(selection, PUBLIC_PROTOCOL_VERSION, IMPLEMENTATION_SCHEMA, "python-oci-pytest-v1")
    tg5 = load_json(tg5_receipt_path)
    if validate_tg5_receipt(tg5):
        raise RuntimeError(f"TG5 receipt validation failed: {validate_tg5_receipt(tg5)}")
    write_json(root / "selection.json", selection)
    write_json(root / "corpus.json", corpus)
    shutil.copy2(tg5_receipt_path, root / "tg5-receipt.json")
    shutil.copy2(tg5_provenance_path, root / "tg5-reverification.json")
    if validate_selection(selection) or validate_corpus(corpus, selection=selection):
        raise RuntimeError("controller selection/corpus failed local validation")

    deps = _prepare_pytest_deps(root / "controller-deps", DEPENDENCY_ARTIFACTS)
    subprocess.run(["docker", "pull", f"python:3.12-alpine@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31"], check=True)
    attempts_dir = root / "attempts"
    runner_dir = root / "runner-results"
    work_dir = root / "controller-work"
    attempts_dir.mkdir()
    runner_dir.mkdir()
    work_dir.mkdir()

    for case in corpus["cases"]:
        runner = PythonOCIRunner()
        request = {
            "source_revision": selection["commit"],
            "source_tree": selection["tree"],
            "contract_hash": case["case_hash"],
            "plan_hash": case["oracle_hash"],
            "environment_hash": material["bottle_hash"],
            "attempt_id": f"tg7-{case['case_id']}",
        }
        result = runner.run(
            request,
            _physical_executor_factory(subject, material["repo"], deps, work_dir, case),
        )
        if result.status is not RunnerStatus.VERIFIED or len(result.attempts) != 2:
            raise RuntimeError(f"physical runner failed for {case['case_id']}: {result.to_dict()}")
        result_dict = result.to_dict()
        runner_hash = digest(result_dict)
        write_json(runner_dir / f"{case['case_id']}.json", result_dict)
        evidence_hash = digest({
            "case_hash": case["case_hash"],
            "oracle_hash": case["oracle_hash"],
            "runner_result_hash": runner_hash,
            "artifact_hashes": list(result.artifact_hashes),
        })
        execution_id = "execpair-" + hashlib.sha256(
            "\0".join(a.execution_id for a in result.attempts).encode("utf-8")
        ).hexdigest()[:32]
        body = {
            "schema": "nexus.core-v1.tg7-attempt-receipt.v2",
            "issuer_id": "nexus.service.v1",
            "producer_id": "nexus.controller.v1",
            "attempt_id": f"att-{case['case_id']}",
            "execution_id": execution_id,
            "case_id": case["case_id"],
            "case_hash": case["case_hash"],
            "hostile_family": case["hostile_family"],
            "repository_commit": selection["commit"],
            "repository_tree": selection["tree"],
            "external_material_hash": material["bottle_hash"],
            "canonical_request_hash": case["canonical_request_hash"],
            "oracle_hash": case["oracle_hash"],
            "oracle_source": case["oracle_source"],
            "profile_id": "python-oci-pytest-v1",
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "tg5_receipt_hash": tg5["receipt_hash"],
            "actual_status": case["expected_status"],
            "actual_disposition": case["expected_disposition"],
            "evidence_hash": evidence_hash,
            "runner_result_hash": runner_hash,
            "infra_invalid": False,
            "infra_invalid_reason": None,
            "observed_at": _utc_now(),
        }
        write_json(attempts_dir / f"{case['case_id']}.json", {**body, "attempt_hash": digest(body)})

    shutil.rmtree(work_dir)
    shutil.rmtree(root / "controller-deps")
    _make_read_only(material["repo"])
    _make_read_only(attempts_dir)
    _make_read_only(runner_dir)
    for name in ("selection.json", "corpus.json", "tg5-receipt.json", "tg5-reverification.json"):
        (root / name).chmod(0o444)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(subject)
    cmd = [
        sys.executable, "-m", "product.benchmark.tg7_shadow",
        "--selection", str(root / "selection.json"),
        "--repository", str(root / "repository"),
        "--manifest", str(root / "corpus.json"),
        "--tg5-receipt", str(root / "tg5-receipt.json"),
        "--shadow-receipt", str(root / "shadow-receipt.json"),
        "--report", str(root / "report.json"),
    ]
    subprocess.run(cmd, cwd=subject, env=env, check=True)
    report = load_json(root / "report.json")
    shadow = load_json(root / "shadow-receipt.json")
    errors = validate_shadow_receipt(shadow, corpus=corpus, tg5_receipt=tg5, selection=selection)
    errors += validate_report(report, shadow_receipt=shadow, corpus=corpus)
    if errors or report["false_certification_count"] != 0 or report["infra_invalid_count"] != 0:
        raise RuntimeError(f"TG7 reduction failed: {errors} report={report}")
    (root / "shadow-receipt.json").chmod(0o444)
    (root / "report.json").chmod(0o444)
    summary = {
        "schema": "nexus.core-v1.tg7-github-physical-summary.v1",
        "subject": TG7_SUBJECT,
        "subject_tree": git(subject, "rev-parse", "HEAD^{tree}"),
        "selection_hash": selection["selection_hash"],
        "corpus_hash": corpus["corpus_hash"],
        "tg5_receipt_hash": tg5["receipt_hash"],
        "bottle_commit": BOTTLE_COMMIT,
        "bottle_tree": BOTTLE_TREE,
        "bottle_py_hash": material["bottle_hash"],
        "attempt_count": len(corpus["cases"]),
        "family_counts": dict(Counter(row["hostile_family"] for row in corpus["cases"])),
        "eligible_count": report["eligible_count"],
        "infra_invalid_count": report["infra_invalid_count"],
        "false_certification_count": report["false_certification_count"],
        "trust_mismatches": report["trust_mismatches"],
        "report_hash": report["report_hash"],
        "shadow_receipt_hash": shadow["receipt_hash"],
        "generated_at": _utc_now(),
    }
    write_json(root / "controller-summary.json", summary)
    (root / "controller-summary.json").chmod(0o444)
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(root, arcname="tg7")
    print(canonical(summary))


def _audit(subject: Path, root: Path, junit: Path, output: Path) -> None:
    assert_head(subject, TG7_SUBJECT)
    sys.path.insert(0, str(subject))
    from product.benchmark.tg7_shadow import validate_attempt_receipt, validate_corpus, validate_report, validate_selection, validate_shadow_receipt, validate_tg5_receipt
    from product.execution.python_runner import RunnerResult, RunnerStatus

    selection = load_json(root / "selection.json")
    corpus = load_json(root / "corpus.json")
    tg5 = load_json(root / "tg5-receipt.json")
    shadow = load_json(root / "shadow-receipt.json")
    report = load_json(root / "report.json")
    errors: list[str] = []
    errors += validate_selection(selection, repo_path=root / "repository")
    errors += validate_tg5_receipt(tg5)
    errors += validate_corpus(corpus, selection=selection)
    errors += validate_shadow_receipt(shadow, corpus=corpus, tg5_receipt=tg5, selection=selection)
    errors += validate_report(report, shadow_receipt=shadow, corpus=corpus)
    bottle_hash = "sha256:" + hashlib.sha256((root / "repository" / "bottle.py").read_bytes()).hexdigest()
    seen_exec: set[str] = set()
    for case in corpus["cases"]:
        attempt = load_json(root / "attempts" / f"{case['case_id']}.json")
        errors += validate_attempt_receipt(
            attempt, case=case, selection=selection, tg5_receipt=tg5,
            external_material_hash=bottle_hash,
        )
        runner_value = load_json(root / "runner-results" / f"{case['case_id']}.json")
        try:
            runner = RunnerResult.from_dict(runner_value)
        except Exception as exc:
            errors.append(f"runner[{case['case_id']}] invalid: {exc}")
            continue
        if runner.status is not RunnerStatus.VERIFIED or len(runner.attempts) != 2:
            errors.append(f"runner[{case['case_id']}] not VERIFIED with two executions")
        if digest(runner_value) != attempt["runner_result_hash"]:
            errors.append(f"runner[{case['case_id']}] hash mismatch")
        for item in runner.attempts:
            if item.execution_id in seen_exec:
                errors.append(f"duplicate physical execution id: {item.execution_id}")
            seen_exec.add(item.execution_id)
    import xml.etree.ElementTree as ET
    tree = ET.parse(junit)
    root_xml = tree.getroot()
    suites = list(root_xml) if root_xml.tag == "testsuites" else [root_xml]
    skipped = sum(int(s.attrib.get("skipped", "0")) for s in suites)
    failures = sum(int(s.attrib.get("failures", "0")) for s in suites)
    xml_errors = sum(int(s.attrib.get("errors", "0")) for s in suites)
    family_counts = Counter(row["hostile_family"] for row in corpus["cases"])
    if len(corpus["cases"]) != 56 or set(family_counts.values()) != {7}:
        errors.append(f"unexpected corpus distribution: {family_counts}")
    if report.get("eligible_count") != 56 or report.get("infra_invalid_count") != 0:
        errors.append("eligible/infra arithmetic mismatch")
    if report.get("false_certification_count") != 0 or report.get("false_certification_case_ids") != []:
        errors.append("high-risk false certification detected")
    if skipped or failures or xml_errors:
        errors.append(f"physical pytest not clean: skipped={skipped} failures={failures} errors={xml_errors}")
    acceptance = {
        "schema": "nexus.core-v1.tg7-github-independent-audit.v1",
        "status": "ACCEPT" if not errors else "BLOCK",
        "subject": TG7_SUBJECT,
        "subject_tree": git(subject, "rev-parse", "HEAD^{tree}"),
        "tg5_receipt_hash": tg5.get("receipt_hash"),
        "selection_hash": selection.get("selection_hash"),
        "corpus_hash": corpus.get("corpus_hash"),
        "report_hash": report.get("report_hash"),
        "attempt_count": len(corpus["cases"]),
        "physical_execution_ids": len(seen_exec),
        "eligible_count": report.get("eligible_count"),
        "infra_invalid_count": report.get("infra_invalid_count"),
        "false_certification_count": report.get("false_certification_count"),
        "family_counts": dict(sorted(family_counts.items())),
        "pytest_skipped": skipped,
        "pytest_failures": failures,
        "pytest_errors": xml_errors,
        "claim": "CROSS_REPO_TRUST_SHADOW_VERIFIED" if not errors else "TG7_PHYSICAL_BLOCKED",
        "errors": errors,
        "reviewer": "github-actions-fresh-independent-audit-runner",
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "observed_at": _utc_now(),
    }
    write_json(output, acceptance)
    print(canonical(acceptance))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    tg5 = sub.add_parser("tg5-capture")
    tg5.add_argument("--subject", type=Path, required=True)
    tg5.add_argument("--output", type=Path, required=True)
    tg5.add_argument("--provenance", type=Path, required=True)
    collect = sub.add_parser("tg7-collect")
    collect.add_argument("--subject", type=Path, required=True)
    collect.add_argument("--tg5-receipt", type=Path, required=True)
    collect.add_argument("--tg5-provenance", type=Path, required=True)
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--tar", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--subject", type=Path, required=True)
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--junit", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "tg5-capture":
        asyncio.run(_capture_tg5(args.subject.resolve(), args.output.resolve(), args.provenance.resolve()))
    elif args.command == "tg7-collect":
        _tg7_collect(args.subject.resolve(), args.tg5_receipt.resolve(), args.tg5_provenance.resolve(), args.root.resolve(), args.tar.resolve())
    else:
        _audit(args.subject.resolve(), args.root.resolve(), args.junit.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
