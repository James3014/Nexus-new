from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

import scripts.ops.trusted_deletion_anchor as trusted_anchor
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
    runtime_identity = {
        "schema_version": trusted_anchor.RUNTIME_SCHEMA_VERSION,
        "runtime_probe": trusted_anchor._runtime_probe(),
        "builder": {"uv_version": trusted_anchor.UV_VERSION},
        "pyproject_sha256": hashlib.sha256(b"").hexdigest(),
        "uv_lock_sha256": hashlib.sha256(b"").hexdigest(),
        "requirements_sha256": hashlib.sha256(b"").hexdigest(),
        "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
    }
    runtime_metadata = _json(runtime_identity) + b"\n"
    return build_manifest(
        _event(),
        raw_diff=b":100644 100644 abcdef1 abcdef2 M\tfile.py\0",
        test_inventory=["tests/ops/test_pr_impact_gate.py"],
        source_archive=b"trusted archive",
        git_bundle=b"git bundle",
        runtime_metadata=runtime_metadata,
        runtime_identity=runtime_identity,
    )


def _evidence(manifest: dict[str, object]) -> dict[str, object]:
    golden_report = {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": manifest["head_sha"],
        "source_tree": manifest["head_tree"],
        "root_binding_mode": "explicit_sha_bound",
        "trusted_evaluator_sha256": manifest["golden_evaluator_sha256"],
        "evaluator_identity": manifest["golden_evaluator_sha256"],
        "corpus_identity": manifest["golden_corpus_sha256"],
        "test_corpus_identity": manifest["golden_test_corpus_sha256"],
        "topology_identity": manifest["golden_topology_sha256"],
        "workspace_dirty": False,
        "validation_errors": [],
        "collection_exit_code": 0,
        "pytest_exit_code": 0,
        "case_count": 1,
        "selected_case_count": 1,
        "case_evidence": [
            {
                "case_id": "GB-TEST",
                "status": "covered",
                "witnesses": [
                    {
                        "collection_status": "collected",
                        "execution_status": "passed",
                    }
                ],
            }
        ],
    }
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "workflow_identity": manifest["workflow_identity"],
        "run_id": manifest["run_id"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "base_tree": manifest["base_tree"],
        "head_tree": manifest["head_tree"],
        "test_tree": manifest["test_tree"],
        "bundle_sha256": manifest["bundle_sha256"],
        "raw_diff_sha256": manifest["raw_diff_sha256"],
        "test_inventory_sha256": manifest["test_inventory_sha256"],
        "node_ids": manifest["node_ids"],
        "source_archive_sha256": manifest["source_archive_sha256"],
        "git_bundle_sha256": manifest["git_bundle_sha256"],
        "golden_evaluator_sha256": manifest["golden_evaluator_sha256"],
        "golden_corpus_sha256": manifest["golden_corpus_sha256"],
        "golden_test_corpus_sha256": manifest["golden_test_corpus_sha256"],
        "golden_topology_sha256": manifest["golden_topology_sha256"],
        "golden_report": golden_report,
        "golden_report_sha256": trusted_anchor._sha(trusted_anchor._json(golden_report)),
        "executor": {
            "exit_code": 0,
            "selected_tests": manifest["test_inventory"],
            "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
            "runtime_probe": manifest["runtime_identity"].get("runtime_probe"),
        },
    }
    for key in (
        "pyproject_sha256",
        "uv_lock_sha256",
        "requirements_sha256",
        "runtime_archive_sha256",
        "runtime_metadata_sha256",
        "runtime_identity",
    ):
        evidence[key] = manifest[key]
    return evidence


def _verify(manifest: dict[str, object], evidence: dict[str, object], **overrides: object) -> str:
    return verify_evidence(
        manifest,
        evidence,
        source_archive=overrides.get("source_archive", b"trusted archive"),
        raw_diff=overrides.get("raw_diff", b":100644 100644 abcdef1 abcdef2 M\tfile.py\0"),
        test_inventory=overrides.get("test_inventory", ["tests/ops/test_pr_impact_gate.py"]),
        git_bundle=overrides.get("git_bundle", b"git bundle"),
        requirements=overrides.get("requirements", b""),
        runtime_archive=overrides.get("runtime_archive", b""),
        runtime_metadata=overrides.get(
            "runtime_metadata", _json(manifest["runtime_identity"]) + b"\n"
        ),
        golden_evaluator=overrides.get("golden_evaluator", b""),
        recomputed_pyproject=overrides.get("pyproject", b""),
        recomputed_uv_lock=overrides.get("uv_lock", b""),
        recomputed_base_tree=overrides.get("base_tree", manifest["base_tree"]),
        recomputed_head_tree=overrides.get("head_tree", manifest["head_tree"]),
        recomputed_test_tree=overrides.get("test_tree", manifest["test_tree"]),
    )


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _synthetic_runtime(
    root: Path,
    *,
    pyproject: bytes = b"",
    uv_lock: bytes = b"",
    probe: dict[str, str] | None = None,
    behavioral_pytest: bool = False,
) -> Path:
    runtime_dir = root / "runtime-artifact"
    runtime_dir.mkdir()
    requirements = b"synthetic locked runtime\n"
    test_driver = (
        (
            b"import json,os,sys\n"
            b"from pathlib import Path\n"
            b"args=sys.argv[1:]\n"
            b"if '--collect-only' in args:\n"
            b"  for token in args:\n"
            b"    if '::' in token:\n"
            b"      print(token)\n"
            b"  raise SystemExit\n"
            b"junit=None\n"
            b"for token in args:\n"
            b"  if token.startswith('--junitxml='):\n"
            b"    junit=token.split('=',1)[1]\n"
            b"if junit:\n"
            b"  import xml.etree.ElementTree as ET\n"
            b"  suite=ET.Element('testsuite',{'tests':str(sum(1 for t in args if '::' in t))})\n"
            b"  for token in args:\n"
            b"    if '::' not in token:\n"
            b"      continue\n"
            b"    path,*parts=token.split('::')\n"
            b"    module=path.removesuffix('.py').replace('/','.')\n"
            b"    if len(parts)>1:\n"
            b"      module=module+'.'+'.'.join(parts[:-1])\n"
            b"    name=parts[-1]\n"
            b"    ET.SubElement(suite,'testcase',{'classname':module,'name':name,'time':'0.0'})\n"
            b"  ET.ElementTree(suite).write(junit,encoding='utf-8',xml_declaration=True)\n"
            b"  raise SystemExit\n"
            b"raise SystemExit\n"
        )
        if behavioral_pytest
        else (
            b"import json,sys\n"
            b"import os\n"
            b"from pathlib import Path\n"
            b"Path('.selected-tests.json').write_text(json.dumps(sys.argv[1:]))\n"
            b"Path('.executor-env.json').write_text(json.dumps(sorted(os.environ)))\n"
        )
    )
    files = {
        "site-packages/pytest/__init__.py": b"",
        "site-packages/pytest/__main__.py": test_driver,
        "site-packages/pytest-9.dist-info/METADATA": (
            b"Metadata-Version: 2.1\nName: pytest\nVersion: 9.0.0\n"
        ),
        "site-packages/pytest_asyncio.py": b"",
        "site-packages/pytest_timeout.py": b"",
    }
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, BytesIO(data))
    metadata = {
        "schema_version": trusted_anchor.RUNTIME_SCHEMA_VERSION,
        "runtime_probe": probe or trusted_anchor._runtime_probe(),
        "builder": {"uv_version": trusted_anchor.UV_VERSION},
        "pyproject_sha256": hashlib.sha256(pyproject).hexdigest(),
        "uv_lock_sha256": hashlib.sha256(uv_lock).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
        "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
    }
    (runtime_dir / "runtime.tar").write_bytes(stream.getvalue())
    (runtime_dir / "runtime-metadata.json").write_bytes(_json(metadata) + b"\n")
    (runtime_dir / "requirements.txt").write_bytes(requirements)
    return runtime_dir


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
    golden_script_path = source / "scripts/ops/trusted_golden_verifier.py"
    golden_script_path.write_bytes((ROOT / "scripts/ops/trusted_golden_verifier.py").read_bytes())
    evaluator_path = source / trusted_anchor.GOLDEN_EVALUATOR_PATH
    evaluator_path.parent.mkdir(parents=True, exist_ok=True)
    evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
    golden_dir = source / "tests/golden_behavior"
    golden_dir.mkdir(parents=True, exist_ok=True)
    for name in ("corpus.py", "test_corpus.py"):
        (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
    test_path = source / "tests/ops/test_pr_impact_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fixture():\n    assert True\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (source / "uv.lock").write_text("version = 1\nrevision = 3\n")
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
    _synthetic_runtime(
        run_root,
        pyproject=b"[project]\nname='fixture'\nversion='0'\n",
        uv_lock=b"version = 1\nrevision = 3\n",
    )
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
    run = run.replace('"https://github.com/$REPOSITORY.git"', shlex.quote(str(origin)))
    return run.replace(
        'python "$trusted_script" runtime-builder --repo-root "$bare_repo" --workflow-sha "$WORKFLOW_SHA" --uv-executable "$(command -v uv)" --output-dir "$runtime_dir"',
        'cp -R "$RUNNER_TEMP/runtime-artifact" "$runtime_dir"',
    )


def _job_block(text: str, job_name: str, next_job_name: str) -> str:
    start = text.index(f"  {job_name}:\n")
    end = text.index(f"  {next_job_name}:\n", start)
    return text[start:end]


def test_valid_fixed_schema_evidence_is_accepted():
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest)) == "PASS"


@pytest.mark.parametrize(
    "witnesses",
    [
        ["not-a-mapping"],
        [{"collection_status": "collected", "execution_status": "skipped"}],
        [{"collection_status": "collected", "execution_status": "not_executed"}],
    ],
)
def test_malformed_or_nonexecuted_covered_witness_fails_closed(witnesses: list[object]):
    manifest = _manifest()
    evidence = _evidence(manifest)
    report = evidence["golden_report"]
    assert isinstance(report, dict)
    report["case_evidence"][0]["witnesses"] = witnesses
    evidence["golden_report_sha256"] = trusted_anchor._sha(trusted_anchor._json(report))
    assert _verify(manifest, evidence) == "IMPACT_UNKNOWN"


def test_finding_witness_cannot_claim_skipped_execution():
    manifest = _manifest()
    evidence = _evidence(manifest)
    report = evidence["golden_report"]
    assert isinstance(report, dict)
    report["case_evidence"][0]["status"] = "finding"
    report["case_evidence"][0]["witnesses"][0]["execution_status"] = "skipped"
    evidence["golden_report_sha256"] = trusted_anchor._sha(trusted_anchor._json(report))
    assert _verify(manifest, evidence) == "IMPACT_UNKNOWN"


def test_supplied_trees_cannot_override_immutable_commit_trees():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), base_tree="e" * 40, head_tree="f" * 40)
        == "IMPACT_UNKNOWN"
    )


def test_controller_rejects_missing_exact_tree_before_deriving_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_event()), encoding="utf-8")
    derived_operations: list[str] = []

    def fake_git(repo: Path, *args: str, binary: bool = False) -> str:
        del repo, binary
        if args[:3] == ("fetch", "--no-tags", "--unshallow"):
            return ""
        if args == ("rev-parse", "--is-shallow-repository"):
            return "false"
        if args[0] == "cat-file" and args[-1].endswith("^{commit}"):
            return ""
        if args[0] == "rev-parse" and args[-1].endswith("^{tree}"):
            return "d" * 40
        if args[0] == "cat-file" and args[-1] == f"{'d' * 40}^{{tree}}":
            raise ValueError("missing exact tree")
        if args[0] in {"diff", "archive"}:
            derived_operations.append(args[0])
        raise AssertionError(f"unexpected git invocation: {args!r}")

    monkeypatch.setattr(trusted_anchor, "_git", fake_git)
    with pytest.raises(ValueError, match="missing exact tree"):
        trusted_anchor._controller(
            argparse.Namespace(
                event_json=str(event_path),
                repo_root=str(tmp_path / "repo.git"),
                output_dir=str(tmp_path / "bundle"),
            )
        )
    assert derived_operations == []


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


def test_non_git_isolated_python_reproduces_missing_pytest(tmp_path: Path):
    source = tmp_path / "extracted-source"
    source.mkdir()
    (source / "test_sample.py").write_text("def test_sample():\n    assert True\n")
    non_git_cwd = tmp_path / "non-git-cwd"
    non_git_cwd.mkdir()
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-m", "pytest", str(source / "test_sample.py")],
        cwd=non_git_cwd,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "No module named pytest" in completed.stderr


def test_extracted_source_without_bootstrap_reproduces_missing_git_head(tmp_path: Path):
    source = tmp_path / "extracted-source"
    source.mkdir()
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True
    )
    assert completed.returncode == 128
    assert "not a git repository" in completed.stderr


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("requirements", b"tampered requirements"),
        ("runtime_archive", b"tampered runtime"),
        ("runtime_metadata", b'{"tampered":true}'),
        ("pyproject", b"tampered project"),
        ("uv_lock", b"tampered lock"),
    ],
)
def test_runtime_or_dependency_contract_tamper_fails_closed(override: str, value: bytes):
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest), **{override: value}) == "IMPACT_UNKNOWN"


def test_verifier_does_not_substitute_its_runner_runtime_for_executor_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    manifest = _manifest()
    evidence = _evidence(manifest)
    monkeypatch.setattr(trusted_anchor, "_runtime_probe", lambda: {"different": "verifier"})
    assert _verify(manifest, evidence) == "PASS"


def test_runtime_builder_uses_frozen_hash_bound_binary_only_contract(tmp_path: Path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "runtime-builder-test")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (repo / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "runtime contract")
    workflow_sha = _run_git(repo, "rev-parse", "HEAD")
    fake_uv = tmp_path / "uv"
    log = tmp_path / "uv.log"
    fake_uv.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:]\n"
        f"with Path({str(log)!r}).open('a') as f: f.write(json.dumps(args)+'\\n')\n"
        "if args == ['--version']:\n print('uv 0.9.2'); raise SystemExit\n"
        "if args[0] == 'export':\n"
        " Path(args[args.index('--output-file')+1]).write_text('pytest==9 --hash=sha256:abc\\n'); raise SystemExit\n"
        "if args[:2] == ['pip','install']:\n"
        " target=Path(args[args.index('--target')+1]); (target/'pytest').mkdir(parents=True)\n"
        " (target/'pytest/__init__.py').write_text(''); (target/'pytest/__main__.py').write_text('')\n"
        " (target/'pytest_asyncio.py').write_text(''); (target/'pytest_timeout.py').write_text('')\n"
        " raise SystemExit\n"
        "raise SystemExit(2)\n"
    )
    fake_uv.chmod(0o755)
    output = tmp_path / "built-runtime"
    trusted_anchor._build_runtime(
        argparse.Namespace(
            repo_root=str(repo),
            workflow_sha=workflow_sha,
            uv_executable=str(fake_uv),
            output_dir=str(output),
        )
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    export = next(call for call in calls if call and call[0] == "export")
    install = next(call for call in calls if call[:2] == ["pip", "install"])
    assert {
        "--frozen",
        "--no-default-groups",
        "--group",
        "dev",
        "--no-emit-project",
        "--no-emit-workspace",
        "--no-emit-local",
    } <= set(export)
    assert {"--require-hashes", "--only-binary", "--no-cache", "--no-python-downloads"} <= set(
        install
    )
    assert all((output / name).is_file() for name in trusted_anchor.RUNTIME_FILENAMES)


def test_controller_executor_verifier_path_from_non_repository_cwd():
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
        (checkout / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
        (checkout / "uv.lock").write_text("version = 1\nrevision = 3\n")
        evaluator_path = checkout / trusted_anchor.GOLDEN_EVALUATOR_PATH
        evaluator_path.parent.mkdir(parents=True, exist_ok=True)
        evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
        golden_dir = checkout / "tests/golden_behavior"
        golden_dir.mkdir(parents=True, exist_ok=True)
        for name in ("corpus.py", "test_corpus.py"):
            (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
        from tests.golden_behavior.corpus import CASES

        authority_paths: set[str] = set()
        witness_paths: set[str] = set()
        for case in CASES:
            for source in case.authority_sources:
                if not source.startswith("http"):
                    authority_paths.add(source.split("#", 1)[0].split(":", 1)[0])
            for nodeid in case.automated_tests:
                witness_paths.add(nodeid.split("::", 1)[0])
        for relative in sorted(authority_paths | witness_paths):
            source_file = ROOT / relative
            if not source_file.is_file():
                continue
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_file.read_bytes())
        _run_git(checkout, "add", ".")
        _run_git(checkout, "commit", "-m", "base")
        base_sha = _run_git(checkout, "rev-parse", "HEAD")
        test_path.write_text("def test_anchor_path():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        _run_git(checkout, "commit", "-am", "head")
        head_sha = _run_git(checkout, "rev-parse", "HEAD")
        _run_git(checkout, "push", "origin", "HEAD:main")
        controller_completed = subprocess.run(
            ["git", "init", "--bare", str(controller_repo)], check=True, capture_output=True
        )
        _run_git(controller_repo, "remote", "add", "origin", str(origin))
        _run_git(controller_repo, "fetch", "--no-tags", "--depth=1", "origin", base_sha)
        event = _event()
        event["workflow_sha"] = base_sha
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        non_repository_cwd = root / "non-repository-cwd"
        non_repository_cwd.mkdir()
        runtime_dir = _synthetic_runtime(
            root,
            pyproject=(checkout / "pyproject.toml").read_bytes(),
            uv_lock=(checkout / "uv.lock").read_bytes(),
            behavioral_pytest=True,
        )
        verifier_script = ROOT / "scripts/ops/trusted_deletion_anchor.py"
        subprocess.run(
            [
                sys.executable,
                str(verifier_script),
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(controller_repo),
                "--output-dir",
                str(bundle),
                "--runtime-dir",
                str(runtime_dir),
            ],
            cwd=non_repository_cwd,
            capture_output=True,
            text=True,
        )
        assert controller_completed.returncode == 0, controller_completed.stderr
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
            ("refs/trusted-anchor/workflow", base_sha),
        ):
            _run_git(clone, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(clone, "rev-parse", f"{ref}^{{commit}}") == revision
        executor_completed = subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "executor",
                "--bundle-dir",
                str(bundle),
            ],
            capture_output=True,
            text=True,
        )
        assert executor_completed.returncode == 0, executor_completed.stderr
        evidence_path = bundle / "raw-evidence.json"
        assert evidence_path.exists()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["status"] == "COMPLETE"
        assert evidence["executor"]["exit_code"] == 0
        golden_report = evidence["golden_report"]
        assert golden_report["schema"] == "nexus.golden_behavior_eval.v1"
        assert golden_report["validation_errors"] == []
        assert golden_report["workspace_dirty"] is False
        assert _run_git(bundle / "source", "rev-parse", "HEAD") == head_sha
        assert _run_git(bundle / "source", "rev-parse", "HEAD^") == base_sha
        assert _run_git(bundle / "source", "rev-parse", "HEAD^{tree}") == manifest["head_tree"]
        assert _run_git(bundle / "source", "rev-parse", "HEAD:tests") == _run_git(
            checkout, "rev-parse", f"{head_sha}:tests"
        )
        assert (bundle / "source/tests/ops/test_pr_impact_gate.py").read_text() == (
            "def test_anchor_path():\n    assert 1 + 1 == 2\n"
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
                str(verifier_script),
                "verifier",
                "--bundle-dir",
                str(bundle),
                *expected,
            ],
            capture_output=True,
            text=True,
            cwd=non_repository_cwd,
        )
        assert verified.returncode == 0, verified.stderr
        assert '"status": "PASS"' in verified.stdout
        original_evidence = evidence_path.read_bytes()
        evidence_tamper = json.loads(original_evidence)
        evidence_tamper["head_tree"] = "0" * 40 if manifest["head_tree"] != "0" * 40 else "1" * 40
        evidence_path.write_bytes(_json(evidence_tamper) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    str(verifier_script),
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
                cwd=non_repository_cwd,
            ).returncode
            != 0
        )
        evidence_path.write_bytes(original_evidence)
        tampered = dict(manifest)
        tampered["head_sha"] = "d" * 40
        (bundle / "manifest.json").write_bytes(_json(tampered) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    str(verifier_script),
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
                cwd=non_repository_cwd,
            ).returncode
            != 0
        )


def _synthetic_git_bundle(root: Path) -> tuple[bytes, dict[str, object], str, str, str]:
    repo = root / "executor-git-source"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "executor-git-test")
    test_path = repo / "tests/ops/test_pr_impact_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fixture():\n    assert True\n")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (repo / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    test_path.write_text("def test_archive_bootstrap():\n    assert True\n")
    _run_git(repo, "commit", "-am", "head")
    head_sha = _run_git(repo, "rev-parse", "HEAD")
    for ref, revision in (
        (trusted_anchor.BASE_REF, base_sha),
        (trusted_anchor.HEAD_REF, head_sha),
        (trusted_anchor.WORKFLOW_REF, base_sha),
    ):
        _run_git(repo, "update-ref", ref, revision)
    path = root / "synthetic-git.bundle"
    subprocess.run(
        [
            "git",
            "bundle",
            "create",
            str(path),
            trusted_anchor.BASE_REF,
            trusted_anchor.HEAD_REF,
            trusted_anchor.WORKFLOW_REF,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    event = _event()
    event["workflow_sha"] = base_sha
    event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
    event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
    return (
        path.read_bytes(),
        event,
        _run_git(repo, "rev-parse", f"{base_sha}^{{tree}}"),
        _run_git(repo, "rev-parse", f"{head_sha}^{{tree}}"),
        _run_git(repo, "rev-parse", f"{head_sha}:tests"),
    )


def _executor_archive_bundle(
    root: Path, unsafe_member: tarfile.TarInfo, *, runtime_probe: dict[str, str] | None = None
) -> Path:
    bundle = root / "bundle"
    bundle.mkdir()
    test_name = "tests/ops/test_pr_impact_gate.py"
    test_data = b"def test_archive_bootstrap():\n    assert True\n"
    with tarfile.open(bundle / "source.tar", "w") as archive:
        test_member = tarfile.TarInfo(test_name)
        test_member.size = len(test_data)
        archive.addfile(test_member, fileobj=BytesIO(test_data))
        unsafe_data = BytesIO(b"x" * unsafe_member.size) if unsafe_member.isreg() else None
        archive.addfile(unsafe_member, fileobj=unsafe_data)
    runtime_dir = _synthetic_runtime(root, probe=runtime_probe)
    requirements = (runtime_dir / "requirements.txt").read_bytes()
    runtime_archive = (runtime_dir / "runtime.tar").read_bytes()
    runtime_metadata = (runtime_dir / "runtime-metadata.json").read_bytes()
    git_bundle, event, base_tree, head_tree, test_tree = _synthetic_git_bundle(root)
    manifest = build_manifest(
        event,
        raw_diff=b"",
        test_inventory=[test_name],
        source_archive=(bundle / "source.tar").read_bytes(),
        git_bundle=git_bundle,
        requirements=requirements,
        runtime_archive=runtime_archive,
        runtime_metadata=runtime_metadata,
        runtime_identity=json.loads(runtime_metadata),
        base_tree=base_tree,
        head_tree=head_tree,
        test_tree=test_tree,
    )
    (bundle / "git-objects.bundle").write_bytes(git_bundle)
    for name in trusted_anchor.RUNTIME_FILENAMES:
        (bundle / name).write_bytes((runtime_dir / name).read_bytes())
    (bundle / "manifest.json").write_bytes(_json(manifest))
    evaluator = ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH
    (bundle / "run_golden_behavior_eval.py").write_bytes(evaluator.read_bytes())
    manifest["golden_evaluator_sha256"] = hashlib.sha256(evaluator.read_bytes()).hexdigest()
    # Rebuild the signed bundle identity after adding the trusted evaluator.
    unsigned = dict(manifest)
    unsigned.pop("bundle_sha256", None)
    manifest["bundle_sha256"] = trusted_anchor._sha(
        trusted_anchor._json(unsigned)
        + (bundle / "source.tar").read_bytes()
        + b""
        + trusted_anchor._json([test_name])
        + git_bundle
        + requirements
        + runtime_archive
        + (runtime_dir / "runtime-metadata.json").read_bytes()
        + evaluator.read_bytes()
    )
    (bundle / "manifest.json").write_bytes(_json(manifest))
    return bundle


def test_missing_runtime_artifact_cannot_emit_complete_evidence(tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link)
    (bundle / "runtime.tar").unlink()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "raw-evidence.json").exists()


def test_executor_rejects_runtime_abi_mismatch(tmp_path: Path):
    probe = trusted_anchor._runtime_probe()
    probe["soabi"] = "incompatible-abi"
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link, runtime_probe=probe)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "offline runtime identity mismatch" in completed.stderr
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "git-digest",
        "malformed-bound-git",
        "substituted-base",
        "substituted-head",
        "substituted-workflow",
        "wrong-tree",
        "wrong-test-tree",
        "bound-source-test-drift",
        "source-digest",
    ],
)
def test_executor_git_context_tamper_fails_closed(tamper: str, tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if tamper == "git-digest":
        (bundle / "git-objects.bundle").write_bytes(
            (bundle / "git-objects.bundle").read_bytes() + b"tamper"
        )
    elif tamper == "malformed-bound-git":
        malformed = b"not a Git bundle"
        (bundle / "git-objects.bundle").write_bytes(malformed)
        manifest["git_bundle_sha256"] = hashlib.sha256(malformed).hexdigest()
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-head":
        manifest["head_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-base":
        manifest["base_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-workflow":
        manifest["workflow_identity"]["workflow_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "wrong-tree":
        manifest["head_tree"] = "0" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "wrong-test-tree":
        manifest["test_tree"] = "0" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "bound-source-test-drift":
        original = tarfile.open(bundle / "source.tar")
        stream = BytesIO()
        with original, tarfile.open(fileobj=stream, mode="w") as rewritten:
            for member in original.getmembers():
                payload = original.extractfile(member) if member.isfile() else None
                if member.name == "tests/ops/test_pr_impact_gate.py":
                    data = b"def test_tampered():\n    assert True\n"
                    member.size = len(data)
                    payload = BytesIO(data)
                rewritten.addfile(member, payload)
        archive = stream.getvalue()
        (bundle / "source.tar").write_bytes(archive)
        manifest["source_archive_sha256"] = hashlib.sha256(archive).hexdigest()
        manifest_path.write_bytes(_json(manifest))
    else:
        (bundle / "source.tar").write_bytes((bundle / "source.tar").read_bytes() + b"tamper")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize("target", ["/tmp/issue104-absolute-link", "../../issue104-outside-link"])
def test_executor_skips_only_external_links_and_runs_safe_tests(target: str, tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = target
    bundle = _executor_archive_bundle(tmp_path, link)
    source = bundle / "source"
    non_git_cwd = tmp_path / "non-git-cwd"
    non_git_cwd.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=non_git_cwd,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert (source / "tests/ops/test_pr_impact_gate.py").is_file()
    assert not (source / ".antigravitycli").exists()
    assert "canonical Golden report is missing" in completed.stderr
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize("member_type", ["outside-path", "device"])
def test_executor_keeps_other_unsafe_archive_forms_fail_closed(member_type: str, tmp_path: Path):
    member = tarfile.TarInfo("../outside.txt" if member_type == "outside-path" else "device")
    if member_type == "outside-path":
        member.size = len(b"must not extract")
    else:
        member.type = tarfile.CHRTYPE
        member.devmajor = 1
        member.devminor = 3
    bundle = _executor_archive_bundle(tmp_path, member)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "outside.txt").exists()
    assert not (bundle / "source" / "device").exists()


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
        (source / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
        (source / "uv.lock").write_text("version = 1\nrevision = 3\n")
        evaluator_path = source / trusted_anchor.GOLDEN_EVALUATOR_PATH
        evaluator_path.parent.mkdir(parents=True, exist_ok=True)
        evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
        golden_dir = source / "tests/golden_behavior"
        golden_dir.mkdir(parents=True, exist_ok=True)
        for name in ("corpus.py", "test_corpus.py"):
            (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
        _run_git(source, "add", ".")
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
        runtime_dir = _synthetic_runtime(
            root,
            pyproject=(source / "pyproject.toml").read_bytes(),
            uv_lock=(source / "uv.lock").read_bytes(),
        )
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
                "--runtime-dir",
                str(runtime_dir),
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
            ("refs/trusted-anchor/workflow", base_sha),
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
    assert workflow["jobs"]["trusted-verifier"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert {job["runs-on"] for job in workflow["jobs"].values()} == {"ubuntu-24.04"}
    runtime_builder = _named_step("trusted-controller", "Acquire fixed trusted runtime builder")
    assert runtime_builder["uses"] == "astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff"
    assert runtime_builder["with"] == {"version": "0.9.2", "enable-cache": False}
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
    assert (
        "runtime-builder"
        in _named_step("trusted-controller", "Acquire and execute exact trusted controller source")[
            "run"
        ]
    )


def test_executor_workflow_has_no_runtime_provisioning_or_authority():
    workflow = _workflow()
    executor = workflow["jobs"]["unprivileged-executor"]
    assert executor["runs-on"] == "ubuntu-24.04"
    assert executor["permissions"] == {}
    text = json.dumps(executor).lower()
    for forbidden in (
        "setup-python",
        "setup-uv",
        "pip install",
        "uv sync",
        "actions/cache",
        "github.token",
        "secrets",
    ):
        assert forbidden not in text


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
        acquisition = _named_step(
            job_name,
            "Acquire and execute exact trusted controller source"
            if job_name == "trusted-controller"
            else "Acquire exact trusted verifier source",
        )["run"]
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


def test_executor_cleanup_removes_only_extracted_material(tmp_path: Path):
    bundle = tmp_path / "trusted-anchor"
    (bundle / "source").mkdir(parents=True)
    (bundle / "runtime").mkdir()
    evidence = bundle / "raw-evidence.json"
    evidence.write_text('{"status":"COMPLETE"}\n')
    cleanup = _named_step("unprivileged-executor", "Cleanup unprivileged executor material")
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", cleanup["run"]],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (bundle / "source").exists()
    assert not (bundle / "runtime").exists()
    assert evidence.is_file()


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
