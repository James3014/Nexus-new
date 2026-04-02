from typing import Any, Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)

class SwarmGraph:
    """🌐 [Wave 3] Swarm Graph: Task Dependency Visualization"""
    
    def __init__(self):
        self.nodes = []
        self.edges = []

    def build_graph(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """從任務清單構建依賴圖譜內容內容及性能內容內容"""
        logger.info(f"🌐 [Swarm-Graph] Generating dependency map for {len(tasks)} nodes...")
        
        for task in tasks:
            node_id = task.get("task_id", "Unknown")
            self.nodes.append({"id": node_id, "label": task.get("description", "No Description")})
            
            # 🚀 行動 19: 建立簡化依賴 (順序依賴)
            if len(self.nodes) > 1:
                self.edges.append({"from": self.nodes[-2]["id"], "to": node_id})
        
        graph_data = {"nodes": self.nodes, "edges": self.edges}
        
        logger.info("🌐 [Swarm-Graph] Graph serialized. (Ready for X-Ray UI)")
        return graph_data

if __name__ == "__main__":
    sg = SwarmGraph()
    test_tasks = [{"task_id": "T1", "description": "Phase P"}, {"task_id": "T2", "description": "Phase X"}]
    print(sg.build_graph(test_tasks))
