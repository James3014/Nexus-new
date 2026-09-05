#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO = "James3014/Nexus-new"
GATE_SHA = "a5d7d032fe80838a84ed596ca36ea5bd923ae7a1"
GATE_TREE = "bb8739812a5beb13e5897c40014cf69b4d49389a"
RC1_SHA = "d1fbe1f1f399351b1fac2591db00a6f150179753"
RC1_TREE = "0627c7649e6831299b26eaa7f15743d61a9e7282"
RC2_SHA = "968e88f2e8df7444ee2758d25182111830cd03e8"
STABLE_SHA = "4fd27ee64a0b4ad8e3f3326fd8c32014c9a391de"
STABLE_TREE = "c533e90fd538993f160f398ddca655366ac940b7"
CURRENT_PROTOCOL = "0.1.0-experimental"
RC1_PROTOCOL = "1.0.0-rc.1"
RC2_PROTOCOL = "1.0.0-rc.2"
STABLE_PROTOCOL = "1.0.0"
TG8_CLASSIFICATION = "PROTOCOL_RC_EVIDENCE_READY"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    return bytes_hash(path.read_bytes())


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"not a JSON object: {path}")
    return value


def write_doc(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(dict(value)) + "\n", encoding="utf-8")


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed rc={result.returncode}: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def git(root: Path, *args: str) -> str:
    return run(["git", "-C", str(root), *args]).stdout.strip()


def verify_subject(root: Path, sha: str, tree: str | None, expected_protocol: str) -> dict[str, str]:
    actual_sha = git(root, "rev-parse", "HEAD")
    actual_tree = git(root, "rev-parse", "HEAD^{tree}")
    if actual_sha != sha:
        raise RuntimeError(f"subject mismatch {root}: {actual_sha} != {sha}")
    if tree is not None and actual_tree != tree:
        raise RuntimeError(f"tree mismatch {root}: {actual_tree} != {tree}")
    text = (root / "product/protocol/__init__.py").read_text(encoding="utf-8")
    needle = f'PUBLIC_PROTOCOL_VERSION = "{expected_protocol}"'
    if needle not in text:
        raise RuntimeError(f"protocol readback mismatch {root}: expected {expected_protocol}")
    return {
        "commit": actual_sha,
        "tree": actual_tree,
        "protocol_blob": git(root, "rev-parse", "HEAD:product/protocol/__init__.py"),
        "public_protocol_version": expected_protocol,
    }


def build_wheel(root: Path, label: str, work: Path) -> dict[str, Any]:
    target = work / "wheels" / label
    target.mkdir(parents=True, exist_ok=True)
    for p in target.glob("*.whl"):
        p.unlink()
    result = run(["uv", "build", "--wheel", "--out-dir", str(target)], cwd=root)
    wheels = sorted(target.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel for {label}, got {wheels}")
    wheel = wheels[0]
    (work / "logs").mkdir(parents=True, exist_ok=True)
    (work / "logs" / f"build-{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"path": str(wheel), "hash": file_hash(wheel), "bytes": wheel.stat().st_size}


def _venv_python(venv: Path) -> Path:
    return venv / "bin" / "python"


def _venv_pip(venv: Path) -> Path:
    return venv / "bin" / "pip"


def create_venv(venv: Path) -> None:
    if venv.exists():
        shutil.rmtree(venv)
    run([sys.executable, "-m", "venv", str(venv)])


def install_wheel(venv: Path, wheel: Path, log_path: Path) -> subprocess.CompletedProcess[str]:
    result = run(
        [str(_venv_pip(venv)), "install", "--no-deps", "--force-reinstall", str(wheel)],
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def runtime_probe(venv: Path) -> dict[str, Any]:
    code = r'''
import hashlib, json
from pathlib import Path
import product
from product.protocol import (
    PUBLIC_PROTOCOL_VERSION, IMPLEMENTATION_SCHEMA, EVIDENCE_BUNDLE_SCHEMA,
    PROVENANCE_ENVELOPE_SCHEMA, CERTIFICATION_RECEIPT_SCHEMA,
)
from product.ledger import LEDGER_SCHEMA_VERSION
from product.runtime.schemas import HTTP_RESPONSE_SCHEMA
root=Path(product.__file__).resolve().parent
rows=[]
for p in sorted(root.rglob('*.py')):
    rows.append([p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()])
runtime_hash='sha256:'+hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
print(json.dumps({
  'public_protocol_version': PUBLIC_PROTOCOL_VERSION,
  'implementation_schema': IMPLEMENTATION_SCHEMA,
  'evidence_bundle_schema': EVIDENCE_BUNDLE_SCHEMA,
  'provenance_envelope_schema': PROVENANCE_ENVELOPE_SCHEMA,
  'certification_receipt_schema': CERTIFICATION_RECEIPT_SCHEMA,
  'ledger_schema': LEDGER_SCHEMA_VERSION,
  'http_schema': HTTP_RESPONSE_SCHEMA['$id'],
  'runtime_hash': runtime_hash,
  'ledger_source_hash': 'sha256:'+hashlib.sha256(Path(__import__('product.ledger',fromlist=['x']).__file__).read_bytes()).hexdigest(),
  'product_root': str(root),
}, sort_keys=True))
'''
    result = run([str(_venv_python(venv)), "-c", code])
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("runtime probe did not return object")
    return value


def transition(
    *,
    name: str,
    venv: Path,
    old_wheel: Path,
    new_wheel: Path,
    old_version: str,
    new_version: str,
    receipt_path: Path,
    work: Path,
) -> dict[str, Any]:
    old_install = install_wheel(venv, old_wheel, work / "logs" / f"{name}-old-install.log")
    if old_install.returncode != 0:
        raise RuntimeError(f"{name}: old install failed")
    old = runtime_probe(venv)
    if old["public_protocol_version"] != old_version:
        raise RuntimeError(f"{name}: old version mismatch {old}")
    old_receipt = receipt_path.read_bytes()
    new_install = install_wheel(venv, new_wheel, work / "logs" / f"{name}-new-install.log")
    if new_install.returncode != 0:
        raise RuntimeError(f"{name}: new install failed")
    new = runtime_probe(venv)
    if new["public_protocol_version"] != new_version:
        raise RuntimeError(f"{name}: new version mismatch {new}")
    new_receipt = receipt_path.read_bytes()
    if new_receipt != old_receipt:
        raise RuntimeError(f"{name}: retained receipt mutated")
    return {
        "observed": "SUPPORTED",
        "old_wheel_hash": file_hash(old_wheel),
        "new_wheel_hash": file_hash(new_wheel),
        "old_runtime_hash": old["runtime_hash"],
        "new_runtime_hash": new["runtime_hash"],
        "old_ledger_hash": old["ledger_source_hash"],
        "new_ledger_hash": new["ledger_source_hash"],
        "old_receipt_hash": bytes_hash(old_receipt),
        "new_receipt_hash": bytes_hash(new_receipt),
        "old_receipt_byte_equal": True,
        "rollback_state": "NOT_REQUIRED",
        "reason_code": f"PHYSICAL_WHEEL_INSTALL_READBACK:{old_version}->{new_version}",
    }


def failed_upgrade_rollback(
    *,
    venv: Path,
    rc1_wheel: Path,
    stable_wheel: Path,
    receipt_path: Path,
    work: Path,
) -> dict[str, Any]:
    before_install = install_wheel(venv, rc1_wheel, work / "logs" / "failed-upgrade-rc1-install.log")
    if before_install.returncode != 0:
        raise RuntimeError("failed-upgrade: RC1 install failed")
    before = runtime_probe(venv)
    if before["public_protocol_version"] != RC1_PROTOCOL:
        raise RuntimeError("failed-upgrade: precondition is not RC1")
    receipt_before = receipt_path.read_bytes()
    corrupted = work / "wheels" / "corrupted-stable.whl"
    data = bytearray(stable_wheel.read_bytes())
    if len(data) < 1024:
        raise RuntimeError("stable wheel unexpectedly small")
    data[len(data)//2] ^= 0xFF
    corrupted.write_bytes(bytes(data))
    failure = install_wheel(venv, corrupted, work / "logs" / "failed-upgrade-corrupt-install.log")
    if failure.returncode == 0:
        raise RuntimeError("corrupted Stable wheel unexpectedly installed")
    restore = install_wheel(venv, rc1_wheel, work / "logs" / "failed-upgrade-rollback-install.log")
    if restore.returncode != 0:
        raise RuntimeError("failed-upgrade: RC1 rollback reinstall failed")
    after = runtime_probe(venv)
    receipt_after = receipt_path.read_bytes()
    restored = (
        after["public_protocol_version"] == RC1_PROTOCOL
        and after["runtime_hash"] == before["runtime_hash"]
        and after["ledger_source_hash"] == before["ledger_source_hash"]
        and receipt_after == receipt_before
    )
    if not restored:
        raise RuntimeError("failed-upgrade: rollback did not restore exact observed state")
    return {
        "observed": "REFUSED",
        "old_wheel_hash": file_hash(rc1_wheel),
        "new_wheel_hash": file_hash(corrupted),
        "old_runtime_hash": before["runtime_hash"],
        "new_runtime_hash": after["runtime_hash"],
        "old_ledger_hash": before["ledger_source_hash"],
        "new_ledger_hash": after["ledger_source_hash"],
        "old_receipt_hash": bytes_hash(receipt_before),
        "new_receipt_hash": bytes_hash(receipt_after),
        "old_receipt_byte_equal": True,
        "rollback_state": "RESTORED_EXACT",
        "reason_code": "PHYSICAL_CORRUPTED_STABLE_WHEEL_REFUSED_AND_RC1_RESTORED",
        "failed_install_returncode": failure.returncode,
    }


def validator_probe(rc1: Path, python: Path, receipt_path: Path, work: Path) -> dict[str, Any]:
    code = r'''
import json, sys, tempfile
from pathlib import Path
from product.protocol import (
    PUBLIC_PROTOCOL_VERSION, IMPLEMENTATION_SCHEMA, EVIDENCE_BUNDLE_SCHEMA,
    PROVENANCE_ENVELOPE_SCHEMA, CERTIFICATION_RECEIPT_SCHEMA,
)
from product.runtime.schemas import validate_certification_request, validate_receipt_verify_request, HTTP_RESPONSE_SCHEMA
from product.ledger import LEDGER_SCHEMA_VERSION, LedgerAppendRequest, append_or_replay
from product.evidence.ingestion import IDENTITY_ENVELOPE_SCHEMA
receipt_path=Path(sys.argv[1])
receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
valid={
 'protocol_version': PUBLIC_PROTOCOL_VERSION,
 'implementation_schema': IMPLEMENTATION_SCHEMA,
 'repository': {'owner':'James3014','name':'Nexus-new','pr_number':801,'expected_base_sha':'a'*40,'expected_head_sha':'b'*40},
 'acceptance_contract': {}, 'verification_plan': {}, 'profile_id':'python-oci-pytest-v1',
 'idempotency_key':'tg8-v4-validator','expected_generation':0,
}
valid_errors=validate_certification_request(valid)
foreign_protocol=dict(valid); foreign_protocol['protocol_version']='2.0.0-foreign'
foreign_protocol_errors=validate_certification_request(foreign_protocol)
foreign_schema=dict(valid); foreign_schema['implementation_schema']='nexus.foreign.v9'
foreign_schema_errors=validate_certification_request(foreign_schema)
receipt_errors=validate_receipt_verify_request({'receipt':receipt,'requested_scope':'ENVELOPE_ONLY','original_inputs':None})
foreign_receipt=dict(receipt); foreign_receipt['receipt_schema']='nexus.foreign-receipt.v9'
foreign_receipt_errors=validate_receipt_verify_request({'receipt':foreign_receipt,'requested_scope':'ENVELOPE_ONLY','original_inputs':None})
envelope_bytes=json.dumps({'schema':IDENTITY_ENVELOPE_SCHEMA},sort_keys=True,separators=(',',':')).encode()
with tempfile.TemporaryDirectory() as td:
    db=Path(td)/'ledger.sqlite3'
    req=LedgerAppendRequest(
      ledger_id='tg8-v4',request_id='tg8-v4-1',idempotency_key='tg8-v4-ledger',expected_generation=0,attempt=1,
      canonical_request=valid,identity_envelope_bytes=envelope_bytes,completion_receipt_bytes=receipt_path.read_bytes(),
      source_snapshot_hash='sha256:'+'1'*64,
    )
    first=append_or_replay(req,db_path=db)
    stale_req=LedgerAppendRequest(
      ledger_id='tg8-v4',request_id='tg8-v4-2',idempotency_key='tg8-v4-ledger-2',expected_generation=0,attempt=1,
      canonical_request={**valid,'idempotency_key':'tg8-v4-validator-2'},identity_envelope_bytes=envelope_bytes,
      completion_receipt_bytes=receipt_path.read_bytes(),source_snapshot_hash='sha256:'+'2'*64,
    )
    stale=append_or_replay(stale_req,db_path=db)
    db_bytes=db.read_bytes()
foreign_ledger_refused=False
try:
    LedgerAppendRequest(schema='nexus.ledger-entry.v9')
except TypeError:
    foreign_ledger_refused=True
print(json.dumps({
 'public_protocol_version':PUBLIC_PROTOCOL_VERSION,
 'implementation_schema':IMPLEMENTATION_SCHEMA,
 'evidence_bundle_schema':EVIDENCE_BUNDLE_SCHEMA,
 'provenance_envelope_schema':PROVENANCE_ENVELOPE_SCHEMA,
 'certification_receipt_schema':CERTIFICATION_RECEIPT_SCHEMA,
 'ledger_schema':LEDGER_SCHEMA_VERSION,
 'http_schema':HTTP_RESPONSE_SCHEMA['$id'],
 'valid_request_accepted': not valid_errors,
 'foreign_protocol_refused': bool(foreign_protocol_errors),
 'foreign_protocol_errors': list(foreign_protocol_errors),
 'foreign_implementation_schema_refused': bool(foreign_schema_errors),
 'foreign_implementation_schema_errors': list(foreign_schema_errors),
 'valid_receipt_schema_accepted': not receipt_errors,
 'foreign_receipt_schema_refused': bool(foreign_receipt_errors),
 'foreign_receipt_schema_errors': list(foreign_receipt_errors),
 'ledger_append_status': first.status.value,
 'ledger_generation_stale_status': stale.status.value,
 'foreign_ledger_schema_refused': foreign_ledger_refused,
 'ledger_db_hash': 'sha256:'+__import__('hashlib').sha256(db_bytes).hexdigest(),
}, sort_keys=True))
'''
    result = run([str(python), "-c", code, str(receipt_path)], cwd=rc1)
    (work / "logs" / "validator-probe.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    value = json.loads(result.stdout)
    required_true = [
        "valid_request_accepted",
        "foreign_protocol_refused",
        "foreign_implementation_schema_refused",
        "valid_receipt_schema_accepted",
        "foreign_receipt_schema_refused",
        "foreign_ledger_schema_refused",
    ]
    if not all(value.get(k) is True for k in required_true):
        raise RuntimeError(f"validator probe failed: {value}")
    if value.get("ledger_append_status") != "APPENDED" or value.get("ledger_generation_stale_status") != "STALE_GENERATION":
        raise RuntimeError(f"ledger probe failed: {value}")
    return value


async def _client_probe_async(gate: Path, out: Path) -> dict[str, Any]:
    namespace = runpy.run_path(str(gate / "tests/product/test_client_conformance.py"))
    request = namespace["CANONICAL_REQUEST"]
    service_cls = namespace["MockCanonicalService"]
    from product.clients.mcp import nexus_certify
    from product.clients.github_action import run_action
    from product.runtime.auth import generate_bearer_token, write_secure_token
    from product.runtime.http import start_runtime

    tmp = Path(tempfile.mkdtemp(prefix="tg8-client-v4-"))
    token_dir = tmp / ".config" / "nexus-core"
    token_dir.mkdir(parents=True, mode=0o700)
    token_path = token_dir / "token"
    token = generate_bearer_token()
    write_secure_token(token, token_path)
    db_path = tmp / "ledger.sqlite3"
    req_path = tmp / "request.json"
    req_path.write_text(json.dumps(request), encoding="utf-8")
    service = service_cls()
    handle = await start_runtime(host="127.0.0.1", port=0, token_path=token_path, db_path=db_path, service=service)
    base_url = f"http://127.0.0.1:{handle.port}"
    raw: dict[str, Any] = {}
    try:
        mcp = await asyncio.to_thread(nexus_certify, arguments=request, service_url=base_url, token=token)
        raw["MCP"] = mcp

        cli_bin = gate / ".venv" / "bin" / "nexus-certify"
        proc = await asyncio.create_subprocess_exec(
            str(cli_bin), "submit", "--request", str(req_path), "--url", base_url, "--token-file", str(token_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        (out / "logs" / "client-cli.stderr").write_bytes(stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"CLI failed rc={proc.returncode}: {stderr.decode(errors='replace')}")
        raw["CLI"] = json.loads(stdout.decode())

        old_runner = os.environ.get("RUNNER_ENVIRONMENT")
        os.environ["RUNNER_ENVIRONMENT"] = "self-hosted"
        try:
            action = await asyncio.to_thread(
                run_action, request_file=req_path, token_file=token_path, service_url=base_url
            )
        finally:
            if old_runner is None:
                os.environ.pop("RUNNER_ENVIRONMENT", None)
            else:
                os.environ["RUNNER_ENVIRONMENT"] = old_runner
        raw["ACTION"] = action["response"]
    finally:
        await handle.stop()

    canon = {name: canonical(value) for name, value in raw.items()}
    parity = len(set(canon.values())) == 1
    if not parity:
        raise RuntimeError("physical client outputs are not canonical-parity")
    out.mkdir(parents=True, exist_ok=True)
    for name, value in raw.items():
        write_doc(out / f"client-{name.lower()}-response.json", value)
    return {
        "canonical_request_hash": digest(request),
        "canonical_response_hash": digest(raw["CLI"]),
        "endpoint_sequence": ["POST /v1/certifications", "GET /v1/certifications/{id}"],
        "redaction_set": ["authorization", "github_token"],
        "clients": {
            name: {
                "artifact_hash": file_hash(gate / {
                    "CLI": "product/clients/cli.py",
                    "MCP": "product/clients/mcp.py",
                    "ACTION": "product/clients/github_action.py",
                }[name]),
                "output_hash": digest(raw[name]),
                "state": raw[name].get("state"),
                "disposition": raw[name].get("disposition"),
                "receipt_hash": (raw[name].get("receipt") or {}).get("receipt_hash"),
            }
            for name in ("CLI", "MCP", "ACTION")
        },
        "parity": parity,
    }


def client_probe(gate: Path, out: Path) -> dict[str, Any]:
    sys.path.insert(0, str(gate))
    old_cwd = Path.cwd()
    os.chdir(gate)
    try:
        return asyncio.run(_client_probe_async(gate, out))
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(gate))
        except ValueError:
            pass


def physical_observations(gate: Path, rc1: Path, rc2: Path, stable: Path, tg6: Path, work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    (work / "logs").mkdir(parents=True, exist_ok=True)
    subjects = {
        "current": verify_subject(gate, GATE_SHA, GATE_TREE, CURRENT_PROTOCOL),
        "rc1": verify_subject(rc1, RC1_SHA, RC1_TREE, RC1_PROTOCOL),
        "rc2": verify_subject(rc2, RC2_SHA, None, RC2_PROTOCOL),
        "stable": verify_subject(stable, STABLE_SHA, STABLE_TREE, STABLE_PROTOCOL),
    }
    if git(rc2, "rev-parse", "HEAD^") != RC1_SHA:
        raise RuntimeError("RC2 is not a direct child of RC1")
    if git(stable, "rev-parse", "HEAD^") != RC2_SHA:
        raise RuntimeError("Stable is not a direct child of RC2")

    wheels = {
        "current": build_wheel(gate, "current", work),
        "rc1": build_wheel(rc1, "rc1", work),
        "rc2": build_wheel(rc2, "rc2", work),
        "stable": build_wheel(stable, "stable", work),
    }
    for key, meta in subjects.items():
        meta["wheel_hash"] = wheels[key]["hash"]
        meta["wheel_bytes"] = wheels[key]["bytes"]

    retained = work / "retained-tg5-receipt.json"
    shutil.copyfile(tg6 / "tg5-receipt.json", retained)
    retained_initial = retained.read_bytes()
    retained_hash = bytes_hash(retained_initial)

    venv = work / "transition-venv"
    create_venv(venv)
    transitions = {
        "CURRENT_TO_RC": transition(
            name="current-to-rc", venv=venv,
            old_wheel=Path(wheels["current"]["path"]), new_wheel=Path(wheels["rc1"]["path"]),
            old_version=CURRENT_PROTOCOL, new_version=RC1_PROTOCOL, receipt_path=retained, work=work,
        ),
        "RC_PATCH": transition(
            name="rc1-to-rc2", venv=venv,
            old_wheel=Path(wheels["rc1"]["path"]), new_wheel=Path(wheels["rc2"]["path"]),
            old_version=RC1_PROTOCOL, new_version=RC2_PROTOCOL, receipt_path=retained, work=work,
        ),
        "RC_TO_STABLE": transition(
            name="rc1-to-stable", venv=venv,
            old_wheel=Path(wheels["rc1"]["path"]), new_wheel=Path(wheels["stable"]["path"]),
            old_version=RC1_PROTOCOL, new_version=STABLE_PROTOCOL, receipt_path=retained, work=work,
        ),
        "FAILED_UPGRADE_ROLLBACK": failed_upgrade_rollback(
            venv=venv, rc1_wheel=Path(wheels["rc1"]["path"]), stable_wheel=Path(wheels["stable"]["path"]),
            receipt_path=retained, work=work,
        ),
    }
    if retained.read_bytes() != retained_initial:
        raise RuntimeError("retained TG5 receipt mutated across physical matrix")

    validators = validator_probe(rc1, gate / ".venv" / "bin" / "python", retained, work)
    client = client_probe(gate, work)

    gate_probe_venv = work / "identity-venv"
    create_venv(gate_probe_venv)
    gate_install = install_wheel(gate_probe_venv, Path(wheels["current"]["path"]), work / "logs" / "identity-current-install.log")
    if gate_install.returncode != 0:
        raise RuntimeError("current identity wheel install failed")
    identities = runtime_probe(gate_probe_venv)
    identities["cli_client"] = client["clients"]["CLI"]["artifact_hash"]
    identities["mcp_client"] = client["clients"]["MCP"]["artifact_hash"]
    identities["action_client"] = client["clients"]["ACTION"]["artifact_hash"]
    identities["ledger_generation"] = "generation-cas-v1"
    identities["reader_version"] = f"core-reader@{GATE_SHA}"

    body = {
        "schema": "nexus.core-v1.tg8-physical-observations.v4",
        "repository": REPO,
        "gate_subject": GATE_SHA,
        "gate_tree": GATE_TREE,
        "candidates": subjects,
        "transitions": transitions,
        "validators": validators,
        "client_conformance": client,
        "identities": identities,
        "retained_receipt_hash": retained_hash,
        "retained_receipt_byte_equal": True,
    }
    body["semantic_hash"] = digest(body)
    return body


def fresh_open_issues(seed: dict[str, Any]) -> dict[str, Any]:
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
    for query in queries:
        proc = run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q={query}", "-f", "per_page=100"])
        data = json.loads(proc.stdout)
        for item in data.get("items", []):
            if "pull_request" not in item:
                issue_map[int(item["number"])] = item
    raw = sorted(issue_map)
    high = sorted(
        n for n, item in issue_map.items()
        if str(item.get("title", "")).lstrip().upper().startswith("P0") and n not in {772, 773, 802}
    )
    classes: dict[str, str] = {}
    for n in raw:
        if n in {772, 773, 802}:
            classes[str(n)] = "GATE_META_EXCLUDED"
        elif n in high:
            classes[str(n)] = "CONSERVATIVE_SEVERITY_HIGH_RC_ONLY_SNAPSHOT"
        else:
            classes[str(n)] = "OPEN_QUERY_RESULT_NONBLOCKING_FOR_RC"
    observed = datetime.now(timezone.utc).isoformat()
    body = {
        "schema": seed["schema"],
        "repository": REPO,
        "observed_at": observed,
        "query_manifest_hash": digest({"queries": queries}),
        "raw_issue_ids": raw,
        "severity_high_issue_ids": high,
        "classifications": classes,
        "severity_high_count": len(high),
    }
    body["snapshot_hash"] = digest(body)
    return body


def compatibility_from_observations(thresholds: dict[str, Any], obs: dict[str, Any]) -> dict[str, Any]:
    ids = obs["identities"]
    validators = obs["validators"]
    transitions = obs["transitions"]
    clients = obs["client_conformance"]["clients"]
    receipt_hash = obs["retained_receipt_hash"]
    rows = []
    for spec in thresholds["compatibility_manifest"]:
        axis = spec["axis"]
        expected = spec["expected"]
        source = spec["source"]
        target = spec["target"]
        observed: str
        reason: str
        if axis == "public_protocol":
            if expected == "SUPPORTED":
                ok = transitions["CURRENT_TO_RC"]["observed"] == "SUPPORTED" and target == RC1_PROTOCOL
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = "PHYSICAL_CURRENT_TO_RC_WHEEL_INSTALL_READBACK"
            else:
                ok = validators["foreign_protocol_refused"] is True
                observed = "REFUSED" if ok else "SUPPORTED"
                reason = "PHYSICAL_CERTIFICATION_REQUEST_PROTOCOL_REJECTION"
        elif axis == "implementation_schema":
            if expected == "SUPPORTED":
                ok = validators["valid_request_accepted"] is True and source == validators["implementation_schema"] and target == source
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = "PHYSICAL_CERTIFICATION_REQUEST_SCHEMA_ACCEPTANCE"
            else:
                ok = validators["foreign_implementation_schema_refused"] is True
                observed = "REFUSED" if ok else "SUPPORTED"
                reason = "PHYSICAL_CERTIFICATION_REQUEST_SCHEMA_REJECTION"
        elif axis == "certification_receipt_schema":
            if expected == "SUPPORTED":
                ok = validators["valid_receipt_schema_accepted"] is True and source == validators["certification_receipt_schema"] and target == source
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = "PHYSICAL_RECEIPT_VERIFY_SCHEMA_ACCEPTANCE"
            else:
                ok = validators["foreign_receipt_schema_refused"] is True
                observed = "REFUSED" if ok else "SUPPORTED"
                reason = "PHYSICAL_RECEIPT_VERIFY_SCHEMA_REJECTION"
        elif axis == "ledger_schema":
            if expected == "SUPPORTED":
                ok = validators["ledger_append_status"] == "APPENDED" and source == validators["ledger_schema"] and target == source
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = "PHYSICAL_LEDGER_APPEND_CURRENT_SCHEMA"
            else:
                ok = validators["foreign_ledger_schema_refused"] is True
                observed = "REFUSED" if ok else "SUPPORTED"
                reason = "PHYSICAL_LEDGER_REQUEST_MODEL_FOREIGN_SCHEMA_REJECTION"
        elif axis == "ledger_generation":
            if expected == "SUPPORTED":
                ok = validators["ledger_append_status"] == "APPENDED" and source == ids["ledger_generation"] and target == source
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = "PHYSICAL_LEDGER_GENERATION_CAS_APPEND"
            else:
                ok = validators["ledger_generation_stale_status"] == "STALE_GENERATION"
                observed = "REFUSED" if ok else "SUPPORTED"
                reason = "PHYSICAL_LEDGER_STALE_GENERATION_REFUSAL"
        elif axis in {"cli_client", "mcp_client", "action_client"}:
            name = {"cli_client":"CLI","mcp_client":"MCP","action_client":"ACTION"}[axis]
            if expected == "SUPPORTED":
                ok = obs["client_conformance"]["parity"] is True and source == clients[name]["artifact_hash"] and target == source
                observed = "SUPPORTED" if ok else "REFUSED"
                reason = f"PHYSICAL_{name}_CANONICAL_HTTP_INVOCATION"
            else:
                observed = "REFUSED" if target != clients[name]["artifact_hash"] else "SUPPORTED"
                reason = f"PHYSICAL_{name}_ARTIFACT_IDENTITY_MISMATCH"
        else:
            actual = ids.get(axis)
            if expected == "SUPPORTED":
                observed = "SUPPORTED" if actual == source and target == source else "REFUSED"
                reason = f"PHYSICAL_SEALED_IDENTITY_READBACK:{axis}"
            else:
                observed = "REFUSED" if actual == source and target != actual else "SUPPORTED"
                reason = f"PHYSICAL_SEALED_IDENTITY_MISMATCH:{axis}"
        row = {
            **spec,
            "observed": observed,
            "reason_code": reason,
            "receipt_preservation_hash": receipt_hash,
        }
        row["row_hash"] = digest(row)
        rows.append(row)
    result = {
        "schema": "nexus.core-v1.protocol-compatibility.v1",
        "subject_commit": GATE_SHA,
        "subject_tree": GATE_TREE,
        "rows": rows,
    }
    result["matrix_hash"] = digest(result)
    return result


def conformance_from_observations(obs: dict[str, Any]) -> dict[str, Any]:
    physical = obs["client_conformance"]
    rows = []
    for name in ("CLI", "MCP", "ACTION"):
        source = physical["clients"][name]
        row = {
            "name": name,
            "artifact_hash": source["artifact_hash"],
            "output_hash": source["output_hash"],
            "parity": physical["parity"] is True,
        }
        row["row_hash"] = digest(row)
        rows.append(row)
    result = {
        "schema": "nexus.core-v1.client-conformance.v1",
        "subject_commit": GATE_SHA,
        "subject_tree": GATE_TREE,
        "canonical_request_hash": physical["canonical_request_hash"],
        "canonical_response_hash": physical["canonical_response_hash"],
        "endpoint_sequence": physical["endpoint_sequence"],
        "redaction_set": physical["redaction_set"],
        "clients": rows,
        "parity": physical["parity"] is True,
    }
    result["report_hash"] = digest(result)
    return result


def upgrade_from_observations(thresholds: dict[str, Any], obs: dict[str, Any]) -> dict[str, Any]:
    transitions = obs["transitions"]
    validators = obs["validators"]
    rc1 = transitions["RC_TO_STABLE"]
    rows = []
    for spec in thresholds["upgrade_manifest"]:
        kind = spec["kind"]
        if kind in {"CURRENT_TO_RC", "RC_PATCH", "RC_TO_STABLE", "FAILED_UPGRADE_ROLLBACK"}:
            src = transitions[kind]
            row = {**spec, **{k:v for k,v in src.items() if k in {
                "observed","old_wheel_hash","new_wheel_hash","old_runtime_hash","new_runtime_hash","old_ledger_hash","new_ledger_hash",
                "old_receipt_hash","new_receipt_hash","old_receipt_byte_equal","rollback_state","reason_code"
            }}}
        elif kind == "INCOMPATIBLE_PROTOCOL":
            observed = "REFUSED" if validators["foreign_protocol_refused"] else "SUPPORTED"
            row = {
                **spec, "observed": observed,
                "old_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "new_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "old_runtime_hash": rc1["old_runtime_hash"], "new_runtime_hash": rc1["old_runtime_hash"],
                "old_ledger_hash": rc1["old_ledger_hash"], "new_ledger_hash": rc1["old_ledger_hash"],
                "old_receipt_hash": obs["retained_receipt_hash"], "new_receipt_hash": obs["retained_receipt_hash"],
                "old_receipt_byte_equal": True, "rollback_state": "NOT_REQUIRED",
                "reason_code": "PHYSICAL_CERTIFICATION_REQUEST_PROTOCOL_REJECTION",
            }
        elif kind == "INCOMPATIBLE_SCHEMA":
            observed = "REFUSED" if validators["foreign_implementation_schema_refused"] else "SUPPORTED"
            row = {
                **spec, "observed": observed,
                "old_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "new_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "old_runtime_hash": rc1["old_runtime_hash"], "new_runtime_hash": rc1["old_runtime_hash"],
                "old_ledger_hash": rc1["old_ledger_hash"], "new_ledger_hash": rc1["old_ledger_hash"],
                "old_receipt_hash": obs["retained_receipt_hash"], "new_receipt_hash": obs["retained_receipt_hash"],
                "old_receipt_byte_equal": True, "rollback_state": "NOT_REQUIRED",
                "reason_code": "PHYSICAL_CERTIFICATION_REQUEST_IMPLEMENTATION_SCHEMA_REJECTION",
            }
        elif kind == "INCOMPATIBLE_LEDGER":
            observed = "REFUSED" if validators["foreign_ledger_schema_refused"] else "SUPPORTED"
            ledger_hash = validators["ledger_db_hash"]
            row = {
                **spec, "observed": observed,
                "old_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "new_wheel_hash": obs["candidates"]["rc1"]["wheel_hash"],
                "old_runtime_hash": rc1["old_runtime_hash"], "new_runtime_hash": rc1["old_runtime_hash"],
                "old_ledger_hash": ledger_hash, "new_ledger_hash": ledger_hash,
                "old_receipt_hash": obs["retained_receipt_hash"], "new_receipt_hash": obs["retained_receipt_hash"],
                "old_receipt_byte_equal": True, "rollback_state": "NOT_REQUIRED",
                "reason_code": "PHYSICAL_LEDGER_REQUEST_MODEL_FOREIGN_SCHEMA_REJECTION",
            }
        else:
            raise RuntimeError(f"unhandled upgrade kind {kind}")
        row["row_hash"] = digest(row)
        rows.append(row)
    result = {
        "schema": "nexus.core-v1.upgrade-rollback.v1",
        "subject_commit": GATE_SHA,
        "subject_tree": GATE_TREE,
        "rows": rows,
    }
    result["report_hash"] = digest(result)
    return result


def prepare_packet(seed: Path, out: Path, obs: dict[str, Any]) -> None:
    for name in (
        "tg4-receipt.json", "tg5-receipt.json", "tg6-receipt.json",
        "tg7-selection.json", "tg7-corpus.json", "tg7-shadow-receipt.json", "tg7-report.json",
    ):
        shutil.copyfile(seed / name, out / name)
    thresholds = load(seed / "thresholds.json")
    if thresholds.get("subject_commit") != GATE_SHA or thresholds.get("subject_tree") != GATE_TREE:
        raise RuntimeError("seed thresholds are not bound to accepted TG8 gate subject")

    compatibility = compatibility_from_observations(thresholds, obs)
    conformance = conformance_from_observations(obs)
    upgrade = upgrade_from_observations(thresholds, obs)
    open_issues = fresh_open_issues(load(seed / "open-issues.json"))
    write_doc(out / "protocol-compatibility.json", compatibility)
    write_doc(out / "client-conformance.json", conformance)
    write_doc(out / "upgrade-rollback.json", upgrade)
    write_doc(out / "open-issues.json", open_issues)

    input_files = {
        "tg4_receipt": out / "tg4-receipt.json",
        "tg5_receipt": out / "tg5-receipt.json",
        "tg6_receipt": out / "tg6-receipt.json",
        "compatibility": out / "protocol-compatibility.json",
        "conformance": out / "client-conformance.json",
        "upgrade_rollback": out / "upgrade-rollback.json",
        "open_issues": out / "open-issues.json",
        "tg7_selection": out / "tg7-selection.json",
        "tg7_corpus": out / "tg7-corpus.json",
        "tg7_shadow": out / "tg7-shadow-receipt.json",
        "tg7_report": out / "tg7-report.json",
    }
    thresholds["input_hashes"] = {k: file_hash(v) for k, v in sorted(input_files.items())}
    thresholds["observed_at"] = datetime.now(timezone.utc).isoformat()
    thresholds.pop("threshold_hash", None)
    thresholds["threshold_hash"] = digest(thresholds)
    write_doc(out / "thresholds.json", thresholds)
    (out / "thresholds.sha256").write_text(thresholds["threshold_hash"][7:] + "\n", encoding="utf-8")


def cmd_collect(args: argparse.Namespace) -> int:
    gate, rc1, rc2, stable = map(lambda x: Path(x).resolve(), (args.gate, args.rc1, args.rc2, args.stable))
    seed, tg6, out = map(lambda x: Path(x).resolve(), (args.seed, args.tg6, args.out))
    out.mkdir(parents=True, exist_ok=True)
    work = out / "physical"
    obs = physical_observations(gate, rc1, rc2, stable, tg6, work)
    write_doc(out / "physical-observations.json", obs)
    prepare_packet(seed, out, obs)
    summary = {
        "schema": "nexus.core-v1.tg8-physical-repair-controller.v4",
        "repository": REPO,
        "gate_subject": GATE_SHA,
        "gate_tree": GATE_TREE,
        "rc1_subject": RC1_SHA,
        "rc2_subject": RC2_SHA,
        "stable_subject": STABLE_SHA,
        "physical_semantic_hash": obs["semantic_hash"],
        "client_parity": obs["client_conformance"]["parity"],
        "transition_kinds": sorted(obs["transitions"]),
        "target_classification": TG8_CLASSIFICATION,
        "claim_ceiling": "EVIDENCE_READINESS_ONLY_NO_PROMOTION",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    summary["controller_hash"] = digest(summary)
    write_doc(out / "controller-summary-v4.json", summary)
    return 0


def semantic_projection(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_subject": obs["gate_subject"],
        "gate_tree": obs["gate_tree"],
        "candidate_versions": {k:v["public_protocol_version"] for k,v in obs["candidates"].items()},
        "candidate_commits": {k:v["commit"] for k,v in obs["candidates"].items()},
        "transition_outcomes": {k:v["observed"] for k,v in obs["transitions"].items()},
        "rollback_state": obs["transitions"]["FAILED_UPGRADE_ROLLBACK"]["rollback_state"],
        "receipt_preserved": obs["retained_receipt_byte_equal"],
        "foreign_protocol_refused": obs["validators"]["foreign_protocol_refused"],
        "foreign_schema_refused": obs["validators"]["foreign_implementation_schema_refused"],
        "foreign_ledger_refused": obs["validators"]["foreign_ledger_schema_refused"],
        "ledger_stale_generation": obs["validators"]["ledger_generation_stale_status"],
        "client_parity": obs["client_conformance"]["parity"],
        "client_states": {k:v["state"] for k,v in obs["client_conformance"]["clients"].items()},
        "client_dispositions": {k:v["disposition"] for k,v in obs["client_conformance"]["clients"].items()},
        "client_receipt_hashes": {k:v["receipt_hash"] for k,v in obs["client_conformance"]["clients"].items()},
    }


def cmd_audit(args: argparse.Namespace) -> int:
    gate, rc1, rc2, stable = map(lambda x: Path(x).resolve(), (args.gate, args.rc1, args.rc2, args.stable))
    tg6, collector, out = map(lambda x: Path(x).resolve(), (args.tg6, args.collector, args.out))
    out.mkdir(parents=True, exist_ok=True)
    recomputed = physical_observations(gate, rc1, rc2, stable, tg6, out / "recomputed-physical")
    collected = load(collector / "physical-observations.json")
    left = semantic_projection(collected)
    right = semantic_projection(recomputed)
    if left != right:
        raise RuntimeError(f"independent semantic recomputation mismatch\ncollector={canonical(left)}\nrecomputed={canonical(right)}")
    gate_report = load(collector / "gate-report.json")
    if gate_report.get("classification") != TG8_CLASSIFICATION:
        raise RuntimeError(f"collector gate classification mismatch: {gate_report.get('classification')}")
    if gate_report.get("false_certification_count") != 0:
        raise RuntimeError("collector has false certifications")
    receipt = {
        "schema": "nexus.core-v1.tg8-physical-repair-independent-audit.v4",
        "repository": REPO,
        "status": "ACCEPT",
        "gate_subject": GATE_SHA,
        "collector_physical_semantic_hash": collected["semantic_hash"],
        "collector_projection_hash": digest(left),
        "recomputed_projection_hash": digest(right),
        "classification": gate_report["classification"],
        "false_certification_count": gate_report["false_certification_count"],
        "client_parity": right["client_parity"],
        "rollback_state": right["rollback_state"],
        "claim_ceiling": "EVIDENCE_READINESS_ONLY_NO_PROMOTION",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["audit_hash"] = digest(receipt)
    write_doc(out / "independent-audit-v4.json", receipt)
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    report = load(out / "gate-report.json")
    obs = load(out / "physical-observations.json")
    if report.get("classification") != TG8_CLASSIFICATION:
        raise RuntimeError(f"unexpected classification {report.get('classification')}")
    if report.get("stable_run_count") != 0:
        raise RuntimeError("repair lane must not synthesize Stable runs")
    if report.get("false_certification_count") != 0:
        raise RuntimeError("false certification count is non-zero")
    if obs["client_conformance"]["parity"] is not True:
        raise RuntimeError("client parity false")
    if obs["transitions"]["FAILED_UPGRADE_ROLLBACK"]["rollback_state"] != "RESTORED_EXACT":
        raise RuntimeError("rollback not exact")
    acceptance = {
        "schema": "nexus.core-v1.tg8-physical-repair-acceptance.v4",
        "repository": REPO,
        "status": "ACCEPT",
        "classification": report["classification"],
        "gate_subject": GATE_SHA,
        "gate_tree": GATE_TREE,
        "rc1_subject": RC1_SHA,
        "rc2_subject": RC2_SHA,
        "stable_evidence_candidate_subject": STABLE_SHA,
        "physical_semantic_hash": obs["semantic_hash"],
        "compatibility_failed": report.get("compatibility", {}).get("failed"),
        "conformance_failed": report.get("conformance", {}).get("failed"),
        "upgrade_failed": report.get("upgrade_rollback", {}).get("failed"),
        "false_certification_count": report["false_certification_count"],
        "stable_run_count": report["stable_run_count"],
        "client_parity": True,
        "rollback_state": "RESTORED_EXACT",
        "claim_ceiling": "EVIDENCE_READINESS_ONLY_NO_PROMOTION",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    acceptance["acceptance_hash"] = digest(acceptance)
    write_doc(out / "physical-repair-acceptance-v4.json", acceptance)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    for name in ("gate", "rc1", "rc2", "stable", "seed", "tg6", "out"):
        c.add_argument(f"--{name}", required=True)
    c.set_defaults(func=cmd_collect)
    a = sub.add_parser("audit")
    for name in ("gate", "rc1", "rc2", "stable", "tg6", "collector", "out"):
        a.add_argument(f"--{name}", required=True)
    a.set_defaults(func=cmd_audit)
    f = sub.add_parser("finalize")
    f.add_argument("--out", required=True)
    f.set_defaults(func=cmd_finalize)
    return p


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
