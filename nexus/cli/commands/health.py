import click
from nexus.cli.utils import _get_service, REPO_ROOT, _log_perf_span, _io_queue

import warnings as _archived_warnings

_archived_warnings.warn(
    "ARCHIVED 2026-10-13 (#1906): never-registered CLI module (nexus/cli/commands/*); live commands live in scripts/engine/commands; see ARCHIVED_2026-10-13.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

@click.group(name="health")
def health_group():
    """🧬 系統健康度與技能掃描"""
    pass

@health_group.command("report")
@click.option("--workspace", default=".", help="Workspace root")
def report(workspace: str):
    """🧬 [Skills-Health] 掃描技能密度與純度報告"""
    _get_service().health_report(workspace)
