import pytest
from pathlib import Path
from nexus.research.research_map import ResearchMapBuilder
from nexus.research.findings_memory import FindingsCard

def test_research_map_rendering():
    """驗證 Mermaid 渲染邏輯。"""
    builder = ResearchMapBuilder(task_id="test-task")
    
    # 添加階段與記憶
    builder.add_stage_node("P", "Scout")
    card = FindingsCard(id="c1", title="Knowledge Title", kind="knowledge", stage="P")
    builder.add_memory_node(card)
    
    mermaid_str = builder.render_mermaid()
    
    assert "graph TD" in mermaid_str
    assert 'stage_P["P: Scout"]' in mermaid_str
    assert 'class stage_P stage' in mermaid_str
    assert 'card_c1["🧠 Knowledge Title"]' in mermaid_str
    assert 'stage_P -- found --> card_c1' in mermaid_str

def test_research_map_export(tmp_path):
    """驗證 .mmd 檔案匯出。"""
    builder = ResearchMapBuilder(task_id="export-test")
    builder.add_stage_node("P", "Scout")
    
    output_path = tmp_path / "research_map.mmd"
    builder.export_mmd(output_path)
    
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "graph TD" in content
    assert 'stage_P' in content

def test_episode_class_assignment():
    """驗證失敗經歷 (Episodes) 的特殊樣式賦值。"""
    builder = ResearchMapBuilder(task_id="episode-test")
    card = FindingsCard(id="e1", title="Cuda Memory Error", kind="episodes", stage="R")
    builder.add_memory_node(card)
    
    mermaid_str = builder.render_mermaid()
    assert 'class card_e1 episode' in mermaid_str
