from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from scripts.bench.eia_roi_wave2 import (
    QUALIFICATION_WITNESSES,
    WAVE2_QUALIFIED,
    WAVE2_REVISE,
    build_qualification_receipt,
    fixture_spec,
    validate_materialization,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def test_wave2_physical_f01_materialization_and_frozen_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    spec = fixture_spec("F01")
    base_sha = str(spec["base_sha"])
    verifier_command = str(spec["verifier_command"])

    assert _git(repo_root, "cat-file", "-t", base_sha) == "commit"

    with tempfile.TemporaryDirectory(prefix="nexus-wave2-f01-") as temporary_root:
        worktree = Path(temporary_root) / "fixture"
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(worktree), base_sha],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            actual_head = _git(worktree, "rev-parse", "HEAD")
            actual_tree = _git(worktree, "rev-parse", "HEAD^{tree}")
            binding = validate_materialization(
                fixture_id="F01",
                actual_head=actual_head,
                actual_tree=actual_tree,
                allowed_paths=spec["allowed_paths"],
                verifier_command=verifier_command,
            )
            assert binding == {"base_sha": base_sha, "base_tree": actual_tree}

            env = os.environ.copy()
            env["PATH"] = f"{repo_root / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
            verifier = subprocess.run(
                shlex.split(verifier_command),
                cwd=worktree,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert verifier.returncode == 0, (
                f"frozen verifier failed at {base_sha}\n"
                f"stdout:\n{verifier.stdout}\n"
                f"stderr:\n{verifier.stderr}"
            )

            witnesses = {
                "exact_base_materialization": f"git:F01:{base_sha}:{actual_tree}",
                "frozen_verifier_readback": f"pytest:F01:{verifier_command}",
                "oracle_ledger_negative_control": (
                    "pytest:test_oracle_quarantine_rejects_leak_and_requires_external_token_set"
                ),
                "pair_identity_mismatch_rejection": (
                    "pytest:test_stage1_pair_requires_exact_same_selected_worker_binding"
                ),
                "observation_roundtrip_not_observed": (
                    "pytest:test_observation_roundtrip_preserves_not_observed_token_provenance"
                ),
                "result_quarantine_rejection": (
                    "pytest:test_result_quarantine_blocks_formal_scoring_until_qualified"
                ),
            }
            assert set(witnesses) == set(QUALIFICATION_WITNESSES)
            receipt = build_qualification_receipt(witnesses)
            assert receipt["gate_passed"] is True
            assert receipt["state"] == WAVE2_QUALIFIED
            assert receipt["formal_scoring_authorized"] is True
        finally:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree)],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "prune"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )


def test_qualification_receipt_rejects_boolean_witness_shortcut() -> None:
    witnesses: dict[str, object] = {name: f"evidence:{name}" for name in QUALIFICATION_WITNESSES}
    witnesses["exact_base_materialization"] = True

    receipt = build_qualification_receipt(witnesses)

    assert receipt["gate_passed"] is False
    assert receipt["state"] == WAVE2_REVISE
    assert receipt["missing_witnesses"] == ["exact_base_materialization"]
    assert receipt["formal_scoring_authorized"] is False
