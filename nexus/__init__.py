"""📦 Nexus Singularity OS SDK (Minimal Embed)"""

# Composition root (#1923): bind engine/app collaborators onto the core-owned
# ports before any nexus.core module can resolve them. nexus.core never
# imports nexus.engine or nexus.app; those layers register here instead.
from .app.core_ports import install_core_app_ports as _install_core_app_ports
from .client import SwarmClient, run_task, status
from .engine.core_ports import install_core_engine_ports as _install_core_engine_ports

_install_core_engine_ports()
_install_core_app_ports()

__version__ = "28.3.0"
__all__ = ["run_task", "status", "SwarmClient"]
