from pathlib import Path
from typing import List, Set, Dict, Any

class HazardMapper:
    """🛡️ P1: Dependency-Aware Hazard Mapping.
    
    Identifies if a task involves 'Red-Zone' modules or files that 
    impact them, forcing L3 (Full Swarm) governance.
    """
    
    # Red-Zone Modules (High Risk/Critical Core)
    RED_ZONE: Set[str] = {
        'nexus.core.auth', 
        'nexus.services.billing_engine', 
        'nexus.core.router',
        'nexus.core.domain_firewall',
        'nexus.engine.pipeline_stages',
        'nexus.core.state_contracts',
        'nexus.engine.extension_guard',
        'nexus.engine.hazard_mapper'
    }

    @classmethod
    def is_red_zone(cls, module_name: str) -> bool:
        """Check if a module name belongs to the red zone."""
        return any(module_name.startswith(rz) for rz in cls.RED_ZONE)

    @classmethod
    def analyze_impact(cls, impact_map: Dict[str, Any]) -> bool:
        """
        🕵️ 依賴感知危害分析。
        
        Args:
            impact_map: The impact map from DependencyProbe.
            
        Returns:
            bool: True if red zone is impacted, False otherwise.
        """
        if not impact_map:
            return False
            
        for file_path, data in impact_map.items():
            # Check target itself
            if cls._is_file_in_red_zone(file_path):
                return True
                
            # Check direct dependents
            for dep in data.get('direct_dependents', []):
                if cls._is_file_in_red_zone(dep):
                    return True
                    
            # Check indirect dependents
            for dep in data.get('indirect_dependents', []):
                if cls._is_file_in_red_zone(dep):
                    return True
                    
        return False

    @classmethod
    def _is_file_in_red_zone(cls, file_path: str) -> bool:
        """Helper to convert file path to module and check red zone."""
        # Normalize path to module format
        module = file_path.replace('/', '.').replace('\\', '.').replace('.py', '')
        # Remove leading dots if any
        module = module.lstrip('.')
        return cls.is_red_zone(module)
