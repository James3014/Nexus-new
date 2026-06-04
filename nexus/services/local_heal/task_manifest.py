from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Dict, Any, Optional

TaskKind = Literal["swebench", "local_concurrency", "cross_domain_experimental"]
LaneType = Literal["baseline", "challenge", "migration"]


@dataclass(frozen=True)
class LocalHealTaskSpec:
    """
    [NEXUS v27] Governance-Oriented Task Specification
    職責: 預留擴展位以支持跨域遷移、自動化晉升與版本化治理。
    """
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
    (0, "astropy__astropy-12907"), (1, "astropy__astropy-13033"),
    (2, "astropy__astropy-13236"), (3, "astropy__astropy-13398"),
    (4, "astropy__astropy-13453"), (5, "astropy__astropy-13579"),
    (6, "astropy__astropy-13977"), (7, "astropy__astropy-14096"),
    (8, "astropy__astropy-14182"), (9, "astropy__astropy-14309"),
]

# 新增 10 題 Django SWE-bench 題目
DJANGO_SWEBENCH_TASKS = [
    (10, "django__django-11001"), (11, "django__django-11019"),
    (12, "django__django-11039"), (13, "django__django-11049"),
    (14, "django__django-11099"), (15, "django__django-11133"),
    (16, "django__django-11179"), (17, "django__django-11283"),
    (18, "django__django-11292"), (19, "django__django-11333"),
]

def local_heal_113_task_manifest() -> tuple[LocalHealTaskSpec, ...]:
    specs = []
    
    for idx, iid in ASTROPY_SWEBENCH_TASKS:
        specs.append(LocalHealTaskSpec(
            task_id=f"astropy-v27-{idx}",
            kind="swebench",
            family="astropy",
            env_profile="python-default",
            swe_index=idx,
            instance_id=iid,
            domain_id="astropy"
        ))
        
    for idx, iid in DJANGO_SWEBENCH_TASKS:
        specs.append(LocalHealTaskSpec(
            task_id=f"django-v27-{idx}",
            kind="swebench",
            family="django",
            env_profile="python-default",
            swe_index=idx,
            instance_id=iid,
            domain_id="django"
        ))
    
    for i in range(10):
        specs.append(LocalHealTaskSpec(
            task_id=f"concurrency-{i}",
            kind="local_concurrency",
            family="concurrency",
            env_profile="python-default",
            domain_id="concurrency"
        ))
        
    specs.extend(v27_expansion_manifest())
    
    return tuple(specs)


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
            extension_metadata={"target_recovery": 0.85}
        ),
        LocalHealTaskSpec(
            task_id="v27-flask-002",
            kind="cross_domain_experimental",
            family="flask",
            env_profile="web-standard-311",
            domain_id="flask",
            verifier_pack_id="v27-web-pack",
            lane="challenge",
            promotion_policy="aggressive_explore"
        )
    )
