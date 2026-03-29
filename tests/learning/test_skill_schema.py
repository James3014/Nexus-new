import pytest
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
import json

def test_skill_schema_serialization():
    metric = SkillSuccessMetric(repair_success=True, retry_count=2, pattern_reuse_rate=0.1)
    fm = SkillFrontmatter(
        name="test-skill",
        description="A test skill",
        task_id="task-123",
        success_metric=metric,
        task_type="bug",
        keywords=["test", "schema"]
    )
    
    # Serialize
    data = fm.to_dict()
    assert data["name"] == "test-skill"
    assert data["success_metric"]["repair_success"] is True
    assert data["trust_level"] == "auto-generated"
    
    # Deserialize
    fm2 = SkillFrontmatter.from_dict(data)
    assert fm2.name == "test-skill"
    assert fm2.success_metric.repair_success is True
    assert fm2.success_metric.retry_count == 2
    assert fm2.keywords == ["test", "schema"]
