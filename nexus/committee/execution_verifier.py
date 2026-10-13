"""Committee verifier that judges each candidate patch by executing it.

Each candidate's unified diff is applied with ``git apply`` to its own copy of the workspace
(``<workspace>/.nexus/committee/<task>/<n>/``) and the request's verify commands run there
through the CLI pre-gate runner. The workspace itself is never modified. The verdict is a plain
pass/fail from the exit codes, so the committee's winner (or abstention) follows from what the
candidates actually do on the fixture instead of from static critics.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess  # nosec B404 - fixed git argv only
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nexus.verifiers.contracts import EvidenceRef, FailureTag, VerifierVerdict

VERIFIER_NAME = "patch_execution"
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".nexus", ".armor", "__pycache__", ".venv", "node_modules"
)


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or ""))[:80] or "task"


@dataclass
class PatchExecutionVerifier:
    workspace_root: Path
    commands: list[str]
    task_id: str
    timeout_sec: int = 30
    results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        self.run_root = self.workspace_root / ".nexus" / "committee" / _safe_segment(self.task_id)

    def evaluate(self, candidate_id: str, patch: str) -> VerifierVerdict:
        from nexus.engine.cli_pregate import run_cli_pregate

        index = len(self.results)
        dest = self.run_root / f"candidate-{index}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.workspace_root, dest, ignore=_COPY_IGNORE)
        patch_text = str(patch or "")
        record: dict[str, Any] = {
            "candidate_id": candidate_id,
            "workspace": str(dest),
            "patch_sha256": hashlib.sha256(patch_text.encode("utf-8")).hexdigest(),
            "apply_status": "",
            "commands": list(self.commands),
            "exit_codes": [],
            # "pass" / "fail": a per-candidate result, deliberately not a ``passed`` flag, so one
            # rejected candidate does not read as a failed committee run.
            "verify_result": "not_run",
        }
        self.results.append(record)
        if not patch_text.strip():
            record["apply_status"] = "empty_patch"
            return self._verdict(
                candidate_id, dest, False, "EMPTY_PATCH", "candidate carries no patch"
            )
        patch_file = dest.parent / f"candidate-{index}.diff"
        patch_file.write_text(
            patch_text if patch_text.endswith("\n") else patch_text + "\n", encoding="utf-8"
        )
        applied = subprocess.run(  # nosec B603 B607 - fixed git argv, patch file we wrote
            ["git", "apply", "--whitespace=nowarn", str(patch_file)],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if applied.returncode != 0:
            record["apply_status"] = "apply_failed"
            record["apply_stderr"] = (applied.stderr or "")[-300:]
            return self._verdict(
                candidate_id, dest, False, "PATCH_APPLY_FAILED", (applied.stderr or "")[-200:]
            )
        record["apply_status"] = "applied"
        all_passed, runs = run_cli_pregate(
            dest, list(self.commands), timeout_per_cmd=self.timeout_sec
        )
        record["exit_codes"] = [run.get("exit_code") for run in runs]
        record["verify_result"] = "pass" if all_passed else "fail"
        if not all_passed:
            tail = next(
                (str(run.get("stderr_tail") or "") for run in runs if not run.get("passed")), ""
            )
            return self._verdict(candidate_id, dest, False, "VERIFY_COMMAND_FAILED", tail[-200:])
        return self._verdict(candidate_id, dest, True, "", "")

    def _verdict(
        self, candidate_id: str, dest: Path, passed: bool, code: str, detail: str
    ) -> VerifierVerdict:
        return VerifierVerdict(
            verifier_name=VERIFIER_NAME,
            candidate_id=candidate_id,
            passed=passed,
            score=1.0 if passed else 0.0,
            evidence_refs=[EvidenceRef(source_file=str(dest), snippet=detail or None)],
            failure_tags=[FailureTag(code=code, description=detail)] if code else [],
        )
