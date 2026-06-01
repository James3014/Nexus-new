from typing import List, Dict, Any, Optional
from pathlib import Path
from .findings_memory import FindingsCard

class ResearchMapBuilder:
    """
    🗺️ Research Map Builder (Mermaid Engine)
    職責: 將研究路徑與記憶節點轉換為可視化的 Mermaid 語法。
    """
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.nodes = [] # List[(id, label, type)]
        self.edges = [] # List[(from, to, label)]

    def add_stage_node(self, stage_code: str, stage_name: str, status: str = "completed"):
        """添加階段節點。"""
        node_id = f"stage_{stage_code}"
        color = "green" if status == "completed" else "yellow"
        label = f"{stage_code}: {stage_name}"
        self.nodes.append((node_id, label, "stage", color))

    def add_memory_node(self, card: FindingsCard):
        """添加記憶節點並連線至當前階段。"""
        node_id = f"card_{card.id}"
        kind_icon = {
            "knowledge": "🧠",
            "episodes": "⚠️",
            "papers": "📄",
            "decisions": "⚖️",
            "ideas": "💡"
        }.get(card.kind, "📝")
        
        label = f"{kind_icon} {card.title}"
        self.nodes.append((node_id, label, "card", "blue"))
        
        # 自動連接到產生它的階段
        if card.stage:
            source_id = f"stage_{card.stage}"
            self.edges.append((source_id, node_id, "found"))

    def add_edge(self, from_id: str, to_id: str, label: str = ""):
        """手動添加邊。"""
        self.edges.append((from_id, to_id, label))

    def render_mermaid(self) -> str:
        """生成 Mermaid Flowchart (TD) 語法。"""
        lines = ["graph TD", "    %% Research Map for " + self.task_id]
        
        # 定義樣式
        lines.append("    classDef stage fill:#f9f,stroke:#333,stroke-width:2px;")
        lines.append("    classDef card fill:#bbf,stroke:#333,stroke-width:1px;")
        lines.append("    classDef episode fill:#fbb,stroke:#333,stroke-width:1px;")
        
        # 節點
        for node_id, label, n_type, _ in self.nodes:
            clean_label = label.replace('"', "'")
            lines.append(f'    {node_id}["{clean_label}"]')
            if n_type == "stage":
                lines.append(f"    class {node_id} stage")
            elif "⚠️" in label:
                lines.append(f"    class {node_id} episode")
            else:
                lines.append(f"    class {node_id} card")
                
        # 邊
        for u, v, label in self.edges:
            if label:
                lines.append(f"    {u} -- {label} --> {v}")
            else:
                lines.append(f"    {u} --> {v}")
                
        return "\n".join(lines)

    def export_mmd(self, output_path: Path):
        """匯出為 .mmd 檔案。"""
        content = self.render_mermaid()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content
