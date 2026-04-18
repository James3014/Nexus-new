from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class AgentRole(str, Enum):
    PLANNER = "PLANNER"
    WORKER = "WORKER"
    INTEGRATOR = "INTEGRATOR"
    AUDITOR = "AUDITOR"

class AgentProfile(BaseModel):
    agent_id: str
    roles: List[AgentRole]
    capabilities: List[str]

class AgentRouter:
    def __init__(self):
        self.agents: Dict[str, AgentProfile] = {}
        # Default registration for simulation
        self._register_default_agents()

    def _register_default_agents(self):
        self.agents["Nexus-Planner"] = AgentProfile(
            agent_id="Nexus-Planner", 
            roles=[AgentRole.PLANNER], 
            capabilities=["task_decomposition", "schema_design"]
        )
        self.agents["Nexus-Worker-Alpha"] = AgentProfile(
            agent_id="Nexus-Worker-Alpha", 
            roles=[AgentRole.WORKER], 
            capabilities=["python", "pytest"]
        )
        self.agents["Nexus-Integrator"] = AgentProfile(
            agent_id="Nexus-Integrator", 
            roles=[AgentRole.INTEGRATOR], 
            capabilities=["git_merge", "release_management"]
        )

    def route_task(self, task_type: str, required_capabilities: List[str]) -> Optional[str]:
        """Simple heuristic to find an agent based on capabilities."""
        for agent in self.agents.values():
            if all(cap in agent.capabilities for cap in required_capabilities):
                return agent.agent_id
        return None

    def get_integrator(self) -> str:
        return "Nexus-Integrator"
