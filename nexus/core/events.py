#!/usr/bin/env python3
"""Compatibility facade for the layered event contracts/store."""

from nexus.events.contracts import NexusEvent
from nexus.events.store import EventStore

__all__ = ["NexusEvent", "EventStore"]
