import logging
from typing import Dict, Any, Type, Optional

logger = logging.getLogger("nexus.services.registry")

class ServiceRegistry:
    """
    🔗 Nexus Service Registry
    Unified management for service discovery and lifecycle.
    """
    _services: Dict[str, Type] = {}
    _instances: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, service_class: Type):
        """Register a service class."""
        cls._services[name] = service_class
        logger.debug(f"Registered service: {name} -> {service_class.__name__}")

    @classmethod
    def get(cls, name: str, *args, **kwargs) -> Any:
        """Get or initialize a service instance (Singleton by default)."""
        if name in cls._instances:
            return cls._instances[name]
        
        if name not in cls._services:
            raise ValueError(f"Service '{name}' is not registered.")
        
        service_class = cls._services[name]
        instance = service_class(*args, **kwargs)
        cls._instances[name] = instance
        return instance

    @classmethod
    def reset(cls):
        """Reset the registry (mainly for testing)."""
        cls._instances.clear()

# Global Registry Instance (Optional, or just use class methods)
nexus_service_registry = ServiceRegistry
