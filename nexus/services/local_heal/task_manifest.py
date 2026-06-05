from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal

TaskKind = Literal["swebench", "local_concurrency", "cross_domain_experimental"]
LaneType = Literal["baseline", "challenge", "migration"]


@dataclass(frozen=True)
class LocalHealTaskSpec:
    task_id: str
    kind: TaskKind
    family: str
    env_profile: str
    swe_index: int | None = None
    instance_id: str | None = None
    local_path: str | None = None

    domain_id: str = "legacy"
    verifier_pack_id: str = "v1-core"
    lane: LaneType = "baseline"
    promotion_policy: str = "default"
    risk_profile_version: str = "v1.0"
    extension_metadata: Dict[str, Any] = field(default_factory=dict)

    probe_goal: str = "general-repair"
    expected_stop_layer: str = "verification"
    expected_reason_family: str = "SOLVED"


ASTROPY_SWEBENCH_TASKS = [
    (0, "astropy__astropy-12907"),
    (1, "astropy__astropy-13033"),
    (2, "astropy__astropy-13236"),
    (3, "astropy__astropy-13398"),
    (4, "astropy__astropy-13453"),
    (5, "astropy__astropy-13579"),
    (6, "astropy__astropy-13977"),
    (7, "astropy__astropy-14096"),
    (8, "astropy__astropy-14182"),
    (9, "astropy__astropy-14309"),
]

NEW_DEEPSWE_TASKS_V2 = [
    (10, "astropy__astropy-14365"),
    (11, "astropy__astropy-14369"),
    (12, "astropy__astropy-14508"),
    (13, "astropy__astropy-14539"),
    (14, "astropy__astropy-14598"),
    (15, "astropy__astropy-14995"),
    (16, "astropy__astropy-7166"),
    (17, "astropy__astropy-7336"),
    (18, "astropy__astropy-7606"),
    (19, "astropy__astropy-7671"),
    (20, "astropy__astropy-8707"),
    (21, "astropy__astropy-8872"),
    (22, "django__django-10097"),
    (23, "django__django-10554"),
    (24, "django__django-10880"),
    (25, "django__django-10914"),
    (26, "django__django-10973"),
    (27, "django__django-10999"),
    (28, "django__django-11066"),
    (29, "django__django-11087"),
]

NEW_DEEPSWE_TASKS_V3 = [
    (30, "django__django-11095"),
    (31, "django__django-11099"),
    (32, "django__django-11119"),
    (33, "django__django-11133"),
    (34, "django__django-11138"),
    (35, "django__django-11141"),
    (36, "django__django-11149"),
    (37, "django__django-11163"),
    (38, "django__django-11179"),
    (39, "django__django-11206"),
    (40, "django__django-11211"),
    (41, "django__django-11239"),
    (42, "django__django-11265"),
    (43, "django__django-11276"),
    (44, "django__django-11292"),
    (45, "django__django-11299"),
    (46, "django__django-11333"),
    (47, "django__django-11400"),
    (48, "django__django-11433"),
    (49, "django__django-11451"),
]

NEW_DEEPSWE_TASKS_V4 = [
    (50, "django__django-11477"),
    (51, "django__django-11490"),
    (52, "django__django-11532"),
    (53, "django__django-11551"),
    (54, "django__django-11555"),
    (55, "django__django-11603"),
    (56, "django__django-11728"),
    (57, "django__django-11734"),
    (58, "django__django-11740"),
    (59, "django__django-11749"),
    (60, "django__django-11790"),
    (61, "django__django-11815"),
    (62, "django__django-11820"),
    (63, "django__django-11848"),
    (64, "django__django-11880"),
    (65, "django__django-11885"),
    (66, "django__django-11951"),
    (67, "django__django-11964"),
    (68, "django__django-11999"),
    (69, "django__django-12039"),
    (70, "django__django-12050"),
    (71, "django__django-12125"),
    (72, "django__django-12143"),
    (73, "django__django-12155"),
    (74, "django__django-12193"),
    (75, "django__django-12209"),
    (76, "django__django-12262"),
    (77, "django__django-12273"),
    (78, "django__django-12276"),
    (79, "django__django-12304"),
    (80, "django__django-12308"),
    (81, "django__django-12325"),
    (82, "django__django-12406"),
    (83, "django__django-12419"),
    (84, "django__django-12663"),
    (85, "django__django-12708"),
    (86, "django__django-12713"),
    (87, "django__django-12741"),
    (88, "django__django-12754"),
    (89, "django__django-12774"),
]

NEW_DEEPSWE_TASKS_V5 = [
    (90, "django__django-12858"),
    (91, "django__django-12965"),
    (92, "django__django-13012"),
    (93, "django__django-13023"),
    (94, "django__django-13028"),
    (95, "django__django-13033"),
    (96, "django__django-13089"),
    (97, "django__django-13109"),
    (98, "django__django-13112"),
    (99, "django__django-13121"),
    (100, "django__django-13128"),
    (101, "django__django-13158"),
    (102, "django__django-13195"),
    (103, "django__django-13212"),
    (104, "django__django-13279"),
    (105, "django__django-13297"),
    (106, "django__django-13315"),
    (107, "django__django-13343"),
    (108, "django__django-13344"),
    (109, "django__django-13346"),
    (110, "django__django-13363"),
    (111, "django__django-13401"),
    (112, "django__django-13406"),
]

CONCURRENCY_TASKS = [
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
]


def _swe_specs(
    tasks: list[tuple[int, str]],
    *,
    task_prefix: str,
    family: str,
    env_profile: str = "python-default",
    challenge_from: int | None = None,
) -> tuple[LocalHealTaskSpec, ...]:
    specs = []
    for idx, iid in tasks:
        is_challenge = challenge_from is not None and idx >= challenge_from
        specs.append(
            LocalHealTaskSpec(
                task_id=f"{task_prefix}-{idx}",
                kind="swebench",
                family=family,
                env_profile=env_profile,
                swe_index=idx,
                instance_id=iid,
                domain_id=family if family != "mixed" else "swebench",
                lane="challenge" if is_challenge else "baseline",
                promotion_policy="evidence_driven" if is_challenge else "default",
                expected_reason_family="PENDING_RECOVERY" if is_challenge else "SOLVED",
            )
        )
    return tuple(specs)


def local_heal_20_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    astropy_specs = _swe_specs(
        ASTROPY_SWEBENCH_TASKS,
        task_prefix="astropy-swe-verified",
        family="astropy",
        env_profile="astropy-legacy",
    )
    concurrency_specs = tuple(
        LocalHealTaskSpec(
            task_id=tid,
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            local_path=lpath,
            domain_id="concurrency",
        )
        for tid, lpath in CONCURRENCY_TASKS
    )
    return astropy_specs + concurrency_specs


def local_heal_40_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    return local_heal_20_task_manifest() + _swe_specs(
        NEW_DEEPSWE_TASKS_V2,
        task_prefix="deepswe-v2",
        family="mixed",
    )


def local_heal_60_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    return local_heal_40_task_manifest() + _swe_specs(
        NEW_DEEPSWE_TASKS_V3,
        task_prefix="deepswe-v3",
        family="django",
    )


def local_heal_100_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    return local_heal_60_task_manifest() + _swe_specs(
        NEW_DEEPSWE_TASKS_V4,
        task_prefix="deepswe-v4",
        family="django",
    )


def local_heal_113_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    return local_heal_100_task_manifest() + _swe_specs(
        NEW_DEEPSWE_TASKS_V5,
        task_prefix="deepswe-v5",
        family="django",
        challenge_from=100,
    )


def local_heal_batch1_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    astropy_specs = _swe_specs(
        [
            (0, "astropy__astropy-12907"),
            (1, "astropy__astropy-13033"),
            (2, "astropy__astropy-13236"),
            (3, "astropy__astropy-13398"),
            (4, "astropy__astropy-13453")
        ],
        task_prefix="astropy-swe-verified",
        family="astropy",
        env_profile="astropy-legacy",
    )
    django_specs = _swe_specs(
        [
            (27, "django__django-10999"),
            (28, "django__django-11066"),
            (29, "django__django-11087"),
            (30, "django__django-11095"),
            (31, "django__django-11099")
        ],
        task_prefix="deepswe-batch1",
        family="django",
        env_profile="django-legacy",
    )
    return astropy_specs + django_specs


def v27_expansion_manifest() -> tuple[LocalHealTaskSpec, ...]:
    return (
        LocalHealTaskSpec(
            task_id="v27-sklearn-001",
            kind="cross_domain_experimental",
            family="scikit-learn",
            env_profile="ml-standard-311",
            domain_id="scikit_learn",
            verifier_pack_id="v27-ml-pack",
            lane="migration",
            promotion_policy="cross_domain_gate",
            extension_metadata={"target_recovery": 0.85},
        ),
        LocalHealTaskSpec(
            task_id="v27-flask-002",
            kind="cross_domain_experimental",
            family="flask",
            env_profile="web-standard-311",
            domain_id="flask",
            verifier_pack_id="v27-web-pack",
            lane="challenge",
            promotion_policy="aggressive_explore",
        ),
    )
