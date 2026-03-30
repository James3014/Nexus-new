"""Disk cleanup policy configuration.

Defines the thresholds and retention rules for the DiskJanitor service.
"""

import os
from dataclasses import dataclass

@dataclass
class DiskPolicy:
    retention_days: int = 90
    max_log_size_mb: int = 50
    max_cache_entries: int = 10000
    max_registry_rows: int = 50000
    vacuum_threshold: int = 1000
    
    @classmethod
    def from_env(cls) -> "DiskPolicy":
        """Load configuration from environment variables."""
        return cls(
            retention_days=int(os.environ.get("NEXUS_DISK_RETENTION_DAYS", "90")),
            max_log_size_mb=int(os.environ.get("NEXUS_MAX_LOG_SIZE_MB", "50")),
            max_cache_entries=int(os.environ.get("NEXUS_MAX_CACHE_ENTRIES", "10000")),
            max_registry_rows=int(os.environ.get("NEXUS_MAX_REGISTRY_ROWS", "50000")),
            vacuum_threshold=int(os.environ.get("NEXUS_VACUUM_THRESHOLD", "1000"))
        )
