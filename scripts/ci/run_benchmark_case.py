"""Deterministic, provider-free benchmark case runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.fixture_materialization import (
    LocalFixtureSource,
    deterministic_fixture_patch,
    deterministic_fixture_source,
    materialize_local_fixture,
)

MAX_VERIFIER_OUTPUT = 1000


def _digest(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def run_case(case: dict[str, object], root: Path, timeout: int = 30) -> dict[str, object]:
    task_id = str(case.get("task_id", ""))
    verifier = str(case.get("verifier", ""))
    result = {"task_id": task_id, "status": "failed", "passed": False}
    try:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", task_id):
            raise ValueError("path_escape")
        if timeout <= 0:
            raise ValueError("invalid_timeout")
        if verifier != "pytest_hidden":
            raise ValueError("missing_verifier")
        fixture_kind = str(case["fixture_kind"])
        target, visible, hidden = deterministic_fixture_source(fixture_kind)
        if case.get("patch") != "deterministic":
            raise ValueError("patch_failed")
        patch = deterministic_fixture_patch(fixture_kind)
        materialized = materialize_local_fixture(
            root,
            task_id=task_id,
            source=LocalFixtureSource(target, visible, hidden),
        )
        target_path = Path(materialized.target_file)
        visible_path = Path(materialized.visible_test_file)
        hidden_path = Path(materialized.hidden_test_file)
        if not target_path.is_file() or not visible_path.is_file() or not hidden_path.is_file():
            raise ValueError("missing_fixture")
        fixture_sha256 = _digest(target_path.read_bytes(), visible_path.read_bytes())
        verifier_sha256 = _digest(hidden_path.read_bytes())
        target_path.write_text(patch, encoding="utf-8")
        patch_sha256 = _digest(patch.encode("utf-8"))
        result.update(
            fixture_sha256=fixture_sha256,
            verifier_sha256=verifier_sha256,
            patch_sha256=patch_sha256,
        )
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(hidden_path)],
            cwd=materialized.case_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        verifier_output = (proc.stdout + proc.stderr)[-MAX_VERIFIER_OUTPUT:]
        result.update(exit_code=proc.returncode, verifier_output=verifier_output)
        if proc.returncode == 0 and re.search(r"\b\d+ passed\b", proc.stdout):
            result.update(status="passed", passed=True)
        else:
            result["status"] = "verifier_failed"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except KeyError:
        result["status"] = "missing_fixture"
    except (ValueError, OSError) as exc:
        reason = str(exc)
        known = {
            "invalid_timeout",
            "missing_fixture",
            "missing_verifier",
            "patch_failed",
            "path_escape",
        }
        if "unknown deterministic fixture" in reason:
            result["status"] = "missing_fixture"
        else:
            result["status"] = reason if reason in known else "error"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    case_path = Path(args.case)
    case = (
        json.loads(case_path.read_text(encoding="utf-8"))
        if case_path.is_file()
        else json.loads(args.case)
    )
    result = run_case(case, Path(args.root).resolve(), args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
