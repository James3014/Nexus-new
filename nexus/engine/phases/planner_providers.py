from typing import Any, Dict, List, Protocol, runtime_checkable
from pathlib import Path

@runtime_checkable
class IntentProvider(Protocol):
    def classify(self, task: str) -> Dict[str, Any]: ...

@runtime_checkable
class DependencyProvider(Protocol):
    def probe_dependencies(self, project_root: Path, target_files: List[str]) -> Dict[str, Any]: ...

@runtime_checkable
class RAGProvider(Protocol):
    def inject_context(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]: ...

@runtime_checkable
class SpecCompilerProvider(Protocol):
    def compile_implementation_pack(self, project_root: Path, task_id: str, planner_output: Dict[str, Any]) -> Dict[str, Any]: ...

class DefaultIntentProvider:
    def classify(self, task: str) -> Dict[str, Any]:
        from nexus.core.engine.intent_classifier import IntentClassifier
        return IntentClassifier().classify(task)

class DefaultDependencyProvider:
    def probe_dependencies(self, project_root: Path, target_files: List[str]) -> Dict[str, Any]:
        from nexus.core.dependency_probe import DependencyProbe
        probe = DependencyProbe(str(project_root))
        probe.build_index()
        impact_map = {}
        for t in target_files:
            impact_map[t] = probe.full_impact(t)
        return impact_map

class DefaultRAGProvider:
    def inject_context(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """🚀 [v0.3] Hierarchical Soul-Palace Injection"""
        try:
            from scripts.ops.soul_palace_engine import SoulPalaceEngine
            palace = SoulPalaceEngine()
            
            # 1. Retrieve High-Density Soul Stack (L0-L2)
            soul_context = palace.retrieve_context(task)
            context["soul_palace_context"] = soul_context
            
            # 2. Traditional Vector RAG (L3 Deep Search / Lessons)
            from nexus.core.vector_rag import VectorRAG
            rag = VectorRAG()
            hits = rag.query(task, k=5)
            block = rag.format_for_prompt(hits)
            if block:
                context["experience_context"] = block
        except Exception as e:
            print(f"⚠️ [SoulPalace:P] Injection failed: {e}")
        return context

class DefaultSpecCompilerProvider:
    def compile_implementation_pack(self, project_root: Path, task_id: str, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        from nexus.services.implementation_pack import ImplementationPackGenerator
        generator = ImplementationPackGenerator(project_root, task_id)
        return generator.generate(planner_output)
