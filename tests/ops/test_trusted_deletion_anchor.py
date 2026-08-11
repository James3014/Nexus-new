from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from scripts.ops.trusted_deletion_anchor import (
    SCHEMA_VERSION,
    _json,
    build_manifest,
    verify_evidence,
)

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/trusted-deletion-anchor.yml"


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW.read_text())


def _named_step(job_name: str, step_name: str) -> dict[str, object]:
    workflow = _workflow()
    return next(
        step
        for step in workflow["jobs"][job_name]["steps"]  # type: ignore[index]
        if step.get("name") == step_name
    )


def _event() -> dict[str, object]:
    return {
        "event_name": "pull_request_target",
        "workflow_ref": "James3014/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "run_id": 1240,
        "repository": {"full_name": "James3014/Nexus-new", "default_branch": "main"},
        "pull_request": {
            "number": 125,
            "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "James3014/Nexus-new"}},
            "head": {"sha": "c" * 40, "repo": {"full_name": "fork/Nexus-new"}},
        },
    }


def _manifest() -> dict[str, object]:
    return build_manifest(
        _event(),
        raw_diff=b":100644 100644 abcdef1 abcdef2 M\tfile.py\0",
        test_inventory=["tests/ops/test_pr_impact_gate.py"],
        source_archive=b"trusted archive",
        git_bundle=b"git bundle",
    )


def _evidence(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "workflow_identity": manifest["workflow_identity"],
        "run_id": manifest["run_id"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "base_tree": manifest["base_tree"],
        "head_tree": manifest["head_tree"],
        "bundle_sha256": manifest["bundle_sha256"],
        "raw_diff_sha256": manifest["raw_diff_sha256"],
        "test_inventory_sha256": manifest["test_inventory_sha256"],
        "node_ids": manifest["node_ids"],
        "source_archive_sha256": manifest["source_archive_sha256"],
        "git_bundle_sha256": manifest["git_bundle_sha256"],
        "executor": {"exit_code": 0, "selected_tests": manifest["test_inventory"]},
    }


def _verify(manifest: dict[str, object], evidence: dict[str, object], **overrides: object) -> str:
    return verify_evidence(
        manifest,
        evidence,
        source_archive=overrides.get("source_archive", b"trusted archive"),
        raw_diff=overrides.get("raw_diff", b":100644 100644 abcdef1 abcdef2 M\tfile.py\0"),
        test_inventory=overrides.get("test_inventory", ["tests/ops/test_pr_impact_gate.py"]),
        git_bundle=overrides.get("git_bundle", b"git bundle"),
        recomputed_base_tree=overrides.get("base_tree", manifest["base_tree"]),
        recomputed_head_tree=overrides.get("head_tree", manifest["head_tree"]),
    )


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _trusted_origin(
    root: Path, *, script_object: str = "blob", hostile_head: bool = False
) -> tuple[Path, str, str, Path]:
    source = root / "trusted-source"
    origin = root / "origin.git"
    marker = root / "head-code-executed"
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    _run_git(source, "config", "user.email", "test@example.invalid")
    _run_git(source, "config", "user.name", "trusted-source-test")
    workflow_path = source / ".github/workflows/trusted-deletion-anchor.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("name: trusted source fixture\n", encoding="utf-8")
    script_path = source / "scripts/ops/trusted_deletion_anchor.py"
    script_path.parent.mkdir(parents=True)
    if script_object == "tree":
        script_path.mkdir()
        (script_path / "payload.py").write_text("raise SystemExit(99)\n", encoding="utf-8")
    else:
        script_path.write_bytes((ROOT / "scripts/ops/trusted_deletion_anchor.py").read_bytes())
        if script_object == "executable":
            script_path.chmod(0o755)
        elif script_object == "symlink":
            script_path.unlink()
            script_path.symlink_to("hostile-target.py")
    test_path = source / "tests/ops/test_pr_impact_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fixture():\n    assert True\n", encoding="utf-8")
    hostile_path = source / "scripts/ops/$(touch hostile-path-executed)"
    hostile_path.write_text("data only\n", encoding="utf-8")
    _run_git(source, "add", ".")
    _run_git(source, "commit", "-m", "trusted workflow source")
    workflow_sha = _run_git(source, "rev-parse", "HEAD")
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    _run_git(source, "remote", "add", "origin", str(origin))
    _run_git(source, "push", "origin", f"{workflow_sha}:refs/heads/main")
    head_sha = workflow_sha
    if hostile_head and script_object == "blob":
        script_path.write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        _run_git(source, "commit", "-am", "hostile head code")
        head_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "push", "origin", f"{head_sha}:refs/heads/hostile-head")
    return origin, workflow_sha, head_sha, marker


def _git_logging_path(root: Path) -> tuple[str, Path]:
    real_git = shutil.which("git")
    assert real_git
    bin_dir = root / "bin"
    bin_dir.mkdir()
    argv_log = root / "git-argv.bin"
    wrapper = bin_dir / "git"
    wrapper.write_text(
        '#!/bin/sh\nprintf "%s\\0" "$@" >> "$ARGV_LOG"\n'
        'if [ "${GIT_CONFIG_COUNT:-}" = 1 ]; then\n'
        '  test "${GIT_CONFIG_KEY_0:-}" = http.extraheader || exit 96\n'
        '  test "${GIT_CONFIG_VALUE_0:-}" = "Authorization: basic $EXPECTED_BASIC" || exit 97\n'
        '  printf "%s\\n" git-basic-ok >> "$AUTH_LOG"\n'
        "fi\n"
        'exec "$REAL_GIT" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    python_wrapper = bin_dir / "python"
    python_wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "${GIT_CONFIG_COUNT:-}" = 1 ]; then\n'
        '  test "${GIT_CONFIG_KEY_0:-}" = http.extraheader || exit 98\n'
        '  test "${GIT_CONFIG_VALUE_0:-}" = "Authorization: basic $EXPECTED_BASIC" || exit 99\n'
        '  printf "%s\\n" python-basic-ok >> "$AUTH_LOG"\n'
        "fi\n"
        'exec "$REAL_PYTHON" "$@"\n',
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)
    return (
        f"{bin_dir}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        argv_log,
    )


def _acquisition_environment(
    run_root: Path, workflow_sha: str, head_sha: str, *, token: str = "token-must-not-be-argv"
) -> dict[str, str]:
    event = _event()
    event["workflow_sha"] = workflow_sha
    event["pull_request"]["base"]["sha"] = workflow_sha  # type: ignore[index]
    event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
    path, argv_log = _git_logging_path(run_root)
    token_bytes = f"x-access-token:{token}".encode()
    encoded = base64.b64encode(token_bytes).decode()
    return {
        **os.environ,
        "ARGV_LOG": str(argv_log),
        "REAL_GIT": shutil.which("git") or "git",
        "REAL_PYTHON": sys.executable,
        "PATH": path,
        "RUNNER_TEMP": str(run_root),
        "EVENT_JSON": json.dumps(event),
        "EVENT_NAME": "pull_request_target",
        "WORKFLOW_REF": event["workflow_ref"],
        "WORKFLOW_SHA": workflow_sha,
        "RUN_ID": str(event["run_id"]),
        "REPOSITORY": event["repository"]["full_name"],
        "DEFAULT_BRANCH": event["repository"]["default_branch"],
        "TRUSTED_TOKEN": token,
        "EXPECTED_BASIC": encoded,
        "AUTH_LOG": str(run_root / "auth.log"),
    }


def _local_acquisition_run(job_name: str, origin: Path) -> str:
    step_name = (
        "Acquire and execute exact trusted controller source"
        if job_name == "trusted-controller"
        else "Acquire exact trusted verifier source"
    )
    run = _named_step(job_name, step_name)["run"]
    return run.replace('"https://github.com/$REPOSITORY.git"', shlex.quote(str(origin)))


def _job_block(text: str, job_name: str, next_job_name: str) -> str:
    start = text.index(f"  {job_name}:\n")
    end = text.index(f"  {next_job_name}:\n", start)
    return text[start:end]


def test_valid_fixed_schema_evidence_is_accepted():
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest)) == "PASS"


def test_supplied_trees_cannot_override_immutable_commit_trees():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), base_tree="e" * 40, head_tree="f" * 40)
        == "IMPACT_UNKNOWN"
    )


@pytest.mark.parametrize("status", ["SKIPPED", "NEUTRAL", "CANCELLED", "MISSING"])
def test_non_complete_status_fails_closed(status: str):
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["status"] = status
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_tampered_artifact_and_head_drift_fail_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["bundle_sha256"] = hashlib.sha256(b"replayed").hexdigest()
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["head_sha"] = "d" * 40
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_malformed_or_token_bearing_evidence_fails_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence.pop("workflow_identity")
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["token"] = "ghs_secret"
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_fork_identity_must_be_bound_to_the_event():
    event = _event()
    event["pull_request"]["head"]["sha"] = "not-a-sha"  # type: ignore[index]
    with pytest.raises(ValueError, match="exact SHA"):
        build_manifest(event, raw_diff=b"", test_inventory=[], source_archive=b"")


def test_workflow_substitution_fails_closed():
    event = _event()
    event["workflow_ref"] = (
        "fork/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main"
    )
    with pytest.raises(ValueError, match="workflow identity"):
        build_manifest(
            event,
            raw_diff=b"",
            test_inventory=["tests/ops/test_pr_impact_gate.py"],
            source_archive=b"",
        )


def test_recomputed_artifact_digest_rejects_replay():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), source_archive=b"replayed archive")
        == "IMPACT_UNKNOWN"
    )


def test_controller_executor_verifier_path_has_cloneable_bundle_and_external_anchor():
    with TemporaryDirectory(prefix="trusted-anchor-e2e-") as directory:
        root = Path(directory)
        origin = root / "origin.git"
        checkout = root / "checkout"
        controller_repo = root / "controller.git"
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(
            ["git", "clone", str(origin), str(checkout)], check=True, capture_output=True
        )
        _run_git(checkout, "config", "user.email", "test@example.invalid")
        _run_git(checkout, "config", "user.name", "trusted-anchor-test")
        test_path = checkout / "tests/ops/test_pr_impact_gate.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("def test_anchor_path():\n    assert True\n", encoding="utf-8")
        _run_git(checkout, "add", "tests/ops/test_pr_impact_gate.py")
        _run_git(checkout, "commit", "-m", "base")
        base_sha = _run_git(checkout, "rev-parse", "HEAD")
        test_path.write_text("def test_anchor_path():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        _run_git(checkout, "commit", "-am", "head")
        head_sha = _run_git(checkout, "rev-parse", "HEAD")
        _run_git(checkout, "push", "origin", "HEAD:main")
        subprocess.run(
            ["git", "init", "--bare", str(controller_repo)], check=True, capture_output=True
        )
        _run_git(controller_repo, "remote", "add", "origin", str(origin))
        _run_git(controller_repo, "fetch", "--no-tags", "--depth=1", "origin", base_sha)
        event = _event()
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(controller_repo),
                "--output-dir",
                str(bundle),
            ],
            check=True,
        )
        manifest = json.loads((bundle / "manifest.json").read_text())
        anchor = json.loads((bundle / "external-anchor.json").read_text())
        assert (bundle / "git-objects.bundle").stat().st_size > 0
        assert (
            anchor["manifest_sha256"]
            == hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
        )
        clone = root / "bundle-clone.git"
        subprocess.run(["git", "init", "--bare", str(clone)], check=True, capture_output=True)
        for ref, revision in (
            ("refs/trusted-anchor/base", base_sha),
            ("refs/trusted-anchor/head", head_sha),
        ):
            _run_git(clone, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(clone, "rev-parse", f"{ref}^{{commit}}") == revision
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "executor",
                "--bundle-dir",
                str(bundle),
            ],
            check=True,
        )
        expected = [
            "--expected-workflow-ref",
            event["workflow_ref"],
            "--expected-workflow-sha",
            event["workflow_sha"],
            "--expected-run-id",
            str(event["run_id"]),
            "--verify-evidence",
            str(bundle / "raw-evidence.json"),
            "--expected-manifest-sha256",
            anchor["manifest_sha256"],
            "--expected-external-anchor-sha256",
            hashlib.sha256((bundle / "external-anchor.json").read_bytes()).hexdigest(),
            "--expected-event-name",
            event["event_name"],
            "--expected-repository",
            event["repository"]["full_name"],
            "--expected-default-branch",
            event["repository"]["default_branch"],
            "--expected-pull-request-number",
            str(event["pull_request"]["number"]),
            "--expected-base-sha",
            base_sha,
            "--expected-head-sha",
            head_sha,
        ]
        verified = subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "verifier",
                "--bundle-dir",
                str(bundle),
                *expected,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert '"status": "PASS"' in verified.stdout
        evidence_path = bundle / "raw-evidence.json"
        original_evidence = evidence_path.read_bytes()
        head_tree_tamper = json.loads(original_evidence)
        head_tree_tamper["head_tree"] = "0" * 40 if manifest["head_tree"] != "0" * 40 else "1" * 40
        evidence_path.write_bytes(_json(head_tree_tamper) + b"\n")
        head_tree_rejected = subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "verifier",
                "--bundle-dir",
                str(bundle),
                *expected,
            ],
            capture_output=True,
        )
        assert head_tree_rejected.returncode != 0
        evidence_path.write_bytes(original_evidence)
        tampered = dict(manifest)
        tampered["head_sha"] = "d" * 40
        (bundle / "manifest.json").write_bytes(_json(tampered) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    "scripts/ops/trusted_deletion_anchor.py",
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
            ).returncode
            != 0
        )


def test_controller_repairs_shallow_merge_head_for_full_history_bundle():
    with TemporaryDirectory(prefix="trusted-anchor-shallow-merge-") as directory:
        root = Path(directory)
        source = root / "source"
        origin = root / "origin.git"
        controller_repo = root / "controller.git"
        verifier_repo = root / "verifier.git"
        subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
        _run_git(source, "config", "user.email", "test@example.invalid")
        _run_git(source, "config", "user.name", "trusted-anchor-shallow-test")
        test_path = source / "tests/ops/test_pr_impact_gate.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("def test_anchor_path():\n    assert True\n", encoding="utf-8")
        _run_git(source, "add", "tests/ops/test_pr_impact_gate.py")
        _run_git(source, "commit", "-m", "base")
        base_sha = _run_git(source, "rev-parse", "HEAD")
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        _run_git(source, "remote", "add", "origin", str(origin))
        _run_git(source, "push", "origin", f"{base_sha}:refs/heads/main")

        _run_git(source, "switch", "-c", "feature")
        (source / "feature.txt").write_text("feature\n", encoding="utf-8")
        _run_git(source, "add", "feature.txt")
        _run_git(source, "commit", "-m", "feature")
        feature_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "switch", "main")
        _run_git(source, "merge", "--no-ff", feature_sha, "-m", "merge head")
        head_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "push", "origin", f"{head_sha}:refs/heads/merge-head")

        subprocess.run(
            ["git", "init", "--bare", str(controller_repo)], check=True, capture_output=True
        )
        _run_git(controller_repo, "remote", "add", "origin", str(origin))
        subprocess.run(
            [
                "git",
                "-C",
                str(controller_repo),
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                base_sha,
            ],
            check=True,
            capture_output=True,
        )
        assert _run_git(controller_repo, "rev-parse", "--is-shallow-repository") == "true"
        missing_merge_parent = subprocess.run(
            [
                "git",
                "-C",
                str(controller_repo),
                "cat-file",
                "-e",
                f"{feature_sha}^{{commit}}",
            ],
            capture_output=True,
        )
        assert missing_merge_parent.returncode != 0

        event = _event()
        event["workflow_sha"] = base_sha
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(controller_repo),
                "--output-dir",
                str(bundle),
            ],
            check=True,
        )
        assert _run_git(controller_repo, "rev-parse", "--is-shallow-repository") == "false"
        assert _run_git(controller_repo, "cat-file", "-e", f"{base_sha}^{{commit}}") == ""
        assert _run_git(controller_repo, "cat-file", "-e", f"{head_sha}^{{commit}}") == ""
        subprocess.run(
            ["git", "init", "--bare", str(verifier_repo)], check=True, capture_output=True
        )
        for ref, revision in (
            ("refs/trusted-anchor/base", base_sha),
            ("refs/trusted-anchor/head", head_sha),
        ):
            _run_git(verifier_repo, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(verifier_repo, "rev-parse", f"{ref}^{{commit}}") == revision
            assert _run_git(verifier_repo, "rev-parse", f"{ref}^{{tree}}") == _run_git(
                controller_repo, "rev-parse", f"{revision}^{{tree}}"
            )
        head_with_parents = next(
            line
            for line in _run_git(
                verifier_repo, "rev-list", "--parents", "refs/trusted-anchor/head"
            ).splitlines()
            if line.startswith(head_sha)
        ).split()
        assert head_with_parents[0] == head_sha
        assert set(head_with_parents[1:]) == {base_sha, feature_sha}
        _run_git(verifier_repo, "merge-base", "--is-ancestor", base_sha, head_sha)


def test_workflow_is_three_job_isolated_anchor():
    workflow = _workflow()
    trigger = workflow.get("on", workflow.get(True))
    assert "pull_request_target" in trigger
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {
        "trusted-controller",
        "unprivileged-executor",
        "trusted-verifier",
    }
    assert workflow["jobs"]["unprivileged-executor"]["permissions"] == {}
    assert workflow["jobs"]["trusted-controller"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["trusted-controller"]["timeout-minutes"] == 10
    assert "timeout-minutes" not in workflow["jobs"]["unprivileged-executor"]
    assert workflow["jobs"]["trusted-verifier"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            assert "actions/checkout@" not in step.get("uses", "")
            if step.get("uses", "").startswith((
                "actions/upload-artifact@",
                "actions/download-artifact@",
            )):
                pin = step["uses"].split("@", 1)[1].split()[0]
                assert re.fullmatch(r"[0-9a-f]{40}", pin)
    assert "--verify-evidence" in next(
        step["run"]
        for step in workflow["jobs"]["trusted-verifier"]["steps"]
        if step.get("name") == "Verify fixed schema and recomputed digests"
    )


def test_executor_workflow_block_is_byte_equivalent_to_setup_baseline():
    baseline = subprocess.run(
        [
            "git",
            "show",
            "49c1495d2bc131831d388acb77f098f02c3feb64:.github/workflows/trusted-deletion-anchor.yml",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert _job_block(
        WORKFLOW.read_text(), "unprivileged-executor", "trusted-verifier"
    ) == _job_block(baseline, "unprivileged-executor", "trusted-verifier")


def test_trusted_jobs_use_bare_exact_sha_and_allowlisted_regular_blob():
    text = WORKFLOW.read_text()
    assert "git init --bare" in text
    assert 'fetch --no-tags --depth=1 origin "$WORKFLOW_SHA"' in text
    assert 'rev-parse "$WORKFLOW_SHA^{commit}"' in text
    assert 'cat-file commit "$WORKFLOW_SHA"' in text
    assert 'ls-tree "$WORKFLOW_SHA"' in text
    assert "100644 blob" in text
    assert 'cat-file blob "$WORKFLOW_SHA:$script_path"' in text
    assert "trusted-source.receipt" in text
    assert "sha256=" in text
    assert '--repo-root "$bare_repo"' in text
    assert "actions/checkout" not in text
    assert "git checkout" not in text
    assert "git worktree" not in text
    assert "git submodule" not in text


def test_trusted_source_identity_and_token_isolation_are_fail_closed():
    workflow = _workflow()
    text = WORKFLOW.read_text().lower()
    assert "https://github.com/$repository.git" in text
    assert "git_config_key_0=http.extraheader" in text
    assert 'git_config_value_0="authorization: basic $basic_auth"' in text
    assert text.count("printf 'x-access-token:%s' \"$trusted_token\" | base64 | tr -d '\\n'") == 2
    assert 'test -n "$basic_auth"' in text
    assert "tr -cd '\\n'" in text
    assert "authorization: bearer" not in text
    assert "persist-credentials" not in text
    assert "credential.helper" not in text
    assert "github.token" in text
    assert "permissions: {}" in text
    assert not re.search(r"\bgit\b[^\n]*\s-c\s[^\n]*\$trusted_token", text)
    assert not re.search(r"\bgit\b[^\n]*(?:authorization|token)[^\n]*\$trusted_token", text)
    assert "env git" not in text
    assert "env python" not in text
    for job_name in ("trusted-controller", "trusted-verifier"):
        steps = workflow["jobs"][job_name]["steps"]
        cleanup = [step for step in steps if step.get("if") == "always()"]
        assert cleanup and steps[-1] is cleanup[-1]
        cleanup_lines = [line.strip() for line in cleanup[-1]["run"].splitlines()]
        remove_index = next(
            index for index, line in enumerate(cleanup_lines) if line.startswith("rm -rf")
        )
        prove_indexes = [
            index for index, line in enumerate(cleanup_lines) if line.startswith("test ! -e")
        ]
        assert prove_indexes and remove_index < min(prove_indexes)
        acquisition = steps[0]["run"]
        assert "trap cleanup_on_exit EXIT" in acquisition
        assert "trap 'exit 130' INT" in acquisition
        assert "trap 'exit 143' TERM" in acquisition
    executor = str(workflow["jobs"]["unprivileged-executor"]).lower()
    assert "secrets" not in executor
    assert "cache" not in executor
    assert "token" not in executor


@pytest.mark.parametrize("job_name", ["trusted-controller", "trusted-verifier"])
def test_cleanup_shell_deletes_lock_and_credential_residue_before_proving_absence(
    job_name: str, tmp_path: Path
):
    prefix = "trusted-controller" if job_name == "trusted-controller" else "trusted-verifier"
    bare_repo = tmp_path / f"{prefix}.git"
    trusted_dir = tmp_path / f"{prefix}-source"
    bare_repo.mkdir()
    trusted_dir.mkdir()
    (bare_repo / "config.lock").write_text("stale lock\n")
    (bare_repo / "config").write_text("http.extraheader=Authorization: bearer secret\n")
    (trusted_dir / "token-file").write_text("ghs_secret\n")
    cleanup = _named_step(
        job_name,
        f"Cleanup trusted {'controller' if job_name == 'trusted-controller' else 'verifier'} source",
    )
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", cleanup["run"]],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not bare_repo.exists()
    assert not trusted_dir.exists()


@pytest.mark.parametrize("job_name", ["trusted-controller", "trusted-verifier"])
def test_no_checkout_acquisition_shell_executes_only_exact_trusted_blob(
    job_name: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, marker = _trusted_origin(tmp_path, hostile_head=True)
    run_root = tmp_path / f"run-{job_name}"
    run_root.mkdir()
    token = "token-must-not-be-argv"
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _local_acquisition_run(job_name, origin)],
        env=_acquisition_environment(run_root, workflow_sha, head_sha, token=token),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert encoded not in completed.stdout
    assert encoded not in completed.stderr
    argv = (run_root / "git-argv.bin").read_bytes()
    assert token.encode() not in argv
    assert encoded.encode() not in argv
    auth_log = (run_root / "auth.log").read_text()
    assert token not in auth_log
    assert encoded not in auth_log
    assert "git-basic-ok" in auth_log.splitlines()
    if job_name == "trusted-controller":
        assert "python-basic-ok" in auth_log.splitlines()
    else:
        assert "python-basic-ok" not in auth_log.splitlines()
    assert not marker.exists()
    assert not (run_root / "hostile-path-executed").exists()
    prefix = "trusted-controller" if job_name == "trusted-controller" else "trusted-verifier"
    receipt = (run_root / f"{prefix}-source/trusted-source.receipt").read_text()
    assert f"commit={workflow_sha}" in receipt
    assert "path=scripts/ops/trusted_deletion_anchor.py" in receipt
    assert re.search(r"(?m)^blob=[0-9a-f]{40}$", receipt)
    assert re.search(r"(?m)^sha256=[0-9a-f]{64}$", receipt)
    assert token not in receipt
    assert encoded not in receipt
    config = (run_root / f"{prefix}.git/config").read_text()
    assert token not in config
    assert encoded not in config
    if job_name == "trusted-controller":
        assert (run_root / "trusted-anchor/manifest.json").is_file()


@pytest.mark.parametrize("script_object", ["executable", "symlink", "tree"])
def test_acquisition_shell_rejects_non_regular_or_wrong_mode_source(
    script_object: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, _ = _trusted_origin(tmp_path, script_object=script_object)
    run_root = tmp_path / "run"
    run_root.mkdir()
    completed = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _local_acquisition_run("trusted-verifier", origin),
        ],
        env=_acquisition_environment(run_root, workflow_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


def test_acquisition_shell_rejects_wrong_workflow_sha_and_cleans_up(tmp_path: Path):
    origin, _, head_sha, _ = _trusted_origin(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    wrong_sha = "f" * 40
    completed = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _local_acquisition_run("trusted-verifier", origin),
        ],
        env=_acquisition_environment(run_root, wrong_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


@pytest.mark.parametrize("interruption", ["false", "kill -TERM $$"])
def test_acquisition_trap_removes_config_lock_on_failure_or_signal(
    interruption: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, _ = _trusted_origin(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    run = _local_acquisition_run("trusted-verifier", origin)
    remote_line = f'git -C "$bare_repo" remote add origin {shlex.quote(str(origin))}'
    run = run.replace(
        remote_line,
        f'{remote_line}\ntouch "$bare_repo/config.lock"\n{interruption}',
    )
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env=_acquisition_environment(run_root, workflow_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


def test_trusted_jobs_never_execute_head_code_or_materialize_a_worktree():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    for job_name in ("trusted-controller", "trusted-verifier"):
        serialized = str(workflow["jobs"][job_name]).lower()
        assert "github.event.pull_request.head" in serialized or job_name == "trusted-controller"
        assert "checkout" not in serialized
        assert "worktree" not in serialized
        assert "submodule" not in serialized
        assert "source.tar" not in serialized or job_name == "trusted-controller"
