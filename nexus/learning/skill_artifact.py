import json
from typing import Dict, Any, Optional
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from datetime import datetime, timezone

def _build_yaml_frontmatter(fm: SkillFrontmatter) -> str:
    """Generates a simple YAML frontmatter string without requiring external dependencies."""
    lines = ["---"]
    lines.append(f"name: {fm.name}")
    # Wrap description in quotes to be safe against special characters
    desc = fm.description.replace('"', '\\"') if fm.description else ""
    lines.append(f'description: "{desc}"')
    lines.append(f"source: {fm.source}")
    lines.append(f"trust_level: {fm.trust_level}")
    lines.append(f"task_type: {fm.task_type}")
    
    if fm.keywords:
        kw_str = ", ".join(f'"{kw}"' for kw in fm.keywords)
        lines.append(f"keywords: [{kw_str}]")
    else:
        lines.append("keywords: []")
        
    lines.append(f'created_at: "{fm.created_at}"')
    lines.append(f"task_id: {fm.task_id}")
    
    lines.append("success_metric:")
    lines.append(f"  repair_success: {'true' if fm.success_metric.repair_success else 'false'}")
    lines.append(f"  retry_count: {fm.success_metric.retry_count}")
    lines.append(f"  pattern_reuse_rate: {fm.success_metric.pattern_reuse_rate}")
    lines.append(f"plan_strategy: {fm.plan_strategy}")
    lines.append(f"winning_hypothesis: {fm.winning_hypothesis}")
    if fm.phantom_patterns:
        pp_str = ", ".join(f'"{p}"' for p in fm.phantom_patterns)
        lines.append(f"phantom_patterns: [{pp_str}]")
    else:
        lines.append("phantom_patterns: []")
    lines.append(f"cycle_count: {fm.cycle_count}")
    lines.append(f"cycle_root_cause: {fm.cycle_root_cause}")
    
    if fm.verification_commands:
        vc_str = ", ".join(f'"{c}"' for c in fm.verification_commands)
        lines.append(f"verification_commands: [{vc_str}]")
        exit_codes_str = ", ".join(str(c) for c in fm.verification_exit_codes)
        lines.append(f"verification_exit_codes: [{exit_codes_str}]")
    else:
        lines.append("verification_commands: []")
        lines.append("verification_exit_codes: []")
    
    lines.append(f"embedding_model_version: {fm.embedding_model_version}")
    lines.append("---")
    return "\n".join(lines)

def validate_frontmatter(content: str) -> tuple[bool, list[str]]:
    """
    Validates the SKILL.md frontmatter against the standard schema.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    if not content or not content.startswith("---"):
        return False, ["Missing YAML frontmatter block starting with '---'"]
        
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, ["Malformed YAML frontmatter block"]
        
    yaml_text = parts[1]
    try:
        data = yaml.safe_load(yaml_text)
    except Exception as e:
        return False, [f"YAML parsing error: {e}"]
        
    if not isinstance(data, dict):
        return False, ["Frontmatter is not a valid YAML dictionary"]
        
    required_keys = ["name", "description", "trust_level", "task_id", "created_at"]
    for key in required_keys:
        if key not in data:
            errors.append(f"Missing required key: {key}")
            
    # Validate types and contents
    if "trust_level" in data and data["trust_level"] not in ("auto-generated", "reviewed", "tested", "production"):
        errors.append(f"Invalid trust_level: {data['trust_level']}")
        
    if "keywords" in data and not isinstance(data["keywords"], list):
        errors.append("keywords must be a list")
        
    if "verification_exit_codes" in data and not isinstance(data["verification_exit_codes"], list):
        errors.append("verification_exit_codes must be a list")
        
    return len(errors) == 0, errors

def build_skill_artifact(
    task_id: str,
    task_desc: str,
    research_pack: Optional[Dict[str, Any]],
    repair_result: Dict[str, Any],
    outcome_event: Dict[str, Any]
) -> Optional[str]:
    """
    Builds a SKILL.md artifact string from a successful task context.
    Returns None if the task does not meet the criteria for skill generation.
    """
    passed = outcome_event.get("passed", False)
    if not passed:
        return None
        
    metrics_dict = repair_result.get("metrics", {})
    retry_count = metrics_dict.get("retry_count", 0)
    has_research = bool(research_pack)
    
    # If the outcome event has its own metrics, use them, otherwise fallback to 0.0
    outcome_metrics = outcome_event.get("metrics", {})
    pattern_reuse_rate = outcome_metrics.get("pattern_reuse_rate", 0.0)
    
    # Criteria: must be non-trivial (retry > 0 or research based) and novel enough (reuse < 0.5)
    if not (retry_count > 0 or has_research):
        return None
    if pattern_reuse_rate >= 0.5:
        return None
        
    # Extract insights for description
    diag_summary = repair_result.get("diagnosis", "未提供診斷資訊")
    
    # Clean task desc for name
    name_slug = task_id
    if task_desc:
        words = "".join(c if c.isalnum() or c.isspace() else " " for c in task_desc[:50]).split()
        if words:
            name_slug = ("-".join(words)).lower()
            
    success_metric = SkillSuccessMetric(
        repair_success=True,
        retry_count=retry_count,
        pattern_reuse_rate=pattern_reuse_rate
    )
    
    task_type = outcome_event.get("task_type", "unknown")
    
    fm = SkillFrontmatter(
        name=name_slug,
        description=diag_summary[:100].replace('\n', ' '),
        task_id=task_id,
        success_metric=success_metric,
        task_type=task_type,
        keywords=[task_type] + (["research"] if research_pack else []),
        plan_strategy=outcome_event.get("plan_strategy_used", ""),
        winning_hypothesis=str(research_pack.get("winner", {}).get("hypothesis_id", "")) if research_pack else "",
        phantom_patterns=list(outcome_event.get("phantom_pattern_history", [])),
        cycle_count=int(outcome_event.get("retry_count", 0)),
        cycle_root_cause=str(outcome_event.get("cycle_root_cause", ""))
    )
    
    yaml_header = _build_yaml_frontmatter(fm)
    
    # Build markdown body
    body_lines = [
        "",
        "# 任務描述",
        task_desc or "未提供",
        "",
        "# 診斷與修復",
        str(repair_result.get("diagnosis", "未提供")),
        "",
        "## 修復步驟",
        "```json",
        json.dumps(repair_result.get("patches", []), indent=2, ensure_ascii=False),
        "```"
    ]
    
    if research_pack:
        body_lines.extend([
            "",
            "# 實驗與研究證據",
            f"- 實驗輪數: {research_pack.get('budget_used', {}).get('rounds', 0)}",
            f"- 勝出假說: {research_pack.get('winner', {}).get('hypothesis_id', 'unknown')}",
            "```json",
            json.dumps(research_pack.get('winner', {}), indent=2, ensure_ascii=False),
            "```"
        ])

    
    return yaml_header + "\n" + "\n".join(body_lines) + "\n"
