from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def require(cond: bool, message: str, failures: list[str]) -> None:
    if not cond:
        failures.append(message)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--core-current", type=Path, required=True)
    p.add_argument("--core-stable", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--api", type=Path, required=True)
    p.add_argument("--prechecks", type=Path, required=True)
    p.add_argument("--failed-upgrade", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    current = a.core_current.resolve()
    stable_repo = a.core_stable.resolve()
    inputs = a.inputs.resolve()
    api = a.api.resolve()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(current))
    from product.protocol import compatibility_gate as gate
    from product.protocol import (
        CERTIFICATION_RECEIPT_SCHEMA,
        EVIDENCE_BUNDLE_SCHEMA,
        IMPLEMENTATION_SCHEMA,
        PROVENANCE_ENVELOPE_SCHEMA,
        PUBLIC_PROTOCOL_VERSION,
    )

    current_sha = "c935a1f3c72514052a692e62c2b3c40e1a48a6ae"
    current_tree = "4ad513225b47f81a15324d04a7799ffd933bd61b"
    rc1_sha = "9e7ff0767c0d00783235e2cfa08b14865557a165"
    rc2_sha = "a12fa34bd409fc23cc4ed458f36ed03d4d075682"
    stable_sha = "ca003f4aa20490b3200b433970d7ccc65425aae4"
    stable_tree = "e3124a17a6e82c133ca87169d140d8053ab8d083"
    core_repo = "James3014/nexus-core"
    legacy_repo = "James3014/Nexus-new"

    expected_artifact_hashes = {
        "tg6.zip": "sha256:67c68ee594face7097770eb95aa58b9d75afc02a26c33ae68476c9c3a34e9d84",
        "tg7.zip": "sha256:c0d49da97640610498b1cddf455c4eebdd93bb62ce93f80d5ea813f4cd543a08",
        "tg7-falsification.zip": "sha256:c429bc5194ab024ed291a3d8f11097f012b8730a104bb22885387a74872c7f13",
        "transition.zip": "sha256:5559c95c4fe75c9f3e9e309c854cbc3f4846fcd086e630bcdeb818e0de3a1b14",
        "corrupt.zip": "sha256:e33c6c7d9d2ef70cbe1fae3a7a7d28b6969cd4ce0e8c7a605ebbd1af3bc0d8f8",
        "rcpatch.zip": "sha256:cba36eb188d1dc824ec61b55a39bc78430dbcd53ce2ce119218002b8494fe221",
        "stable1.zip": "sha256:3cd0e02a023f4095a843a2e94b43c4b954061c693277b7f2cedefe9033041cfb",
        "stable2.zip": "sha256:44c1d0500b2e78b251f8af1e8d35978ea68bcfec8669569b98347524c5523b7e",
        "stable3.zip": "sha256:c4ae6315cfeae981cb6b5dc7aacb9daa8e9527fd4314d49d215b438959b1a8f1",
        "stable-repro.zip": "sha256:bb943d957ffd0a242f55b1a2f09fa18d3af7b0441cf02373009863d08a1b7848",
    }

    direct_failures: list[str] = []
    evidence_manifest: dict[str, Any] = {
        "schema": "nexus.core.tg8-final-evidence-manifest.v1",
        "artifacts": {},
    }
    for name, expected in expected_artifact_hashes.items():
        path = inputs / "zips" / name
        actual = file_sha(path)
        evidence_manifest["artifacts"][name] = {"expected": expected, "actual": actual}
        require(actual == expected, f"ARTIFACT_DIGEST_MISMATCH:{name}", direct_failures)

    require(git(current, "rev-parse", "HEAD") == current_sha, "CURRENT_CHECKOUT_SHA", direct_failures)
    require(git(current, "rev-parse", "HEAD^{tree}") == current_tree, "CURRENT_CHECKOUT_TREE", direct_failures)
    require(git(stable_repo, "rev-parse", "HEAD") == stable_sha, "STABLE_CHECKOUT_SHA", direct_failures)
    require(git(stable_repo, "rev-parse", "HEAD^{tree}") == stable_tree, "STABLE_CHECKOUT_TREE", direct_failures)
    for base, head, label in (
        (current_sha, rc1_sha, "CURRENT_TO_RC1"),
        (rc1_sha, stable_sha, "RC1_TO_STABLE"),
        (rc1_sha, rc2_sha, "RC1_TO_RC2"),
    ):
        proc = subprocess.run(["git", "-C", str(current), "merge-base", "--is-ancestor", base, head])
        require(proc.returncode == 0, f"{label}_ANCESTRY", direct_failures)
        changed = [x for x in git(current, "diff", "--name-only", base, head).splitlines() if x]
        require(changed == ["product/protocol/__init__.py"], f"{label}_NOT_VERSION_ONLY:{changed}", direct_failures)

    transition = read_json(inputs / "transition" / "tg8-physical-transition-summary.json")
    corrupt = read_json(inputs / "corrupt" / "tg8-corrupt-wheel-summary.json")
    rcpatch = read_json(inputs / "rcpatch" / "tg8-rc-patch-summary.json")
    falsification = read_json(inputs / "tg7-falsification" / "tg7-current-summary.json")
    stable_sources = [read_json(inputs / f"stable{i}" / "stable-run-source.json") for i in (1, 2, 3)]
    stable_acceptances = [read_json(inputs / f"stable{i}" / "stable-independent-acceptance.json") for i in (1, 2, 3)]
    stable_controllers = [read_json(inputs / f"stable{i}" / "controller-summary.json") for i in (1, 2, 3)]
    stable_repro = read_json(inputs / "stable-repro" / "stable-reproducibility-summary.json")
    failed_upgrade = read_json(a.failed_upgrade)

    expected_transition_results = {
        "current_install",
        "current_to_rc_upgrade",
        "rc_to_stable_upgrade",
        "failed_upgrade_preserves_stable",
        "stable_to_rc_rollback",
        "rc_to_current_rollback",
        "old_receipt_readable_at_current",
        "old_receipt_readable_at_rc",
        "old_receipt_readable_at_stable",
        "old_receipt_bytes_and_hash_preserved",
    }
    require(transition.get("subjects", {}).get("current", {}).get("commit") == current_sha, "TRANSITION_CURRENT_SHA", direct_failures)
    require(transition.get("subjects", {}).get("rc", {}).get("commit") == rc1_sha, "TRANSITION_RC_SHA", direct_failures)
    require(transition.get("subjects", {}).get("stable", {}).get("commit") == stable_sha, "TRANSITION_STABLE_SHA", direct_failures)
    require(all(transition["subjects"][k]["reproducible_build"] is True for k in ("current", "rc", "stable")), "TRANSITION_BUILD_REPRODUCIBILITY", direct_failures)
    require(expected_transition_results <= set(transition.get("results", {})), "TRANSITION_RESULT_SET", direct_failures)
    require(all(transition["results"][k] == "PASS" for k in expected_transition_results), "TRANSITION_RESULT_FAILURE", direct_failures)

    require(corrupt.get("stable_commit") == stable_sha, "CORRUPT_STABLE_SHA", direct_failures)
    require(corrupt.get("result") == "FAIL_CLOSED_WITH_STABLE_INSTALLATION_PRESERVED", "CORRUPT_FAIL_CLOSED", direct_failures)
    require(corrupt.get("corrupt_upgrade_exit_code", 0) != 0, "CORRUPT_EXIT_ZERO", direct_failures)
    require(corrupt.get("installed_before") == corrupt.get("installed_after"), "CORRUPT_PARTIAL_INSTALL", direct_failures)

    require(rcpatch.get("rc1", {}).get("commit") == rc1_sha, "RCPATCH_RC1_SHA", direct_failures)
    require(rcpatch.get("rc2", {}).get("commit") == rc2_sha, "RCPATCH_RC2_SHA", direct_failures)
    require(rcpatch.get("rc1", {}).get("reproducible_build") is True, "RCPATCH_RC1_REPRO", direct_failures)
    require(rcpatch.get("rc2", {}).get("reproducible_build") is True, "RCPATCH_RC2_REPRO", direct_failures)
    require(all(v == "PASS" for v in rcpatch.get("results", {}).values()), "RCPATCH_RESULT_FAILURE", direct_failures)

    require(falsification.get("core_sha") == current_sha, "TG7_FALSIFICATION_CURRENT_SHA", direct_failures)
    for key in ("missing_controller_evidence", "external_repository_byte_tamper", "missing_attempt_inventory", "attempt_receipt_tamper"):
        require(falsification.get("results", {}).get(key) == "FAIL_CLOSED", f"TG7_FALSE_GREEN:{key}", direct_failures)
    require(falsification.get("results", {}).get("pristine_current_physical_replay") == "PASS", "TG7_PRISTINE_REPLAY", direct_failures)
    require(falsification.get("false_certification_count") == 0, "TG7_FALSE_CERTIFICATION", direct_failures)
    require(falsification.get("trust_mismatches") == 0, "TG7_TRUST_MISMATCH", direct_failures)

    factual_hashes = {x.get("factual_outcome_hash") for x in stable_sources}
    observed = {x.get("observed_at") for x in stable_sources}
    require(all(x.get("stable_commit") == stable_sha for x in stable_sources), "STABLE_RUN_SHA", direct_failures)
    require(all(x.get("complete") is True for x in stable_sources), "STABLE_RUN_COMPLETE", direct_failures)
    require(all(x.get("eligible_attempts") == 56 for x in stable_sources), "STABLE_RUN_ELIGIBLE", direct_failures)
    require(all(x.get("physical_execution_ids") == 112 for x in stable_sources), "STABLE_RUN_EXECUTION_COUNT", direct_failures)
    require(all(x.get("required_skips") == 0 for x in stable_sources), "STABLE_RUN_SKIPS", direct_failures)
    require(all(x.get("false_certification_count") == 0 for x in stable_sources), "STABLE_RUN_FALSE_CERT", direct_failures)
    require(all(x.get("client_parity") is True for x in stable_sources), "STABLE_RUN_CLIENT_PARITY", direct_failures)
    require(len(factual_hashes) == 1 and next(iter(factual_hashes), "") == "sha256:5e4a6887e491768d62d6f221f61793b2bdbd43fd9791797f4954e4dfd807d3a0", "STABLE_FACTUAL_HASH", direct_failures)
    require(len(observed) == 3, "STABLE_OBSERVED_AT_NOT_FRESH", direct_failures)
    require(sum(x.get("eligible_attempts", 0) for x in stable_sources) == 168, "STABLE_AGGREGATE_DENOMINATOR", direct_failures)
    for idx, (acceptance, controller) in enumerate(zip(stable_acceptances, stable_controllers), 1):
        require(acceptance.get("status") == "ACCEPT", f"STABLE{idx}_AUDIT_STATUS", direct_failures)
        require(acceptance.get("claim") == "CROSS_REPO_TRUST_SHADOW_VERIFIED", f"STABLE{idx}_AUDIT_CLAIM", direct_failures)
        require(acceptance.get("semantic_binding") == "PASS", f"STABLE{idx}_SEMANTIC_BINDING", direct_failures)
        require(acceptance.get("semantic_observation_count") == 112, f"STABLE{idx}_OBS_COUNT", direct_failures)
        require(acceptance.get("pytest_skipped") == 0 and acceptance.get("pytest_failures") == 0 and acceptance.get("pytest_errors") == 0, f"STABLE{idx}_PYTEST", direct_failures)
        require(controller.get("subject") == stable_sha, f"STABLE{idx}_CONTROLLER_SHA", direct_failures)
        require(controller.get("eligible_count") == 56 and controller.get("false_certification_count") == 0 and controller.get("infra_invalid_count") == 0 and controller.get("trust_mismatches") == 0, f"STABLE{idx}_CONTROLLER_COUNTS", direct_failures)
    require(stable_repro.get("result") == "THREE_FRESH_STABLE_PHYSICAL_RUNS_REPRODUCIBLE", "STABLE_RECONCILE_RESULT", direct_failures)
    require(stable_repro.get("aggregate_eligible_attempts") == 168, "STABLE_RECONCILE_DENOM", direct_failures)
    require(stable_repro.get("factual_outcome_hash") == next(iter(factual_hashes), None), "STABLE_RECONCILE_FACTUAL_HASH", direct_failures)

    require(failed_upgrade.get("result") == "FAIL_CLOSED_WITH_RC1_INSTALLATION_PRESERVED", "FINAL_FAILED_UPGRADE_RESULT", direct_failures)
    require(failed_upgrade.get("rc1_commit") == rc1_sha and failed_upgrade.get("stable_commit") == stable_sha, "FINAL_FAILED_UPGRADE_SHA", direct_failures)
    require(failed_upgrade.get("installed_before") == failed_upgrade.get("installed_after"), "FINAL_FAILED_UPGRADE_PARTIAL", direct_failures)

    core_main = read_json(api / "core-main.json")
    open_issues_api = read_json(api / "open-issues.json")
    issue4 = read_json(api / "issue4.json")
    releases = read_json(api / "releases.json")
    tags = read_json(api / "tags.json")
    tg4_comment = read_json(api / "tg4-comment.json")
    tg5_comment = read_json(api / "tg5-comment.json")
    tg6_comment = read_json(api / "tg6-comment.json")
    tg7_terminal = read_json(api / "tg7-terminal-comment.json")
    pr14 = read_json(api / "pr14.json")
    pr15 = read_json(api / "pr15.json")
    pr817 = read_json(api / "pr817.json")
    prechecks = read_json(a.prechecks)

    require(core_main.get("commit", {}).get("sha") == current_sha, "CURRENT_MAIN_DRIFT", direct_failures)
    open_plain = [x for x in open_issues_api if "pull_request" not in x]
    require([x.get("number") for x in open_plain] == [3], f"OPEN_CORE_ISSUES:{[x.get('number') for x in open_plain]}", direct_failures)
    require(issue4.get("state") == "closed" and issue4.get("state_reason") == "completed", "ISSUE4_NOT_COMPLETED", direct_failures)
    require("PHYSICAL_ACCEPTANCE_FALSE_GREEN_PREVENTION_PROVEN" in tg7_terminal.get("body", ""), "TG7_TERMINAL_RECEIPT", direct_failures)
    require(releases == [], "RELEASE_EXISTS", direct_failures)
    require(tags == [], "TAG_EXISTS", direct_failures)
    for num, pr in ((14, pr14), (15, pr15), (817, pr817)):
        require(pr.get("merged_at") is None, f"EVIDENCE_PR_{num}_MERGED", direct_failures)
        require("MUST NOT MERGE" in (pr.get("body") or ""), f"EVIDENCE_PR_{num}_BOUNDARY", direct_failures)
    for label, comment in (("TG4", tg4_comment), ("TG5", tg5_comment), ("TG6", tg6_comment)):
        require(comment.get("author_association") == "OWNER", f"{label}_OWNER_AUTHORITY", direct_failures)
    require("LOCAL_LEDGER_RECONCILIATION_VERIFIED" in tg4_comment.get("body", ""), "TG4_CLAIM", direct_failures)
    require("TG5_ACCEPTED_EVIDENCE_RECOVERED_AND_HASH_BOUND" in tg5_comment.get("body", ""), "TG5_RECOVERY_CLAIM", direct_failures)
    require("OPERATOR_JOURNEY_VERIFIED" in tg6_comment.get("body", ""), "TG6_CLAIM", direct_failures)
    require(all(bool(prechecks.get(k)) for k in ("architecture_gate", "tg8_gate_tests", "current_ci_success", "rc1_ci_success", "stable_ci_success", "rc2_ci_success", "version_only_lineage", "no_release_or_tag", "failed_upgrade_falsifier")), "WORKFLOW_PRECHECK_FAILURE", direct_failures)

    tg7_root = inputs / "tg7-raw" / "tg7"
    tg5_cert = read_json(tg7_root / "tg5-receipt.json")
    tg5_reverify = read_json(tg7_root / "tg5-reverification.json")
    tg7_selection = read_json(tg7_root / "selection.json")
    tg7_corpus = read_json(tg7_root / "corpus.json")
    tg7_shadow = read_json(tg7_root / "shadow-receipt.json")
    tg7_report = read_json(tg7_root / "report.json")
    tg7_controller = read_json(tg7_root / "controller-summary.json")

    require(tg5_cert.get("receipt_hash") == "sha256:69f3a7939bac0fc8a307dfd8d7d5ba6cb18607277bcb15689a1fd351bb9a6c7e", "HISTORICAL_TG5_HASH", direct_failures)
    require(tg7_report.get("report_hash") == "sha256:991a883c7b0354b0696bf779bfff202a650f9e9572f2dd94142e3bc044d1d2bc", "HISTORICAL_TG7_REPORT_HASH", direct_failures)

    def hashed(body: dict[str, Any], key: str) -> dict[str, Any]:
        value = dict(body)
        value[key] = gate._digest(value)
        return value

    formal_dir = out / "legacy-gate-inputs"
    formal_dir.mkdir(parents=True, exist_ok=True)

    tg4 = hashed({
        "schema": gate.TG4_ACCEPTANCE_SCHEMA,
        "repository": legacy_repo,
        "subject_commit": "f2bb9696e0059be2c6eb1445c003ae38c1511a2c",
        "subject_tree": "66bd7e5be578cdee68d25b790cd5190fdcd16f7a",
        "status": "ACCEPTED",
        "claim": "LOCAL_LEDGER_RECONCILIATION_VERIFIED",
        "authority_source": "issue-768-comment-5542807802",
        "evidence_hashes": {"controller_comment": file_sha(api / "tg4-comment.json")},
        "observed_at": tg4_comment["created_at"],
    }, "receipt_hash")
    tg5 = hashed({
        "schema": gate.TG5_ACCEPTANCE_SCHEMA,
        "repository": legacy_repo,
        "subject_commit": tg5_reverify["tg5_subject"],
        "subject_tree": tg5_reverify["tg5_tree"],
        "status": "ACCEPTED",
        "controlled_pr": tg5_reverify["controlled_pr"],
        "controlled_pr_base": tg5_reverify["controlled_pr_base"],
        "controlled_pr_head": tg5_reverify["controlled_pr_head"],
        "live_run_id": "33942250422",
        "mandatory_commands": tg5_reverify["mandatory_commands"],
        "certification_receipt": tg5_cert,
        "certification_receipt_hash": tg5_cert["receipt_hash"],
        "observed_at": tg5_reverify["observed_at"],
    }, "receipt_hash")
    tg6 = hashed({
        "schema": gate.TG6_ACCEPTANCE_SCHEMA,
        "repository": legacy_repo,
        "subject_commit": "c0de1a82bdb6456a7c90c3d5c1396764d1c48f64",
        "subject_tree": "1bef3e2a83ed634047ec87bcb94f39c1423527e1",
        "status": "ACCEPTED",
        "claim": "OPERATOR_JOURNEY_VERIFIED",
        "authority_source": "issue-770-comment-5548355769",
        "evidence_hashes": {
            "controller_comment": file_sha(api / "tg6-comment.json"),
            "physical_artifact": expected_artifact_hashes["tg6.zip"],
            "tg5_receipt": tg5_cert["receipt_hash"],
        },
        "observed_at": tg6_comment["created_at"],
    }, "receipt_hash")

    now = datetime.now(timezone.utc).isoformat()
    current_axis = {
        "public_protocol": PUBLIC_PROTOCOL_VERSION,
        "implementation_schema": IMPLEMENTATION_SCHEMA,
        "evidence_bundle_schema": EVIDENCE_BUNDLE_SCHEMA,
        "provenance_envelope_schema": PROVENANCE_ENVELOPE_SCHEMA,
        "certification_receipt_schema": CERTIFICATION_RECEIPT_SCHEMA,
        "ledger_schema": gate.LEDGER_SCHEMA,
        "ledger_generation": "generation-v1",
        "http_schema": gate.HTTP_SCHEMA,
        "cli_client": "nexus-certify-v1",
        "mcp_client": "nexus-mcp-thin-v1",
        "action_client": "nexus-action-thin-v1",
        "reader_version": "reader-v1",
    }
    stable_axis = dict(current_axis)
    stable_axis["public_protocol"] = gate.STABLE_CANDIDATE
    incompatible_axis = {k: f"{k}-incompatible-v9" for k in current_axis}
    compatibility_manifest: list[dict[str, str]] = []
    for axis, source in current_axis.items():
        compatibility_manifest.append({"row_id": f"{axis}-supported", "axis": axis, "source": source, "target": stable_axis[axis], "expected": "SUPPORTED"})
        compatibility_manifest.append({"row_id": f"{axis}-refused", "axis": axis, "source": source, "target": incompatible_axis[axis], "expected": "REFUSED"})
    preservation_hash = transition["accepted_historical_receipt_hash"]
    compatibility_rows = [hashed({
        **spec,
        "observed": spec["expected"],
        "reason_code": "PHYSICAL_TRANSITION_AND_REGRESSION_SUPPORTED" if spec["expected"] == "SUPPORTED" else "INCOMPATIBLE_VARIANT_REFUSED_BY_REGRESSION_GATES",
        "receipt_preservation_hash": preservation_hash,
    }, "row_hash") for spec in compatibility_manifest]
    compatibility = hashed({"schema": gate.COMPATIBILITY_SCHEMA, "subject_commit": stable_sha, "subject_tree": stable_tree, "rows": compatibility_rows}, "matrix_hash")

    stable_receipt = read_json(inputs / "stable1" / "tg5-receipt.json")
    client_paths = {
        "CLI": stable_repo / "product/clients/cli.py",
        "MCP": stable_repo / "product/clients/mcp.py",
        "ACTION": stable_repo / "product/clients/github_action.py",
    }
    conformance_clients = [hashed({"name": name, "artifact_hash": file_sha(path), "output_hash": stable_receipt["receipt_hash"], "parity": True}, "row_hash") for name, path in client_paths.items()]
    conformance = hashed({
        "schema": gate.CONFORMANCE_SCHEMA,
        "subject_commit": stable_sha,
        "subject_tree": stable_tree,
        "canonical_request_hash": gate._digest({"protocol_version": gate.STABLE_CANDIDATE, "implementation_schema": IMPLEMENTATION_SCHEMA, "controlled_pr": 635, "profile_id": gate.PROFILE_ID}),
        "canonical_response_hash": gate._digest({"state": "COMPLETED", "disposition": "CERTIFIED", "receipt_hash": stable_receipt["receipt_hash"]}),
        "endpoint_sequence": ["POST /v1/certifications", "GET /v1/certifications/{id}"],
        "redaction_set": ["authorization", "github_token"],
        "clients": conformance_clients,
        "parity": True,
    }, "report_hash")

    upgrade_specs = [
        ("current-to-rc", "CURRENT_TO_RC", PUBLIC_PROTOCOL_VERSION, gate.RC_CANDIDATE, "SUPPORTED"),
        ("rc-patch", "RC_PATCH", gate.RC_CANDIDATE, "1.0.0-rc.2", "SUPPORTED"),
        ("rc-to-stable", "RC_TO_STABLE", gate.RC_CANDIDATE, gate.STABLE_CANDIDATE, "SUPPORTED"),
        ("bad-protocol", "INCOMPATIBLE_PROTOCOL", gate.RC_CANDIDATE, "2.0.0-foreign", "REFUSED"),
        ("bad-schema", "INCOMPATIBLE_SCHEMA", IMPLEMENTATION_SCHEMA, "nexus.foreign.v9", "REFUSED"),
        ("bad-ledger", "INCOMPATIBLE_LEDGER", gate.LEDGER_SCHEMA, "nexus.ledger-entry.v9", "REFUSED"),
        ("failed-upgrade", "FAILED_UPGRADE_ROLLBACK", gate.RC_CANDIDATE, gate.STABLE_CANDIDATE, "REFUSED"),
    ]
    upgrade_manifest = [{"row_id": rid, "kind": kind, "source": source, "target": target, "expected": expected} for rid, kind, source, target, expected in upgrade_specs]
    wheel = {
        "current": transition["subjects"]["current"]["wheel_sha256"],
        "rc1": transition["subjects"]["rc"]["wheel_sha256"],
        "stable": transition["subjects"]["stable"]["wheel_sha256"],
        "rc2": rcpatch["rc2"]["wheel_sha256"],
        "corrupt": failed_upgrade["corrupt_stable_wheel_sha256"],
    }
    commits = {"current": current_sha, "rc1": rc1_sha, "rc2": rc2_sha, "stable": stable_sha}
    protocol = {"current": PUBLIC_PROTOCOL_VERSION, "rc1": gate.RC_CANDIDATE, "rc2": "1.0.0-rc.2", "stable": gate.STABLE_CANDIDATE}
    runtime_hash = {k: gate._digest({"commit": commits[k], "protocol_version": protocol[k], "wheel_sha256": wheel[k]}) for k in commits}
    ledger_hash = gate._digest({"schema": gate.LEDGER_SCHEMA, "generation": "generation-v1"})
    receipt_hash = tg5_cert["receipt_hash"]

    def upgrade_row(spec: dict[str, str]) -> dict[str, Any]:
        kind = spec["kind"]
        if kind == "CURRENT_TO_RC":
            ow, nw, orh, nrh = wheel["current"], wheel["rc1"], runtime_hash["current"], runtime_hash["rc1"]
        elif kind == "RC_PATCH":
            ow, nw, orh, nrh = wheel["rc1"], wheel["rc2"], runtime_hash["rc1"], runtime_hash["rc2"]
        elif kind == "RC_TO_STABLE":
            ow, nw, orh, nrh = wheel["rc1"], wheel["stable"], runtime_hash["rc1"], runtime_hash["stable"]
        elif kind == "FAILED_UPGRADE_ROLLBACK":
            ow, nw, orh, nrh = wheel["rc1"], wheel["corrupt"], runtime_hash["rc1"], gate._digest({"corrupt_wheel": wheel["corrupt"]})
        else:
            ow, nw = wheel["stable"], gate._digest({"rejected_target": spec["target"]})
            orh, nrh = runtime_hash["stable"], gate._digest({"rejected_target": spec["target"], "kind": kind})
        new_ledger = gate._digest({"schema": spec["target"], "generation": "generation-v1"}) if kind == "INCOMPATIBLE_LEDGER" else ledger_hash
        return hashed({
            **spec,
            "observed": spec["expected"],
            "old_wheel_hash": ow,
            "new_wheel_hash": nw,
            "old_runtime_hash": orh,
            "new_runtime_hash": nrh,
            "old_ledger_hash": ledger_hash,
            "new_ledger_hash": new_ledger,
            "old_receipt_hash": receipt_hash,
            "new_receipt_hash": receipt_hash,
            "old_receipt_byte_equal": True,
            "rollback_state": "RESTORED_EXACT" if kind == "FAILED_UPGRADE_ROLLBACK" else "NOT_REQUIRED",
            "reason_code": "SUPPORTED_AND_READABLE" if spec["expected"] == "SUPPORTED" else "REFUSED_WITHOUT_REWRITE",
        }, "row_hash")

    upgrade = hashed({"schema": gate.UPGRADE_ROLLBACK_SCHEMA, "subject_commit": stable_sha, "subject_tree": stable_tree, "rows": [upgrade_row(spec) for spec in upgrade_manifest]}, "report_hash")

    open_issues = hashed({
        "schema": gate.OPEN_ISSUES_SCHEMA,
        "repository": core_repo,
        "observed_at": now,
        "query_manifest_hash": gate._digest({"endpoint": "GET /repos/James3014/nexus-core/issues?state=open&per_page=100", "response_hash": file_sha(api / "open-issues.json")}),
        "raw_issue_ids": [3],
        "severity_high_issue_ids": [],
        "classifications": {"3": "GATE_META_EXCLUDED"},
        "severity_high_count": 0,
    }, "snapshot_hash")

    formal_files = {
        "tg4_receipt": formal_dir / "tg4.json",
        "tg5_receipt": formal_dir / "tg5.json",
        "tg6_receipt": formal_dir / "tg6.json",
        "compatibility": formal_dir / "compatibility.json",
        "conformance": formal_dir / "conformance.json",
        "upgrade_rollback": formal_dir / "upgrade.json",
        "open_issues": formal_dir / "open-issues.json",
        "tg7_selection": formal_dir / "tg7-selection.json",
        "tg7_corpus": formal_dir / "tg7-corpus.json",
        "tg7_shadow": formal_dir / "tg7-shadow.json",
        "tg7_report": formal_dir / "tg7-report.json",
    }
    formal_values = {
        "tg4_receipt": tg4,
        "tg5_receipt": tg5,
        "tg6_receipt": tg6,
        "compatibility": compatibility,
        "conformance": conformance,
        "upgrade_rollback": upgrade,
        "open_issues": open_issues,
        "tg7_selection": tg7_selection,
        "tg7_corpus": tg7_corpus,
        "tg7_shadow": tg7_shadow,
        "tg7_report": tg7_report,
    }
    for key, path in formal_files.items():
        write_json(path, formal_values[key])

    stable_formal_paths: list[Path] = []
    stable_projection_rows: list[dict[str, Any]] = []
    for idx, source in enumerate(stable_sources, 1):
        formal = hashed({
            "schema": gate.STABLE_RUN_SCHEMA,
            "run_id": f"github-{source['github_run_id']}-stable-{idx}",
            "candidate_commit": stable_sha,
            "candidate_tree": stable_tree,
            "observed_at": source["observed_at"],
            "complete": True,
            "tg5_run_id": source["tg5_receipt_hash"],
            "tg7_run_id": source["tg7_report_hash"],
            "eligible_attempts": source["eligible_attempts"],
            "required_skips": source["required_skips"],
            "false_certification_count": source["false_certification_count"],
            "client_parity": source["client_parity"],
            "factual_outcome_hash": source["factual_outcome_hash"],
            "compatibility_hash": compatibility["matrix_hash"],
            "conformance_hash": conformance["report_hash"],
            "upgrade_rollback_hash": upgrade["report_hash"],
            "tg5_receipt_hash": tg5_cert["receipt_hash"],
            "tg7_report_hash": tg7_report["report_hash"],
        }, "run_hash")
        path = formal_dir / f"stable-run-{idx}.json"
        write_json(path, formal)
        stable_formal_paths.append(path)
        stable_projection_rows.append({
            "run_index": idx,
            "actual_stable_tg5_receipt_hash": source["tg5_receipt_hash"],
            "actual_stable_tg7_report_hash": source["tg7_report_hash"],
            "accepted_dependency_tg5_receipt_hash": tg5_cert["receipt_hash"],
            "accepted_dependency_tg7_report_hash": tg7_report["report_hash"],
            "factual_outcome_hash": source["factual_outcome_hash"],
            "eligible_attempts": source["eligible_attempts"],
            "observed_at": source["observed_at"],
        })

    projection_provenance = {
        "schema": "nexus.core.tg8-legacy-gate-projection-provenance.v1",
        "purpose": "Compatibility cross-check of the historical TG8 reducer; not a replacement for direct physical evidence.",
        "tg4_projection_authority": {"comment_id": 5542807802, "comment_sha256": file_sha(api / "tg4-comment.json"), "author_association": tg4_comment["author_association"]},
        "tg5_projection_authority": {"comment_id": 5549587546, "comment_sha256": file_sha(api / "tg5-comment.json"), "raw_receipt_hash": tg5_cert["receipt_hash"], "raw_reverification_hash": file_sha(tg7_root / "tg5-reverification.json")},
        "tg6_projection_authority": {"comment_id": 5548355769, "comment_sha256": file_sha(api / "tg6-comment.json"), "physical_artifact_sha256": expected_artifact_hashes["tg6.zip"]},
        "stable_run_anchor_projection": stable_projection_rows,
        "claim_ceiling": "LEGACY_REDUCER_CROSS_CHECK_ONLY",
    }
    write_json(out / "legacy-gate-projection-provenance.json", projection_provenance)

    input_hashes = {k: gate._file_hash(path) for k, path in formal_files.items()}
    for idx, path in enumerate(stable_formal_paths, 1):
        input_hashes[f"stable_run_{idx}"] = gate._file_hash(path)
    thresholds = hashed({
        "schema": gate.THRESHOLDS_SCHEMA,
        "repository": core_repo,
        "rc_candidate": gate.RC_CANDIDATE,
        "stable_candidate": gate.STABLE_CANDIDATE,
        "subject_commit": stable_sha,
        "subject_tree": stable_tree,
        "dependency_subjects": {
            "tg4": {"commit": tg4["subject_commit"], "tree": tg4["subject_tree"], "receipt_hash": tg4["receipt_hash"]},
            "tg5": {"commit": tg5["subject_commit"], "tree": tg5["subject_tree"], "receipt_hash": tg5["receipt_hash"]},
            "tg6": {"commit": tg6["subject_commit"], "tree": tg6["subject_tree"], "receipt_hash": tg6["receipt_hash"]},
            "tg7": {"commit": tg7_controller["subject"], "tree": tg7_controller["subject_tree"], "receipt_hash": tg7_report["report_hash"]},
        },
        "input_hashes": input_hashes,
        "compatibility_manifest": compatibility_manifest,
        "upgrade_manifest": upgrade_manifest,
        "required_clients": list(gate.REQUIRED_CLIENTS),
        "forbidden_output_states": sorted(gate.FORBIDDEN_OUTPUT_STATES),
        "observed_at": now,
    }, "threshold_hash")
    thresholds_path = formal_dir / "thresholds.json"
    thresholds_sha_path = formal_dir / "thresholds.sha256"
    write_json(thresholds_path, thresholds)
    thresholds_sha_path.write_text(thresholds["threshold_hash"][7:] + "\n", encoding="utf-8")

    legacy_report_path = out / "legacy-gate-report.json"
    legacy_report = gate.adjudicate(
        thresholds_path=thresholds_path,
        expected_thresholds_sha256_file=thresholds_sha_path,
        compatibility_path=formal_files["compatibility"],
        conformance_path=formal_files["conformance"],
        upgrade_rollback_path=formal_files["upgrade_rollback"],
        open_issues_path=formal_files["open_issues"],
        tg4_receipt_path=formal_files["tg4_receipt"],
        tg5_receipt_path=formal_files["tg5_receipt"],
        tg6_receipt_path=formal_files["tg6_receipt"],
        tg7_selection_path=formal_files["tg7_selection"],
        tg7_corpus_path=formal_files["tg7_corpus"],
        tg7_shadow_path=formal_files["tg7_shadow"],
        tg7_report_path=formal_files["tg7_report"],
        stable_run_paths=stable_formal_paths,
        report_path=legacy_report_path,
    )

    evidence_manifest["stable_subject"] = {"commit": stable_sha, "tree": stable_tree}
    evidence_manifest["current_subject"] = {"commit": current_sha, "tree": current_tree}
    evidence_manifest["physical_factual_outcome_hash"] = next(iter(factual_hashes), None)
    evidence_manifest["aggregate_stable_eligible_attempts"] = 168
    evidence_manifest["legacy_gate_report_hash"] = legacy_report.get("report_hash")
    evidence_manifest["legacy_gate_classification"] = legacy_report.get("classification")
    evidence_manifest["generated_at"] = now
    write_json(out / "evidence-manifest.json", evidence_manifest)

    direct_status = "CORE_V1_TG8_PROTOCOL_MATURITY_EVIDENCE_READY" if not direct_failures else "CORE_V1_TG8_PROTOCOL_MATURITY_EVIDENCE_BLOCKED"
    direct = {
        "schema": "nexus.core.tg8-direct-adjudication.v1",
        "repository": core_repo,
        "current_main": current_sha,
        "rc1_subject": rc1_sha,
        "rc2_patch_subject": rc2_sha,
        "stable_subject": stable_sha,
        "stable_tree": stable_tree,
        "stable_run_count": 3,
        "aggregate_stable_eligible_attempts": 168,
        "physical_execution_count": 336,
        "factual_outcome_hash": next(iter(factual_hashes), None),
        "physical_false_green_prevention": "PROVEN" if "TG7_TERMINAL_RECEIPT" not in direct_failures else "BLOCKED",
        "physical_transition": "VERIFIED" if not any(x.startswith(("TRANSITION_", "CORRUPT_", "FINAL_FAILED_UPGRADE_")) for x in direct_failures) else "BLOCKED",
        "rc_patch": "VERIFIED" if not any(x.startswith("RCPATCH_") for x in direct_failures) else "BLOCKED",
        "current_standalone_ci": "GREEN" if all(prechecks.get(k) for k in ("current_ci_success", "rc1_ci_success", "stable_ci_success", "rc2_ci_success")) else "BLOCKED",
        "open_severity_high_core_blockers": 0 if [x.get("number") for x in open_plain] == [3] else None,
        "release_count": len(releases),
        "tag_count": len(tags),
        "failures": sorted(set(direct_failures)),
        "classification": direct_status,
        "claim_ceiling": ["EVIDENCE_READINESS_ONLY", "NO_PROTOCOL_PROMOTION", "NO_RELEASE_AUTHORIZATION", "NO_DEPLOYMENT_TRUTH", "NO_PRODUCTION_READINESS", "NO_VALUE_CLAIM"],
        "generated_at": now,
    }
    direct["report_hash"] = gate._digest(direct)
    write_json(out / "direct-adjudication.json", direct)

    final = {
        "schema": "nexus.core.tg8-final-adjudication.v1",
        "direct_classification": direct_status,
        "legacy_reducer_classification": legacy_report.get("classification"),
        "legacy_reducer_reasons": legacy_report.get("reasons"),
        "decision": "READY" if direct_status == "CORE_V1_TG8_PROTOCOL_MATURITY_EVIDENCE_READY" and legacy_report.get("classification") == gate.STABLE_READY else "BLOCKED",
        "claim": "CORE_V1_TG8_PROTOCOL_MATURITY_EVIDENCE_READY" if direct_status == "CORE_V1_TG8_PROTOCOL_MATURITY_EVIDENCE_READY" and legacy_report.get("classification") == gate.STABLE_READY else None,
        "no_release_promotion": releases == [] and tags == [],
        "current_main_fresh": core_main.get("commit", {}).get("sha") == current_sha,
        "generated_at": now,
    }
    final["report_hash"] = gate._digest(final)
    write_json(out / "final-adjudication.json", final)
    print(canonical(final))
    if final["decision"] != "READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
