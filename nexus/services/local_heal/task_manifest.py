from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TaskKind = Literal["swebench", "local_concurrency"]


@dataclass(frozen=True)
class LocalHealTaskSpec:
    task_id: str
    kind: TaskKind
    family: str
    env_profile: str
    swe_index: int | None = None
    instance_id: str | None = None
    local_path: str | None = None
    probe_goal: str = "general-repair"
    expected_stop_layer: str = "verification"
    expected_reason_family: str = "SOLVED"


ASTROPY_SWEBENCH_INDICES: tuple[int, ...] = tuple(range(10))

CONCURRENCY_TASKS: tuple[tuple[str, str], ...] = (
    ("singleton-race", "scripts/benchmarks/deepswe_task4_singleton_race.py"),
    ("counter-race", "scripts/benchmarks/deepswe_task5_counter_race.py"),
    ("free-threading-weakref", "scripts/benchmarks/free_threading_ref_race.py"),
)


def local_heal_20_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    # E1a: Policy Block Probe
    e1a = LocalHealTaskSpec(
        task_id="astropy-swe-verified-0-policy",
        kind="swebench",
        family="astropy",
        env_profile="astropy-311", # Has numpy < 2.0.0 constraint which will trigger policy block
        swe_index=0,
        probe_goal="verify policy-based early exit",
        expected_stop_layer="env_resolver",
        expected_reason_family="env_noise",
    )
    # E1b: Authenticity Probe
    e1b = LocalHealTaskSpec(
        task_id="astropy-swe-verified-0",
        kind="swebench",
        family="astropy",
        env_profile="astropy-311-modern", # No numpy constraints, auto_heal_enabled=True
        swe_index=0,
        probe_goal="verify ALREADY_FIXED detection",
        expected_stop_layer="repro_runner",
        expected_reason_family="already_fixed",
    )
    # D1: Semantic Repair Probe
    d1 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-14096",
        kind="swebench",
        family="astropy",
        env_profile="astropy-311-modern", 
        swe_index=7, 
        probe_goal="verify 7B/14B patch routing",
        expected_stop_layer="patcher", # Currently stops here due to 14B capacity
        expected_reason_family="patch_mismatch",
    )
    # B1: Localization Probe
    b1 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-13033-localize",
        kind="swebench",
        family="astropy",
        env_profile="astropy-311-modern", 
        swe_index=1,
        probe_goal="verify single-function localization",
        expected_stop_layer="patcher",
        expected_reason_family="patch_mismatch",
    )
    # C2: Format Mismatch Probe
    c2 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-13579-format",
        kind="swebench",
        family="astropy",
        env_profile="astropy-311-modern", 
        swe_index=5,
        probe_goal="verify SEARCH/REPLACE contract enforcement",
        expected_stop_layer="patcher",
        expected_reason_family="patch_mismatch",
    )

    astropy_tasks = (e1a, e1b, d1, b1, c2) + tuple(
        LocalHealTaskSpec(
            task_id=f"astropy-swe-verified-{index}",
            kind="swebench",
            family="astropy",
            env_profile="astropy-311-modern",
            swe_index=index,
        )
        for index in range(1, 10) if index not in (1, 2, 7)
    )
    concurrency_tasks = tuple(
        LocalHealTaskSpec(
            task_id=task_id,
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path=local_path,
        )
        for task_id, local_path in CONCURRENCY_TASKS
    )
    return astropy_tasks + concurrency_tasks
