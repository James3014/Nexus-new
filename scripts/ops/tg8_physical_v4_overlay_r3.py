#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import tg8_physical_v4_overlay as base


def _sh(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_cwd = cwd
    if effective_cwd is None and cmd and "/venvs/" in str(Path(cmd[0])):
        effective_cwd = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    result = subprocess.run(
        cmd,
        cwd=effective_cwd,
        check=False,
        text=True,
        capture_output=True,
        input=input,
    )
    if check and result.returncode:
        sys.stderr.write("COMMAND_FAILED: " + " ".join(cmd) + "\n")
        if effective_cwd is not None:
            sys.stderr.write(f"CWD: {effective_cwd}\n")
        if result.stdout:
            sys.stderr.write("STDOUT:\n" + result.stdout + "\n")
        if result.stderr:
            sys.stderr.write("STDERR:\n" + result.stderr + "\n")
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_hash(root: Path) -> str:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": _file_hash(path)})
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _literal_assignment(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    raise RuntimeError(f"literal assignment {name} not found in {path}")


def _state(venv: Path) -> dict[str, str]:
    python = venv / "bin" / "python"
    locator = _sh(
        [
            str(python),
            "-c",
            (
                "import json; from pathlib import Path; "
                "from product.protocol import PUBLIC_PROTOCOL_VERSION, IMPLEMENTATION_SCHEMA; "
                "import product; "
                "print(json.dumps({'root':str(Path(product.__file__).resolve().parent),"
                "'protocol':PUBLIC_PROTOCOL_VERSION,'implementation_schema':IMPLEMENTATION_SCHEMA},sort_keys=True))"
            ),
        ]
    )
    identity = json.loads(locator.stdout)
    product_root = Path(identity["root"])
    runtime_root = product_root / "runtime"
    ledger_path = product_root / "ledger.py"
    if not runtime_root.is_dir() or not ledger_path.is_file():
        raise RuntimeError(f"installed Product files missing under {product_root}")
    return {
        "protocol": str(identity["protocol"]),
        "implementation_schema": str(identity["implementation_schema"]),
        "runtime_hash": _dir_hash(runtime_root),
        "ledger_hash": _file_hash(ledger_path),
        "ledger_schema": _literal_assignment(ledger_path, "LEDGER_SCHEMA_VERSION"),
    }


def _run_schema_validator(venv: Path, function_name: str, payload: dict[str, Any]) -> bool:
    python = venv / "bin" / "python"
    code = (
        "import json,runpy,sys; from pathlib import Path; import product; "
        "ns=runpy.run_path(str(Path(product.__file__).resolve().parent/'runtime'/'schemas.py')); "
        "f=ns[sys.argv[1]]; print(json.dumps(list(f(json.loads(sys.stdin.read())))))"
    )
    result = _sh([str(python), "-c", code, function_name], input=json.dumps(payload))
    return not json.loads(result.stdout)


def _req_probe(venv: Path, protocol: str, schema: str) -> bool:
    payload = {
        "protocol_version": protocol,
        "implementation_schema": schema,
        "repository": {
            "owner": "James3014",
            "name": "Nexus-new",
            "pr_number": 635,
            "expected_base_sha": "a" * 40,
            "expected_head_sha": "b" * 40,
        },
        "acceptance_contract": {},
        "verification_plan": {},
        "profile_id": "python-oci-pytest-v1",
        "idempotency_key": "tg8-v4",
        "expected_generation": 0,
    }
    return _run_schema_validator(venv, "validate_certification_request", payload)


def _receipt_probe(venv: Path, receipt: dict[str, Any]) -> bool:
    payload = {
        "receipt": receipt,
        "requested_scope": "ENVELOPE_ONLY",
        "original_inputs": None,
    }
    return _run_schema_validator(venv, "validate_receipt_verify_request", payload)


def _tracked_export(src: Path, dst: Path) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    archive = dst.parent / f"{dst.name}.tar"
    try:
        with archive.open("wb") as handle:
            result = subprocess.run(
                ["git", "-C", str(src), "archive", "--format=tar", "HEAD"],
                check=False,
                stdout=handle,
                stderr=subprocess.PIPE,
            )
        if result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                stderr=result.stderr,
            )
        with tarfile.open(archive, "r:") as tf:
            tf.extractall(dst, filter="data")
    finally:
        archive.unlink(missing_ok=True)


def _hostile(src: Path, root: Path, kind: str) -> Path:
    dst = root / ("src-" + kind)
    _tracked_export(src, dst)
    if kind == "protocol":
        path = dst / "product/protocol/__init__.py"
        text = path.read_text(encoding="utf-8")
        old = 'PUBLIC_PROTOCOL_VERSION = "1.0.0-rc.1"'
        assert text.count(old) == 1
        path.write_text(text.replace(old, 'PUBLIC_PROTOCOL_VERSION = "2.0.0-foreign"', 1), encoding="utf-8")
    elif kind == "schema":
        path = dst / "product/protocol/__init__.py"
        text = path.read_text(encoding="utf-8")
        old = 'IMPLEMENTATION_SCHEMA = "nexus.changeset_certification.v2"'
        assert text.count(old) == 1
        path.write_text(text.replace(old, 'IMPLEMENTATION_SCHEMA = "nexus.foreign.v9"', 1), encoding="utf-8")
    elif kind == "ledger":
        path = dst / "product/ledger.py"
        text = path.read_text(encoding="utf-8")
        old = 'LEDGER_SCHEMA_VERSION = "nexus.ledger-entry.v1"'
        assert text.count(old) == 1
        path.write_text(text.replace(old, 'LEDGER_SCHEMA_VERSION = "nexus.ledger-entry.v9"', 1), encoding="utf-8")
    else:
        raise ValueError(kind)
    out = root / ("wheel-" + kind)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=dst,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        sys.stderr.write(f"HOSTILE_BUILD_FAILED:{kind}\n{result.stdout}\n{result.stderr}\n")
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


base.sh = _sh
base.state = _state
base.req_probe = _req_probe
base.receipt_probe = _receipt_probe
base.hostile = _hostile

if __name__ == "__main__":
    raise SystemExit(base.main())
