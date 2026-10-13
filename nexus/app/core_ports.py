"""App-side bindings for the ports declared in ``nexus.core.layer_ports`` (#1923).

The dependency points app -> core; see ``nexus.engine.core_ports``.
"""

from __future__ import annotations

from nexus.core.layer_ports import bind_lazy_ports

# port name -> (app module, attribute)
CORE_APP_PORTS: dict[str, tuple[str, str]] = {
    # nexus.core.capability_executor_registry
    "nightshift.AutoResearchNightShift": (
        "nexus.app.nightshift_runner_service",
        "AutoResearchNightShift",
    ),
    "nightshift.compute_time_budget": (
        "nexus.app.nightshift_runner_service",
        "compute_time_budget",
    ),
    "learn_scheduler.LearnSchedulerService": (
        "nexus.app.learn_scheduler_service",
        "LearnSchedulerService",
    ),
}


def install_core_app_ports() -> None:
    """Bind every app collaborator core uses. Idempotent."""
    bind_lazy_ports(CORE_APP_PORTS)
