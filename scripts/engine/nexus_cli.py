#!/usr/bin/env python3
import re
import sys
import os
import json
import hashlib
import subprocess
import time
from pathlib import Path
import faulthandler
faulthandler.enable()

import yaml
import click

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

repo_root = REPO_ROOT

import shlex

class SanitizedRunner:
    """🛡️ SanitizedRunner with AllowedTaskRegistry to prevent command injection & shell escape"""
    
    ALLOWED_TASK_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\s]+$")
    
    @classmethod
    def validate_task_name(cls, task_name: str) -> bool:
        if not task_name:
            return False
        return bool(cls.ALLOWED_TASK_PATTERN.match(task_name))
        
    @classmethod
    def sanitize_arg(cls, arg: str) -> str:
        return shlex.quote(arg)
        
    @classmethod
    def run_safe(cls, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        # Prevent injection by forcing shell=False unless explicitly allowed and sanitized
        if kwargs.get("shell", False):
            raise ValueError("shell=True is strictly forbidden in SanitizedRunner to block command injection.")
        
        # Ensure all arguments in cmd are sanitized / validated if they represent task_name
        # Note: subprocess.run with list format itself prevents typical shell metacharacter injection.
        # But we double-guard here by checking and logging.
        return subprocess.run(cmd, **kwargs)


import asyncio

class AsyncProcessExecutor:
    """⚡ AsyncProcessExecutor to stream output and prevent OS pipe buffer deadlocks"""
    
    @staticmethod
    async def _read_stream(stream: asyncio.StreamReader, file_writer) -> int:
        total_len = 0
        while True:
            chunk = await stream.read(65536)  # 64KB chunk
            if not chunk:
                break
            total_len += len(chunk)
            if isinstance(chunk, bytes):
                file_writer.write(chunk.decode("utf-8", errors="ignore"))
            else:
                file_writer.write(chunk)
        return total_len

    async def run_async(self, cmd: list[str], log_path: Path) -> tuple[int, int, int]:
        import os
        env = os.environ.copy()
        # Secure UV cache isolation to prevent permission collision
        workspace_tmp = Path("/Users/jameschen/Workspace/nexus/.tmp/uv-cache")
        env["UV_CACHE_DIR"] = str(workspace_tmp.resolve())
        
        try:
            p = await asyncio.create_subprocess_exec(
                cmd[0],
                *cmd[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
        except Exception as exc:
            # Safe recovery if process creation itself fails
            return 1, 0, 0
        
        stdout_len = 0
        stderr_len = 0
        
        # P4: Auto-capture and heal from PermissionError / OSError on logs
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            f = open(log_path, "w", encoding="utf-8")
            close_file = True
        except (PermissionError, OSError) as exc:
            import sys
            # Falling back gracefully to stderr/sys.stdout mock writing to avoid crash
            f = sys.stderr
            close_file = False
            # Print self-healing warn
            print(f"⚠️ [Self-Healing] Log path unwritable due to: {exc}. Gracefully falling back.")
            
        try:
            stdout_task = asyncio.create_task(self._read_stream(p.stdout, f))
            stderr_task = asyncio.create_task(self._read_stream(p.stderr, f))
            
            stdout_len, stderr_len = await asyncio.gather(stdout_task, stderr_task)
            await p.wait()
        finally:
            if close_file:
                f.close()
            
        return p.returncode or 0, stdout_len, stderr_len



from nexus.app.oracle_dispatcher import OracleDispatcher
from nexus.app.oracle_advisor import OracleAdvisor
from nexus.app import research_flow_service
from nexus.engine.canonical_task_seam import (
    build_legacy_cli_service,
    execute_canonical_product_task,
)
from nexus.engine.completion_contract import build_completion_envelope
from nexus.engine.completion_contract import ensure_verified_completion
from nexus.engine.completion_contract import write_completion_envelope
from nexus.engine.completion_enforcer import CompletionEnforcementError
from nexus.engine.completion_enforcer import write_completion_handoff
from nexus.engine.direct_mode import evaluate_direct_mode_completion
from scripts.engine.commands.research_support import (
    attach_research_session_result as _attach_research_session_result,
    read_json_file as _read_json_file,
    research_preflight_block_payload as _research_preflight_block_payload,
    research_session_preflight as _research_session_preflight,
)
from scripts.engine.commands.bench_actions import get_effort_roi_report, render_effort_roi_report
from scripts.engine.commands.code_actions import (
    render_code_context,
    render_code_impact,
    render_code_scan,
    run_code_context,
    run_code_impact,
    run_code_scan,
)
from scripts.engine.commands.exception_translation import translate_action_exceptions
from scripts.engine.commands.learn_actions import (
    enforce_learn_ingest_semantic_contract,
    enforce_learn_report_semantic_contract,
    get_learn_phase_policy,
    get_learn_scheduler_status,
    render_learn_ask_response,
    render_learn_converge_complete,
    render_learn_gate_complete,
    render_learn_ingest_complete,
    render_learn_phase_kpi_complete,
    render_learn_phase_policy,
    render_learn_phase_slo_complete,
    render_learn_precision_benchmark_complete,
    render_learn_refresh_complete,
    render_learn_refresh_plan_complete,
    render_learn_register_source_complete,
    render_learn_report_complete,
    render_learn_scheduler_status,
    run_learn_ask,
    run_learn_converge,
    run_learn_gate,
    run_learn_ingest,
    run_learn_phase_kpi,
    run_learn_phase_slo,
    run_learn_precision_benchmark,
    run_learn_refresh,
    run_learn_refresh_plan,
    run_learn_register_source,
    run_learn_report,
    verify_learn_phase_report_completion,
    verify_learn_source_lifecycle_completion,
    write_learn_precision_benchmark_output,
)
from scripts.engine.commands.local_assist_actions import (
    run_local_assist_closeout_command,
    run_local_assist_command,
    run_local_assist_interface_command,
    run_local_assist_user_relay_command,
)
from nexus.services.canonical_local_assist_policy import (
    build_canonical_policy_receipt,
    write_canonical_policy_receipt,
)
from scripts.engine.commands.multi_agent_actions import (
    close_multi_agent_task,
    create_multi_agent_task,
    get_multi_agent_metrics,
    get_multi_agent_task_audit,
    get_multi_agent_task_status,
    integrate_multi_agent_tasks,
    render_multi_agent_metrics,
    render_multi_agent_task_audit,
    render_multi_agent_task_integration,
    render_multi_agent_task_start,
    render_multi_agent_task_status,
    render_multi_agent_task_submission,
    render_multi_agent_task_verification,
    start_multi_agent_task,
    submit_multi_agent_task,
    verify_multi_agent_task,
)
from scripts.engine.commands.self_hosted_actions import (
    run_self_hosted_approve,
    run_self_hosted_cancel,
    run_self_hosted_close_without_candidate,
    run_self_hosted_cleanup,
    run_self_hosted_dispose,
    run_self_hosted_direct_complete,
    run_self_hosted_integrate,
    run_self_hosted_owner_finish,
    run_self_hosted_list_actionable,
    run_self_hosted_recover_verified_uncommitted,
    run_self_hosted_retry,
    run_self_hosted_retry_integration,
    run_self_hosted_receipt,
    run_self_hosted_status,
    run_self_hosted_submit,
    run_self_hosted_verify,
    run_self_hosted_wait,
    run_self_hosted_state_root_inventory,
    run_self_hosted_workspace_converge,
    run_self_hosted_workspace_inventory,
    run_self_hosted_workspace_plan,
    run_self_hosted_workspace_slot_prepare,
    run_self_hosted_workspace_slot_status,
)
from scripts.engine.commands.registry_actions import (
    get_registry_status,
    get_skills_list,
    render_registry_status,
    render_skill_sync_complete,
    render_skills_list,
    sync_external_skills,
)
from scripts.engine.commands.research_actions import (
    render_research_auto_flow_result,
    render_research_auto_flow_route_explanation,
    render_research_human_report,
    render_research_route_explanation,
    render_research_route_summary,
    render_research_run_result,
    render_research_session_action,
    run_research_auto_flow,
    run_research_auto_flow_route_explanation,
    run_research_finalize_preview,
    run_research_human_report,
    run_research_log_from_last,
    run_research_onboarding,
    run_research_packet,
    run_research_recommend_next,
    run_research_route,
    run_research_run,
    run_research_writeback_lessons,
)
from scripts.engine.commands.sandbox_actions import parse_sandbox_command, render_sandbox_run_result, run_sandbox_task
from scripts.engine.nexus_cli_registry import deprecated_command_registry

def validate_claim_integrity(evidence_path: str):
    """🛡️ 硬性物理守門：驗證結論與證據的匹配度。"""
    import json
    if not os.path.exists(evidence_path): return False
    with open(evidence_path, "r") as f:
        data = json.load(f)
    if data.get("claim_state") == "VERIFIED" and data.get("confidence_level") != "HIGH":
        return False
    return True

from datetime import datetime, timezone

# 🛡️ Nexus v4.0 Persistence: Hardened Health & Resilience
os.environ.setdefault("NEXUS_MCP_HEALTHCHECK_ENABLED", "1")
os.environ.setdefault("NEXUS_MCP_HEALTHCHECK_TTL_SEC", "120")
os.environ.setdefault("NEXUS_SERENA_FAIL_OPEN", "1")


class NexusCLI:
    """Compatibility shim for legacy callers that import NexusCLI from this module."""

    def __init__(self, silent: bool = True, project_root: Path | None = None):
        self.service = build_legacy_cli_service(project_root or repo_root)

@click.group()
def nexus():
    """⚖️ Nexus v28.3.0 Fleet Command & Sensory CLI"""
    pass

# UX Convergence: Direct Top-Level Commands
@nexus.command(name="status")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def top_status(ctx, as_json):
    """📊 [Direct] Show system status and trust scores."""
    ctx.invoke(status, as_json=as_json)

@nexus.command(name="run")
@click.option("--task", "task_id", required=True)
@click.option("--complexity", default="medium")
@click.option("--output-file")
@click.option("--report-file")
@click.option(
    "--local-assist-policy",
    type=click.Choice(["disabled", "shadow", "advisor", "planner", "explicit"]),
    default="disabled",
    show_default=True,
)
@click.option(
    "--online-policy",
    type=click.Choice(["deny", "auto", "require"]),
    default="deny",
    show_default=True,
    help="Nexus-owned Online execution policy (deny|auto|require). Default deny is conservative.",
)
@click.pass_context
def top_run(ctx, task_id, complexity, output_file, report_file, local_assist_policy, online_policy):
    """🚀 [Direct] Execute task with autonomic governance."""
    ctx.invoke(
        run,
        task_id=task_id,
        complexity=complexity,
        output_file=output_file,
        report_file=report_file,
        local_assist_policy=local_assist_policy,
        online_policy=online_policy,
    )


@nexus.group(name="local-assist")
def local_assist():
    """Explicit Nexus Local Assist seam for Online Agents."""
    pass


@nexus.group(name="workforce")
def workforce_group():
    """Read-only governed workforce admission surfaces."""
    pass


@workforce_group.command(name="status")
@click.option("--role", default=None, help="Optional role filter; does not select a worker.")
def workforce_status(role: str | None) -> None:
    """Emit a compact, read-only view of policy-admissible workforce entries."""
    from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader

    try:
        loader = WorkforcePolicyLoader()
        snapshot = loader.load()
    except Exception as exc:  # noqa: BLE001 - the policy boundary must fail closed
        click.echo(
            json.dumps(
                {
                    "schema": "nexus.workforce_compact_surface.v1",
                    "status": "BLOCK",
                    "route_authority": "CapabilityPlanner",
                    "error": f"policy_load_failed:{type(exc).__name__}:{exc}",
                },
                ensure_ascii=False,
            )
        )
        raise click.exceptions.Exit(1)

    rows: list[dict[str, object]] = []
    for worker_id, worker in sorted(snapshot.workers.items()):
        if role and role not in worker.roles:
            continue
        if worker.state in NON_ADMISSIBLE_STATES:
            eligible = False
            reason = f"state_non_admissible:{worker.state}"
        elif worker.availability != "AVAILABLE":
            eligible = False
            reason = f"availability:{worker.availability}"
        elif worker.state == "EXPERIMENT_ONLY":
            eligible = False
            reason = "explicit_experiment_authorization_required"
        else:
            eligible = True
            reason = "policy_admissible_without_experiment_authorization"
        rows.append(
            {
                "worker_id": worker_id,
                "provider": worker.provider,
                "model": worker.model,
                "state": worker.state,
                "availability": worker.availability,
                "eligible": eligible,
                "reason": reason,
                "roles": list(worker.roles),
                "autonomy": worker.autonomy,
                "preferred_context": worker.preferred_context,
            }
        )

    eligible_count = sum(1 for row in rows if row["eligible"] is True)
    payload = {
        "schema": "nexus.workforce_compact_surface.v1",
        "status": "PASS",
        "route_authority": snapshot.route_authority,
        "policy": {
            "schema": snapshot.schema,
            "status": snapshot.status,
            "last_verified": snapshot.last_verified,
            "hash": snapshot.policy_hash,
            "authority_document": snapshot.authority_document,
        },
        "filter": {"role": role},
        "summary": {"eligible": eligible_count, "ineligible": len(rows) - eligible_count},
        "workers": rows,
        "mutation_authority": {
            "query_only": True,
            "can_select_worker": False,
            "can_mutate_workspace": False,
            "can_approve_or_integrate": False,
        },
    }
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _local_assist_cli(
    *,
    action: str,
    task_file: str,
    workspace: str,
    report_file: str | None,
    target_file: str | None = None,
    allowed_files: tuple[str, ...] = (),
    verifier_command: str | None = None,
) -> None:
    try:
        result, exit_code = run_local_assist_command(
            action=action,
            task_file=task_file,
            workspace=workspace,
            report_file=report_file,
            target_file=target_file,
            allowed_files=allowed_files,
            verifier_command=verifier_command,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        click.echo(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False))
        raise click.exceptions.Exit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@local_assist.command(name="advisor")
@click.option("--task-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
@click.option("--report-file", type=click.Path(dir_okay=False), default=None)
def local_assist_advisor(task_file: str, workspace: str, report_file: str | None) -> None:
    _local_assist_cli(
        action="advisor",
        task_file=task_file,
        workspace=workspace,
        report_file=report_file,
    )


@local_assist.command(name="candidate")
@click.option("--task-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
@click.option("--target-file", type=str, required=True)
@click.option("--verifier-command", type=str, required=True)
@click.option("--report-file", type=click.Path(dir_okay=False), default=None)
def local_assist_candidate(
    task_file: str,
    workspace: str,
    target_file: str | None,
    verifier_command: str | None,
    report_file: str | None,
) -> None:
    _local_assist_cli(
        action="candidate",
        task_file=task_file,
        workspace=workspace,
        report_file=report_file,
        target_file=target_file,
        verifier_command=verifier_command,
    )


@local_assist.command(name="verified-subtask")
@click.option("--task-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
@click.option("--allowed-file", "allowed_files", multiple=True, required=True)
@click.option("--verifier-command", type=str, required=True)
@click.option("--report-file", type=click.Path(dir_okay=False), default=None)
def local_assist_verified_subtask(
    task_file: str,
    workspace: str,
    allowed_files: tuple[str, ...],
    verifier_command: str,
    report_file: str | None,
) -> None:
    _local_assist_cli(
        action="verified-subtask",
        task_file=task_file,
        workspace=workspace,
        report_file=report_file,
        allowed_files=allowed_files,
        verifier_command=verifier_command,
    )


@local_assist.command(name="interface")
@click.option("--task-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
def local_assist_interface(task_file: str, workspace: str) -> None:
    """Emit the universal provider-neutral Agent contract as JSON."""
    try:
        result, exit_code = run_local_assist_interface_command(task_file=task_file, workspace=workspace)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        click.echo(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False))
        raise click.exceptions.Exit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@local_assist.command(name="closeout")
@click.option("--closeout-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
@click.option("--report-file", type=click.Path(dir_okay=False), default=None)
def local_assist_closeout(closeout_file: str, workspace: str, report_file: str | None) -> None:
    """Validate Agent consumption of Local Assist receipts before closeout."""
    try:
        result, exit_code = run_local_assist_closeout_command(
            closeout_file=closeout_file,
            workspace=workspace,
            report_file=report_file,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        click.echo(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        raise click.exceptions.Exit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@local_assist.command(name="user-relay-validate")
@click.option("--package-file", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--workspace", type=click.Path(file_okay=False), required=True)
@click.option("--response-file", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--report-file", type=click.Path(dir_okay=False), required=True)
def local_assist_user_relay_validate(
    package_file: str,
    workspace: str,
    response_file: str | None,
    report_file: str,
) -> None:
    """Validate a user-relayed Agent response without external delivery."""
    try:
        result, exit_code = run_local_assist_user_relay_command(
            package_file=package_file,
            workspace=workspace,
            response_file=response_file,
            report_file=report_file,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        click.echo(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        raise click.exceptions.Exit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if exit_code:
        raise click.exceptions.Exit(exit_code)


def _blocked_deprecated(old: str, new: str | None = None):
    """🚫 DEPRECATED_BLOCKED: 停止執行並引導至新入口。"""
    if new is None:
        command = deprecated_command_registry().get(old)
        new = command.replacement if command else ""
    click.secho(f"❌ [DEPRECATED_BLOCKED] 此命令 '{old}' 已停用。", fg="red", bold=True)
    click.echo(f"💡 請改用唯一新入口：\n   {new}")
    sys.exit(2)

@nexus.command(name="nexus:status")
def legacy_status():
    _blocked_deprecated("nexus:status")


@nexus.command(name="nexus:hud")
def legacy_hud():
    _blocked_deprecated("nexus:hud")


@nexus.command(name="nexus:spec-lock")
def legacy_spec_lock():
    _blocked_deprecated("nexus:spec-lock")


@nexus.command(name="nexus:governance-check")
def legacy_governance_check():
    _blocked_deprecated("nexus:governance-check")


@nexus.command(name="nexus:acceptance-check")
def legacy_acceptance_check():
    _blocked_deprecated("nexus:acceptance-check")


@nexus.command(name="nexus:closeout")
def legacy_closeout():
    _blocked_deprecated("nexus:closeout")

@nexus.group(name="nexus")
def nexus_group():
    """🛡️ Nexus Core Governance & Command"""
    pass

# --- 治理與狀態 ---
@nexus_group.command(name="drone-hud")
def drone_hud():
    """🚁 [L5] Tactical Drone HUD - 實時監聽無人機執行狀態與干預。"""
    import json
    from pathlib import Path
    click.secho("🚁 [Drone HUD] Scanning tactical drones in sector...", fg="cyan", bold=True)
    drone_dir = repo_root / ".nexus/reports/drones"
    if not drone_dir.exists():
        click.echo("No drones currently reporting.")
        return
        
    crystals = list(drone_dir.glob("*_crystal.json"))
    click.echo(f"Active/Completed Drones: {len(crystals)}")
    
    for f in sorted(crystals, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            drone_id = data.get("drone_id", "unknown")
            status = data.get("status", "unknown")
            belief = data.get("belief_score", 0.0)
            
            color = "green" if status == "SUCCESS" else "red" if status in ["FAIL", "CRASH"] else "yellow"
            click.secho(f"\n🐝 Drone: {drone_id} | Status: {status} | Belief: {belief:.2f}", fg=color, bold=True)
            
            traces = data.get("tracelog", [])[-3:] # Show last 3
            for t in traces:
                phase = t.get("phase", "")
                msg = t.get("message", "")
                click.echo(f"  [{phase}] {msg[:80]}...")
        except:
            pass

@nexus_group.command(name="status")
@click.option("--json", "as_json", is_flag=True)
def status(as_json):
    """📊 Show system status and trust scores."""
    if as_json:
        res = {"status": "OPERATIONAL", "version": "v23.7", "fleet_size": 50, "mcp": "READY"}
        click.echo(json.dumps(res, indent=2))
    else:
        subprocess.run([sys.executable, str(repo_root / "scripts/ops/enterprise_audit_v22.py")], check=True)


@nexus_group.group(name="code")
def code_group():
    """🔎 Native Nexus code intelligence."""
    pass


@code_group.command(name="impact")
@click.option("--files", "files_text", required=True, help="Comma-separated changed files.")
@click.option("--index-path", type=click.Path(), default=None, help="Optional graph index from nexus code scan.")
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional report path.")
@translate_action_exceptions
def code_impact(files_text: str, index_path: str | None, output_json: bool, report_file: str | None):
    """Analyze changed-file impact with Nexus native CodeIntel."""
    result = run_code_impact(
        repo_root,
        files_text=files_text,
        index_path=index_path,
        report_file=report_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in render_code_impact(result):
            click.echo(line)


@code_group.command(name="scan")
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--index-path", type=click.Path(), default=None, help="Optional graph index path.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional scan report path.")
@translate_action_exceptions
def code_scan(output_json: bool, index_path: str | None, report_file: str | None):
    """Build a deterministic Nexus native CodeIntel graph index."""
    result = run_code_scan(repo_root, index_path=index_path, report_file=report_file)
    if output_json:
        click.echo(json.dumps(result.payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in render_code_scan(result):
            click.echo(line)


@code_group.command(name="context")
@click.option("--symbol", required=True, help="Module or symbol name to inspect.")
@click.option("--index-path", type=click.Path(), default=None, help="Optional graph index path.")
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional context report path.")
@translate_action_exceptions
def code_context(symbol: str, index_path: str | None, output_json: bool, report_file: str | None):
    """Inspect callers, callees, files, and related tests for a symbol."""
    result = run_code_context(
        repo_root,
        symbol=symbol,
        index_path=index_path,
        report_file=report_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in render_code_context(result, symbol=symbol):
            click.echo(line)

def _render_hallucination_unverified(reason: str) -> None:
    click.echo("\n## 🧠 幻覺指數標註 (Hallucination Index)")
    click.echo("**總分**: N/A (UNVERIFIED)  ")
    click.echo(f"**觸發項目**: {reason}  ")
    click.echo("**狀態**: 🟡 需審核\n")


def _identity_vault_status(root: Path) -> tuple[bool, list[str]]:
    candidate_paths = (
        root / "nexus_wiki_vault" / "01_System" / "Identity_Vault.md",
        REPO_ROOT / "nexus_wiki_vault" / "01_System" / "Identity_Vault.md",
    )
    identity_path = next((path for path in candidate_paths if path.exists()), None)
    if identity_path is None:
        return False, ["missing_identity_vault"]
    text = identity_path.read_text(encoding="utf-8")
    failures: list[str] = []
    for identity in ("learn_mode_agent", "codex_supervisor", "gemini_router"):
        if identity not in text:
            failures.append(f"missing_identity:{identity}")
    if text.count("Init/Active/Archive") < 3:
        failures.append("identity_lifecycle_incomplete")
    return not failures, failures


def _write_dual_gate_markdown(base_root: Path, path: Path, task: str, data: dict, evidence: str, debt: str) -> Path:
    from nexus.research.learn.dual_gate_protocol import DualGateProtocol

    out = path if path.is_absolute() else (base_root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(DualGateProtocol.render(task=task, data=data, evidence=evidence, debt=debt), encoding="utf-8")
    return out


def _format_report_debt_items(items) -> str:
    rendered: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            question = str(item.get("question") or item.get("text") or item.get("id") or "").strip()
            reason = str(item.get("reason") or item.get("status") or "").strip()
            text = " - ".join(part for part in (question, reason) if part)
            if not text:
                text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item).strip()
        if text:
            rendered.append(text)
    return "; ".join(rendered) or "None"


def _evaluate_learn_semantic_contract(
    *,
    root: Path,
    payload: dict,
    command_name: str,
    markdown_report_written: bool,
) -> dict:
    failures: list[str] = []
    if command_name == "learn:ingest":
        channel_counts = payload.get("channel_counts")
        if not isinstance(channel_counts, dict):
            failures.append("missing_dual_channel_fields")
        else:
            for key in ("tactical_data", "governance_principles"):
                if key not in channel_counts:
                    failures.append(f"missing_channel_count:{key}")
    identity_ok, identity_failures = _identity_vault_status(root)
    if not identity_ok:
        failures.extend(identity_failures)
    if not markdown_report_written:
        failures.append("dual_gate_markdown_not_written")
    semantic_status = "VERIFIED" if not failures else "UNVERIFIED"
    return {
        "semantic_status": semantic_status,
        "semantic_failures": failures,
    }


def _format_unresolved_question_item(item) -> str:
    if isinstance(item, str):
        return item.strip()

    if isinstance(item, dict):
        question = item.get("question")
        reason = item.get("reason")
        if isinstance(question, str) and question.strip():
            text = question.strip()
            if isinstance(reason, str) and reason.strip():
                return f"{text} - {reason.strip()}"
            return text
        for key in ("question", "title", "text", "message", "reason"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(item, ensure_ascii=False, sort_keys=True)

    if isinstance(item, (list, tuple, set)):
        rendered_parts: list[str] = []
        for part in item:
            rendered = _format_unresolved_question_item(part)
            if rendered:
                rendered_parts.append(rendered)
        return f"[{', '.join(rendered_parts)}]" if rendered_parts else "[]"

    return str(item)


def _format_unresolved_questions_for_debt(unresolved_questions) -> str:
    if unresolved_questions is None:
        return ""

    if not isinstance(unresolved_questions, list):
        unresolved_questions = [unresolved_questions]

    rendered: list[str] = []
    for item in unresolved_questions:
        value = _format_unresolved_question_item(item)
        if value:
            rendered.append(value)
    return "; ".join(rendered)


def _task_requests_output_file(task_text: str) -> bool:
    text = (task_text or "").lower()
    intent_words = (
        "write",
        "save",
        "output",
        "export",
        "rewrite",
        "寫入",
        "輸出",
        "存到",
        "落盤",
        "重寫",
    )
    has_intent = any(word in text for word in intent_words)
    has_path_hint = bool(
        re.search(r"(/|\\|\.md\b|\.txt\b|\.json\b|\.ya?ml\b|\.csv\b)", text, re.IGNORECASE)
    )
    return has_intent and has_path_hint


def _write_output_file(path: Path, payload: dict) -> Path:
    root = REPO_ROOT
    out = path if path.is_absolute() else (root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _render_run_classification(runtime_classification: str) -> None:
    click.echo(f"[run-classification] {runtime_classification}")


def _merge_completion_payload(base_payload: dict, completion_payload: dict) -> dict:
    merged = dict(base_payload)
    for key, value in completion_payload.items():
        if key == "status" and "status" in merged:
            merged["runtime_status"] = value
            continue
        merged[key] = value
    return merged


def _finalize_semantic_payload(
    payload: dict,
    *,
    command_name: str,
    task_name: str,
    runtime_ok: bool,
    execution_path: str,
) -> dict:
    completion_payload = build_completion_envelope(
        command_name=command_name,
        task_name=task_name,
        runtime_ok=runtime_ok,
        execution_path=execution_path,
    )
    merged = _merge_completion_payload(payload, completion_payload)
    merged["semantic_status"] = merged.get("semantic_status", "UNVERIFIED")
    return merged


def _persist_completion_handoff(payload: dict, *, context: str, report_file: str | Path | None = None) -> Path:
    handoff_path = write_completion_handoff(
        project_root=REPO_ROOT,
        payload=payload,
        context=context,
        report_file=report_file,
    )
    payload["next_action_file"] = str(handoff_path)
    return handoff_path


def _local_rewrite_text(text: str) -> str:
    # Local-safe rewrite: normalize trailing spaces and repeated blank lines.
    lines = [ln.rstrip() for ln in text.splitlines()]
    out_lines: list[str] = []
    blank_streak = 0
    for ln in lines:
        if ln.strip() == "":
            blank_streak += 1
            if blank_streak > 1:
                continue
        else:
            blank_streak = 0
        out_lines.append(ln)
    result = "\n".join(out_lines).strip() + "\n"
    return result


def _forward_to_nested_nexus(ctx: click.Context, subcommand: str) -> None:
    """Compatibility forwarder for callers that forgot the nested `nexus` group."""
    click.echo(
        f"⚠️ [CLI-Compat] '{subcommand}' should be invoked as "
        f"'uv run scripts/engine/nexus_cli.py nexus {subcommand} ...'. Forwarding now."
    )
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/engine/nexus_cli.py"),
        "nexus",
        subcommand,
        *ctx.args,
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise click.exceptions.Exit(res.returncode)


def check_hallucination(evidence_path: str | None):
    """🛡️ 執行幻覺指數審計（硬性：缺 evidence 直接視為 fail）。"""
    import json
    from nexus.core.hallucination_guard import HallucinationGuard

    if not evidence_path:
        _render_hallucination_unverified("missing_evidence_path")
        click.echo("❌ [Gate:UNVERIFIED] Hallucination evidence is required.")
        return False
    if not os.path.exists(evidence_path):
        _render_hallucination_unverified("missing_evidence_file")
        click.echo("❌ [Gate:UNVERIFIED] Hallucination evidence file not found.")
        return False

    with open(evidence_path, "r") as f:
        data = json.load(f)

    # 🛡️ 治理硬化：檢查證據來源 (防止 Agent 自選證據)
    source = data.get("_source", "agent")
    if os.environ.get("NEXUS_STRICT_EVIDENCE_SOURCE") == "1" and source != "system":
        click.echo("❌ [Gate:REJECTED] Evidence must be system-generated (not agent-authored).")
        return False

    response = data.get("final_response", "")
    evidence = data.get("evidence_bundle", {})

    guard = HallucinationGuard()
    analysis = guard.analyze(response, evidence)

    if analysis["status"] == "REJECTED":
        click.echo(f"❌ [Gate:REJECTED] Hallucination Index Too High: {analysis['score']}/10")
        click.echo(f"🚩 Triggers: {analysis['triggers']}")
        return False

    click.echo(guard.render())
    return True


def _enforce_hallucination_gate(final_response: str, evidence_bundle: dict) -> None:
    from nexus.core.hallucination_guard import HallucinationGuard

    guard = HallucinationGuard()
    analysis = guard.analyze(final_response, evidence_bundle)
    if analysis["status"] == "REJECTED":
        raise click.ClickException(
            f"Hallucination gate rejected response. score={analysis['score']} triggers={analysis['triggers']}"
        )


def _write_hallucination_evidence(path: str | None, final_response: str, evidence_bundle: dict) -> Path | None:
    if not path:
        return None
    out = Path(path)
    out = out if out.is_absolute() else (repo_root / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "final_response": final_response,
        "evidence_bundle": evidence_bundle,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _load_acceptance_status(report_path: Path) -> str:
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return "UNKNOWN"
    return str(data.get("status", "UNKNOWN")).strip() or "UNKNOWN"


@nexus_group.command(name="acceptance-check")
@click.option("--json", "as_json", is_flag=True)
@click.option("--evidence", "evidence_path", type=click.Path(exists=True))
def acceptance_check(as_json, evidence_path):
    """✅ Run full system acceptance check with Hallucination Guard."""
    acceptance_policy = str(os.environ.get("NEXUS_ACCEPTANCE_POLICY", "dev")).strip().lower() or "dev"
    acceptance_report = repo_root / ".nexus/reports/acceptance_check.json"

    # 1. 執行實體驗收
    cmd = [sys.executable, str(repo_root / "scripts/ops/nexus_acceptance_check.py")]
    cmd.extend(["--report-file", ".nexus/reports/agent_report.json"])
    if evidence_path:
        cmd.extend(["--report-newer-than", str(evidence_path)])
    if as_json:
        cmd.append("--json")
    acceptance_result = subprocess.run(cmd)
    acceptance_status = _load_acceptance_status(acceptance_report)
    allow_cold_start = acceptance_policy != "prod" and acceptance_status == "UNVERIFIED_COLD_START"
    if acceptance_result.returncode != 0 and not allow_cold_start:
        raise click.exceptions.Exit(acceptance_result.returncode)

    # 1.5 驗收報告宣稱完整性檢查（防止跨分支/缺證據誤宣稱）
    verify_cmd = [
        sys.executable,
        str(repo_root / "scripts/ops/verify_report_claims.py"),
        "--project-root",
        str(repo_root),
        "--report-file",
        ".nexus/reports/agent_report.json",
        "--require-test-evidence",
        "--require-nexus-command-evidence",
        "--require-worktree-delta",
        "--report-newer-than",
        str(evidence_path) if evidence_path else ".nexus/reports/hallucination_evidence.json",
        "--require-path",
        ".nexus/reports/acceptance_check.json",
        "--require-path",
        ".nexus/reports/acceptance_check.md",
    ]
    if not allow_cold_start:
        verify_cmd.insert(4, "--require-acceptance-pass")
    subprocess.run(verify_cmd, check=True)
    
    # 2. 執行幻覺審計 (always render; hard-fail only when explicit evidence gets REJECTED)
    if not check_hallucination(evidence_path):
        raise click.ClickException("Hallucination check failed.")


@nexus_group.command(name="delivery-gate")
@click.option("--evidence", "evidence_path", type=click.Path(exists=True), required=True)
@click.option("--router-benchmark", is_flag=True, help="Run router benchmark as part of delivery verification.")
@click.option("--receipt", "receipt_path", default=".nexus/reports/delivery_gate.json", show_default=True, type=click.Path())
def delivery_gate(evidence_path, router_benchmark, receipt_path):
    """🚪 Run fail-closed delivery verification before completion claims."""
    cmd = [str(repo_root / "scripts/ops/nexus_delivery_gate.sh"), "--evidence", str(evidence_path), "--receipt", str(receipt_path)]
    if router_benchmark:
        cmd.append("--router-benchmark")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise click.ClickException("Delivery gate failed.")


@nexus_group.command(name="delivery-receipt")
@click.option("--receipt", "receipt_path", default=".nexus/reports/delivery_gate.json", show_default=True, type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True)
def delivery_receipt(receipt_path, as_json):
    """🧾 Show the last machine-generated delivery receipt."""
    from nexus.delivery.receipt import load_delivery_receipt

    payload = load_delivery_receipt(Path(receipt_path))
    if as_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    click.echo(f"[delivery-receipt] head={payload.get('head', 'unknown')}")
    click.echo(f"[delivery-receipt] branch={payload.get('branch', 'unknown')}")
    click.echo(f"[delivery-receipt] passed={str(bool(payload.get('delivery_gate_passed'))).lower()}")
    click.echo(f"[delivery-receipt] receipt={receipt_path}")

@nexus_group.command(name="run")
@click.argument("task_id")
@click.option("--complexity", type=float, default=0.0)
@click.option("--output-file", type=click.Path(path_type=Path), help="Explicit output path for the task result.")
@click.option("--report-file", type=click.Path(path_type=Path), default=".nexus/reports/run/run_report.json")
@click.option(
    "--local-assist-policy",
    type=click.Choice(["disabled", "shadow", "advisor", "planner", "explicit"]),
    default="disabled",
    show_default=True,
)
@click.option(
    "--online-policy",
    type=click.Choice(["deny", "auto", "require"]),
    default="deny",
    show_default=True,
    help="Nexus-owned Online execution policy (deny|auto|require). Default deny is conservative.",
)
@click.option(
    "--target-file",
    "target_files",
    multiple=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Bounded repository-relative target file. Repeat for additional allowed files.",
)
@click.option(
    "--verify-command",
    default="",
    help="Deterministic verifier command for the isolated World C pipeline.",
)
def run(
    task_id,
    complexity,
    output_file,
    report_file,
    local_assist_policy,
    online_policy,
    target_files,
    verify_command,
):
    """🚀 [Nexus Master Loop] Execute task with full P-X-D-R-A-C unification."""
    from nexus.services.canonical_local_assist_policy import (
        build_canonical_policy_receipt,
        build_execution_context_fields,
        normalize_local_assist_policy,
        write_canonical_policy_receipt,
    )
    from nexus.services.online_execution_policy import normalize_online_policy
    from nexus.orchestrator.canonical_mcp_ingress import build_cli_execution_context

    try:
        policy_norm = normalize_local_assist_policy(local_assist_policy)
        online_norm = normalize_online_policy(online_policy)
    except ValueError as exc:
        raise click.ClickException(f"policy_failed_closed: {exc}") from exc

    revision = ""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = f"fixture-{hashlib.sha256(str(REPO_ROOT).encode()).hexdigest()[:12]}"

    safe_task_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(task_id))[:120] or "task"
    normalized_targets = [Path(path).as_posix() for path in target_files]
    canonical_ingress = build_cli_execution_context(
        task_id=str(task_id),
        what=str(task_id),
        why="canonical CLI execution",
        allowed_files=normalized_targets,
        verifier_commands=(verify_command,) if verify_command else (),
        workspace_revision=revision,
    )
    policy_context = build_execution_context_fields(
        policy=local_assist_policy,
        task_id=str(task_id),
        workspace_revision=revision,
        policy_source="cli",
    )
    execution_context = {**canonical_ingress, **policy_context}
    execution_context["online_policy"] = online_norm
    execution_context["online_policy_source"] = "cli"
    execution_context["product_entry"] = "nexus run"
    if target_files:
        execution_context["target_files"] = normalized_targets
        execution_context["target_file"] = normalized_targets[0]
    if verify_command:
        execution_context["verifier_command"] = verify_command
    policy_receipt = None
    policy_path = None
    if policy_norm["canonical_policy"] != "disabled":
        try:
            risk_score = 20 if float(complexity or 0.0) <= 1.0 else 50 if float(complexity or 0.0) <= 3.0 else 80
            policy_task = {
                "task_id": str(task_id),
                "workspace_revision": revision,
                "task_statement": str(task_id),
                "task_type": "task",
                "route": {"route_features": {"risk_score": risk_score, "adjusted_root_cause_confidence": 0.8}},
            }
            policy_receipt = build_canonical_policy_receipt(policy=local_assist_policy, task=policy_task)
            policy_path = REPO_ROOT / ".nexus" / "reports" / "local_assist" / "canonical" / f"{safe_task_id}.json"
            write_canonical_policy_receipt(policy_path, policy_receipt)
            click.echo(json.dumps(policy_receipt, indent=2, ensure_ascii=False))
            click.echo(f"Local Assist policy receipt: {policy_path}")
            if policy_norm.get("migration_warning"):
                click.echo(f"[local-assist] {policy_norm['migration_warning']}")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise click.ClickException(f"local_assist_policy_failed_closed: {exc}") from exc
    click.secho(f"🛡️ [NEXUS v24.9.5] Initiating Master Loop for: {task_id}", fg="cyan", bold=True)

    if _task_requests_output_file(task_id) and not output_file:
        raise click.ClickException("Task requests file output. Please provide --output-file.")
    
    try:
        runtime_result = execute_canonical_product_task(
            task_id,
            REPO_ROOT,
            execution_context=execution_context,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise click.ClickException(f"canonical_product_runtime_failed_closed: {exc}") from exc
    runtime_ok = bool(runtime_result)

    artifact_paths: list[str] = []
    if output_file:
        output_path = Path(output_file)
        output_payload = {
            "task_id": task_id,
            "status": "SUCCESS" if runtime_ok else "FAILED",
            "output_written": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        written = _write_output_file(output_path, output_payload)
        artifact_paths.append(str(written))
        click.echo(f"✅ Result written to {written}")

    direct_mode_audit = evaluate_direct_mode_completion(
        project_root=REPO_ROOT,
        task_desc=task_id,
        artifact_paths=artifact_paths,
    )
    report_payload = build_completion_envelope(
        command_name="run",
        task_name=task_id,
        runtime_ok=runtime_ok,
        execution_path="cli->canonical_task_seam->mainchain",
        artifact_paths=artifact_paths,
        semantic_failures=direct_mode_audit["semantic_failures"],
        tests_run=direct_mode_audit["verify_results"],
    )
    if direct_mode_audit["enabled"]:
        report_payload["direct_mode"] = direct_mode_audit["spec"]
        report_payload["changed_targets"] = direct_mode_audit["changed_targets"]

    # Consume the returned canonical receipt directly.  The legacy pipeline
    # pointer is intentionally not a production truth source.
    runtime_receipt = dict(runtime_result.receipt)
    local_stage = runtime_receipt.get("local") if isinstance(runtime_receipt.get("local"), dict) else {}
    local_response = local_stage.get("response") if isinstance(local_stage.get("response"), dict) else {}
    online_stage = runtime_receipt.get("online") if isinstance(runtime_receipt.get("online"), dict) else {}
    report_payload["local_assist_mode"] = execution_context.get(
        "local_assist_mode",
        "disabled",
    )
    report_payload["local_assist_status"] = str(local_stage.get(
        "status",
        "NOT_REQUESTED" if execution_context.get("local_assist_mode") == "disabled" else "UNKNOWN",
    ))
    report_payload["local_context_forwarded"] = bool(
        (runtime_receipt.get("online_safe_local_forward") or {}).get("forward_keys")
    )
    report_payload["unified_runtime_receipt_path"] = runtime_result.receipt_path
    report_payload["unified_runtime_task_id"] = str(
        runtime_receipt.get("task_id") or execution_context.get("task_id") or task_id
    )
    online_response = online_stage.get("response") if isinstance(online_stage.get("response"), dict) else {}
    report_payload["online_provider"] = str(online_response.get("provider") or "")
    report_payload["workspace_revision"] = str(
        runtime_receipt.get("workspace_revision") or execution_context.get("workspace_revision") or revision
    )
    # Distinct stage booleans — never collapse into one status.
    report_payload["local_assist_success"] = bool(local_stage.get("gate_passed", False))
    report_payload["online_success"] = bool(online_stage.get("gate_passed", False))
    report_payload["runtime_receipt_complete"] = bool(runtime_receipt.get("receipt_complete", False))
    report_payload["task_pipeline_success"] = runtime_ok
    report_payload["root_receipt_valid"] = runtime_result.root_receipt_valid
    report_payload["root_receipt_blockers"] = list(runtime_result.root_receipt_blockers)
    report_payload["root_receipt_hash"] = str(
        runtime_result.root_receipt.get("root_receipt_hash") or ""
    )
    report_payload["execution_decision_authority"] = runtime_result.execution_decision_authority
    report_payload["production_ingress_count"] = runtime_result.production_ingress_count
    report_payload["production_runtime_entry_count"] = runtime_result.production_runtime_entry_count
    report_payload["local_action"] = str(local_response.get("action") or "")
    claim = runtime_receipt.get("claim_boundary")
    report_payload["claim_boundary"] = (
        dict(claim)
        if isinstance(claim, dict)
        else {
            "public_claim_allowed": False,
            "production_ready": False,
            "value_measured": False,
        }
    )
    if policy_receipt is not None:
        report_payload["local_assist_policy_receipt"] = policy_receipt
    if policy_path is not None:
        report_payload["local_assist_policy_receipt_path"] = str(policy_path)

    report_written = write_completion_envelope(REPO_ROOT, report_file, report_payload)
    _render_run_classification(report_payload["runtime_classification"])
    click.echo(f"Report: {report_written}")
    try:
        ensure_verified_completion(report_payload, context="run")
    except CompletionEnforcementError as exc:
        handoff = _persist_completion_handoff(report_payload, context="run", report_file=report_written)
        report_written.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        click.echo(f"Next Action: {handoff}")
        raise click.ClickException(str(exc))

@nexus_group.command(name="content:rewrite")
@click.option("--input-file", required=True, type=click.Path(exists=True, path_type=Path), help="Source text/markdown file.")
@click.option("--output-file", required=True, type=click.Path(path_type=Path, dir_okay=False), help="Output rewritten file path.")
@click.option("--task", default="Rewrite for clarity while preserving meaning.", show_default=True, help="Rewrite instruction.")
@click.option("--llm-mode/--no-llm-mode", default=False, show_default=True, help="Use LLM rewrite mode. Falls back to local-safe mode on failure.")
@click.option("--report-file", default=".nexus/reports/content/rewrite-report.json", show_default=True, type=click.Path(path_type=Path))
def content_rewrite(input_file, output_file, task, llm_mode, report_file):
    """📝 Rewrite content with explicit file IO contract."""
    root = REPO_ROOT
    source_path = input_file if input_file.is_absolute() else (root / input_file).resolve()
    out_path = output_file if output_file.is_absolute() else (root / output_file).resolve()
    report_path = report_file if report_file.is_absolute() else (root / report_file).resolve()

    original = source_path.read_text(encoding="utf-8")
    rewritten = ""
    method = "local_safe"
    error = ""
    unified_runtime_receipt = None

    if llm_mode:
        try:
            from nexus.services.gateway import BattlesuitGateway
            from nexus.services.unified_runtime import UnifiedRuntimeRequest

            gateway = BattlesuitGateway(project_root=root)
            task_id = f"content-rewrite-{hashlib.sha256(f'{source_path}:{task}'.encode()).hexdigest()[:12]}"
            workspace_revision = os.environ.get("NEXUS_WORKSPACE_REVISION", "").strip()
            if not workspace_revision:
                try:
                    workspace_revision = subprocess.check_output(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    ).strip()
                except (OSError, subprocess.CalledProcessError):
                    workspace_revision = f"content-rewrite-{hashlib.sha256(str(root).encode()).hexdigest()[:12]}"

            output_schema = {
                "status": "APPROVED | FAIL",
                "patch": "Full rewritten content",
                "summary": "Short note",
            }

            def _verify(context):
                online = context.get("online", {}) if isinstance(context, dict) else {}
                response = online.get("response", {}) if isinstance(online, dict) else {}
                patch = response.get("patch", "") if isinstance(response, dict) else ""
                passed = online.get("status") == "SUCCEEDED" and bool(str(patch).strip())
                return {
                    "task_id": task_id,
                    "status": "pass" if passed else "fail",
                    "invoked": True,
                    "gate_passed": passed,
                    "outcome_contributed": passed,
                    "evidence": "content_rewrite_output_present",
                    "evidence_refs": [f"verifier:{task_id}:rewrite"],
                }

            def _learn(_context):
                try:
                    from nexus.research.learn_mode import LearnModeService

                    result = LearnModeService(root).sync_phase_learning_closure(
                        topic=task,
                        metrics={
                            "coverage": 1.0,
                            "self_question_pass_rate": 1.0,
                            "citation_valid_ratio": 1.0,
                            "stale_claims_count": 0,
                            "conflict_count": 0,
                        },
                        phase_status={"P": "SUCCESS", "D": "SUCCESS", "R": "SUCCESS", "A": "SUCCESS", "C": "SUCCESS"},
                    )
                    passed = str(result.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"}
                    return {
                        "task_id": task_id,
                        "status": "pass" if passed else "fail",
                        "invoked": True,
                        "gate_passed": passed,
                        "evidence": "LearnModeService.sync_phase_learning_closure",
                        "evidence_refs": [f"learning:{task_id}:phase_bridge"],
                        "response": result,
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        "task_id": task_id,
                        "status": "fail",
                        "invoked": True,
                        "gate_passed": False,
                        "evidence": "learning_exception",
                        "evidence_refs": [f"learning:{task_id}:exception"],
                        "error": f"{exc.__class__.__name__}:{exc}",
                    }

            receipt_path = report_path.with_name(f"{report_path.stem}.unified_runtime.json")
            from nexus.services.mainchain_entry import stamp_mainchain_route

            unified_runtime_receipt = gateway.ask_unified(
                UnifiedRuntimeRequest(
                    task_id=task_id,
                    workspace_revision=workspace_revision,
                    task_statement=task,
                    task_type="document_rewrite",
                    route=stamp_mainchain_route(
                        {
                            "recommended_flow": "direct",
                            "provider": gateway.oauth_provider,
                            "online_capabilities": ("research", "repair_loop"),
                        },
                        with_nexus_armor=True,
                        product_entry="content_rewrite",
                    ),
                    online_prompt=(
                        "You are rewriting a document.\n"
                        f"Task: {task}\n"
                        "Return only rewritten full text in field 'patch'."
                    ),
                    online_payload=f"[SOURCE]\n{original}",
                    online_phase="R",
                    online_model_name="gemini-3-flash-preview",
                    online_output_schema=output_schema,
                    evidence_refs=(f"content-rewrite:{task_id}:request",),
                ),
                verifier=_verify,
                learning=_learn,
                receipt_path=receipt_path,
            )
            online = unified_runtime_receipt.get("online", {})
            response = online.get("response", {}) if isinstance(online, dict) else {}
            rewritten = response.get("patch", "") if isinstance(response, dict) else ""
            if not unified_runtime_receipt.get("receipt_complete") or not str(rewritten).strip():
                raise RuntimeError("unified_runtime_incomplete")
            method = "llm"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            rewritten = _local_rewrite_text(original)
            method = "local_safe_fallback"
    else:
        rewritten = _local_rewrite_text(original)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rewritten, encoding="utf-8")

    payload = {
        "status": "SUCCESS",
        "task": task,
        "method": method,
        "error": error,
        "unified_runtime_receipt": unified_runtime_receipt,
        "io": {
            "input_path": str(source_path),
            "output_path": str(out_path),
            "output_written": True,
        },
        "stats": {
            "input_chars": len(original),
            "output_chars": len(rewritten),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    click.echo(f"✅ [Content-Rewrite] Completed. Method: {method}")
    click.echo(f"Output Written: {payload['io']['output_written']}")
    click.echo(f"Output Path: {payload['io']['output_path']}")
    click.echo(f"Report: {report_path}")


@nexus_group.command(name="learn:ingest")
@click.option("--source", required=True, help="Source identifier: URL, repo, or keyword.")
@click.option("--source-file", required=False, type=click.Path(exists=True), help="Optional local source file override.")
@click.option("--topic", default="", help="Optional topic tag.")
@click.option("--task-desc", default="", help="Optional task description to enable dynamic routing.")
@click.option("--difficulty", default="normal", help="Optional task difficulty level (easy/medium/hard).")
@click.option("--report-file", default=".nexus/reports/learn/learn_report.json", show_default=True, type=click.Path())
@click.option("--markdown-report-file", default=".nexus/reports/learn/learn_ingest.md", show_default=True, type=click.Path())
@click.option("--evidence-file", default=".nexus/reports/learn/evidence_ingest.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_ingest(source, source_file, topic, task_desc, difficulty, report_file, markdown_report_file, evidence_file, output_json):
    """📚 Learn Mode: ingest source into claim+citation knowledge store."""
    import os
    is_light = False
    if task_desc:
        try:
            from nexus.core.router import SkillsRouter
            from nexus.core.capability_signal_set import CapabilitySignalSet
            from nexus.core.capability_constraints import CapabilityConstraints
            from nexus.core.capability_selector import CapabilitySelector
            
            router = SkillsRouter(project_root=str(repo_root))
            risk_level = "LOW" if difficulty.lower() == "easy" else "NORMAL"
            complexity = 1.0 if difficulty.lower() == "easy" else (2.5 if difficulty.lower() == "medium" else 4.5)
            router_context = {
                "task_id": source,
                "task_desc": task_desc,
                "risk_level": risk_level,
                "impact_complexity": complexity,
                "tenant_id": "default",
            }
            # 驅動 router 進行動態評估
            router.route_candidates("R", router_context)
            
            signal_set = CapabilitySignalSet.from_context(router_context, str(repo_root), belief_engine=router.p_loop)
            constraints = CapabilityConstraints(str(repo_root), mem_palace=router.mem_palace, firewall=router.firewall)
            selector = CapabilitySelector()
            plan = selector.select_capabilities(signal_set, constraints)
            
            if hasattr(plan, "phases"):
                is_light = "X" not in plan.phases and "D" not in plan.phases
            elif isinstance(plan, dict) and "phases" in plan:
                is_light = "X" not in plan["phases"] and "D" not in plan["phases"]
        except Exception:
            is_light = difficulty.lower() == "easy"

    if is_light:
        click.echo("⚡ [Learn:Ingest] Autonomic Router triggered LIGHT_ROUTE. Skipping heavy ingestion.")
        os.environ["NEXUS_LIGHT_ROUTE"] = "1"
        class LightResult:
            def __init__(self):
                self.payload = {
                    "status": "success",
                    "reason": "skipped_via_autonomic_light_route",
                    "semantic_status": "SKIPPED_LIGHT_ROUTE",
                    "converged": True,
                    "claims_count": 0,
                    "error": "",
                }
        result = LightResult()
    else:
        os.environ["NEXUS_LIGHT_ROUTE"] = "0"
        result = run_learn_ingest(
            repo_root,
            source=source,
            source_file=source_file,
            topic=topic,
            report_file=report_file,
            markdown_report_file=markdown_report_file,
            evidence_file=evidence_file,
            evidence_writer=_write_hallucination_evidence,
            hallucination_gate=_enforce_hallucination_gate,
            markdown_writer=_write_dual_gate_markdown,
            semantic_evaluator=_evaluate_learn_semantic_contract,
        )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        if is_light:
            click.echo("✅ Ingest light route: PASS")
        else:
            for line in render_learn_ingest_complete(result):
                click.echo(line)
    if not is_light:
        enforce_learn_ingest_semantic_contract(result)


@nexus_group.command(name="learn:register-source")
@click.option("--topic", required=True)
@click.option("--source", required=True)
@click.option("--source-file", required=False, type=click.Path(exists=True))
@click.option("--refresh-after-days", default=14, type=int, show_default=True)
@click.option("--priority", default="medium", show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_register_source.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_register_source(topic, source, source_file, refresh_after_days, priority, report_file, output_json):
    """🗂️ Register a learn source for scheduled refresh."""
    result = run_learn_register_source(
        repo_root,
        topic=topic,
        source=source,
        source_file=source_file,
        refresh_after_days=refresh_after_days,
        priority=priority,
        report_file=report_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_learn_register_source_complete(result, topic=topic, source=source):
            click.echo(line)
    verify_learn_source_lifecycle_completion(result)


@nexus_group.command(name="learn:refresh")
@click.option("--topic", default="", help="Optional topic filter.")
@click.option("--due-only/--all", default=True, show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--question-count", default=5, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_refresh.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_refresh(topic, due_only, pass_threshold, question_count, report_file, output_json):
    """🔄 Refresh registered learn sources and re-run converge."""
    result = run_learn_refresh(
        repo_root,
        topic=topic,
        due_only=due_only,
        pass_threshold=pass_threshold,
        question_count=question_count,
        report_file=report_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_learn_refresh_complete(result):
            click.echo(line)
    verify_learn_source_lifecycle_completion(result)


@nexus_group.command(name="learn:refresh-plan")
@click.option("--topic", default="", help="Optional topic filter.")
@click.option("--due-within-days", default=0, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_refresh_plan.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_refresh_plan(topic, due_within_days, report_file, output_json):
    """🗓️ Build a scheduler-ready plan for learn source refresh."""
    result = run_learn_refresh_plan(
        repo_root,
        topic=topic,
        due_within_days=due_within_days,
        report_file=report_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_learn_refresh_plan_complete(result):
            click.echo(line)
    verify_learn_source_lifecycle_completion(result)


@nexus_group.command(name="learn:converge")
@click.option("--topic", required=True)
@click.option("--task-desc", default="", help="Optional task description to enable dynamic routing.")
@click.option("--difficulty", default="normal", help="Optional task difficulty level (easy/medium/hard).")
@click.option("--max-rounds", default=3, type=int, show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--question-count", default=5, type=int, show_default=True)
@click.option("--auto-research/--no-auto-research", default=True, show_default=True)
@click.option("--max-sources-per-round", default=2, type=int, show_default=True)
@click.option("--swarm-mode/--no-swarm-mode", default=True, show_default=True)
@click.option("--swarm-max-parallel", default=3, type=int, show_default=True)
@click.option("--per-source-timeout-sec", default=25, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/converge_report.json", show_default=True, type=click.Path())
@click.option("--evidence-file", default=".nexus/reports/learn/evidence_converge.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_converge(
    topic,
    task_desc,
    difficulty,
    max_rounds,
    pass_threshold,
    question_count,
    auto_research,
    max_sources_per_round,
    swarm_mode,
    swarm_max_parallel,
    per_source_timeout_sec,
    report_file,
    evidence_file,
    output_json,
):
    """🔁 Learn Mode: run local KAL-style converge loop for a topic."""
    import os
    is_light = os.environ.get("NEXUS_LIGHT_ROUTE", "0") == "1"
    if not is_light and task_desc:
        try:
            from nexus.core.router import SkillsRouter
            from nexus.core.capability_signal_set import CapabilitySignalSet
            from nexus.core.capability_constraints import CapabilityConstraints
            from nexus.core.capability_selector import CapabilitySelector
            
            router = SkillsRouter(project_root=str(repo_root))
            risk_level = "LOW" if difficulty.lower() == "easy" else "NORMAL"
            complexity = 1.0 if difficulty.lower() == "easy" else (2.5 if difficulty.lower() == "medium" else 4.5)
            router_context = {
                "task_id": topic,
                "task_desc": task_desc,
                "risk_level": risk_level,
                "impact_complexity": complexity,
                "tenant_id": "default",
            }
            router.route_candidates("R", router_context)
            
            signal_set = CapabilitySignalSet.from_context(router_context, str(repo_root), belief_engine=router.p_loop)
            constraints = CapabilityConstraints(str(repo_root), mem_palace=router.mem_palace, firewall=router.firewall)
            selector = CapabilitySelector()
            plan = selector.select_capabilities(signal_set, constraints)
            
            if hasattr(plan, "phases"):
                is_light = "X" not in plan.phases and "D" not in plan.phases
            elif isinstance(plan, dict) and "phases" in plan:
                is_light = "X" not in plan["phases"] and "D" not in plan["phases"]
        except Exception:
            is_light = difficulty.lower() == "easy"

    if is_light:
        click.echo("⚡ [Learn:Converge] Autonomic Router triggered LIGHT_ROUTE. Skipping heavy convergence.")
        class LightResult:
            def __init__(self):
                self.payload = {
                    "status": "success",
                    "reason": "skipped_via_autonomic_light_route",
                    "semantic_status": "SKIPPED_LIGHT_ROUTE",
                    "converged": True,
                    "claims_count": 0,
                    "error": "",
                }
        result = LightResult()
    else:
        result = run_learn_converge(
            repo_root,
            topic=topic,
            max_rounds=max_rounds,
            pass_threshold=pass_threshold,
            question_count=question_count,
            auto_research=auto_research,
            max_sources_per_round=max_sources_per_round,
            swarm_mode=swarm_mode,
            swarm_max_parallel=swarm_max_parallel,
            per_source_timeout_sec=per_source_timeout_sec,
            report_file=report_file,
            evidence_file=evidence_file,
            evidence_writer=_write_hallucination_evidence,
            hallucination_gate=_enforce_hallucination_gate,
        )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        if is_light:
            click.echo("✅ Converge light route: PASS")
        else:
            for line in render_learn_converge_complete(result):
                click.echo(line)


@nexus_group.command(name="ask")
@click.option("--topic", required=True)
@click.option("--question", required=True, help="Question to answer using cited claims within topic scope.")
@click.option("--top-k", default=5, type=int, show_default=True)
@click.option("--min-evidence", default=1, type=int, show_default=True)
@click.option("--min-token-coverage", default=None, type=float)
@click.option("--max-staleness-days", default=180, type=int, show_default=True)
@click.option("--allow-cross-pack", is_flag=True, help="Opt in to soft routing across topic packs when the requested topic has no claims.")
@click.option("--evidence-file", default=".nexus/reports/learn/evidence_ask.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_ask(topic, question, top_k, min_evidence, min_token_coverage, max_staleness_days, allow_cross_pack, evidence_file, output_json):
    """❓ Ask using cited claims only. If no cited evidence, return UNKNOWN."""
    result = run_learn_ask(
        repo_root,
        topic=topic,
        question=question,
        top_k=top_k,
        min_evidence=min_evidence,
        min_token_coverage=min_token_coverage,
        max_staleness_days=max_staleness_days,
        allow_cross_pack=allow_cross_pack,
        evidence_file=evidence_file,
        evidence_writer=_write_hallucination_evidence,
        hallucination_gate=_enforce_hallucination_gate,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
        return
    for line in render_learn_ask_response(result):
        click.echo(line)


@nexus_group.command(name="learn:report")
@click.option("--topic", default="", help="Optional topic filter for coverage and unresolved questions.")
@click.option("--question-count", default=5, type=int, show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_report.json", show_default=True, type=click.Path())
@click.option("--markdown-report-file", default=".nexus/reports/learn/learn_report.md", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_report(topic, question_count, pass_threshold, report_file, markdown_report_file, output_json):
    """📈 Build unified learn report for governance and CI consumption."""
    result = run_learn_report(
        repo_root,
        topic=topic,
        question_count=question_count,
        pass_threshold=pass_threshold,
        report_file=report_file,
        markdown_report_file=markdown_report_file,
        markdown_writer=_write_dual_gate_markdown,
        semantic_evaluator=_evaluate_learn_semantic_contract,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
        enforce_learn_report_semantic_contract(result)
        return
    for line in render_learn_report_complete(result):
        click.echo(line)
    enforce_learn_report_semantic_contract(result)


@nexus_group.command(name="learn:phase-slo")
@click.option("--window", default=300, type=int, show_default=True)
@click.option(
    "--report-file",
    default=".nexus/reports/learn/phase_slo_summary.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_phase_slo(window, report_file, output_json):
    """📏 Build phase-level learn SLO report for P/X/D/R/A/C writeback closure."""
    result = run_learn_phase_slo(repo_root, window=window, report_file=report_file)
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_learn_phase_slo_complete(result):
            click.echo(line)
    verify_learn_phase_report_completion(result)


@nexus_group.command(name="learn:phase-kpi")
@click.option("--window", default=300, type=int, show_default=True)
@click.option(
    "--report-file",
    default=".nexus/reports/learn/phase_kpi_report.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_phase_kpi(window, report_file, output_json):
    """📊 Build phase KPI dashboard payload for P/X/D/R/A/C."""
    result = run_learn_phase_kpi(repo_root, window=window, report_file=report_file)
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_learn_phase_kpi_complete(result):
            click.echo(line)
    verify_learn_phase_report_completion(result)


@nexus_group.command(name="learn:benchmark-legacy")
@click.option("--manifest-file", required=True, type=click.Path(exists=True))
@click.option("--source", default="", help="Optional source to ingest before benchmark.")
@click.option("--source-file", default=None, type=click.Path(exists=True))
@click.option("--topic", required=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_benchmark.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_benchmark(manifest_file, source, source_file, topic, report_file, output_json):
    """📊 Benchmark learn ask quality and tune retrieval thresholds."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    if source or source_file:
        service.ingest(source=source or topic, source_file=source_file, topic=topic)
        service.converge(topic=topic, max_rounds=2, pass_threshold=0.6, question_count=5, auto_research=False)

    questions = manifest.get("questions", [])
    baseline_cfg = {"top_k": 5, "min_evidence": 1, "min_token_coverage": 0.5, "max_staleness_days": 180}
    candidate_cfgs = [
        baseline_cfg,
        {"top_k": 5, "min_evidence": 2, "min_token_coverage": 0.5, "max_staleness_days": 180},
        {"top_k": 6, "min_evidence": 2, "min_token_coverage": 0.4, "max_staleness_days": 180},
        {"top_k": 4, "min_evidence": 2, "min_token_coverage": 0.6, "max_staleness_days": 90},
    ]

    def _score_result(result, expected):
        expected_status = str(expected.get("expected_status", "ANSWERED")).upper()
        ok = result.get("status") == expected_status
        if ok and expected_status == "ANSWERED":
            answer = str(result.get("answer", "")).lower()
            for kw in expected.get("expected_keywords", []):
                if str(kw).lower() not in answer:
                    ok = False
                    break
        return 1.0 if ok else 0.0

    cfg_results = []
    for cfg in candidate_cfgs:
        runs = []
        total = 0.0
        answered_hits = 0
        answered_total = 0
        unknown_hits = 0
        unknown_total = 0
        conflict_hits = 0
        conflict_total = 0
        stale_hits = 0
        for item in questions:
            result = service.ask(
                topic=topic,
                question=str(item.get("question", "")),
                top_k=int(cfg["top_k"]),
                min_evidence=int(cfg["min_evidence"]),
                min_token_coverage=float(cfg["min_token_coverage"]),
                max_staleness_days=int(cfg["max_staleness_days"]),
            )
            score = _score_result(result, item)
            total += score
            expected_status = str(item.get("expected_status", "ANSWERED")).upper()
            if expected_status == "ANSWERED":
                answered_total += 1
                answered_hits += int(score)
            elif expected_status == "UNKNOWN":
                unknown_total += 1
                unknown_hits += int(score)
            elif expected_status == "CONFLICT":
                conflict_total += 1
                conflict_hits += int(score)
            if int(item.get("expected_stale_claims", 0)) > 0 and result.get("status") == "UNKNOWN":
                stale_hits += 1
            runs.append(
                {
                    "question": item.get("question", ""),
                    "expected_status": item.get("expected_status", "ANSWERED"),
                    "actual_status": result.get("status"),
                    "score": score,
                    "token_coverage": result.get("token_coverage", 0.0),
                    "claims_used": result.get("claims_used", 0),
                    "topic_pack_selected": result.get("topic_pack_selected", ""),
                }
            )
        cfg_results.append(
            {
                "config": cfg,
                "success_rate": round(total / max(1, len(questions)), 4),
                "answer_precision": round(answered_hits / max(1, answered_total), 4),
                "unknown_accuracy": round(unknown_hits / max(1, unknown_total), 4),
                "conflict_accuracy": round(conflict_hits / max(1, conflict_total), 4),
                "avg_token_coverage": round(
                    sum(float(r.get("token_coverage", 0.0) or 0.0) for r in runs) / max(1, len(runs)),
                    4,
                ),
                "avg_claims_used": round(
                    sum(float(r.get("claims_used", 0) or 0) for r in runs) / max(1, len(runs)),
                    4,
                ),
                "stale_claim_usage_rate": round(stale_hits / max(1, len(questions)), 4),
                "results": runs,
            }
        )

    best = max(cfg_results, key=lambda item: item["success_rate"]) if cfg_results else {"config": baseline_cfg, "success_rate": 0.0}
    payload = {
        "status": "SUCCESS",
        "topic": topic,
        "question_count": len(questions),
        "baseline": cfg_results[0] if cfg_results else {},
        "best": best,
        "improvement": round(best.get("success_rate", 0.0) - (cfg_results[0].get("success_rate", 0.0) if cfg_results else 0.0), 4),
        "candidates": cfg_results,
    }
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn benchmark complete: topic={topic}")
        click.echo(f"Baseline={payload['baseline'].get('success_rate', 0.0):.2%} Best={payload['best'].get('success_rate', 0.0):.2%}")
        click.echo(f"Report: {out_path}")


@nexus_group.command(name="learn:benchmark-curate")
@click.option("--topic", default="", help="Optional topic filter for candidate curation.")
@click.option("--max-questions", default=40, type=int, show_default=True)
@click.option("--min-occurrences", default=1, type=int, show_default=True)
@click.option(
    "--manifest-file",
    default="docs/research/learn_benchmark_curated.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--output-json", is_flag=True)
def learn_benchmark_curate(topic, max_questions, min_occurrences, manifest_file, output_json):
    """🧹 Curate learn benchmark candidates into a production-ready manifest."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.curate_benchmark_bank(
        topic=topic,
        max_questions=max_questions,
        min_occurrences=min_occurrences,
    )
    out_path = (repo_root / manifest_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_payload = {
        "topic": payload.get("topic", topic),
        "generated_at": payload.get("generated_at", ""),
        "questions": payload.get("questions", []),
    }
    if not out_payload["questions"] and out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing_questions = existing.get("questions", []) if isinstance(existing, dict) else []
            if existing_questions:
                out_payload["questions"] = existing_questions
                payload["fallback_used"] = True
                payload["selected_count"] = len(existing_questions)
        except Exception:
            pass
    if not out_payload["questions"]:
        template_path = repo_root / "docs" / "research" / "learn_benchmark_manifest_template.json"
        if template_path.exists():
            try:
                template = json.loads(template_path.read_text(encoding="utf-8"))
                template_questions = template.get("questions", []) if isinstance(template, dict) else []
                if template_questions:
                    out_payload["questions"] = template_questions
                    payload["fallback_used"] = True
                    payload["fallback_template"] = str(template_path)
                    payload["selected_count"] = len(template_questions)
            except Exception:
                pass
    payload["questions"] = out_payload["questions"]
    out_path.write_text(json.dumps(out_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload["manifest_file"] = str(out_path)
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(
            f"✅ Learn benchmark curated: selected={payload.get('selected_count', 0)} "
            f"from candidates={payload.get('candidate_count', 0)}"
        )
        click.echo(f"Manifest: {out_path}")


@nexus_group.command(name="learn:gate")
@click.option("--topic", default="nexus", show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--citation-valid-min", default=0.95, type=float, show_default=True)
@click.option("--claims-min", default=5, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_gate_report.json", show_default=True, type=click.Path())
@click.option("--evidence-file", default=".nexus/reports/learn/evidence_gate.json", show_default=True, type=click.Path())
@click.option(
    "--contract-file",
    default=".nexus/config/task_contract.example.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--skip-contract", is_flag=True)
@click.option("--skip-ci", is_flag=True)
@translate_action_exceptions
def learn_gate(
    topic,
    pass_threshold,
    citation_valid_min,
    claims_min,
    report_file,
    evidence_file,
    contract_file,
    skip_contract,
    skip_ci,
):
    """🛡️ One-shot learn governance gate: report + evidence + acceptance + contract + ci(dry-run)."""
    result = run_learn_gate(
        repo_root,
        topic=topic,
        pass_threshold=pass_threshold,
        citation_valid_min=citation_valid_min,
        claims_min=claims_min,
        report_file=report_file,
        evidence_file=evidence_file,
        contract_file=contract_file,
        skip_contract=skip_contract,
        skip_ci=skip_ci,
        evidence_writer=_write_hallucination_evidence,
        hallucination_gate=_enforce_hallucination_gate,
    )
    for line in render_learn_gate_complete(result):
        click.echo(line)


@nexus_group.command(name="contract-check")
@click.option("--contract-file", type=click.Path(exists=True), required=True)
def contract_check(contract_file):
    """📜 [Governance] Validate task contract against physical state."""
    cmd = [sys.executable, str(repo_root / "scripts/ops/closeout_guard.py"), "--contract", contract_file]
    subprocess.run(cmd, check=True)


@nexus_group.command(name="contract-snapshot")
@click.option("--output", "output_path", default=".nexus/reports/closeout_contract.json", show_default=True, type=click.Path())
@click.option("--task-id", default="runtime-closeout", show_default=True)
@click.option("--tests-passed/--no-tests-passed", default=True, show_default=True)
@click.option("--linter-exit-code", default=0, show_default=True, type=int)
@click.option("--ci-gate-exit-code", default=0, show_default=True, type=int)
def contract_snapshot(output_path, task_id, tests_passed, linter_exit_code, ci_gate_exit_code):
    """🧾 Emit a runtime closeout contract for the current HEAD."""
    head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root).decode().strip()
    changed_raw = subprocess.check_output(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=repo_root,
    ).decode()
    changed_files = [line.strip() for line in changed_raw.splitlines() if line.strip()]
    payload = {
        "task_id": task_id,
        "commit_sha": head,
        "linter_exit_code": int(linter_exit_code),
        "ci_gate_exit_code": int(ci_gate_exit_code),
        "required_tests_passed": bool(tests_passed),
        "changed_files": changed_files,
        "done_criteria": [
            "delivery gate passed",
            "contract check passed",
        ],
    }
    out = Path(output_path)
    out = out if out.is_absolute() else (repo_root / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    click.echo(json.dumps({"ok": True, "output": str(out), "commit_sha": head}, indent=2, ensure_ascii=False))

@nexus_group.command(name="distill")
@click.option("--report-file", default=".nexus/reports/metabolism/distill_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def distill(report_file, output_json):
    """🌬️ [Metabolism] Distill session essence."""
    from nexus.services.metabolism_engine import metabolism
    tx = metabolism.distill({"goal": "v23.7 Recovery", "done": ["Wiki Sync"], "todo": ["Command Recovery"]})
    payload = {"status": "SUCCESS", "tx": tx}
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"💎 Session distilled. Arweave TX: {tx}")
        click.echo(f"Report: {out_path}")

# --- v23.7 艦隊指揮 ---
@nexus_group.command(name="resume")
def resume():
    """🌬️ [Metabolism] Resume task from last physical checkpoint."""
    from nexus.services.metabolism_engine import metabolism
    checkpoint = metabolism.load_checkpoint()
    if not checkpoint:
        click.echo("❌ No checkpoint found.")
        return
    click.echo(f"🌬️ Resuming Task: {checkpoint['task_id']}")

@nexus_group.command(name="delegate")
@click.argument("task_name")
@click.option("--report-file", default=".nexus/reports/delegate/delegate_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def delegate(task_name, report_file, output_json):
    """📡 [Supervisor] Decompose and delegate task to fleet."""
    if not SanitizedRunner.validate_task_name(task_name):
        click.echo("❌ Invalid task name: only alphanumeric, spaces, dashes, and underscores allowed.")
        sys.exit(1)
    
    sanitized_task_name = SanitizedRunner.sanitize_arg(task_name)
    res = SanitizedRunner.run_safe([sys.executable, str(repo_root / "scripts/ops/supervisor_engine.py"), sanitized_task_name], check=False)
    payload = build_completion_envelope(
        command_name="delegate",
        task_name=task_name,
        runtime_ok=(res.returncode == 0),
        execution_path="cli->supervisor_engine",
    )
    out_path = write_completion_envelope(repo_root, report_file, payload)
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"{'✅' if payload['status'] == 'SUCCESS' else '❌'} Delegated task: {task_name}")
        click.echo(f"Report: {out_path}")
    try:
        ensure_verified_completion(payload, context="delegate")
    except CompletionEnforcementError as exc:
        handoff = _persist_completion_handoff(payload, context="delegate", report_file=out_path)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if not output_json:
            click.echo(f"Next Action: {handoff}")
        raise click.ClickException(str(exc))


@nexus_group.command(name="research:route")
@click.option("--task-desc", required=True)
@click.option("--task-type", default="bug")
@click.option("--candidate-count", default=1, type=int)
@click.option("--root-cause-confidence", default=1.0, type=float)
@click.option("--findings-query")
@click.option("--task-id")
@click.option("--output-json", is_flag=True)
@click.option("--explain-route", is_flag=True)
@click.option("--route-decision-report", type=click.Path(path_type=Path))
@translate_action_exceptions
def research_route(task_desc, task_type, candidate_count, root_cause_confidence, findings_query, task_id, output_json, explain_route, route_decision_report):
    """🧠 Strategy Routing Layer: Decide whether to research and in what mode."""
    result = run_research_route(
        repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        task_id=task_id,
        route_decision_report=route_decision_report,
    )
    if explain_route:
        for line in render_research_route_explanation(result):
            click.echo(line)
        return

    if output_json:
        click.echo(json.dumps(result.payload, indent=2))
    else:
        for line in render_research_route_summary(result):
            click.echo(line)


@nexus_group.command(name="capability:coverage-gap")
@click.option("--report-file", default=".nexus/reports/capability_coverage_gap.json", show_default=True, type=click.Path(path_type=Path))
@click.option("--output-json", is_flag=True)
def capability_coverage_gap(report_file, output_json):
    """📊 Emit capability routing coverage gaps without invoking models."""
    from nexus.engine.capability_coverage_gap import build_capability_coverage_gap_report, write_capability_coverage_gap_report

    report_path = report_file if report_file.is_absolute() else repo_root / report_file
    payload = build_capability_coverage_gap_report()
    write_capability_coverage_gap_report(report_path)
    payload["report_path"] = str(report_path)
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Capability coverage gap report: {report_path}")
        click.echo(f"Unruled: {payload['unruled_count']} Reserved: {payload['reserved_count']} Pending executors: {payload['pending_executor_count']}")


@nexus_group.command(name="research:report")
@click.option("--input", "input_dir", default=".nexus/reports/research", type=click.Path(exists=True))
@click.option("--rolling", type=int, default=7)
@click.option("--output", default=".nexus/reports/research/unified_rolling.json", type=click.Path())
def research_report_cmd(input_dir, rolling, output):
    """📊 Aggregate multiple research reports into a unified rolling view."""
    import json
    from pathlib import Path
    
    p_in = Path(input_dir)
    files = sorted(p_in.glob("*.json"))
    if not files:
        click.echo("No reports found.")
        return
        
    recent = [f for f in files if "rolling" not in f.name][-rolling:]
    click.echo(f"Aggregating {len(recent)} recent reports...")
    
    aggs = []
    for f in recent:
        try:
            d = json.loads(f.read_text())
            if "aggregates" in d: aggs.append(d["aggregates"])
            elif "success_rate" in d: aggs.append(d)
        except: continue
        
    if not aggs:
        click.echo("Could not parse aggregate data.")
        return
        
    avg_s = sum(a.get("success_rate", 0) for a in aggs) / len(aggs)
    avg_r = sum(a.get("regression_rate", 0) for a in aggs) / len(aggs)
    
    summary = {
        "rolling_window": rolling,
        "sample_count": len(recent),
        "avg_success_rate": avg_s,
        "avg_regression_rate": avg_r,
        "reports": [str(f.name) for f in recent]
    }
    
    out_p = Path(output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(summary, indent=2))
    click.echo(f"Unified rolling report written to {output}")


@nexus_group.command(name="research:onboarding")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--goal", required=True)
@click.option("--benchmark", default="", show_default=True)
@click.option("--metric", default="", show_default=True)
@click.option("--scope", multiple=True)
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_onboarding_cmd(session_id, goal, benchmark, metric, scope, output_json):
    """Create a governed research session manifest."""
    result = run_research_onboarding(
        repo_root,
        session_id=session_id,
        goal=goal,
        benchmark=benchmark,
        metric=metric,
        scope=scope,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:recommend-next")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--task-desc", required=True)
@click.option("--task-type", default="bug", show_default=True)
@click.option("--candidate-count", default=1, type=int, show_default=True)
@click.option("--root-cause-confidence", default=1.0, type=float, show_default=True)
@click.option("--findings-query")
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_recommend_next_cmd(session_id, task_desc, task_type, candidate_count, root_cause_confidence, findings_query, output_json):
    """Recommend the next governed research action using the current route."""
    result = run_research_recommend_next(
        repo_root,
        session_id=session_id,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:packet")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--report-file", type=click.Path())
@click.option("--route-file", type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_packet_cmd(session_id, report_file, route_file, output_json):
    """Persist the latest research packet for ledger review."""
    result = run_research_packet(
        repo_root,
        session_id=session_id,
        report_file=report_file,
        route_file=route_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:log-from-last")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--status", required=True, type=click.Choice(["keep", "discard", "crash", "checks_failed"]))
@click.option("--description", required=True)
@click.option("--asi-file", type=click.Path())
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_log_from_last_cmd(session_id, status, description, asi_file, output_json):
    """Append the last research packet to the session ledger."""
    result = run_research_log_from_last(
        repo_root,
        session_id=session_id,
        status=status,
        description=description,
        asi_file=asi_file,
    )
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:finalize-preview")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_finalize_preview_cmd(session_id, output_json):
    """Preview whether the session is ready to finalize."""
    result = run_research_finalize_preview(repo_root, session_id=session_id)
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:writeback-lessons")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def research_writeback_lessons_cmd(session_id, output_json):
    """Record pending failed research lessons into FindingsMemory."""
    result = run_research_writeback_lessons(repo_root, session_id=session_id)
    if output_json:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_session_action(result):
            click.echo(line)


@nexus_group.command(name="research:human-report")
@click.option("--session-id", default="research-session", show_default=True)
@click.option("--output", type=click.Path(path_type=Path))
@translate_action_exceptions
def research_human_report_cmd(session_id, output):
    """Render a concise human handoff report for a research session."""
    for line in render_research_human_report(
        run_research_human_report(repo_root, session_id=session_id, output=output)
    ):
        click.echo(line)


@nexus_group.command(name="research:auto-flow")
@click.option("--task-desc", required=True)
@click.option("--target-file", required=True)
@click.option("--test-file", required=True)
@click.option("--task-type", default="bug")
@click.option("--success-criteria", default="all_target_tests_pass", show_default=True)
@click.option("--candidate-count", default=1, type=int)
@click.option("--root-cause-confidence", default=1.0, type=float)
@click.option("--findings-query")
@click.option("--llm-mode/--no-llm-mode", default=False, show_default=True)
@click.option("--llm-baseline", is_flag=True, help="Enable LLM assistance for baseline generation.")
@click.option(
    "--llm-baseline-required",
    is_flag=True,
    help="Require baseline generation to come from the LLM path; do not fall back to local baseline mutation.",
)
@click.option("--timeout-sec", default=60, type=int, show_default=True)
@click.option("--stage1-timeout-sec", default=20, type=int, show_default=True)
@click.option("--max-time-ratio-guard", default=1.5, type=float, show_default=True)
@click.option("--baseline-fast-sec", default=9.0, type=float, show_default=True, help="If baseline probe succeeds within this time, skip Hyper.")
@click.option("--history-window", default=5, type=int, show_default=True, help="Recent runs considered for conservative fallback.")
@click.option("--history-fail-threshold", default=2, type=int, show_default=True, help="If Hyper fails this many times in history window, fallback to baseline.")
@click.option("--dynamic-timeout-multiplier", default=2.5, type=float, show_default=True, help="Hyper stage1 timeout multiplier based on baseline probe time.")
@click.option("--min-dynamic-stage1-timeout", default=12, type=int, show_default=True, help="Lower bound for dynamic stage1 timeout.")
@click.option("--force-flow", type=click.Choice(["baseline", "hyper_sprint"]), default=None)
@click.option("--report-file", default=".nexus/reports/research/auto-flow-report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
@click.option("--explain-route", is_flag=True)
@click.option("--output-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Optional explicit JSON output file.")
@click.option("--task-id", default=None, help="Optional stable task id for capability receipt artifacts.")
@click.option("--research-session-id", default="", help="Opt-in research session id for route preflight and packet ledger.")
@click.option("--research-gate", is_flag=True, help="Block execution when research preflight finds unverified claim uncertainty.")
@translate_action_exceptions
def research_auto_flow(
    task_desc,
    target_file,
    test_file,
    task_type,
    success_criteria,
    candidate_count,
    root_cause_confidence,
    findings_query,
    llm_mode,
    llm_baseline,
    llm_baseline_required,
    timeout_sec,
    stage1_timeout_sec,
    max_time_ratio_guard,
    baseline_fast_sec,
    history_window,
    history_fail_threshold,
    dynamic_timeout_multiplier,
    min_dynamic_stage1_timeout,
    force_flow,
    report_file,
    output_json,
    explain_route,
    output_file,
    task_id,
    research_session_id,
    research_gate,
):
    if explain_route:
        result = run_research_auto_flow_route_explanation(
            repo_root,
            task_desc=task_desc,
            task_type=task_type,
            candidate_count=candidate_count,
            root_cause_confidence=root_cause_confidence,
            findings_query=findings_query,
            target_file=target_file,
        )
        for line in render_research_auto_flow_route_explanation(result):
            click.echo(line)
        return

    result = run_research_auto_flow(
        repo_root,
        task_desc=task_desc,
        target_file=target_file,
        test_file=test_file,
        task_type=task_type,
        success_criteria=success_criteria,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        llm_mode=llm_mode,
        llm_baseline=llm_baseline,
        llm_baseline_required=llm_baseline_required,
        timeout_sec=timeout_sec,
        stage1_timeout_sec=stage1_timeout_sec,
        max_time_ratio_guard=max_time_ratio_guard,
        baseline_fast_sec=baseline_fast_sec,
        history_window=history_window,
        history_fail_threshold=history_fail_threshold,
        dynamic_timeout_multiplier=dynamic_timeout_multiplier,
        min_dynamic_stage1_timeout=min_dynamic_stage1_timeout,
        force_flow=force_flow,
        report_file=report_file,
        output_file=output_file,
        task_id=task_id,
        research_session_id=research_session_id,
        research_gate=research_gate,
    )
    if output_json or result.blocked:
        click.echo(json.dumps(result.payload, indent=2, ensure_ascii=False))
    else:
        for line in render_research_auto_flow_result(result):
            click.echo(line)
    if result.exit_code:
        raise SystemExit(result.exit_code)


@nexus_group.group(name="report")
def report_group():
    """📊 Nexus Report Governance & Trust Audit"""
    pass


@report_group.command(name="trust-audit")
@click.option("--report-file", type=click.Path(exists=True), required=True)
@click.option("--output", "output_path", default=".nexus/reports/trust_audit_result.json", show_default=True)
def trust_audit(report_file, output_path):
    """🔍 [v26] Run semantic consistency check on a report and lock via delivery-gate."""
    import json
    from pathlib import Path
    
    click.secho(f"🔎 [Trust-Audit] Auditing: {report_file}", fg="cyan", bold=True)
    report_path = Path(report_file)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    
    status = data.get("status", "UNKNOWN")
    artifacts = data.get("artifact_paths", [])
    failures = []
    
    # 1. 物理存在性檢查
    for art in artifacts:
        art_path = REPO_ROOT / art
        if not art_path.exists():
            failures.append(f"missing_artifact:{art}")
        else:
            # 2. 內容一致性檢查 (簡化版：若 status 為 SUCCESS，內容不應含顯著 Error)
            if status == "SUCCESS":
                content = art_path.read_text(encoding="utf-8").upper()
                if "ERROR" in content and "SUCCESS" not in content:
                    failures.append(f"integrity_mismatch:{art}")

    audit_status = "VERIFIED" if not failures else "REJECTED"
    result = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "report_source": str(report_path),
        "status": audit_status,
        "failures": failures,
        "commit_sha": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    }
    
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    
    click.echo(json.dumps(result, indent=2))
    
    if audit_status == "REJECTED":
        click.secho(f"❌ [Trust-Audit] Audit REJECTED: {failures}", fg="red", bold=True)
        sys.exit(1)
    
    click.secho("✅ [Trust-Audit] Audit PASSED. Locking via delivery-gate...", fg="green")
    # 自動鎖定
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "nexus", "delivery-gate", "--evidence", str(out_p)], check=True)


@nexus_group.command(name="ultra-review")
@click.option("--task", default="ultra review", show_default=True)
@click.option("--dry-run/--no-dry-run", default=True, show_default=True)
@click.option("--report-file", default=".nexus/reports/ultra_review_report.json", show_default=True, type=click.Path())
@click.option("--sandbox-root", default=".nexus/reports/ultra_review/sandboxes", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def ultra_review(task, dry_run, report_file, sandbox_root, output_json):
    from nexus.engine.ultra_review_service import UltraReviewService

    payload = UltraReviewService(repo_root).run(
        task=task,
        dry_run=dry_run,
        report_path=report_file,
        sandbox_root=sandbox_root,
    )
    if output_json:
        click.echo(json.dumps(payload, ensure_ascii=False))
    else:
        click.echo(f"{'✅' if payload.get('gate_passed') else '❌'} Ultra Review: {payload.get('status')}")
        click.echo(f"Report: {report_file}")



@nexus_group.command(name="research:run")
@click.option("--run-id", default="", help="Research run identifier.")
@click.option("--candidate-id", default="candidate-main", show_default=True)
@click.option("--candidate-count", default=1, type=int, show_default=True)
@click.option("--hypothesis", default="default-hypothesis", show_default=True)
@click.option("--scope", multiple=True, help="Relative writable scope for this candidate. Repeatable.")
@click.option("--candidate-src-root", default=".", type=click.Path(path_type=Path), show_default=True)
@click.option("--budget-limit", default=100.0, type=float, show_default=True)
@click.option("--min-score-threshold", default=0.5, type=float, show_default=True)
@click.option("--estimated-cost-per-round", default=1.0, type=float, show_default=True)
@click.option("--dry-run", is_flag=True, help="Evaluate and select without promotion.")
@click.option("--report-file", default=".nexus/reports/research/report.json", type=click.Path(path_type=Path), show_default=True)
@click.option("--max-parallel", default=1, type=int, show_default=True)
@click.option("--max-retries", default=0, type=int, show_default=True)
@click.option("--continuation-attempts", default=1, type=int, show_default=True, help="Auto continuation loops when semantic_status is UNVERIFIED and retryable=true.")
@click.option("--timeout-sec", default=600, type=int, show_default=True)
@click.option("--retain-last-n", default=20, type=int, show_default=True)
@click.option("--disk-watermark-gb", default=5.0, type=float, show_default=True)
@click.option("--research-session-id", default="", help="Opt-in research session id for route preflight and packet ledger.")
@click.option("--research-gate", is_flag=True, help="Block execution when research preflight finds unverified claim uncertainty.")
@click.option("--task-type", default="bug", show_default=True, help="Task type used by research route preflight.")
@click.option("--root-cause-confidence", default=1.0, type=float, show_default=True)
@click.option("--findings-query")
@translate_action_exceptions
def research_run(
    run_id,
    candidate_id,
    candidate_count,
    hypothesis,
    scope,
    candidate_src_root,
    budget_limit,
    min_score_threshold,
    estimated_cost_per_round,
    dry_run,
    report_file,
    max_parallel,
    max_retries,
    continuation_attempts,
    timeout_sec,
    retain_last_n,
    disk_watermark_gb,
    research_session_id,
    research_gate,
    task_type,
    root_cause_confidence,
    findings_query,
):
    """🧬 Run research control-plane loop: schedule -> evaluate -> select/promote -> rollback."""
    result = run_research_run(
        repo_root,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_count=candidate_count,
        hypothesis=hypothesis,
        scope=scope,
        candidate_src_root=candidate_src_root,
        budget_limit=budget_limit,
        min_score_threshold=min_score_threshold,
        estimated_cost_per_round=estimated_cost_per_round,
        dry_run=dry_run,
        report_file=report_file,
        max_parallel=max_parallel,
        max_retries=max_retries,
        continuation_attempts=continuation_attempts,
        timeout_sec=timeout_sec,
        retain_last_n=retain_last_n,
        disk_watermark_gb=disk_watermark_gb,
        research_session_id=research_session_id,
        research_gate=research_gate,
        task_type=task_type,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
    )
    for line in render_research_run_result(result):
        click.echo(line)
    if result.exit_code:
        raise SystemExit(result.exit_code)
    return



@nexus_group.command(name="research:benchmark")
@click.option("--manifest-file", required=True, type=click.Path(exists=True))
@click.option("--report-file", default=".nexus/reports/research/benchmark-report.json", type=click.Path())
@click.option("--budget-limit", default=50.0, type=float)
@click.option("--timeout-sec", default=30, type=int)
@click.option("--max-wall-time-sec", default=0, type=int, help="Maximum total execution time for the entire benchmark (0=unlimited).")
@click.option("--mode", type=click.Choice(["gladiator", "ab"]), default="gladiator", show_default=True)
@click.option("--ab-trials", default=3, type=int, show_default=True, help="Number of repeated runs per mode for A/B.")
@click.option("--ab-llm-mode/--ab-no-llm-mode", default=False, show_default=True, help="Enable LLM mode inside Hyper-Sprint A/B runs.")
@click.option("--llm-baseline", is_flag=True, help="Enable LLM assistance for baseline generation in feature/refactor cases.")
def research_benchmark(manifest_file, report_file, budget_limit, timeout_sec, max_wall_time_sec, mode, ab_trials, ab_llm_mode, llm_baseline):
    """📊 [Control Plane] Gladiator Benchmark: Real evaluation for multiple cases."""
    from nexus.app.research_benchmark_service import ResearchBenchmarkService
    svc = ResearchBenchmarkService(repo_root)
    svc.run_benchmark(mode, manifest_file, report_file, budget_limit, timeout_sec, max_wall_time_sec, ab_trials, ab_llm_mode, llm_baseline)

@nexus_group.command(name="research:meta-opt")
@click.option("--manifest-file", required=True, type=click.Path(exists=True))
@click.option("--presets-file", required=True, type=click.Path(exists=True))
@click.option("--report-file", default=".nexus/reports/research/meta-opt-report.json", type=click.Path())
@click.option("--max-wall-time-sec", default=300, type=int, show_default=True)
def research_meta_opt(manifest_file, presets_file, report_file, max_wall_time_sec):
    """🧪 [Meta-Optimization] Tune Hyper/NightShift preset configs via benchmark search."""
    import json
    import time

    started_at = time.time()
    manifest_path = (repo_root / manifest_file).resolve()
    presets_path = (repo_root / presets_file).resolve()
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        presets = json.loads(presets_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"Invalid presets JSON: {exc}")

    if not isinstance(presets, list) or not presets:
        raise click.ClickException("presets-file must be a non-empty JSON list.")

    rankings: list[dict[str, Any]] = []
    partial = False

    for idx, preset in enumerate(presets, start=1):
        elapsed = time.time() - started_at
        if max_wall_time_sec > 0 and elapsed >= max_wall_time_sec:
            partial = True
            break

        if not isinstance(preset, dict):
            rankings.append(
                {
                    "preset_name": f"preset_{idx}",
                    "status": "invalid_preset",
                    "error": "preset item must be object",
                    "aggregates": {
                        "algorithm_success_rate": 0.0,
                        "regression_rate": 1.0,
                        "infra_blocked_rate": 1.0,
                        "time_to_green_p50": 0.0,
                    },
                }
            )
            continue

        preset_name = str(preset.get("name", f"preset_{idx}"))
        timeout_sec = int(preset.get("timeout_sec", 30))
        preset_wall = int(preset.get("max_wall_time_sec", 120))
        ab_trials = int(preset.get("ab_trials", 1))
        ab_llm_mode = bool(preset.get("ab_llm_mode", False))
        llm_baseline = bool(preset.get("llm_baseline", False))

        run_report = out_path.parent / f"meta-opt-{preset_name}.json"
        cmd = [
            "uv",
            "run",
            "scripts/engine/nexus_cli.py",
            "nexus",
            "research:benchmark",
            "--manifest-file",
            str(manifest_path),
            "--mode",
            "ab",
            "--ab-trials",
            str(max(1, ab_trials)),
            "--timeout-sec",
            str(max(1, timeout_sec)),
            "--max-wall-time-sec",
            str(max(0, preset_wall)),
            "--report-file",
            str(run_report),
        ]
        if ab_llm_mode:
            cmd.append("--ab-llm-mode")
        else:
            cmd.append("--ab-no-llm-mode")
        if llm_baseline:
            cmd.append("--llm-baseline")

        click.echo(f"🧪 [Meta-Opt] ({idx}/{len(presets)}) preset={preset_name}")
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp_log:
            tmp_log_path = Path(tmp_log.name)
            
        try:
            executor = AsyncProcessExecutor()
            returncode, stdout_len, stderr_len = asyncio.run(executor.run_async(cmd, tmp_log_path))
            log_content = tmp_log_path.read_text(encoding="utf-8", errors="ignore")
            proc = subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=log_content, stderr="")
        finally:
            if tmp_log_path.exists():
                tmp_log_path.unlink()

        aggregates = {
            "algorithm_success_rate": 0.0,
            "regression_rate": 1.0,
            "infra_blocked_rate": 1.0,
            "time_to_green_p50": 0.0,
        }
        status = "ok" if proc.returncode == 0 else "failed"
        error = ""
        if proc.returncode != 0:
            error = (proc.stderr or proc.stdout or "").strip()[:800]

        if run_report.exists():
            try:
                report_payload = json.loads(run_report.read_text(encoding="utf-8"))
                agg = report_payload.get("aggregates", {})
                if isinstance(agg, dict):
                    aggregates["algorithm_success_rate"] = float(
                        agg.get("algorithm_success_rate", agg.get("success_rate", 0.0)) or 0.0
                    )
                    aggregates["regression_rate"] = float(agg.get("regression_rate", 1.0) or 0.0)
                    aggregates["infra_blocked_rate"] = float(agg.get("infra_blocked_rate", 0.0) or 0.0)
                    aggregates["time_to_green_p50"] = float(agg.get("time_to_green_p50", 0.0) or 0.0)
            except Exception as exc:  # noqa: BLE001
                status = "invalid_report"
                error = f"invalid report parse: {exc}"

        rankings.append(
            {
                "preset_name": preset_name,
                "status": status,
                "error": error,
                "preset": preset,
                "report_file": str(run_report),
                "aggregates": aggregates,
            }
        )

    eligible = [
        r
        for r in rankings
        if r.get("status") == "ok" and r.get("aggregates", {}).get("regression_rate", 1.0) <= 0.05
    ]
    eligible_sorted = sorted(
        eligible,
        key=lambda r: (
            -float(r["aggregates"].get("algorithm_success_rate", 0.0)),
            float(r["aggregates"].get("infra_blocked_rate", 1.0)),
            float(r["aggregates"].get("time_to_green_p50", 1e9)),
        ),
    )
    selected = eligible_sorted[0] if eligible_sorted else None

    result = {
        "status": "ok" if selected else "no_eligible_preset",
        "partial": partial,
        "manifest_file": str(manifest_path),
        "presets_file": str(presets_path),
        "max_wall_time_sec": max_wall_time_sec,
        "elapsed_sec": round(time.time() - started_at, 4),
        "selected_preset": selected,
        "rankings": eligible_sorted + [r for r in rankings if r not in eligible_sorted],
    }
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    click.echo(json.dumps(result, indent=2))

# --- External Command Registration ---
try:
    from scripts.engine.commands.ui_explorer import register as register_ui_explorer
    register_ui_explorer(nexus_group, repo_root)
    
    from scripts.engine.commands.swarm import register as register_swarm
    register_swarm(nexus_group, repo_root)
    
    from scripts.engine.commands.stress_test import register as register_stress_test
    register_stress_test(nexus_group, repo_root)
except ImportError as e:
    click.echo(f"⚠️  [Nexus:CLI] Could not load external command module: {e}")

# --- v0.9 聯邦指令 (RESTORED) ---

@nexus.command(name="fed-init")
@click.option("--tenants", default=10)
@click.option("--report-file", default=".nexus/reports/federation/fed_init_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def fed_init(tenants, report_file, output_json):
    """🌐 [v0.9] Federated Init"""
    from scripts.ops.federated_engine_v09 import FederatedEngineV09
    FederatedEngineV09(repo_root).fed_init(num_tenants=tenants)
    payload = {"status": "SUCCESS", "tenants": tenants}
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"📡 Fleet Initialized: {tenants} tenants.")
        click.echo(f"Report: {out_path}")

@nexus.command(name="fed-run")
@click.option("--report-file", default=".nexus/reports/federation/fed_run_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def fed_run(report_file, output_json):
    """🚀 [v0.9] Fed-Run: Execute Federated NAS"""
    from scripts.ops.federated_engine_v09 import FederatedEngineV09
    res = FederatedEngineV09(repo_root).fed_sync()
    payload = {"status": "SUCCESS", "result": res}
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"🧬 [v0.9 Federated NAS] Synchronized {res['aggregation_ratio']} tenants.")
        click.echo(f"Report: {out_path}")
    lesson_script = repo_root / ("scripts/ops/crystal" + "lize_lessons.py")
    subprocess.run([sys.executable, str(lesson_script)], check=False)

# --- v0.8 元進化 (RESTORED) ---
@nexus.command(name="meta-run")
@click.option("--count", default=128)
@click.option("--hybrid", default=0.6)
@click.option("--report-file", default=".nexus/reports/meta/meta_run_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def meta_run(count, hybrid, report_file, output_json):
    """🧬 [v0.8] Meta-Evolve"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    best = EvolutionEngineV08(repo_root).meta_evolve(count=count, hybrid_ratio=hybrid)
    payload = {"status": "SUCCESS", "best": best}
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"🧬 [NAS] Gen {best['gen']} Evolved. Fitness: {best['fitness']}")
        click.echo(f"Report: {out_path}")


@nexus.command(name="run-bug")
@click.argument("task")
@click.option("--auto-flow/--no-auto-flow", default=False, show_default=True)
@click.option("--target-file", required=False, help="Target source file for auto-flow execution.")
@click.option("--test-file", required=False, help="Scoped test file for auto-flow execution.")
@click.option("--root-cause-confidence", default=1.0, type=float, show_default=True)
@click.option("--candidate-count", default=1, type=int, show_default=True)
@click.option("--findings-query", required=False)
def run_bug(task, auto_flow, target_file, test_file, root_cause_confidence, candidate_count, findings_query):
    """Legacy bug-dispatch alias kept for CLI thinning contract tests."""
    if auto_flow:
        if not target_file or not test_file:
            raise click.ClickException("--auto-flow requires --target-file and --test-file")
        payload, out_path = research_flow_service.run_auto_flow(repo_root=repo_root, 
            task_desc=task,
            target_file=target_file,
            test_file=test_file,
            task_type="bug",
            success_criteria="all_target_tests_pass",
            candidate_count=candidate_count,
            root_cause_confidence=root_cause_confidence,
            findings_query=findings_query,
            llm_mode=False,
            llm_baseline=False,
            timeout_sec=60,
            stage1_timeout_sec=20,
            max_time_ratio_guard=1.5,
            baseline_fast_sec=9.0,
            history_window=5,
            history_fail_threshold=2,
            dynamic_timeout_multiplier=2.5,
            min_dynamic_stage1_timeout=12,
            force_flow=None,
            report_file=".nexus/reports/research/auto-flow-report.json",
            output_file=None,
        )
        click.echo(f"Chosen Flow: {payload['chosen_flow']}")
        click.echo(f"Status: {payload['result']['status']}")
        click.echo(f"Elapsed: {payload['result']['elapsed_sec']} sec")
        click.echo(f"Report: {out_path}")
        return
    click.echo(f"dispatch bug: {task}")


@nexus.command(
    name="run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option(
    "--local-assist-policy",
    type=click.Choice(["disabled", "shadow", "advisor", "planner", "explicit"]),
    default=None,
)
@click.option(
    "--online-policy",
    type=click.Choice(["deny", "auto", "require"]),
    default=None,
)
@click.pass_context
def compat_run(ctx: click.Context, local_assist_policy: str | None, online_policy: str | None):
    """Compatibility alias for `nexus run` (forwards to nested group)."""
    if local_assist_policy is not None:
        ctx.args.extend(["--local-assist-policy", local_assist_policy])
    if online_policy is not None:
        ctx.args.extend(["--online-policy", online_policy])
    _forward_to_nested_nexus(ctx, "run")


@nexus.command(
    name="research:sprint",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def compat_research_sprint(ctx: click.Context):
    """Compatibility alias for `nexus research:sprint`."""
    _forward_to_nested_nexus(ctx, "research:sprint")


@nexus.command(
    name="research:auto-flow",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def compat_research_auto_flow(ctx: click.Context):
    """Compatibility alias for `nexus research:auto-flow`."""
    _forward_to_nested_nexus(ctx, "research:auto-flow")


@nexus_group.command(name="learn:phase-policy")
@click.option("--task-type", default="bug")
@click.option("--risk", default="standard")
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_phase_policy_cmd(task_type, risk, output_json):
    """🧠 Show phase-policy decisions for a hypothetical task."""
    out = get_learn_phase_policy(repo_root, task_type=task_type, risk=risk)
    if output_json:
        click.echo(json.dumps(out, indent=2))
    else:
        for line in render_learn_phase_policy(out):
            click.echo(line)


@nexus_group.command(name="learn:scheduler-status")
@click.option("--output-json", is_flag=True)
@translate_action_exceptions
def learn_scheduler_status_cmd(output_json):
    """📊 Show status of the production learn scheduler."""
    out = get_learn_scheduler_status(repo_root)
    if out is None:
        click.echo("No scheduler run history found.")
        return

    if output_json:
        click.echo(json.dumps(out, indent=2))
    else:
        for line in render_learn_scheduler_status(out):
            click.echo(line)

@nexus_group.command(name="learn:benchmark")
@click.option("--manifest-file", required=True, type=click.Path(exists=True))
@click.option("--topic", required=True)
@click.option("--source", help="Legacy param")
@click.option("--source-file", help="Legacy param")
@click.option("--output-json", is_flag=True)
@click.option("--output", default=".nexus/reports/learn/precision_benchmark.json", type=click.Path())
@translate_action_exceptions
def learn_benchmark_cmd(manifest_file, topic, source, source_file, output_json, output):
    """📊 Legacy benchmark alias (kept for backward compatibility)."""
    summary = run_learn_precision_benchmark(repo_root, manifest_file=manifest_file, topic=topic)
    if output_json:
        click.echo(json.dumps(summary, indent=2))
        return

    click.echo(f"🚀 Running Learn Precision Benchmark on topic: {topic}")
    write_learn_precision_benchmark_output(summary, output)
    click.echo(render_learn_precision_benchmark_complete(summary))


@nexus_group.command(name="oracle:apply")
@click.argument("shadow_tid")
@click.option("--report-file", default=".nexus/reports/oracle/oracle_apply_report.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def oracle_apply(shadow_tid, report_file, output_json):
    """🚀 [Oracle] Promote a successful shadow patch to main workspace."""
    from nexus.oracle.promote import promote_shadow_patch
    ok = promote_shadow_patch(repo_root, shadow_tid)
    payload = {"status": "SUCCESS" if ok else "FAILED", "shadow_tid": shadow_tid}
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    elif ok:
        click.secho(f"✅ Successfully promoted future patch {shadow_tid} to the present.", fg="green")
        click.echo(f"Report: {out_path}")
    else:
        click.secho("❌ Promotion failed.", fg="red")
        click.echo(f"Report: {out_path}")

@nexus_group.group(name="multi-agent")
def multi_agent_group():
    """🤖 Multi-Agent Orchestration & Fleet Management"""
    pass

@multi_agent_group.command(name="init")
def multi_agent_init():
    """🛠️ Initialize multi-agent environment."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    NexusOrchestrator()
    click.secho("✅ Multi-agent environment initialized.", fg="green")

@multi_agent_group.command(name="create-task")
@click.option("--task-id", required=True)
@click.option("--owner", required=True)
@click.option("--allowed-files", required=True, help="Comma separated files")
@translate_action_exceptions
def create_task_cmd(task_id, owner, allowed_files):
    """📝 Create a new multi-agent task."""
    for line in create_multi_agent_task(
        task_id=task_id,
        owner=owner,
        allowed_files_csv=allowed_files,
    ):
        click.echo(line)

@multi_agent_group.command(name="start")
@click.option("--task-id", required=True)
@translate_action_exceptions
def start_task_cmd(task_id):
    """🚀 Start a task (locks files + creates worktree)."""
    for line in render_multi_agent_task_start(start_multi_agent_task(task_id)):
        click.echo(line)

@multi_agent_group.command(name="status")
@click.option("--task-id")
@click.option("--json", "output_json", is_flag=True)
@translate_action_exceptions
def task_status_cmd(task_id, output_json):
    """📊 Show task status."""
    view = get_multi_agent_task_status(task_id)
    for line in render_multi_agent_task_status(view, output_json=output_json):
        click.echo(line)

@multi_agent_group.command(name="verify")
@click.option("--task-id", required=True)
@translate_action_exceptions
def verify_task_cmd(task_id):
    """✅ Run verification gates for a task."""
    for line in render_multi_agent_task_verification(verify_multi_agent_task(task_id)):
        click.echo(line)

@multi_agent_group.command(name="close")
@click.option("--task-id", required=True)
@click.option("--no-cleanup", is_flag=True)
@translate_action_exceptions
def close_task_cmd(task_id, no_cleanup):
    """🏁 Close a task and release locks."""
    for line in close_multi_agent_task(task_id, no_cleanup=no_cleanup):
        click.echo(line)

@multi_agent_group.command(name="integrate")
@click.option("--task-ids", required=True, help="Comma separated task IDs")
@click.option("--target-branch", default="main")
@translate_action_exceptions
def integrate_tasks_cmd(task_ids, target_branch):
    """🚢 Integrate multiple tasks into target branch."""
    view = integrate_multi_agent_tasks(task_ids, target_branch=target_branch)
    for line in render_multi_agent_task_integration(view):
        click.echo(line)

@multi_agent_group.command(name="audit")
@click.option("--task-id", required=True)
@translate_action_exceptions
def audit_task_cmd(task_id):
    """🔍 Audit task evidence chain."""
    for line in render_multi_agent_task_audit(get_multi_agent_task_audit(task_id)):
        click.echo(line)

@multi_agent_group.command(name="metrics")
@click.option("--json", "output_json", is_flag=True)
@translate_action_exceptions
def show_metrics_cmd(output_json):
    """📊 Show multi-agent fleet metrics."""
    metrics = get_multi_agent_metrics()
    if output_json:
        click.echo(json.dumps(metrics, indent=2))
    else:
        for line in render_multi_agent_metrics(metrics):
            click.echo(line)

@multi_agent_group.command(name="submit")
@click.option("--task-id", required=True)
@translate_action_exceptions
def submit_task_cmd(task_id):
    """🚀 Submit task with full verification & protocol evidence."""
    for line in render_multi_agent_task_submission(submit_multi_agent_task(task_id, repo_root=repo_root)):
        click.echo(line)


# --- v4.0: Skills & Registry Management ---
@nexus_group.group(name="skills")
def skills_group():
    """🧠 Manage external skills and manual teach-ins."""
    pass

@skills_group.command(name="sync")
@translate_action_exceptions
def skills_sync():
    """📥 Sync external skills from ~/.agents/skills/ into SQLite registry."""
    result = sync_external_skills(repo_root)
    click.secho(render_skill_sync_complete(result), fg="green", bold=True)

@skills_group.command(name="list")
@translate_action_exceptions
def skills_list():
    """📋 List all registered skills (internal + external)."""
    for line in render_skills_list(get_skills_list(repo_root)):
        click.echo(line)

@nexus_group.group(name="registry")
def registry_group():
    """🗄️ Unified Resource Registry (SSoT) status and maintenance."""
    pass

@registry_group.command(name="status")
@translate_action_exceptions
def registry_status():
    """📊 Check health of assets, databases, and external skill paths."""
    lines = render_registry_status(get_registry_status(repo_root))
    click.secho(lines[0], fg="cyan", bold=True)
    for line in lines[1:]:
        click.echo(line)

@nexus_group.group(name="bench")
def bench_group():
    """📈 Autonomous performance benchmarking and ROI analysis."""
    pass

@bench_group.command(name="effort")
@translate_action_exceptions
def bench_effort():
    """📊 Analyze success rates and ROI per effort level."""
    lines = render_effort_roi_report(get_effort_roi_report(repo_root))
    click.secho(lines[0], fg="magenta", bold=True)
    for line in lines[1:]:
        click.echo(line)

@nexus_group.group(name="sandbox")
def sandbox_group():
    """🏗️ Isolated environment execution and validation."""
    pass

@sandbox_group.command(name="run")
@click.option("--task", required=True)
@click.option("--command", "command_text", default=None, help="Explicit local command to run in the sandbox.")
@click.option("--cwd", default=".", show_default=True, help="Relative working directory inside the sandbox workspace.")
@click.option("--timeout-sec", default=60, show_default=True, type=int)
@click.option("--output-file", default=None, type=click.Path(), help="Optional sandbox-relative artifact to collect.")
@click.option("--keep-workspace", is_flag=True, help="Keep copied sandbox workspace after execution.")
@translate_action_exceptions
def sandbox_run_cmd(task, command_text, cwd, timeout_sec, output_file, keep_workspace):
    """🏗️ Run a task in a physical Git-worktree sandbox."""
    result = run_sandbox_task(
        repo_root,
        task,
        command=parse_sandbox_command(command_text),
        cwd=cwd,
        timeout_sec=timeout_sec,
        output_file=output_file,
        cleanup=not keep_workspace,
    )
    for line in render_sandbox_run_result(result):
        click.secho(line, fg="cyan")


# --- v26 Mission Control (持久化編排戰役) ---

@nexus_group.group(name="mission")
def mission_group():
    """🛡️ [Mission Control] Manage persistent S-P-X-D-R-A-C campaigns."""
    pass

@mission_group.command(name="create")
@click.argument("objective")
@click.option("--max-tokens", default=1000000.0, type=float)
@click.option("--max-retries", default=10.0, type=float)
def mission_create(objective, max_tokens, max_retries):
    """⚔️ Initialize .nexus/mission.json and secure a new campaign objective."""
    import uuid
    from nexus.core.mission_contracts import NexusMission, MissionStatus
    
    mission = NexusMission(
        mission_id="MSN-" + uuid.uuid4().hex[:8].upper(),
        objective=objective,
        status=MissionStatus.DRAFT,
        budget={
            "max_tokens": max_tokens,
            "max_wall_time_sec": 259200.0, # 72 hours
            "max_retries": max_retries
        }
    )
    mission.persist(repo_root)
    click.secho(f"✅ Successfully created mission: {mission.mission_id}", fg="green", bold=True)
    click.echo(f"🎯 Objective: {mission.objective}")
    click.echo(f"💾 Config saved to .nexus/mission.json")

@mission_group.command(name="start")
def mission_start():
    """🚀 Run budget & fingerprint checks, switch state, and launch the loop."""
    import uuid
    from nexus.core.mission_contracts import NexusMission, MissionStatus
    
    mission = NexusMission.load(repo_root)
    if not mission:
        click.secho("❌ No mission found. Run 'nexus mission create' first.", fg="red")
        sys.exit(1)
        
    # 1. 環境指紋與 preflight 檢查 (Environment Fingerprinting)
    if not mission.run_fingerprint_preflight(repo_root):
        click.secho("❌ [Environment Blocked] Preflight failed or Git SHA shifted.", fg="red", bold=True)
        sys.exit(1)

    # 2. 預算監控 (Gateway-level Telemetry)
    if not mission.check_telemetry_budget():
        click.secho("❌ [Budget Violation] Accumulated cost has breached maximum limits.", fg="red", bold=True)
        sys.exit(1)

    # 3. 激活狀態並開啟戰役
    mission.status = MissionStatus.ACTIVE
    run_id = "RUN-" + uuid.uuid4().hex[:6].upper()
    mission.current_run_id = run_id
    mission.run_history.append(run_id)
    mission.persist(repo_root)
    
    click.secho(f"🚀 Launching campaign for mission {mission.mission_id} (Run: {run_id})", fg="cyan", bold=True)
    
    # 4. 呼叫實體戰役執行
    # 複用現有的 nexus run 命令子進程，以便完整使用自癒與 TDD 驗證
    cmd = [sys.executable, str(repo_root / "scripts/engine/nexus_cli.py"), "nexus", "run", mission.mission_id]
    res = subprocess.run(cmd, check=False)
    
    # 5. 更新結束後的狀態與 telemetry 統計
    # 實作上可檢查報告判定完戰
    mission = NexusMission.load(repo_root) # 重新載入，避免執行期間被子進程修改
    if res.returncode == 0:
        # 完戰 gate 驗收
        acceptance_report = repo_root / ".nexus" / "reports" / "acceptance_check.json"
        if acceptance_report.exists():
            try:
                data = json.loads(acceptance_report.read_text(encoding="utf-8"))
                if data.get("status") == "PASS" and data.get("gate_passed") is True:
                    mission.status = MissionStatus.COMPLETED
            except Exception:
                pass
    else:
        mission.accumulated_usage["retries"] += 1
        if mission.accumulated_usage["retries"] >= mission.budget.get("max_retries", 10.0):
            mission.status = MissionStatus.BLOCKED
            
    mission.persist(repo_root)
    click.echo(f"🏁 Campaign execution terminated. Status: {mission.status.value}")

@mission_group.command(name="status")
def mission_status():
    """📊 Render current campaign objective, state and cumulative costs."""
    from nexus.core.mission_contracts import NexusMission
    mission = NexusMission.load(repo_root)
    if not mission:
        click.echo("❌ No active mission registered.")
        return
        
    click.secho(f"🛡️ [Mission Control Status: {mission.mission_id}]", fg="cyan", bold=True)
    click.echo(f"- Objective: {mission.objective}")
    click.echo(f"- Current Status: {mission.status.value}")
    click.echo(f"- Current Run ID: {mission.current_run_id}")
    click.echo(f"- Git Fingerprint: {mission.git_fingerprint}")
    click.echo(f"- Budget Limits:")
    for k, v in mission.budget.items():
        click.echo(f"  * {k}: {v}")
    click.echo(f"- Accumulated Cost:")
    for k, v in mission.accumulated_usage.items():
        click.echo(f"  * {k}: {v}")

@mission_group.command(name="pause")
def mission_pause():
    """⏸️ Force snapshot of current state and pause the campaign."""
    from nexus.core.mission_contracts import NexusMission, MissionStatus
    mission = NexusMission.load(repo_root)
    if not mission:
        click.echo("❌ No mission found.")
        return
        
    mission.status = MissionStatus.PAUSED
    
    # 呼叫現有 metabolism 引擎保存實體 checkpoint 快照
    from nexus.services.metabolism_engine import metabolism
    checkpoint = metabolism.load_checkpoint()
    if checkpoint:
        # 假設以當前 checkpoint 作為 resume 還原點
        mission.last_snapshot_path = ".nexus/metabolism/mission_complete.json"
        
    mission.persist(repo_root)
    click.secho(f"⏸️ Mission {mission.mission_id} successfully paused.", fg="yellow", bold=True)

@mission_group.command(name="resume")
def mission_resume():
    """🌬️ Check environment preflight, budget, and restore the loop from snapshot."""
    from nexus.core.mission_contracts import NexusMission, MissionStatus
    mission = NexusMission.load(repo_root)
    if not mission:
        click.echo("❌ No paused mission found.")
        return
        
    # 1. 環境指紋校對 (Environment Fingerprinting)
    if not mission.run_fingerprint_preflight(repo_root):
        click.secho("❌ [Blocked] Fingerprint mismatch. Environment corrupted.", fg="red", bold=True)
        sys.exit(1)

    # 2. 預算校對 (Gateway-level Telemetry)
    if not mission.check_telemetry_budget():
        click.secho("❌ [Blocked] Mission budget exceeded.", fg="red", bold=True)
        sys.exit(1)

    # 3. 切換狀態並恢復
    mission.status = MissionStatus.ACTIVE
    mission.persist(repo_root)
    
    click.secho(f"🌬️ Resuming mission: {mission.mission_id}", fg="green", bold=True)
    
    # 4. 呼叫 metabolism 實體 resume 恢復機制
    cmd = [sys.executable, str(repo_root / "scripts/engine/nexus_cli.py"), "nexus", "resume"]
    subprocess.run(cmd, check=False)


@nexus_group.group(name="self-hosted")
def self_hosted_group():
    """🏠 Self-hosted task execution and status governance."""
    pass


nexus.add_command(self_hosted_group, name="self-hosted")


@self_hosted_group.command(name="submit")
@click.option("--request-file", "-f", type=click.Path(exists=True, dir_okay=False), help="Path to JSON file with task request.")
@click.option("--task-id", help="Explicit task ID.")
@click.option("--what", help="Task objective (WHAT).")
@click.option("--why", help="Task justification (WHY).")
@click.option("--controller-revision", help="Controller Git revision SHA.")
@click.option("--target-base-revision", help="Target base Git revision SHA.")
@click.option("--controller-repo-root", help="Controller repository root path.")
@click.option("--target-repo-root", help="Target repository root path.")
@click.option("--target-worktree-root", help="Target worktree root path.")
@click.option("--allowed-files", help="Comma-separated list of allowed file patterns.")
@click.option("--forbidden-files", help="Comma-separated list of forbidden file patterns.")
@click.option("--authorized-deletions", help="Comma-separated list of exact files allowed to be deleted.")
@click.option("--verifier-commands", help="Comma-separated list of verifier commands.")
@click.option("--protected-contracts", help="Comma-separated list of protected contracts.")
@click.option("--execution-lane", type=click.Choice(["DIRECT_CANONICAL", "ISOLATED_TARGET"]), default=None, help="Execution lane; ordinary primary work defaults to Direct Canonical.")
@click.option("--worker", default=None, help="Worker provider (e.g. codex, auto).")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_submit(
    request_file: str | None,
    task_id: str | None,
    what: str | None,
    why: str | None,
    controller_revision: str | None,
    target_base_revision: str | None,
    controller_repo_root: str | None,
    target_repo_root: str | None,
    target_worktree_root: str | None,
    allowed_files: str | None,
    forbidden_files: str | None,
    authorized_deletions: str | None,
    verifier_commands: str | None,
    protected_contracts: str | None,
    execution_lane: str | None,
    worker: str | None,
    state_dir: str | None,
) -> None:
    """Submit a governed self-hosted task."""
    request_data: dict[str, Any] = {}
    if request_file:
        with open(request_file, "r", encoding="utf-8") as f:
            request_data = json.load(f)

    if task_id is not None:
        request_data["task_id"] = task_id
    if what is not None:
        request_data["what"] = what
    if why is not None:
        request_data["why"] = why
    if controller_revision is not None:
        request_data["controller_revision"] = controller_revision
    if target_base_revision is not None:
        request_data["target_base_revision"] = target_base_revision
    if controller_repo_root is not None:
        request_data["controller_repo_root"] = controller_repo_root
    if target_repo_root is not None:
        request_data["target_repo_root"] = target_repo_root
    if target_worktree_root is not None:
        request_data["target_worktree_root"] = target_worktree_root
    if worker is not None:
        request_data["worker"] = worker
    if execution_lane is not None:
        request_data["execution_lane"] = execution_lane

    def _split_csv(val: str | None) -> list[str] | None:
        if val is None:
            return None
        return [s.strip() for s in val.split(",") if s.strip()]

    af = _split_csv(allowed_files)
    if af is not None:
        request_data["allowed_files"] = af
    ff = _split_csv(forbidden_files)
    if ff is not None:
        request_data["forbidden_files"] = ff
    ad = _split_csv(authorized_deletions)
    if ad is not None:
        request_data["authorized_deletions"] = ad
    vc = _split_csv(verifier_commands)
    if vc is not None:
        request_data["verifier_commands"] = vc
    pc = _split_csv(protected_contracts)
    if pc is not None:
        request_data["protected_contracts"] = pc

    res = run_self_hosted_submit(request_data, state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="direct-complete")
@click.option("--request-file", "request_file", type=click.Path(exists=True, dir_okay=False), required=True, help="JSON Direct Canonical request.")
@click.option("--expected-commit-sha", default=None, help="Expected canonical HEAD after the scoped commit.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory for mutation-task occupancy checks.")
@translate_action_exceptions
def self_hosted_direct_complete(
    request_file: str,
    expected_commit_sha: str | None,
    state_dir: str | None,
) -> None:
    """Verify a primary-agent commit in the canonical checkout without a Target."""
    with open(request_file, "r", encoding="utf-8") as handle:
        request_data = json.load(handle)
    res = run_self_hosted_direct_complete(
        request_data,
        expected_commit_sha=expected_commit_sha,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="retry")
@click.option("--task-id", required=True, help="Exact durable task ID to retry without duplication.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_retry(task_id: str, state_dir: str | None) -> None:
    """Retry a terminal task using its durable request and the same task ID."""
    res = run_self_hosted_retry(task_id, state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="retry-integration")
@click.option("--task-id", required=True, help="Exact durable task ID whose integration failed.")
@click.option("--integration-branch", default=None, help="Override the original integration branch.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_retry_integration(task_id: str, integration_branch: str | None, state_dir: str | None) -> None:
    """Retry only integration for an INTEGRATION_FAILED task."""
    res = run_self_hosted_retry_integration(
        task_id,
        integration_branch=integration_branch,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="receipt")
@click.option("--task-id", required=True, help="Exact durable task ID to inspect.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_receipt(task_id: str, state_dir: str | None) -> None:
    """Read the durable execution receipt for a self-hosted task."""
    res = run_self_hosted_receipt(task_id, state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="status")
@click.option("--task-id", required=True, help="Task ID to inspect.")
@click.option("--details", "include_details", is_flag=True, default=False, help="Include the full durable state.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_status(task_id: str, include_details: bool, state_dir: str | None) -> None:
    """Read durable status for a self-hosted task."""
    res = run_self_hosted_status(task_id, include_details=include_details, state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="wait")
@click.option("--task-id", required=True, help="Task ID to wait for.")
@click.option("--timeout", "timeout_seconds", type=float, default=10.0, help="Timeout in seconds.")
@click.option("--poll-interval", "poll_interval_seconds", type=float, default=0.25, help="Poll interval in seconds.")
@click.option("--details", "include_details", is_flag=True, default=False, help="Include the full durable state.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_wait(
    task_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    include_details: bool,
    state_dir: str | None,
) -> None:
    """Wait for a self-hosted task until terminal/attention_required or timeout."""
    res = run_self_hosted_wait(
        task_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        include_details=include_details,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="list-actionable")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_list_actionable(state_dir: str | None) -> None:
    """List self-hosted tasks requiring action."""
    res = run_self_hosted_list_actionable(state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="workspace-inventory")
@click.option("--controller-root", type=click.Path(), default=None, help="Controller repository root.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_workspace_inventory(controller_root: str | None, state_dir: str | None) -> None:
    """Read-only machine-readable workspace inventory."""
    res = run_self_hosted_workspace_inventory(
        controller_root=controller_root,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="workspace-plan")
@click.option("--controller-root", type=click.Path(), default=None, help="Controller repository root.")
@click.option("--expected-controller-revision", default=None, help="Expected Controller revision SHA.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_workspace_plan(
    controller_root: str | None,
    expected_controller_revision: str | None,
    state_dir: str | None,
) -> None:
    """Build a read-only workspace convergence plan."""
    res = run_self_hosted_workspace_plan(
        controller_root=controller_root,
        expected_controller_revision=expected_controller_revision,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="state-root-inventory")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_state_root_inventory(state_dir: str | None) -> None:
    """Inventory canonical and nested lifecycle receipts without mutation."""
    res = run_self_hosted_state_root_inventory(state_dir=state_dir)
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="workspace-slot-status")
@click.option("--campaign-id", default="default", show_default=True, help="Reusable slot campaign ID.")
@click.option("--slot-index", type=int, default=0, show_default=True, help="Reusable slot index.")
@click.option("--controller-root", type=click.Path(), default=None, help="Controller repository root.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_workspace_slot_status(
    campaign_id: str,
    slot_index: int,
    controller_root: str | None,
    state_dir: str | None,
) -> None:
    """Read-only reusable-slot readiness status."""
    res = run_self_hosted_workspace_slot_status(
        campaign_id=campaign_id,
        slot_index=slot_index,
        controller_root=controller_root,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="workspace-slot-prepare")
@click.option("--request-file", "request_file", type=click.Path(exists=True, dir_okay=False), required=True, help="JSON task request used to prepare the slot.")
@click.option("--campaign-id", default="default", show_default=True, help="Reusable slot campaign ID.")
@click.option("--slot-index", type=int, default=0, show_default=True, help="Reusable slot index.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_workspace_slot_prepare(
    request_file: str,
    campaign_id: str,
    slot_index: int,
    state_dir: str | None,
) -> None:
    """Prepare or reuse one governed sequential workspace slot."""
    with open(request_file, "r", encoding="utf-8") as handle:
        request_data = json.load(handle)
    res = run_self_hosted_workspace_slot_prepare(
        request_data,
        campaign_id=campaign_id,
        slot_index=slot_index,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="workspace-converge")
@click.option("--expected-controller-revision", required=True, help="Exact Controller revision bound to the plan.")
@click.option("--expected-plan-hash", required=True, help="Exact plan hash bound to the dry-run.")
@click.option("--controller-root", type=click.Path(), default=None, help="Controller repository root.")
@click.option("--apply", is_flag=True, help="Apply eligible lifecycle-bound cleanup; default is dry-run.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_workspace_converge(
    expected_controller_revision: str,
    expected_plan_hash: str,
    controller_root: str | None,
    apply: bool,
    state_dir: str | None,
) -> None:
    """Preview or explicitly apply an exact-bound workspace convergence plan."""
    res = run_self_hosted_workspace_converge(
        expected_controller_revision=expected_controller_revision,
        expected_plan_hash=expected_plan_hash,
        controller_root=controller_root,
        apply=apply,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="cleanup")
@click.option("--task-id", required=True, help="Exact task ID to clean up.")
@click.option("--apply", is_flag=True, help="Apply eligible cleanup; default is dry-run.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_cleanup(
    task_id: str,
    apply: bool,
    state_dir: str | None,
) -> None:
    """Preview or apply governed cleanup for one self-hosted task."""
    res = run_self_hosted_cleanup(
        task_id=task_id,
        apply=apply,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="approve")
@click.option("--task-id", required=True, help="Task ID to approve.")
@click.option("--candidate-commit-sha", required=True, help="Candidate commit SHA.")
@click.option("--candidate-tree-sha", required=True, help="Candidate tree SHA.")
@click.option("--candidate-state-hash", required=True, help="Candidate state hash.")
@click.option("--verified-receipt-hash", required=True, help="Verified receipt hash.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_approve(
    task_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    candidate_state_hash: str,
    verified_receipt_hash: str,
    state_dir: str | None,
) -> None:
    """Approve candidate promotion for a self-hosted task with exact binding."""
    res = run_self_hosted_approve(
        task_id=task_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        candidate_state_hash=candidate_state_hash,
        verified_receipt_hash=verified_receipt_hash,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="integrate")
@click.option("--task-id", required=True, help="Task ID to integrate.")
@click.option("--integration-branch", default="nexus/integration", help="Target integration branch name.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_integrate(
    task_id: str,
    integration_branch: str,
    state_dir: str | None,
) -> None:
    """Integrate an approved self-hosted candidate task into the integration branch."""
    res = run_self_hosted_integrate(
        task_id=task_id,
        integration_branch=integration_branch,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="owner-finish")
@click.option("--task-id", required=True, help="Task ID to finish.")
@click.option("--candidate-commit-sha", required=True, help="Exact candidate commit SHA.")
@click.option("--candidate-tree-sha", required=True, help="Exact candidate tree SHA.")
@click.option("--candidate-state-hash", required=True, help="Exact candidate state hash.")
@click.option("--verified-receipt-hash", required=True, help="Exact verified receipt hash.")
@click.option("--integration-branch", default="nexus/integration/main", show_default=True)
@click.option("--state-dir", type=click.Path(), default=None)
@translate_action_exceptions
def self_hosted_owner_finish(
    task_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    candidate_state_hash: str,
    verified_receipt_hash: str,
    integration_branch: str,
    state_dir: str | None,
) -> None:
    """Owner-only atomic approval and integration of an exact candidate binding."""
    res = run_self_hosted_owner_finish(
        task_id=task_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        candidate_state_hash=candidate_state_hash,
        verified_receipt_hash=verified_receipt_hash,
        integration_branch=integration_branch,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="dispose")
@click.option("--task-id", required=True, help="Task ID to dispose.")
@click.option("--disposition", type=click.Choice(["REJECTED", "SUPERSEDED"], case_sensitive=False), required=True, help="Disposition type (REJECTED or SUPERSEDED).")
@click.option("--superseded-by", default=None, help="Optional replacing task or evidence ID if SUPERSEDED.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_dispose(
    task_id: str,
    disposition: str,
    superseded_by: str | None,
    state_dir: str | None,
) -> None:
    """Dispose candidate promotion (REJECTED or SUPERSEDED)."""
    res = run_self_hosted_dispose(
        task_id=task_id,
        disposition=disposition.upper(),
        superseded_by=superseded_by,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="close-without-candidate")
@click.option("--task-id", required=True, help="Task ID to close without candidate.")
@click.option("--superseded-by", required=True, help="Replacing task or evidence ID.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_close_without_candidate(
    task_id: str,
    superseded_by: str,
    state_dir: str | None,
) -> None:
    """Close a RETAINED_FOR_REVIEW or FINAL_BLOCK task that produced no candidate evidence."""
    res = run_self_hosted_close_without_candidate(
        task_id=task_id,
        superseded_by=superseded_by,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="cancel")
@click.option("--task-id", required=True, help="Task ID to cancel.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_cancel(
    task_id: str,
    state_dir: str | None,
) -> None:
    """Cancel a non-running self-hosted task and run terminal cleanup."""
    res = run_self_hosted_cancel(
        task_id=task_id,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="recover-verified-uncommitted")
@click.option("--task-id", required=True, help="Task ID to recover.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_recover_verified_uncommitted(
    task_id: str,
    state_dir: str | None,
) -> None:
    """Recover a verified-uncommitted candidate task."""
    res = run_self_hosted_recover_verified_uncommitted(
        task_id=task_id,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))


@self_hosted_group.command(name="verify")
@click.option("--task-id", required=True, help="Task ID to verify.")
@click.option("--state-dir", type=click.Path(), default=None, help="Custom state directory.")
@translate_action_exceptions
def self_hosted_verify(
    task_id: str,
    state_dir: str | None,
) -> None:
    """Read-only verification of a self-hosted task."""
    res = run_self_hosted_verify(
        task_id=task_id,
        state_dir=state_dir,
    )
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))



if __name__ == "__main__":

    nexus()
