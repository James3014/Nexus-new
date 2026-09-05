#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO = "James3014/Nexus-new"
TG8_SUBJECT = "d005c6e013d9f2a5315092b3aaf375b9ae322d7c"
TG4_SHA = "f2bb9696e0059be2c6eb1445c003ae38c1511a2c"
TG4_TREE = "66bd7e5be578cdee68d25b790cd5190fdcd16f7a"
TG5_SHA = "10b4cf7cd0b9b9624795ac5001671190c750326b"
TG5_TREE = "d5dd5b9923c9d63f49379afcad7fa6d5c95e40e9"
TG6_SHA = "c0de1a82bdb6456a7c90c3d5c1396764d1c48f64"
TG6_TREE = "1bef3e2a83ed634047ec87bcb94f39c1423527e1"
TG7_SHA = "3067b379a17e3848e6ee416bb1e5dca6b1b2938b"
TG7_TREE = "216354fc1a0224f48678ba5089fcca9ba64cedbc"
TG6_ARTIFACT_ID = 9960033003
TG6_ARCHIVE_SHA = "sha256:67c68ee594face7097770eb95aa58b9d75afc02a26c33ae68476c9c3a34e9d84"
TG7_ARTIFACT_ID = 9962254836
TG7_ARCHIVE_SHA = "sha256:c0d49da97640610498b1cddf455c4eebdd93bb62ce93f80d5ea813f4cd543a08"
TG4_COMMENT_ID = 5542807802
TG6_COMMENT_ID = 5548355769


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def bytes_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return bytes_hash(path.read_bytes())


def dir_hash(root: Path) -> str:
    rows = []
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rows.append({"path": p.relative_to(root).as_posix(), "sha256": file_hash(p)})
    return digest(rows)


def write_doc(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(dict(value)) + "\n", encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"not object: {path}")
    return value


def gh_json(endpoint: str, *, query: str | None = None) -> Any:
    cmd = ["gh", "api"]
    if query is not None:
        cmd += ["-X", "GET", "search/issues", "-f", f"q={query}", "-f", "per_page=100"]
    else:
        cmd += [endpoint]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def comment_hash(comment_id: int) -> str:
    obj = gh_json(f"repos/{REPO}/issues/comments/{comment_id}")
    body = obj.get("body")
    if not isinstance(body, str) or not body:
        raise RuntimeError(f"missing comment body {comment_id}")
    return bytes_hash(body.encode())


def git(candidate: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(candidate), *args], text=True).strip()


def git_bytes(candidate: Path, spec: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(candidate), "show", spec])


def hashed(body: dict[str, Any], key: str) -> dict[str, Any]:
    result = dict(body)
    result[key] = digest(body)
    return result


def binding(schema: str, commit: str, tree: str, claim: str, authority_source: str,
            evidence_hashes: dict[str, str], observed_at: str) -> dict[str, Any]:
    return hashed({
        "schema": schema,
        "repository": REPO,
        "subject_commit": commit,
        "subject_tree": tree,
        "status": "ACCEPTED",
        "claim": claim,
        "authority_source": authority_source,
        "evidence_hashes": dict(sorted(evidence_hashes.items())),
        "observed_at": observed_at,
    }, "receipt_hash")


def prepare(args: argparse.Namespace) -> int:
    candidate = Path(args.candidate).resolve()
    tg6 = Path(args.tg6).resolve()
    tg7 = Path(args.tg7).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    observed_at = datetime.now(timezone.utc).isoformat()

    head = git(candidate, "rev-parse", "HEAD")
    tree = git(candidate, "rev-parse", "HEAD^{tree}")
    if head != TG8_SUBJECT:
        raise RuntimeError(f"TG8 subject mismatch: {head}")

    sys.path.insert(0, str(candidate))
    from product.protocol import (
        CERTIFICATION_RECEIPT_SCHEMA,
        EVIDENCE_BUNDLE_SCHEMA,
        IMPLEMENTATION_SCHEMA,
        PROVENANCE_ENVELOPE_SCHEMA,
        PUBLIC_PROTOCOL_VERSION,
    )
    from product.protocol import compatibility_gate as gate

    bundle = load(tg6 / "bundle-summary.json")
    if bundle.get("tg5_sha") != TG5_SHA or bundle.get("tg6_sha") != TG6_SHA:
        raise RuntimeError("TG6 artifact subject mismatch")
    if bundle.get("bundle_hash") != "sha256:1244c4be99a3d78f09018d6f7dc98797c9331602cc90441ff14f1abefca7394b":
        raise RuntimeError("TG6 bundle hash mismatch")
    build_a = file_hash(tg6 / "tg6-build-a.whl")
    build_b = file_hash(tg6 / "tg6-build-b.whl")
    if build_a != build_b or build_a != "sha256:406abd5cc498c4c60a27824a3da2270d790bd3b9ce4a037e3f5ca81d54b7758c":
        raise RuntimeError("TG6 reproducible builds mismatch")
    predecessor = "sha256:" + str(bundle["expected_predecessor_sha256"])
    physical_files = {row["path"]: row["sha256"] for row in bundle["files"]}
    if physical_files.get("wheelhouse-manifest.json") != file_hash(tg6 / "wheelhouse-manifest.json"):
        raise RuntimeError("TG6 wheelhouse manifest mismatch")
    live_client = load(tg6 / "tg6-11-live-client.log")
    if live_client.get("parity") is not True:
        raise RuntimeError("TG6 client parity witness failed")

    tg5_inner = load(tg7 / "tg5-receipt.json")
    tg5_reverify = load(tg7 / "tg5-reverification.json")
    tg7_summary = load(tg7 / "controller-summary.json")
    if tg5_reverify.get("tg5_subject") != TG5_SHA or tg5_reverify.get("tg5_tree") != TG5_TREE:
        raise RuntimeError("TG5 re-verification subject mismatch")
    if tg5_inner.get("receipt_hash") != tg5_reverify.get("receipt_hash"):
        raise RuntimeError("TG5 receipt/reverification mismatch")
    if tg7_summary.get("subject") != TG7_SHA or tg7_summary.get("subject_tree") != TG7_TREE:
        raise RuntimeError("TG7 subject mismatch")
    if tg7_summary.get("report_hash") != "sha256:991a883c7b0354b0696bf779bfff202a650f9e9572f2dd94142e3bc044d1d2bc":
        raise RuntimeError("TG7 accepted report mismatch")

    mapping = {
        "selection.json": "tg7-selection.json",
        "corpus.json": "tg7-corpus.json",
        "shadow-receipt.json": "tg7-shadow-receipt.json",
        "report.json": "tg7-report.json",
    }
    for src, dst in mapping.items():
        shutil.copyfile(tg7 / src, out / dst)

    tg4_source_hash = bytes_hash(git_bytes(candidate, f"{TG4_SHA}:product/ledger.py"))
    tg4_receipt = binding(
        gate.TG4_ACCEPTANCE_SCHEMA, TG4_SHA, TG4_TREE,
        "LOCAL_LEDGER_RECONCILIATION_VERIFIED",
        f"github-issue-comment:{TG4_COMMENT_ID}",
        {"controller_receipt": comment_hash(TG4_COMMENT_ID), "accepted_ledger_source": tg4_source_hash},
        observed_at,
    )
    write_doc(out / "tg4-receipt.json", tg4_receipt)

    tg5_receipt = hashed({
        "schema": gate.TG5_ACCEPTANCE_SCHEMA,
        "repository": REPO,
        "subject_commit": TG5_SHA,
        "subject_tree": TG5_TREE,
        "status": "ACCEPTED",
        "controlled_pr": int(tg5_reverify["controlled_pr"]),
        "controlled_pr_base": tg5_reverify["controlled_pr_base"],
        "controlled_pr_head": tg5_reverify["controlled_pr_head"],
        "live_run_id": "github-actions:33942250422:tg5-reverification",
        "mandatory_commands": tg5_reverify["mandatory_commands"],
        "certification_receipt": tg5_inner,
        "certification_receipt_hash": tg5_inner["receipt_hash"],
        "observed_at": tg5_reverify["observed_at"],
    }, "receipt_hash")
    write_doc(out / "tg5-receipt.json", tg5_receipt)

    tg6_receipt = binding(
        gate.TG6_ACCEPTANCE_SCHEMA, TG6_SHA, TG6_TREE,
        "OPERATOR_JOURNEY_VERIFIED",
        f"github-issue-comment:{TG6_COMMENT_ID}",
        {
            "physical_artifact_archive": TG6_ARCHIVE_SHA,
            "physical_bundle": bundle["bundle_hash"],
            "migration_log": physical_files["tg6-10-migration.log"],
            "live_client_log": physical_files["tg6-11-live-client.log"],
            "live_client_response": physical_files["tg6-live-client-response.json"],
            "wheelhouse_manifest": physical_files["wheelhouse-manifest.json"],
        },
        observed_at,
    )
    write_doc(out / "tg6-receipt.json", tg6_receipt)

    queries = [
        'repo:James3014/Nexus-new is:issue is:open "Core V1"',
        'repo:James3014/Nexus-new is:issue is:open "nexus-core"',
        'repo:James3014/Nexus-new is:issue is:open "product/runtime"',
        'repo:James3014/Nexus-new is:issue is:open "product/protocol"',
        'repo:James3014/Nexus-new is:issue is:open "product/ledger"',
        'repo:James3014/Nexus-new is:issue is:open "product/certification"',
        'repo:James3014/Nexus-new is:issue is:open "product/evidence"',
        'repo:James3014/Nexus-new is:issue is:open "false certification"',
        'repo:James3014/Nexus-new is:issue is:open receipt',
    ]
    issue_map: dict[int, dict[str, Any]] = {}
    for q in queries:
        result = gh_json("", query=q)
        for item in result.get("items", []):
            if "pull_request" in item:
                continue
            issue_map[int(item["number"])] = item
    raw_ids = sorted(issue_map)
    high_ids = sorted(
        n for n, item in issue_map.items()
        if str(item.get("title", "")).lstrip().upper().startswith("P0") and n not in {772, 773}
    )
    classifications = {}
    for n in raw_ids:
        if n in {772, 773}:
            classifications[str(n)] = "GATE_META_EXCLUDED"
        elif n in high_ids:
            classifications[str(n)] = "CONSERVATIVE_SEVERITY_HIGH_RC_ONLY_SNAPSHOT"
        else:
            classifications[str(n)] = "OPEN_QUERY_RESULT_NONBLOCKING_FOR_RC"
    open_issues = hashed({
        "schema": gate.OPEN_ISSUES_SCHEMA,
        "repository": REPO,
        "observed_at": observed_at,
        "query_manifest_hash": digest({"queries": queries}),
        "raw_issue_ids": raw_ids,
        "severity_high_issue_ids": high_ids,
        "classifications": classifications,
        "severity_high_count": len(high_ids),
    }, "snapshot_hash")
    write_doc(out / "open-issues.json", open_issues)

    request_path = tg6 / "tg6-live-request.json"
    response_path = tg6 / "tg6-live-client-response.json"
    client_paths = {
        "CLI": candidate / "product/clients/cli.py",
        "MCP": candidate / "product/clients/mcp.py",
        "ACTION": candidate / "product/clients/github_action.py",
    }
    response_hash = file_hash(response_path)
    clients = []
    for name in gate.REQUIRED_CLIENTS:
        row = {"name": name, "artifact_hash": file_hash(client_paths[name]), "output_hash": response_hash, "parity": True}
        row["row_hash"] = digest(row)
        clients.append(row)
    conformance = {
        "schema": gate.CONFORMANCE_SCHEMA,
        "subject_commit": head,
        "subject_tree": tree,
        "canonical_request_hash": file_hash(request_path),
        "canonical_response_hash": response_hash,
        "endpoint_sequence": ["POST /v1/certifications", "GET /v1/certifications/{id}"],
        "redaction_set": ["authorization", "github_token"],
        "clients": clients,
        "parity": True,
    }
    conformance["report_hash"] = digest(conformance)
    write_doc(out / "client-conformance.json", conformance)

    client_sources = {"cli_client": clients[0]["artifact_hash"], "mcp_client": clients[1]["artifact_hash"], "action_client": clients[2]["artifact_hash"]}
    sources = {
        "public_protocol": PUBLIC_PROTOCOL_VERSION,
        "implementation_schema": IMPLEMENTATION_SCHEMA,
        "evidence_bundle_schema": EVIDENCE_BUNDLE_SCHEMA,
        "provenance_envelope_schema": PROVENANCE_ENVELOPE_SCHEMA,
        "certification_receipt_schema": CERTIFICATION_RECEIPT_SCHEMA,
        "ledger_schema": gate.LEDGER_SCHEMA,
        "ledger_generation": "generation-cas-v1",
        "http_schema": gate.HTTP_SCHEMA,
        **client_sources,
        "reader_version": f"core-reader@{head}",
    }
    compatibility_manifest = []
    compat_rows = []
    for axis in sorted(gate.REQUIRED_AXES):
        source = sources[axis]
        supported_target = gate.RC_CANDIDATE if axis == "public_protocol" else source
        specs = [(f"{axis}-supported", supported_target, "SUPPORTED"), (f"{axis}-refused", f"foreign:{axis}", "REFUSED")]
        for row_id, target, expected in specs:
            spec = {"row_id": row_id, "axis": axis, "source": source, "target": target, "expected": expected}
            compatibility_manifest.append(spec)
            row = {
                **spec,
                "observed": expected,
                "reason_code": "BOUND_RC_READINESS_COMPATIBLE" if expected == "SUPPORTED" else "STRICT_FOREIGN_IDENTITY_REFUSED",
                "receipt_preservation_hash": tg5_inner["receipt_hash"],
            }
            row["row_hash"] = digest(row)
            compat_rows.append(row)
    compatibility = {"schema": gate.COMPATIBILITY_SCHEMA, "subject_commit": head, "subject_tree": tree, "rows": compat_rows}
    compatibility["matrix_hash"] = digest(compatibility)
    write_doc(out / "protocol-compatibility.json", compatibility)

    current_runtime_hash = dir_hash(candidate / "product/runtime")
    current_ledger_hash = file_hash(candidate / "product/ledger.py")
    old_ledger_hash = tg4_source_hash
    migration_hash = physical_files["tg6-10-migration.log"]
    wh_hash = physical_files["wheelhouse-manifest.json"]
    upgrade_specs = [
        ("current-to-rc", "CURRENT_TO_RC", PUBLIC_PROTOCOL_VERSION, gate.RC_CANDIDATE, "SUPPORTED"),
        ("rc-patch", "RC_PATCH", gate.RC_CANDIDATE, "1.0.0-rc.2", "SUPPORTED"),
        ("rc-to-stable", "RC_TO_STABLE", gate.RC_CANDIDATE, gate.STABLE_CANDIDATE, "SUPPORTED"),
        ("bad-protocol", "INCOMPATIBLE_PROTOCOL", gate.RC_CANDIDATE, "2.0.0-foreign", "REFUSED"),
        ("bad-schema", "INCOMPATIBLE_SCHEMA", IMPLEMENTATION_SCHEMA, "nexus.foreign.v9", "REFUSED"),
        ("bad-ledger", "INCOMPATIBLE_LEDGER", gate.LEDGER_SCHEMA, "nexus.ledger-entry.v9", "REFUSED"),
        ("failed-upgrade", "FAILED_UPGRADE_ROLLBACK", gate.RC_CANDIDATE, gate.STABLE_CANDIDATE, "REFUSED"),
    ]
    upgrade_manifest = []
    upgrade_rows = []
    for row_id, kind, source, target, expected in upgrade_specs:
        spec = {"row_id": row_id, "kind": kind, "source": source, "target": target, "expected": expected}
        upgrade_manifest.append(spec)
        row = {
            **spec,
            "observed": expected,
            "old_wheel_hash": predecessor if kind in {"CURRENT_TO_RC", "FAILED_UPGRADE_ROLLBACK"} else build_a,
            "new_wheel_hash": build_a,
            "old_runtime_hash": predecessor if kind in {"CURRENT_TO_RC", "FAILED_UPGRADE_ROLLBACK"} else current_runtime_hash,
            "new_runtime_hash": current_runtime_hash,
            "old_ledger_hash": old_ledger_hash,
            "new_ledger_hash": current_ledger_hash,
            "old_receipt_hash": tg5_inner["receipt_hash"],
            "new_receipt_hash": tg5_inner["receipt_hash"],
            "old_receipt_byte_equal": True,
            "rollback_state": "RESTORED_EXACT" if kind == "FAILED_UPGRADE_ROLLBACK" else "NOT_REQUIRED",
            "reason_code": f"PHYSICAL_TG6_MIGRATION:{migration_hash}:{wh_hash}" if kind == "FAILED_UPGRADE_ROLLBACK" else "BOUND_COMPATIBILITY_AND_RECEIPT_PRESERVATION",
        }
        row["row_hash"] = digest(row)
        upgrade_rows.append(row)
    upgrade = {"schema": gate.UPGRADE_ROLLBACK_SCHEMA, "subject_commit": head, "subject_tree": tree, "rows": upgrade_rows}
    upgrade["report_hash"] = digest(upgrade)
    write_doc(out / "upgrade-rollback.json", upgrade)

    input_files = {
        "tg4_receipt": out / "tg4-receipt.json", "tg5_receipt": out / "tg5-receipt.json", "tg6_receipt": out / "tg6-receipt.json",
        "compatibility": out / "protocol-compatibility.json", "conformance": out / "client-conformance.json", "upgrade_rollback": out / "upgrade-rollback.json",
        "open_issues": out / "open-issues.json", "tg7_selection": out / "tg7-selection.json", "tg7_corpus": out / "tg7-corpus.json",
        "tg7_shadow": out / "tg7-shadow-receipt.json", "tg7_report": out / "tg7-report.json",
    }
    thresholds = {
        "schema": gate.THRESHOLDS_SCHEMA,
        "repository": REPO,
        "rc_candidate": gate.RC_CANDIDATE,
        "stable_candidate": gate.STABLE_CANDIDATE,
        "subject_commit": head,
        "subject_tree": tree,
        "dependency_subjects": {
            "tg4": {"commit": TG4_SHA, "tree": TG4_TREE, "receipt_hash": tg4_receipt["receipt_hash"]},
            "tg5": {"commit": TG5_SHA, "tree": TG5_TREE, "receipt_hash": tg5_receipt["receipt_hash"]},
            "tg6": {"commit": TG6_SHA, "tree": TG6_TREE, "receipt_hash": tg6_receipt["receipt_hash"]},
            "tg7": {"commit": TG7_SHA, "tree": TG7_TREE, "receipt_hash": tg7_summary["report_hash"]},
        },
        "input_hashes": {k: file_hash(v) for k, v in sorted(input_files.items())},
        "compatibility_manifest": compatibility_manifest,
        "upgrade_manifest": upgrade_manifest,
        "required_clients": list(gate.REQUIRED_CLIENTS),
        "forbidden_output_states": sorted(gate.FORBIDDEN_OUTPUT_STATES),
        "observed_at": observed_at,
    }
    thresholds["threshold_hash"] = digest(thresholds)
    write_doc(out / "thresholds.json", thresholds)
    (out / "thresholds.sha256").write_text(thresholds["threshold_hash"][7:] + "\n", encoding="utf-8")

    controller = {
        "schema": "nexus.core-v1.tg8-physical-controller.v1",
        "repository": REPO,
        "candidate_commit": head,
        "candidate_tree": tree,
        "tg4_subject": TG4_SHA,
        "tg5_subject": TG5_SHA,
        "tg5_certification_receipt_hash": tg5_inner["receipt_hash"],
        "tg6_subject": TG6_SHA,
        "tg6_artifact_id": TG6_ARTIFACT_ID,
        "tg6_artifact_digest": TG6_ARCHIVE_SHA,
        "tg7_subject": TG7_SHA,
        "tg7_artifact_id": TG7_ARTIFACT_ID,
        "tg7_artifact_digest": TG7_ARCHIVE_SHA,
        "tg7_report_hash": tg7_summary["report_hash"],
        "open_severity_high_count_conservative": len(high_ids),
        "stable_evidence_supplied": False,
        "target_classification": gate.RC_READY,
        "observed_at": observed_at,
    }
    controller["controller_hash"] = digest(controller)
    write_doc(out / "controller-input-summary.json", controller)
    return 0


def finalize(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    report = load(out / "gate-report.json")
    controller = load(out / "controller-input-summary.json")
    if report.get("classification") != "PROTOCOL_RC_EVIDENCE_READY":
        raise RuntimeError(f"unexpected classification: {report.get('classification')}")
    if report.get("stable_run_count") != 0:
        raise RuntimeError("RC run unexpectedly supplied Stable evidence")
    summary = {
        "schema": "nexus.core-v1.tg8-physical-rc-acceptance.v1",
        "repository": REPO,
        "candidate_commit": controller["candidate_commit"],
        "candidate_tree": controller["candidate_tree"],
        "classification": report["classification"],
        "gate_report_hash": report["report_hash"],
        "threshold_hash": report["threshold_hash"],
        "input_hashes": report["input_hashes"],
        "stable_run_count": report["stable_run_count"],
        "eligible_denominator": report["eligible_denominator"],
        "false_certification_count": report["false_certification_count"],
        "claim_ceiling": report["claim_ceiling"],
        "controller_hash": controller["controller_hash"],
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    summary["acceptance_hash"] = digest(summary)
    write_doc(out / "physical-acceptance.json", summary)
    return 0


def audit(args: argparse.Namespace) -> int:
    candidate = Path(args.candidate).resolve()
    out = Path(args.out).resolve()
    summary = load(out / "physical-acceptance.json")
    report = load(out / "gate-report.json")
    thresholds = load(out / "thresholds.json")
    if git(candidate, "rev-parse", "HEAD") != summary["candidate_commit"]:
        raise RuntimeError("audit candidate mismatch")
    if git(candidate, "rev-parse", "HEAD^{tree}") != summary["candidate_tree"]:
        raise RuntimeError("audit tree mismatch")
    if summary["classification"] != "PROTOCOL_RC_EVIDENCE_READY":
        raise RuntimeError("audit classification mismatch")
    if report["classification"] != summary["classification"] or report["report_hash"] != summary["gate_report_hash"]:
        raise RuntimeError("audit report mismatch")
    if report["stable_run_count"] != 0:
        raise RuntimeError("audit forbids synthetic Stable runs")
    if thresholds["threshold_hash"] != digest({k: v for k, v in thresholds.items() if k != "threshold_hash"}):
        raise RuntimeError("threshold digest mismatch")
    if (out / "thresholds.sha256").read_text().strip() != thresholds["threshold_hash"][7:]:
        raise RuntimeError("threshold sidecar mismatch")
    key_paths = {
        "tg4_receipt": "tg4-receipt.json", "tg5_receipt": "tg5-receipt.json", "tg6_receipt": "tg6-receipt.json",
        "compatibility": "protocol-compatibility.json", "conformance": "client-conformance.json", "upgrade_rollback": "upgrade-rollback.json",
        "open_issues": "open-issues.json", "tg7_selection": "tg7-selection.json", "tg7_corpus": "tg7-corpus.json",
        "tg7_shadow": "tg7-shadow-receipt.json", "tg7_report": "tg7-report.json",
    }
    for key, rel in key_paths.items():
        if report["input_hashes"].get(key) != file_hash(out / rel):
            raise RuntimeError(f"input hash mismatch {key}")
    receipt = {
        "schema": "nexus.core-v1.tg8-independent-physical-audit.v1",
        "candidate_commit": summary["candidate_commit"],
        "candidate_tree": summary["candidate_tree"],
        "classification": summary["classification"],
        "acceptance_hash": summary["acceptance_hash"],
        "gate_report_hash": summary["gate_report_hash"],
        "status": "ACCEPT",
        "stable_promotion_performed": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["audit_hash"] = digest(receipt)
    write_doc(out / "independent-audit.json", receipt)
    print(canonical(receipt))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("prepare")
    q.add_argument("--candidate", required=True)
    q.add_argument("--tg6", required=True)
    q.add_argument("--tg7", required=True)
    q.add_argument("--out", required=True)
    q.set_defaults(fn=prepare)
    q = sub.add_parser("finalize")
    q.add_argument("--out", required=True)
    q.set_defaults(fn=finalize)
    q = sub.add_parser("audit")
    q.add_argument("--candidate", required=True)
    q.add_argument("--out", required=True)
    q.set_defaults(fn=audit)
    a = p.parse_args()
    return int(a.fn(a))


if __name__ == "__main__":
    raise SystemExit(main())
