from __future__ import annotations

from pathlib import Path
from typing import Iterable

from nexus.services.local_heal.env_resolver import EnvResolver, requirement_for_profile
from nexus.services.local_heal.task_manifest import LocalHealTaskSpec


def _local_path_status(spec: LocalHealTaskSpec, root_dir: Path) -> tuple[bool, str]:
    if spec.kind != "local_concurrency":
        return True, ""
    if not spec.local_path:
        return False, "LOCAL_FIXTURE_MISSING"
    local_path = root_dir / spec.local_path
    if not local_path.exists():
        return False, "LOCAL_FIXTURE_MISSING"
    if not local_path.is_file():
        return False, "LOCAL_FIXTURE_NOT_FILE"
    return True, ""


def build_preflight_rows(
    specs: Iterable[LocalHealTaskSpec],
    *,
    root_dir: Path,
    resolver: EnvResolver | None = None,
) -> list[dict[str, object]]:
    env_resolver = resolver or EnvResolver()
    rows: list[dict[str, object]] = []

    for spec in specs:
        env_resolution = env_resolver.resolve(requirement_for_profile(spec.env_profile))
        local_path_ready, local_path_reason = _local_path_status(spec, root_dir)
        failure_reason = ""
        if not env_resolution.ready:
            failure_reason = env_resolution.reason
        elif not local_path_ready:
            failure_reason = local_path_reason

        rows.append(
            {
                "schema": "nexus.local_heal.preflight_row.v1",
                "instance_id": spec.instance_id or spec.task_id,
                "manifest_task_id": spec.task_id,
                "kind": spec.kind,
                "family": spec.family,
                "env_profile": spec.env_profile,
                "swe_index": spec.swe_index,
                "local_path": spec.local_path or "",
                "local_path_exists": local_path_ready,
                "env_resolution": env_resolution.to_receipt(),
                "preflight_ready": not failure_reason,
                "failure_reason": failure_reason,
                "would_invoke_model": False,
            }
        )
    return rows
