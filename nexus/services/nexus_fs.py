import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PathNode:
    name: str
    is_dir: bool
    physical_path: Optional[Path] = None
    children: Dict[str, 'PathNode'] = None
    content_provider: Optional[str] = None # 'wiki', 'knowledge', 'wisdom', 'belief'
    metadata: Optional[Dict[str, Any]] = None

class NexusFS:
    """
    🏗️ NexusFS: Virtual Memory Indexing Layer
    Inspired by Mintlify ChromaFs architecture.
    Provides unified ls/cat/search over Nexus memory tiers and Wiki.
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.root_node = PathNode("/", is_dir=True, children={})
        self._cache: Dict[str, Any] = {}
        self._tree_built = False
        self._wisdom_vault = None

    def build_path_tree(self):
        """🧩掃描所有物理與邏輯來源，建立統一路徑樹。"""
        if self._tree_built: return
        
        # 建立頂層虛擬目錄
        self.root_node.children = {
            "wiki": PathNode("wiki", is_dir=True, children={}),
            "knowledge": PathNode("knowledge", is_dir=True, children={}),
            "wisdom": PathNode("wisdom", is_dir=True, children={}),
            "memory": PathNode("memory", is_dir=True, children={}),
            "beliefs": PathNode("beliefs", is_dir=True, children={})
        }

        # 1. 映射 Wiki (nexus_wiki_vault)
        wiki_root = self.project_root / "nexus_wiki_vault"
        if wiki_root.exists():
            self._map_physical_dir(wiki_root, self.root_node.children["wiki"], provider="wiki")

        # 2. 映射 Knowledge (.nexus/knowledge)
        knowledge_root = self.project_root / ".nexus" / "knowledge"
        if knowledge_root.exists():
            self._map_logical_knowledge(knowledge_root, self.root_node.children["knowledge"])

        # 3. 映射 Wisdom (.nexus/vector_db)
        wisdom_root = self.project_root / ".nexus" / "vector_db"
        if wisdom_root.exists():
            self._map_logical_wisdom(wisdom_root, self.root_node.children["wisdom"])

        # 4. 映射 Beliefs (MemPalace projection)
        self._map_logical_beliefs(self.root_node.children["beliefs"])

        self._tree_built = True
        logger.info("🌲 [NexusFS] PathTree built successfully.")

    def _map_physical_dir(self, physical_dir: Path, virtual_node: PathNode, provider: str):
        """遞歸映射物理目錄到虛擬節點。"""
        try:
            for item in physical_dir.iterdir():
                if item.name.startswith("."): continue
                
                is_dir = item.is_dir()
                node = PathNode(
                    name=item.name,
                    is_dir=is_dir,
                    physical_path=item,
                    children={} if is_dir else None,
                    content_provider=provider
                )
                virtual_node.children[item.name] = node
                if is_dir:
                    self._map_physical_dir(item, node, provider)
        except Exception as e:
            logger.warning(f"⚠️ [NexusFS] Failed to map physical dir {physical_dir}: {e}")

    def _map_logical_knowledge(self, knowledge_root: Path, virtual_node: PathNode):
        """映射邏輯 Knowledge 條目。"""
        # 政策目錄
        virtual_node.children["policies"] = PathNode("policies", is_dir=True, children={})
        policy_file = knowledge_root / "policy_memory.jsonl"
        if policy_file.exists():
            try:
                with open(policy_file, "r") as f:
                    for line in f:
                        if not line.strip(): continue
                        data = json.loads(line)
                        rule_id = data.get("rule_id", "unknown")
                        virtual_node.children["policies"].children[rule_id] = PathNode(
                            name=rule_id, is_dir=False, content_provider="knowledge", metadata=data
                        )
            except Exception: pass

    def _map_logical_wisdom(self, wisdom_root: Path, virtual_node: PathNode):
        """映射 Wisdom 表。"""
        tables = ["patterns", "soul"]
        for t in tables:
            virtual_node.children[t] = PathNode(t, is_dir=True, children={})
            # 這裡暫不填充每一條記錄以節省內存，採 Lazy Load。

    def _map_logical_beliefs(self, virtual_node: PathNode):
        """映射 Belief 投影。"""
        virtual_node.children["current"] = PathNode("current", is_dir=True, children={})
        virtual_node.children["router_bias"] = PathNode("router_bias", is_dir=False, content_provider="belief")

    def ls(self, path: str = "/") -> List[str]:
        """列出虛擬路徑。"""
        self.build_path_tree()
        
        # 動態注入 Beliefs 到 Ls 結果
        if path.rstrip("/") == "/beliefs/current":
            try:
                from nexus.services.mem_palace import MemPalace
                palace = MemPalace(str(self.project_root))
                beliefs = palace.list_beliefs(status="ACTIVE")
                return sorted([str(b.get("task") or b.get("id")) for b in beliefs])
            except Exception as e:
                logger.warning(f"⚠️ [NexusFS] Failed to list dynamic beliefs: {e}")
                return []

        node = self._resolve_path(path)
        if not node or not node.is_dir: return []
        return sorted(list(node.children.keys()))

    def cat(self, path: str) -> str:
        """讀取虛擬路徑內容。"""
        self.build_path_tree()
        node = self._resolve_path(path)
        if not node or node.is_dir: return ""
        
        # 1. Wiki Provider
        if node.content_provider == "wiki" and node.physical_path:
            return node.physical_path.read_text(encoding="utf-8")
        
        # 2. Knowledge Provider
        if node.content_provider == "knowledge" and node.metadata:
            return json.dumps(node.metadata, indent=2, ensure_ascii=False)
        
        # 3. Belief Provider
        if node.content_provider == "belief":
            return self._handle_belief_cat(path, node)
            
        return ""

    def _resolve_path(self, path: str) -> Optional[PathNode]:
        """將虛擬路徑解析為 PathNode。"""
        parts = [p for p in path.split("/") if p]
        curr = self.root_node
        for p in parts:
            if curr.children and p in curr.children:
                curr = curr.children[p]
            else:
                return None
        return curr

    def _handle_belief_cat(self, path: str, node: PathNode) -> str:
        from nexus.services.mem_palace import MemPalace
        palace = MemPalace(str(self.project_root))
        
        if node.name == "router_bias":
            bias = palace.get_router_bias()
            return json.dumps({"global_router_bias": bias}, indent=2)
            
        if "/beliefs/current/" in path:
            belief = palace.get_belief(node.name)
            if belief:
                return json.dumps(belief, indent=2, ensure_ascii=False)
                
        return ""
    def _get_wisdom_vault(self):
        """Lazy Singleton for WisdomVault."""
        if self._wisdom_vault is None:
            try:
                from nexus.research.wisdom.wisdom_vault import WisdomVault
                db_path = str(self.project_root / ".nexus" / "vector_db")
                self._wisdom_vault = WisdomVault(db_path=db_path)
            except Exception as e:
                logger.debug(f"Failed to instantiate WisdomVault: {e}")
        return self._wisdom_vault

    def search(self, query: str, path: str = "/") -> List[Dict[str, Any]]:
        """🔍 跨域語義檢索入口。"""
        results = []
        
        # 1. LanceDB 跨表 FTS (Knowledge 層)
        try:
            from nexus.services.memory_repository import MemoryRepository
            repo = MemoryRepository(self.project_root / ".nexus" / "knowledge" / "lancedb")
            tables = ["policy", "fault_lessons"]
            df = repo.search_fts_across_tables(query, tables)
            if not df.empty:
                results.extend(df.to_dict("records"))
        except Exception as e:
            logger.debug(f"NexusFS search (FTS) failed: {e}")
        
        # 2. WisdomVault 語義搜尋 (Wisdom 層 - 🆕 接線)
        try:
            vault = self._get_wisdom_vault()
            if vault:
                wisdom_hits = vault.search_wisdom(query, limit=3)
                if wisdom_hits is not None and not wisdom_hits.empty:
                    for _, row in wisdom_hits.iterrows():
                        results.append({
                            "content": row.get("resolution", ""),
                            "task": row.get("task", ""),
                            "_source_table": "nexus_knowledge",
                            "_score": 1.0 - float(row.get("_distance", 0.5))
                        })
        except Exception as e:
            logger.debug(f"NexusFS search (Wisdom) failed: {e}")
        
        return results

    def grep(self, pattern: str, path: str = "/", flags: str = "") -> List[Dict[str, Any]]:
        """
        🚀 語義 Grep: 受 Mintlify 啟發的粗篩+精篩架構。
        """
        # 1. Coarse Filter (粗篩): 使用 FTS 找出可能命中的 Chunk
        coarse_results = self.search(pattern, path)
        
        # 2. Fine Filter (精篩): 在記憶體中執行精確匹配
        import re
        re_flags = re.IGNORECASE if "i" in flags else 0
        refined = []
        for res in coarse_results:
            content = str(res.get("content") or res.get("action") or res.get("lesson", ""))
            if re.search(pattern, content, re_flags):
                source = res.get("_source_table")
                if source == "nexus_knowledge":
                    # Wisdom 來源的路徑映射
                    v_path = f"/wisdom/{res.get('task', 'pattern')}"
                else:
                    # Knowledge 來源的路徑映射
                    v_path = f"/knowledge/{source}/{res.get('rule_id') or res.get('fault_hash')}"
                
                refined.append({
                    "path": v_path,
                    "line": content,
                    "score": res.get("_score", 1.0)
                })
        return refined
