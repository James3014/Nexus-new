"""Trusted pull_request_target impact gate (#1754 B)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sysconfig
from pathlib import Path

import pytest
import yaml

import scripts.ops.trusted_impact_gate as tig

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/trusted-impact-gate.yml"
REPOSITORY = "James3014/Nexus-new"
MAP_HEADER = "| 程式碼路徑 | 測試 | 狀態 | 風險 | 原因 |\n| :--- | :--- | :--- | :--- | :--- |\n"
TEST_MOD = "def test_a():\n    assert True\n\n\ndef test_b():\n    assert {value}\n"
TEST_OTHER = "class TestOther:\n    def test_c(self):\n        assert True\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def pr_repo(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _write(
        repo,
        {
            "pytest.ini": "[pytest]\npython_files = test_*.py\n",
            "docs/testing/test_impact_map.md": MAP_HEADER
            + "| pkg | tests/test_mod.py, tests/test_other.py | active | low | fixture |\n",
            "pkg/__init__.py": "",
            "pkg/mod.py": "VALUE = 1\n",
            "tests/__init__.py": "",
            "tests/test_mod.py": TEST_MOD.format(value="True"),
            "tests/test_other.py": TEST_OTHER,
            "tests/test_unplanned.py": "def test_x():\n    assert True\n",
            "tests/core/test_core.py": "def test_ok():\n    assert True\n",
            "tests/core/test_web_dom_mapper.py": "def test_browser():\n    assert True\n",
            "tests/services/test_policy_gate.py": "def test_ok():\n    assert True\n",
        },
    )
    base = _commit(repo, "base")
    _write(repo, {"pkg/mod.py": "VALUE = 2\n"})
    head = _commit(repo, "head")
    return {"repo": repo, "base": base, "head": head, "tmp": tmp_path}


def _event(base: str, head: str, *, head_repo: str = REPOSITORY) -> dict:
    return {
        "event_name": "pull_request_target",
        "workflow_ref": f"{REPOSITORY}/{tig.WORKFLOW_PATH}@refs/heads/main",
        "workflow_sha": base,
        "run_id": 42,
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "pull_request": {
            "number": 7,
            "base": {"sha": base, "ref": "main", "repo": {"full_name": REPOSITORY}},
            "head": {"sha": head, "repo": {"full_name": head_repo}},
        },
    }


def _bundle(pr_repo: dict) -> tuple[Path, dict, str]:
    event = _event(pr_repo["base"], pr_repo["head"])
    bundle = pr_repo["tmp"] / "bundle"
    manifest = tig.write_bundle(
        pr_repo["repo"],
        tig.identity(event),
        bundle,
        runtime_files={name: b"runtime:" + name.encode() for name in tig.anchor.RUNTIME_FILENAMES},
        runtime_identity={"fixture": True},
    )
    return bundle, manifest, hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()


def _junit(cases: list[tuple[str, str, str]]) -> bytes:
    body = []
    for classname, name, outcome in cases:
        child = {"pass": "", "fail": "<failure message='x'/>", "error": "<error message='x'/>"}
        body.append(f'<testcase classname="{classname}" name="{name}">{child[outcome]}</testcase>')
    return (
        f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" '
        f'tests="{len(cases)}">{"".join(body)}</testsuite></testsuites>'
    ).encode()


HONEST = [
    ("tests.test_mod", "test_a", "pass"),
    ("tests.test_mod", "test_b", "pass"),
    ("tests.test_other.TestOther", "test_c", "pass"),
]


def _evidence(
    evidence_dir: Path,
    manifest: dict,
    manifest_sha: str,
    side: str,
    *,
    junit: bytes | None,
    exit_code: int | None = 0,
    **overrides,
) -> str:
    spec = manifest["sides"][side]
    directory = evidence_dir / side
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": tig.SCHEMA_VERSION,
        "side": side,
        "revision": spec["revision"],
        "tree": spec["source_tree"],
        "manifest_sha256": manifest_sha,
        "mode": spec["mode"],
        "pytest_args": spec["pytest_args"],
        "pytest_exit_code": exit_code,
        "junit_sha256": hashlib.sha256(junit).hexdigest() if junit is not None else None,
    }
    payload.update(overrides)
    raw = tig.anchor._json(payload) + b"\n"
    (directory / "executor-evidence.json").write_bytes(raw)
    if junit is not None:
        (directory / "junit.xml").write_bytes(junit)
    return hashlib.sha256(raw).hexdigest()


def _verify(pr_repo: dict, bundle: Path, manifest_sha: str, base_sha256: str, **kwargs) -> dict:
    options = {
        "event": _event(pr_repo["base"], pr_repo["head"]),
        "repo": pr_repo["repo"],
        "bundle": bundle,
        "evidence_dir": pr_repo["tmp"] / "evidence",
        "expected_manifest_sha256": manifest_sha,
        "expected_base_evidence_sha256": base_sha256,
        "job_results": {"controller": "success", "base executor": "success"},
        "fetch": False,
    }
    options.update(kwargs)
    return tig.verify(**options)


def _honest(pr_repo: dict, head_cases=HONEST, head_exit: int = 0):
    bundle, manifest, manifest_sha = _bundle(pr_repo)
    evidence = pr_repo["tmp"] / "evidence"
    base_sha256 = _evidence(evidence, manifest, manifest_sha, "base", junit=_junit(HONEST))
    _evidence(
        evidence, manifest, manifest_sha, "head", junit=_junit(head_cases), exit_code=head_exit
    )
    return bundle, manifest, manifest_sha, base_sha256


# ----------------------------------------------------------------------------- workflow shape


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_trigger_and_top_level_permissions_are_locked():
    workflow = _workflow()
    trigger = workflow[True]
    assert set(trigger) == {"pull_request_target"}
    assert trigger["pull_request_target"] == {
        "types": ["opened", "synchronize", "reopened", "ready_for_review"],
        "branches": ["main"],
    }
    assert workflow["permissions"] == {}


def test_workflow_jobs_names_and_per_job_permissions():
    jobs = _workflow()["jobs"]
    assert set(jobs) == {
        "trusted-controller",
        "unprivileged-base-executor",
        "unprivileged-head-executor",
        "trusted-verifier",
    }
    assert jobs["trusted-controller"]["permissions"] == {"contents": "read"}
    assert jobs["unprivileged-base-executor"]["permissions"] == {}
    assert jobs["unprivileged-head-executor"]["permissions"] == {}
    verifier = jobs["trusted-verifier"]
    assert verifier["name"] == "Trusted impact gate (default branch)"
    assert verifier["permissions"] == {"contents": "read", "actions": "read"}
    assert verifier["if"] == "always()"
    assert set(verifier["needs"]) == {
        "trusted-controller",
        "unprivileged-base-executor",
        "unprivileged-head-executor",
    }


def test_no_job_checks_out_the_workspace_or_uses_head_runtime():
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "actions/checkout",
        "GITHUB_WORKSPACE",
        ".venv",
        "PYTHONPATH",
        "uv sync",
        "actions/cache",
        "github.head_ref",
        "pull_request.head.ref",
    ):
        assert forbidden not in text, forbidden


def test_verifier_runs_only_default_branch_sources():
    verifier = _workflow()["jobs"]["trusted-verifier"]
    scripts = "\n".join(step.get("run", "") for step in verifier["steps"])
    assert (
        'test "$WORKFLOW_REF" = "$REPOSITORY/$workflow_path@refs/heads/$DEFAULT_BRANCH"' in scripts
    )
    assert 'fetch --no-tags --depth=1 origin "$WORKFLOW_SHA"' in scripts
    assert (
        'python -I "$RUNNER_TEMP/trusted-impact-verifier-source/scripts/ops/trusted_impact_gate.py" verifier'
        in scripts
    )
    for line in scripts.splitlines():
        stripped = line.strip()
        if stripped.startswith("python"):
            assert stripped.startswith(("python -I ", "python -c ")), stripped
    assert "trusted-impact-bundle/code" not in scripts
    assert "setup-uv" not in json.dumps(verifier)


def test_executors_only_run_hash_bound_bundle_code():
    jobs = _workflow()["jobs"]
    for job in ("unprivileged-base-executor", "unprivileged-head-executor"):
        steps = jobs[job]["steps"]
        uses = [step["uses"].split("@")[0] for step in steps if "uses" in step]
        assert set(uses) <= {"actions/download-artifact", "actions/upload-artifact"}
        script = "\n".join(step.get("run", "") for step in steps)
        assert '= "$EXPECTED_MANIFEST_SHA256"' in script
        side = "base" if "base" in job else "head"
        assert f"--side {side} " in script
        assert "TRUSTED_TOKEN" not in json.dumps(jobs[job])
    assert "outputs" not in jobs["unprivileged-head-executor"]


def test_workflow_extracts_every_bundled_code_file_by_blob():
    text = WORKFLOW.read_text(encoding="utf-8")
    loop = "for path in " + " ".join(tig.CODE_FILES) + "; do"
    assert text.count(loop) == 2
    assert text.count('test "$(git hash-object "$trusted_dir/$path")" = "$blob_id"') == 2


def test_legacy_impact_gate_job_is_untouched():
    pytest_yml = yaml.safe_load((ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8"))
    assert pytest_yml["jobs"]["impact-gate"]["name"] == "Exact-base impact gate"


def test_impact_map_maps_new_script_to_these_tests():
    rules = tig.select_tests.load_impact_rules(ROOT / "docs/testing/test_impact_map.md")
    targets = {
        target
        for rule in rules
        if rule.code_path == "scripts/ops/trusted_impact_gate.py"
        for target in rule.targets
    }
    assert "tests/ops/test_trusted_impact_gate.py" in targets


# ----------------------------------------------------------------------------- identity


def test_fork_pull_request_fails_closed_with_clear_reason(pr_repo):
    event = _event(pr_repo["base"], pr_repo["head"], head_repo="attacker/Nexus-new")
    with pytest.raises(tig.GateError, match="fork pull requests are not supported"):
        tig.identity(event)
    event["pull_request"]["head"]["repo"] = None
    with pytest.raises(tig.GateError, match="fork pull requests"):
        tig.identity(event)


def test_fork_pull_request_cli_writes_rejection(pr_repo, tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(_event(pr_repo["base"], pr_repo["head"], head_repo="attacker/x")),
        encoding="utf-8",
    )
    output = tmp_path / "classification.json"
    code = tig.main([
        "verifier",
        "--event-json",
        str(event_path),
        "--repo-root",
        str(pr_repo["repo"]),
        "--bundle-dir",
        str(tmp_path / "missing"),
        "--evidence-dir",
        str(tmp_path / "missing"),
        "--expected-manifest-sha256",
        "0" * 64,
        "--expected-base-evidence-sha256",
        "0" * 64,
        "--controller-result",
        "failure",
        "--base-executor-result",
        "skipped",
        "--head-executor-result",
        "skipped",
        "--output",
        str(output),
    ])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["classification"] == "TRUSTED_GATE_REJECTED"
    assert payload["blocking"] is True
    assert "fork pull requests are not supported" in payload["reason"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("event_name",), "pull_request"),
        (("workflow_ref",), f"{REPOSITORY}/{tig.WORKFLOW_PATH}@refs/heads/feature"),
        (("pull_request", "base", "ref"), "release"),
        (("run_id",), True),
    ],
)
def test_untrusted_workflow_identity_is_rejected(pr_repo, path, value):
    event = _event(pr_repo["base"], pr_repo["head"])
    target = event
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(tig.GateError):
        tig.identity(event)


# ----------------------------------------------------------------------------- plan


def test_plan_comes_from_trusted_code_and_base_map(pr_repo):
    plan = tig.derive_plan(pr_repo["repo"], pr_repo["base"], pr_repo["head"])
    assert plan["changed_paths"] == ["pkg/mod.py"]
    assert plan["pytest_targets"] == ["tests/test_mod.py", "tests/test_other.py"]
    assert plan["impact_class"] == "SCOPED_IMPLEMENTATION"
    assert plan["base_source_tree"] == _git(
        pr_repo["repo"], "rev-parse", f"{pr_repo['base']}^{{tree}}"
    )


def test_head_map_cannot_narrow_rows_the_base_map_covers(pr_repo):
    repo = pr_repo["repo"]
    _write(
        repo,
        {
            "docs/testing/test_impact_map.md": MAP_HEADER
            + "| pkg/mod.py | tests/test_unplanned.py | active | low | narrowed |\n"
            + "| newpkg | tests/test_unplanned.py | active | low | new |\n",
            "newpkg/__init__.py": "",
        },
    )
    head = _commit(repo, "narrow map")
    plan = tig.derive_plan(repo, pr_repo["base"], head)
    assert "tests/test_mod.py" in plan["pytest_targets"]
    assert "tests/test_other.py" in plan["pytest_targets"]
    assert "newpkg/__init__.py" not in plan["unmatched_paths"]


# ----------------------------------------------------------------------------- verifier


FALLBACK = ["tests/core", "tests/services/test_policy_gate.py"]


def _existing_unmapped(pr_repo: dict, head_files: dict[str, str]) -> dict:
    repo = pr_repo["repo"]
    _write(
        repo,
        {
            "legacy/__init__.py": "",
            "legacy/core.py": "VALUE = 1\n",
            # Base maps the index file itself so editing it is not unmatched.
            ".nexus/test_impact_index.json": json.dumps({
                "mappings": {".nexus/test_impact_index.json": ["tests/test_other.py"]}
            }),
        },
    )
    pr_repo["base"] = _commit(repo, "base with an existing unmapped module")
    _write(repo, {"legacy/core.py": "VALUE = 2\n", **head_files})
    pr_repo["head"] = _commit(repo, "head maps the existing module")
    return tig.derive_plan(repo, pr_repo["base"], pr_repo["head"])


def _base_map(pr_repo: dict) -> str:
    return (pr_repo["repo"] / "docs/testing/test_impact_map.md").read_text(encoding="utf-8")


HEAD_MAPPING_VECTORS = {
    "exact_row": lambda pr_repo: {
        "docs/testing/test_impact_map.md": _base_map(pr_repo)
        + "| legacy/core.py | tests/test_unplanned.py | active | low | head |\n"
    },
    "prefix_row": lambda pr_repo: {
        "docs/testing/test_impact_map.md": _base_map(pr_repo)
        + "| legacy | tests/test_unplanned.py | active | low | head |\n"
    },
    "index_key": lambda pr_repo: {
        ".nexus/test_impact_index.json": json.dumps({
            "mappings": {
                ".nexus/test_impact_index.json": ["tests/test_other.py"],
                "legacy/core.py": ["tests/test_unplanned.py"],
            }
        })
    },
}


def test_existing_unmapped_path_without_head_data_keeps_base_fallback(pr_repo):
    plan = _existing_unmapped(pr_repo, {})
    assert plan["impact_class"] == "IMPACT_UNKNOWN"
    assert set(FALLBACK) <= set(plan["pytest_targets"])


@pytest.mark.parametrize("vector", sorted(HEAD_MAPPING_VECTORS))
def test_head_mapping_for_existing_unmapped_path_adds_but_never_removes(pr_repo, vector):
    plan = _existing_unmapped(pr_repo, HEAD_MAPPING_VECTORS[vector](pr_repo))
    assert set(FALLBACK) <= set(plan["pytest_targets"])
    assert "tests/test_unplanned.py" in plan["pytest_targets"]

    bundle, manifest, manifest_sha = _bundle(pr_repo)
    assert json.loads((bundle / "plan.json").read_text(encoding="utf-8")) == plan
    head_spec = manifest["sides"]["head"]
    assert set(FALLBACK) <= set(head_spec["executed_targets"])
    evidence = pr_repo["tmp"] / "evidence"
    known = {
        "tests/core": ("tests.core.test_core", "test_ok", "pass"),
        "tests/services/test_policy_gate.py": (
            "tests.services.test_policy_gate",
            "test_ok",
            "pass",
        ),
        "tests/test_other.py": ("tests.test_other.TestOther", "test_c", "pass"),
        "tests/test_mod.py": ("tests.test_mod", "test_a", "pass"),
    }
    cases = [known[target] for target in head_spec["executed_targets"] if target in known]
    cases.append(("tests.test_unplanned", "test_x", "pass"))
    base_sha256 = _evidence(evidence, manifest, manifest_sha, "base", junit=_junit(cases))
    # The attack: head runs only the head-picked target and reports it passing.
    _evidence(
        evidence,
        manifest,
        manifest_sha,
        "head",
        junit=_junit(cases[-1:]),
        pytest_args=["tests/test_unplanned.py"],
    )
    with pytest.raises(tig.GateError, match="pytest_args does not match"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)
    # Honest evidence for the union plan passes the verifier's re-derivation.
    _evidence(evidence, manifest, manifest_sha, "head", junit=_junit(cases))
    assert _verify(pr_repo, bundle, manifest_sha, base_sha256)["classification"] == "PASS"


def test_head_row_for_a_new_path_still_maps(pr_repo):
    repo = pr_repo["repo"]
    _write(
        repo,
        {
            "docs/testing/test_impact_map.md": _base_map(pr_repo)
            + "| newpkg | tests/test_unplanned.py | active | low | new |\n",
            "newpkg/__init__.py": "",
        },
    )
    head = _commit(repo, "new package with its own row")
    plan = tig.derive_plan(repo, pr_repo["base"], head)
    assert plan["impact_class"] != "IMPACT_UNKNOWN"
    assert "tests/test_unplanned.py" in plan["pytest_targets"]


def test_combine_plans_never_lowers_tier_or_drops_targets():
    base_only = {
        "pytest_targets": ["a", "b"],
        "pytest_required": True,
        "workflow_validation_required": True,
        "impact_class": "HIGH_RISK_INTEGRATION",
        "tier": 2,
        "confidence": 0.4,
        "reasons": [],
    }
    merged = {
        **base_only,
        "pytest_targets": ["c"],
        "workflow_validation_required": False,
        "impact_class": "SCOPED_IMPLEMENTATION",
        "tier": 1,
        "confidence": 0.9,
    }
    combined = tig.combine_plans(base_only, merged)
    assert combined["pytest_targets"] == ["c", "a", "b"]
    assert (combined["impact_class"], combined["tier"], combined["confidence"]) == (
        "HIGH_RISK_INTEGRATION",
        2,
        0.4,
    )
    assert combined["workflow_validation_required"] is True


def test_utf16_junit_with_doctype_is_rejected(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    body = (
        '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE t [<!ENTITY p "pass">]>'
        + (_junit(HONEST).decode().split("?>", 1)[1])
    )
    junit = body.encode("utf-16")
    assert b"<!DOCTYPE" not in junit
    _evidence(pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=junit)
    with pytest.raises(tig.GateError, match="not UTF-8"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_utf8_bytes_declaring_another_encoding_are_rejected(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    junit = _junit(HONEST).replace(b'encoding="utf-8"', b'encoding="latin-1"')
    _evidence(pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=junit)
    with pytest.raises(tig.GateError, match="non-UTF-8 encoding"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_honest_pass_passes(pr_repo):
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    payload = _verify(pr_repo, bundle, manifest_sha, base_sha256)
    assert payload["classification"] == "PASS"
    assert payload["blocking"] is False
    assert payload["trusted_source"] == "default-branch-verifier"


def test_honest_new_regression_fails(pr_repo):
    head_cases = [HONEST[0], ("tests.test_mod", "test_b", "fail"), HONEST[2]]
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo, head_cases, head_exit=1)
    payload = _verify(pr_repo, bundle, manifest_sha, base_sha256)
    assert payload["classification"] == "NEW_REGRESSION"
    assert payload["blocking"] is True
    assert payload["new_failures"] == ["tests.test_mod::test_b"]


def test_forged_fewer_executed_targets_fails(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    _evidence(
        pr_repo["tmp"] / "evidence",
        manifest,
        manifest_sha,
        "head",
        junit=_junit(HONEST[:2]),
        pytest_args=["tests/test_mod.py"],
    )
    with pytest.raises(tig.GateError, match="pytest_args does not match"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_missing_node_ids_for_a_planned_target_fail(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    _evidence(pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=_junit(HONEST[:2]))
    with pytest.raises(tig.GateError, match="no results for planned targets"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


@pytest.mark.parametrize(
    "extra",
    [
        ("tests.test_unplanned", "test_x", "pass"),
        ("tests.test_ghost", "test_y", "pass"),
    ],
)
def test_extra_node_ids_fail(pr_repo, extra):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    _evidence(
        pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=_junit([*HONEST, extra])
    )
    with pytest.raises(tig.GateError, match="outside the planned targets|maps to no file"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_inconsistent_duplicate_node_fails(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    cases = [*HONEST, ("tests.test_mod", "test_b", "fail")]
    _evidence(pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=_junit(cases))
    with pytest.raises(tig.GateError, match="duplicated inconsistently"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


@pytest.mark.parametrize(
    "junit",
    [
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><testsuites/>',
        b"<testsuites><testsuite>",
        b"<html/>",
    ],
)
def test_malformed_junit_fails_closed(pr_repo, junit):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    _evidence(pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=junit)
    with pytest.raises(tig.GateError):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_junit_digest_mismatch_fails(pr_repo):
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    (pr_repo["tmp"] / "evidence/head/junit.xml").write_bytes(_junit(HONEST) + b" ")
    with pytest.raises(tig.GateError, match="junit digest mismatch"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


@pytest.mark.parametrize(
    "victim", ["plan.json", "code/scripts/ops/pr_impact_gate.py", "runtime.tar"]
)
def test_bundle_hash_mismatch_fails(pr_repo, victim):
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    with (bundle / victim).open("ab") as handle:
        handle.write(b"\n# tampered\n")
    with pytest.raises(tig.GateError, match="bundle hash mismatch"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_manifest_not_anchored_to_controller_output_fails(pr_repo):
    bundle, _manifest, _manifest_sha, base_sha256 = _honest(pr_repo)
    with pytest.raises(tig.GateError, match="controller job output"):
        _verify(pr_repo, bundle, "f" * 64, base_sha256)


def test_unexpected_bundle_file_fails(pr_repo):
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    (bundle / "code/scripts/ops/sitecustomize.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(tig.GateError, match="unexpected files"):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


def test_base_evidence_must_match_base_job_output(pr_repo):
    bundle, _manifest, manifest_sha, _base_sha256 = _honest(pr_repo)
    with pytest.raises(tig.GateError, match="base executor evidence digest"):
        _verify(pr_repo, bundle, manifest_sha, "0" * 64)


def test_failed_upstream_job_fails_closed(pr_repo):
    bundle, _manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    with pytest.raises(tig.GateError, match="head executor job did not succeed"):
        _verify(
            pr_repo,
            bundle,
            manifest_sha,
            base_sha256,
            job_results={"controller": "success", "head executor": "failure"},
        )


def test_forged_controller_plan_fails(pr_repo):
    bundle, manifest, _manifest_sha, base_sha256 = _honest(pr_repo)
    plan = json.loads((bundle / "plan.json").read_text(encoding="utf-8"))
    plan["pytest_targets"] = ["tests/test_mod.py"]
    (bundle / "plan.json").write_bytes(tig.anchor._json(plan) + b"\n")
    manifest["files"]["plan.json"] = tig._sha_file(bundle / "plan.json")
    raw = tig.anchor._json(manifest) + b"\n"
    (bundle / "manifest.json").write_bytes(raw)
    with pytest.raises(tig.GateError, match="independently re-derived plan"):
        _verify(pr_repo, bundle, hashlib.sha256(raw).hexdigest(), base_sha256)


def test_evidence_claiming_a_run_the_plan_does_not_need_fails(pr_repo):
    bundle, manifest, manifest_sha, base_sha256 = _honest(pr_repo)
    _evidence(
        pr_repo["tmp"] / "evidence", manifest, manifest_sha, "head", junit=None, exit_code=None
    )
    with pytest.raises(tig.GateError):
        _verify(pr_repo, bundle, manifest_sha, base_sha256)


# ----------------------------------------------------------------------------- executor


def test_real_executor_output_round_trips_through_the_verifier(pr_repo, monkeypatch):
    bundle, manifest, manifest_sha = _bundle(pr_repo)
    purelib = Path(sysconfig.get_paths()["purelib"])
    monkeypatch.setattr(tig, "_prepare_runtime", lambda *_args: purelib)
    evidence = pr_repo["tmp"] / "evidence"
    for side in tig.SIDES:
        assert (
            tig._executor(
                argparse.Namespace(
                    bundle_dir=str(bundle),
                    side=side,
                    expected_manifest_sha256=manifest_sha,
                    output_dir=str(evidence / side),
                )
            )
            == 0
        )
    recorded = json.loads((evidence / "head/executor-evidence.json").read_text(encoding="utf-8"))
    assert recorded["pytest_exit_code"] == 0, (evidence / "head/pytest-output.log").read_text()
    base_sha256 = hashlib.sha256(
        (evidence / "base/executor-evidence.json").read_bytes()
    ).hexdigest()
    payload = _verify(pr_repo, bundle, manifest_sha, base_sha256)
    assert payload["classification"] == "PASS"


def test_executor_rejects_bundle_not_bound_to_controller_output(pr_repo, tmp_path):
    bundle, _manifest, _manifest_sha = _bundle(pr_repo)
    with pytest.raises(tig.GateError):
        tig._executor(
            argparse.Namespace(
                bundle_dir=str(bundle),
                side="head",
                expected_manifest_sha256="0" * 64,
                output_dir=str(tmp_path / "out"),
            )
        )


def test_ls_tree_check_uses_tab_separator():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '"100644 blob $blob_id"$\'\\t\'"$path"' in text


@pytest.mark.parametrize(
    "payload",
    [
        b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY p "pass">]><testsuites>&p;</testsuites>',
        b'<!DOCTYPE t [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><testsuites>&b;</testsuites>',
        b'<!DOCTYPE t SYSTEM "http://example.invalid/x.dtd"><testsuites/>',
    ],
)
def test_expat_pass_rejects_dtd_and_entities_without_the_byte_check(payload):
    # Called directly: this is the second, parser-level line of defence that
    # holds even if the textual DOCTYPE/ENTITY pre-check were bypassed.
    with pytest.raises(tig.GateError, match="DTD or entity"):
        tig.reject_dtd_and_entities(payload, "head")


def test_expat_pass_accepts_plain_junit_and_rejects_malformed():
    tig.reject_dtd_and_entities(_junit(HONEST), "head")
    with pytest.raises(tig.GateError, match="not well-formed"):
        tig.reject_dtd_and_entities(b"<testsuites><testsuite>", "head")
