from typing import Dict, List, Callable, Any
import logging

logger = logging.getLogger(__name__)

class NexusEventBus:
    """Lightweight in-process pub/sub for cross-system notifications."""
    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to an event type."""
        cls._subscribers.setdefault(event_type, []).append(handler)

    @classmethod
    def publish(cls, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish an event to all subscribers. Errors in handlers do not block execution."""
        for handler in cls._subscribers.get(event_type, []):
            try:
                handler(payload)
            except Exception as e:
                logger.error(f"Event handler error for event {event_type}: {e}")
