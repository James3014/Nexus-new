import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import json
import logging

logging.basicConfig(level=logging.DEBUG)

# Add project root to sys.path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from nexus.core.context_hub import ContextHub
from nexus.services.mem_palace import MemPalace
from nexus.core.state_contracts import NexusState, NexusDiagnosis
from nexus.engine.autonomic_router import AutonomicRouter

def test_phase13():
    db_path = project_root / ".nexus" / "registry" / "shared_skills.db"
    
    # Init Registry
    registry = SkillRegistry(db_path)
    
    # 1. Affinity Search Test
    print("--- Test 1. Affinity Search ---")
    fm1 = SkillFrontmatter(
        name="python-fix", description="Python specific fix", task_id="py-001",
        success_metric=SkillSuccessMetric(), task_type="standard",
        languages=["python"], file_patterns=["*.py"], win_rate=0.8
    )
    fm2 = SkillFrontmatter(
        name="rust-fix", description="Rust specific fix", task_id="rs-001",
        success_metric=SkillSuccessMetric(), task_type="standard",
        languages=["rust"], file_patterns=["*.rs"], win_rate=0.9
    )
    fm3 = SkillFrontmatter(
        name="general-fix", description="General fix", task_id="gen-001",
        success_metric=SkillSuccessMetric(), task_type="standard",
        languages=["python", "rust"], file_patterns=["*"], win_rate=0.5
    )
    
    registry.upsert(fm1)
    registry.upsert(fm2)
    registry.upsert(fm3)
    
    results = registry.search_by_affinity(languages=["python"])
    print(f"Python affinity search returned {len(results)} results:")
    for r in results:
        print(f" - {r['task_id']} ({r['win_rate']})")
        
    assert len(results) >= 2
    assert results[0]["task_id"] == "py-001" or results[0]["task_id"] == "gen-001"
    
    # 2. ContextHub dynamic injection
    print("\n--- Test 2. ContextHub Injection ---")
    hub = ContextHub(str(project_root), skill_registry=registry)
    
    diag = NexusDiagnosis(
        task_id="test-diag",
        status="pending",
        summary="Failed to parse JSON",
        pseudo_flows=["use json module"],
        hotspots=["src/main.py"],
        confidence=0.9
    )
    
    pack = hub.assemble_repair_pack(diagnosis=diag, reflections=[])
    recommended = pack.get("recommended_skills", [])
    print(f"Recommended skills: {recommended}")
    
    # 3. Win Rate update test
    print("\n--- Test 3. Win Rate Update ---")
    registry.update_win_rate("py-001", 1.0)
    updated = registry.get_by_task_id("py-001")
    print(f"Updated py-001 win rate: {updated.get('win_rate')}")
    assert updated.get("win_rate") == 1.0
    
    # 4. MemPalace Constraints Test
    print("\n--- Test 4. MemPalace Filter ---")
    mempalace = MemPalace(str(project_root))
    # mock beliefs
    mempalace.list_beliefs = lambda status: [{"content": "禁止使用 pip install", "created_at": datetime.now(timezone.utc).isoformat()}]
    
    hub_with_palace = ContextHub(str(project_root), skill_registry=registry, mem_palace=mempalace)
    
    fm_bad = SkillFrontmatter(
        name="bad-fix", description="pip install requests", task_id="bad-001",
        success_metric=SkillSuccessMetric(), task_type="standard",
        languages=["python"], file_patterns=["*.py"], win_rate=0.9,
        winning_hypothesis="we should pip install something"
    )
    registry.upsert(fm_bad)
    
    constraints = hub_with_palace.mem_palace.get_skill_constraints()
    print(f"Extracted Constraints: {constraints}")
    
    pack2 = hub_with_palace.assemble_repair_pack(diagnosis=diag, reflections=[])
    recommended2 = pack2.get("recommended_skills", [])
    print(f"Recommended skills (with MemPalace filtering): {recommended2}")
    
    # 5. Router Bias Test
    print("\n--- Test 5. Router Bias ---")
    mempalace.get_router_bias = lambda: [0.1, 0.9, 0.0, 0.0]  # swarm_weight = 0.9
    router = AutonomicRouter(str(project_root), mem_palace=mempalace)
    
    print(f"Original threshold: {router.config['token_threshold']}")
    state = NexusState(task_id="task-bias")
    plan = router.route("Normal task", state, forecast={"est_tokens": 7500})
    print(f"Routed Mode (est 7500 tokens): {plan.mode} (Expected swarm because threshold dropped to 7200)")

if __name__ == "__main__":
    test_phase13()
