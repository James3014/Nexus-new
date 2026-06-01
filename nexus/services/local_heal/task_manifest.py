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
    ("deepswe-task4", "scripts/benchmarks/deepswe_task4_singleton_race.py"),
    ("deepswe-task5", "scripts/benchmarks/deepswe_task5_counter_race.py"),
    ("deepswe-task6", "scripts/benchmarks/deepswe_task6_cache_race.py"),
    ("deepswe-task7", "scripts/benchmarks/deepswe_task7_pubsub_race.py"),
    ("deepswe-task8", "scripts/benchmarks/deepswe_task8_transaction_race.py"),
    ("deepswe-task9", "scripts/benchmarks/deepswe_task9_pool_race.py"),
    ("deepswe-task10", "scripts/benchmarks/deepswe_task10_ordered_list_race.py"),
    ("django-31505", "scripts/benchmarks/django_31505_simulation.py"),
    ("asyncio-barrier", "scripts/benchmarks/asyncio_barrier_race_real.py"),
    ("free-threading-weakref", "scripts/benchmarks/free_threading_ref_race.py"),
)


def local_heal_20_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    # E1b: Authenticity Probe
    e1b = LocalHealTaskSpec(
        task_id="astropy-swe-verified-0",
        kind="swebench",
        family="astropy",
        env_profile="astropy-legacy",
        swe_index=0,
        probe_goal="verify ALREADY_FIXED detection",
        expected_stop_layer="repro_runner",
        expected_reason_family="env_noise",
    )
    # D1: Semantic Repair Probe
    d1 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-14096",
        kind="swebench",
        family="astropy",
        env_profile="astropy-legacy",
        swe_index=7, 
        probe_goal="verify 7B/14B patch routing",
        expected_stop_layer="verification",
        expected_reason_family="SOLVED",
    )
    # B1: Localization Probe
    b1 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-13033-localize",
        kind="swebench",
        family="astropy",
        env_profile="astropy-legacy",
        swe_index=1,
        probe_goal="verify single-function localization",
        expected_stop_layer="patcher",
    )
    # C2: Format Mismatch Probe
    c2 = LocalHealTaskSpec(
        task_id="astropy-swe-verified-13236-format",
        kind="swebench",
        family="astropy",
        env_profile="astropy-legacy",
        swe_index=2,
        probe_goal="verify SEARCH/REPLACE contract enforcement",
        expected_stop_layer="patcher",
    )

    astropy_tasks = (e1b, d1, b1, c2) + tuple(
        LocalHealTaskSpec(
            task_id=f"astropy-swe-verified-{index}",
            kind="swebench",
            family="astropy",
            env_profile="astropy-legacy",
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
