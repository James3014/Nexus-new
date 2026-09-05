#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import tg8_physical_v4_overlay as base


def _sh(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        input=input,
    )
    if check and result.returncode:
        sys.stderr.write("COMMAND_FAILED: " + " ".join(cmd) + "\n")
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


base.sh = _sh
base.state = _state

if __name__ == "__main__":
    raise SystemExit(base.main())
