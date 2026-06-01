from pathlib import Path

from nexus.services.local_heal.env_resolver import EnvResolver
from nexus.services.local_heal.preflight import build_preflight_rows
from nexus.services.local_heal.task_manifest import LocalHealTaskSpec


def test_preflight_rows_do_not_require_dataset_for_astropy_or_local_tasks(tmp_path):
    local_file = tmp_path / "scripts" / "benchmarks" / "race.py"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("def test_challenge():\n    pass\n", encoding="utf-8")
    specs = (
        LocalHealTaskSpec(
            task_id="astropy-swe-verified-0",
            kind="swebench",
            family="astropy",
            env_profile="astropy-legacy",
            swe_index=0,
        ),
        LocalHealTaskSpec(
            task_id="local-race",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path="scripts/benchmarks/race.py",
        ),
    )
    resolver = EnvResolver(
        which=lambda candidate: "/usr/bin/python3" if candidate == "python3" else None,
        version_probe=lambda executable: "3.14.0",
    )

    rows = build_preflight_rows(specs, root_dir=tmp_path, resolver=resolver)

    assert rows[0]["manifest_task_id"] == "astropy-swe-verified-0"
    assert rows[0]["instance_id"] == "astropy-swe-verified-0"
    assert rows[0]["preflight_ready"] is False
    assert rows[0]["failure_reason"] == "ASTROPY_VERSION_PARITY_MISSING"
    assert rows[0]["would_invoke_model"] is False

    assert rows[1]["manifest_task_id"] == "local-race"
    assert rows[1]["preflight_ready"] is True
    assert rows[1]["failure_reason"] == ""
    assert rows[1]["local_path_exists"] is True
    assert rows[1]["would_invoke_model"] is False


def test_preflight_rows_block_missing_local_fixture(tmp_path):
    specs = (
        LocalHealTaskSpec(
            task_id="missing-race",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path="scripts/benchmarks/missing.py",
        ),
    )
    resolver = EnvResolver(
        which=lambda candidate: "/usr/bin/python3" if candidate == "python3" else None,
        version_probe=lambda executable: "3.14.0",
    )

    rows = build_preflight_rows(specs, root_dir=tmp_path, resolver=resolver)

    assert rows[0]["preflight_ready"] is False
    assert rows[0]["failure_reason"] == "LOCAL_FIXTURE_MISSING"
