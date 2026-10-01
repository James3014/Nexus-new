#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.research.core_effectiveness_mutation import (  # noqa: E402
    PASS_GATE,
    evaluate_g1_results,
    validate_g1_matrix,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_core_api(core_root: Path) -> dict[str, Any]:
    root = str(core_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)

    from product.adapters.generic_verification import verify_generic_changeset
    from product.clients.local_golden_path import (
        check_repository,
        init_repository,
        validate_verification_receipt_payload,
    )
    from product.protocol.generic_verification import (
        acceptance_contract_hash,
        canonical_hash,
        change_manifest_hash,
        change_set_hash,
        evidence_bundle_hash,
        verification_plan_hash,
    )

    return {
        "verify_generic_changeset": verify_generic_changeset,
        "check_repository": check_repository,
        "init_repository": init_repository,
        "validate_verification_receipt_payload": validate_verification_receipt_payload,
        "acceptance_contract_hash": acceptance_contract_hash,
        "canonical_hash": canonical_hash,
        "change_manifest_hash": change_manifest_hash,
        "change_set_hash": change_set_hash,
        "evidence_bundle_hash": evidence_bundle_hash,
        "verification_plan_hash": verification_plan_hash,
    }


def _new_repo(root: Path) -> Path:
    repo = root / "subject"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "g1-probe@example.invalid")
    _git(repo, "config", "user.name", "Nexus Core G1 Probe")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")
    return repo


def _configure(api: Mapping[str, Any], repo: Path) -> None:
    api["init_repository"](
        repo,
        base_ref="main",
        allowed_patterns=("*.py",),
        deletion_policy="FORBID",
        verifier_command=(sys.executable, "-c", "import sys; sys.exit(0)"),
    )


def _receipt(api: Mapping[str, Any], repo: Path) -> dict[str, Any]:
    result = api["check_repository"](repo)
    return json.loads(result["receipt_path"].read_text(encoding="utf-8"))


def _reseal_receipt(api: Mapping[str, Any], payload: dict[str, Any]) -> None:
    payload["receipt_hash"] = api["canonical_hash"]({
        key: value for key, value in payload.items() if key != "receipt_hash"
    })


def _recompute_request(api: Mapping[str, Any], payload: dict[str, Any]) -> None:
    request = payload["inputs"]["request"]
    contract = request["acceptance_contract"]
    change_set = request["change_set"]
    manifest = request["change_manifest"]
    plan = request["verification_plan"]
    evidence = request["evidence_bundle"]

    contract_hash = api["acceptance_contract_hash"](contract)
    entries = manifest["entries"]
    change_set["paths"] = sorted(str(entry["path"]) for entry in entries)
    change_set["deleted_paths"] = sorted(
        str(entry["path"]) for entry in entries if entry["change_type"] == "DELETE"
    )
    change_set["diff_hash"] = api["change_manifest_hash"](manifest)
    change_hash = api["change_set_hash"](change_set)
    plan["acceptance_contract_hash"] = contract_hash
    plan["change_set_hash"] = change_hash
    evidence["acceptance_contract_hash"] = contract_hash
    evidence["change_set_hash"] = change_hash
    evidence["verification_plan_hash"] = api["verification_plan_hash"](plan)
    evidence["claimed_bundle_hash"] = None
    evidence["claimed_bundle_hash"] = api["evidence_bundle_hash"](evidence)

    status, response = api["verify_generic_changeset"](request)
    if status != 200:
        raise AssertionError(
            f"re-sealed probe request was not internally valid: {status} {response}"
        )
    payload["manifest_hash"] = api["change_manifest_hash"](manifest)
    payload["core_response"] = response
    payload["outcome"]["status"] = response["verification"]["status"]
    payload["outcome"]["reason_codes"] = response["verification"]["reason_codes"]
    _reseal_receipt(api, payload)


def _validation_probe(
    api: Mapping[str, Any],
    payload: dict[str, Any],
    repo: Path,
    *,
    required_signal: str,
) -> tuple[list[str], str]:
    validation = api["validate_verification_receipt_payload"](payload, repo=repo)
    reasons = sorted(str(reason) for reason in validation["reason_codes"])
    if validation["valid"] is not False:
        raise AssertionError(f"mutant unexpectedly validated: {required_signal}")
    if required_signal not in reasons:
        raise AssertionError(f"missing expected signal {required_signal}: {reasons}")
    if "RECEIPT_HASH_MISMATCH" in reasons:
        raise AssertionError(
            f"{required_signal} probe degraded to outer receipt-hash detection: {reasons}"
        )
    return reasons, json.dumps(validation, sort_keys=True)


def _probe_omitted_untracked(api: Mapping[str, Any]) -> tuple[list[str], str]:
    with tempfile.TemporaryDirectory(prefix="nexus-core-g1-m05-") as directory:
        repo = _new_repo(Path(directory))
        _configure(api, repo)
        (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (repo / "new.py").write_text("NEW = True\n", encoding="utf-8")
        payload = _receipt(api, repo)
        entries = payload["inputs"]["request"]["change_manifest"]["entries"]
        if {entry["path"] for entry in entries} != {"app.py", "new.py"}:
            raise AssertionError(f"valid receipt did not bind tracked+untracked state: {entries}")
        payload["inputs"]["request"]["change_manifest"]["entries"] = [
            entry for entry in entries if entry["path"] != "new.py"
        ]
        _recompute_request(api, payload)
        return _validation_probe(api, payload, repo, required_signal="GIT_MANIFEST_MISMATCH")


def _probe_index_worktree_mismatch(api: Mapping[str, Any]) -> tuple[list[str], str]:
    with tempfile.TemporaryDirectory(prefix="nexus-core-g1-m06-") as directory:
        repo = _new_repo(Path(directory))
        _configure(api, repo)
        (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        _git(repo, "add", "app.py")
        index_tree = _git(repo, "write-tree")
        (repo / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        payload = _receipt(api, repo)
        worktree_tree = payload["target_tree"].removeprefix("git-tree:")
        if index_tree == worktree_tree:
            raise AssertionError("probe failed to create staged/worktree divergence")

        request = payload["inputs"]["request"]
        request["change_manifest"]["target_tree"] = f"git-tree:{index_tree}"
        request["change_set"]["target_revision"] = f"git-tree:{index_tree}"
        payload["target_revision"] = f"git-tree:{index_tree}"
        payload["target_tree"] = f"git-tree:{index_tree}"
        _recompute_request(api, payload)
        return _validation_probe(api, payload, repo, required_signal="GIT_MANIFEST_MISMATCH")


def _probe_verifier_artifact_hash_tamper(
    api: Mapping[str, Any],
) -> tuple[list[str], str]:
    with tempfile.TemporaryDirectory(prefix="nexus-core-g1-m11-") as directory:
        repo = _new_repo(Path(directory))
        _configure(api, repo)
        (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        payload = _receipt(api, repo)
        payload["verifier"]["artifact_hash"] = "sha256:" + "0" * 64
        _reseal_receipt(api, payload)
        return _validation_probe(api, payload, repo, required_signal="VERIFIER_ARTIFACT_MISMATCH")


def _probe_canonical_request_tamper(api: Mapping[str, Any]) -> tuple[list[str], str]:
    with tempfile.TemporaryDirectory(prefix="nexus-core-g1-m12-") as directory:
        repo = _new_repo(Path(directory))
        _configure(api, repo)
        (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        payload = _receipt(api, repo)
        payload["inputs"]["request"]["acceptance_contract"]["allowed_paths"] = ["other.py"]
        _reseal_receipt(api, payload)
        return _validation_probe(api, payload, repo, required_signal="CORE_RESPONSE_MISMATCH")


_PROBES: dict[str, Callable[[Mapping[str, Any]], tuple[list[str], str]]] = {
    "probe:omitted_untracked": _probe_omitted_untracked,
    "probe:index_worktree_mismatch": _probe_index_worktree_mismatch,
    "probe:verifier_artifact_hash_tamper": _probe_verifier_artifact_hash_tamper,
    "probe:canonical_request_tamper": _probe_canonical_request_tamper,
}


def _run_subject_test(
    core_root: Path,
    selector: str,
    *,
    cache: dict[str, tuple[int, str, str]],
) -> tuple[bool, str]:
    if selector not in cache:
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", selector],
            cwd=core_root,
            check=False,
            capture_output=True,
            text=True,
        )
        cache[selector] = (process.returncode, process.stdout, process.stderr)
    returncode, stdout, stderr = cache[selector]
    evidence_hash = _sha256_text(stdout + "\n---stderr---\n" + stderr)
    return (
        returncode == 0,
        f"pytest={selector};exit={returncode};output={evidence_hash}",
    )


def _run_case(
    case: Mapping[str, Any],
    *,
    core_root: Path,
    api: Mapping[str, Any],
    test_cache: dict[str, tuple[int, str, str]],
) -> dict[str, Any]:
    case_id = str(case["id"])
    witness_kind = str(case["witness_kind"])
    selector = str(case["selector"])
    expected_signals = [str(signal) for signal in case["expected_signals"]]
    try:
        if witness_kind == "SUBJECT_TEST":
            passed, evidence = _run_subject_test(core_root, selector, cache=test_cache)
            return {
                "executed": True,
                "observed_outcome": case["expected_outcome"] if passed else "WITNESS_FAILED",
                "observed_signals": expected_signals if passed else ["PYTEST_WITNESS_FAILED"],
                "evidence": evidence,
            }
        if witness_kind == "EXTERNAL_BLACK_BOX_PROBE":
            probe = _PROBES.get(selector)
            if probe is None:
                raise AssertionError(f"unknown external probe: {selector}")
            signals, evidence = probe(api)
            return {
                "executed": True,
                "observed_outcome": case["expected_outcome"],
                "observed_signals": signals,
                "evidence": f"{selector};{evidence}",
            }
        raise AssertionError(f"unsupported witness kind: {witness_kind}")
    except Exception as exc:
        return {
            "executed": True,
            "observed_outcome": "WITNESS_ERROR",
            "observed_signals": [type(exc).__name__],
            "evidence": f"{case_id}:{selector}:{exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Nexus Core effectiveness G1 controlled evidence mutation matrix."
    )
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    manifest_value = json.loads(args.matrix.read_text(encoding="utf-8"))
    if not isinstance(manifest_value, dict):
        raise SystemExit("matrix must be a JSON object")
    manifest = validate_g1_matrix(manifest_value)

    core_root = args.core_root.resolve()
    observed_revision = _git(core_root, "rev-parse", "HEAD")
    observed_tree = _git(core_root, "rev-parse", "HEAD^{tree}")
    api = _load_core_api(core_root)

    observations: dict[str, dict[str, Any]] = {}
    test_cache: dict[str, tuple[int, str, str]] = {}
    for case in [*manifest["mutants"], *manifest["controls"]]:
        observations[str(case["id"])] = _run_case(
            case,
            core_root=core_root,
            api=api,
            test_cache=test_cache,
        )

    report = evaluate_g1_results(
        manifest,
        observations,
        observed_subject_revision=observed_revision,
    )
    report["subject_tree"] = observed_tree
    report["subject_ci_run_id"] = manifest["subject"]["ci_run_id"]
    report["subject_ci_job_id"] = manifest["subject"].get("ci_job_id")
    report["subject_product_test_passed"] = manifest["subject"]["product_test_passed"]
    report["subject_product_test_deselected"] = manifest["subject"].get(
        "product_test_deselected", 0
    )
    report["observations"] = observations
    report["matrix_sha256"] = _sha256_text(
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    )

    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["gate"] == PASS_GATE else 2


if __name__ == "__main__":
    raise SystemExit(main())
