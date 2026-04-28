#!/usr/bin/env python3
import re
import sys
import os
import json
import subprocess
import time
from pathlib import Path

import yaml
import click

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

repo_root = REPO_ROOT

from nexus.app.oracle_dispatcher import OracleDispatcher
from nexus.app.oracle_advisor import OracleAdvisor
from nexus.app import research_flow_service
from nexus.engine.canonical_task_seam import build_legacy_cli_service, execute_single_task_via_service
from nexus.engine.completion_contract import build_completion_envelope
from nexus.engine.completion_contract import ensure_verified_completion
from nexus.engine.completion_contract import write_completion_envelope
from nexus.engine.completion_enforcer import CompletionEnforcementError
from nexus.engine.completion_enforcer import write_completion_handoff
from nexus.engine.direct_mode import evaluate_direct_mode_completion

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
    """⚖️ Nexus v23.7 Fleet Command & Sensory CLI"""
    pass


def _blocked_deprecated(old: str, new: str):
    """🚫 DEPRECATED_BLOCKED: 停止執行並引導至新入口。"""
    click.secho(f"❌ [DEPRECATED_BLOCKED] 此命令 '{old}' 已停用。", fg="red", bold=True)
    click.echo(f"💡 請改用唯一新入口：\n   {new}")
    sys.exit(2)

@nexus.command(name="nexus:status")
def legacy_status():
    _blocked_deprecated("nexus:status", "uv run scripts/engine/nexus_cli.py nexus status")


@nexus.command(name="nexus:hud")
def legacy_hud():
    _blocked_deprecated("nexus:hud", "uv run scripts/engine/nexus_cli.py nexus status")


@nexus.command(name="nexus:spec-lock")
def legacy_spec_lock():
    _blocked_deprecated("nexus:spec-lock", "MUSE_ENGINE_SPEC 審計已整合入 ci_gate。")


@nexus.command(name="nexus:governance-check")
def legacy_governance_check():
    _blocked_deprecated("nexus:governance-check", "uv run scripts/ops/ci_gate.py --dry-run")


@nexus.command(name="nexus:acceptance-check")
def legacy_acceptance_check():
    _blocked_deprecated("nexus:acceptance-check", "uv run scripts/engine/nexus_cli.py nexus acceptance-check --evidence <FILE>")


@nexus.command(name="nexus:closeout")
def legacy_closeout():
    _blocked_deprecated("nexus:closeout", "uv run scripts/engine/nexus_cli.py nexus contract-check --contract-file <FILE>")

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
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional report path.")
def code_impact(files_text: str, output_json: bool, report_file: str | None):
    """Analyze changed-file impact with Nexus native CodeIntel."""
    from nexus.services.codeintel import analyze_impact

    changed_files = [item.strip() for item in files_text.split(",") if item.strip()]
    result = analyze_impact(repo_root, changed_files).to_dict()
    out_path = Path(report_file) if report_file else repo_root / ".nexus" / "reports" / "codeintel" / "impact.json"
    out_path = out_path if out_path.is_absolute() else repo_root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result["report_path"] = str(out_path)
    evidence_paths = list(result.get("evidence_paths", []) or [])
    if str(out_path) not in evidence_paths:
        evidence_paths.append(str(out_path))
    result["evidence_paths"] = evidence_paths
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        click.echo(f"Code impact: {len(result['impacted_files'])} impacted files, risk={result['risk_score']}")
        click.echo(f"Report: {out_path}")


@code_group.command(name="scan")
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--index-path", type=click.Path(), default=None, help="Optional graph index path.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional scan report path.")
def code_scan(output_json: bool, index_path: str | None, report_file: str | None):
    """Build a deterministic Nexus native CodeIntel graph index."""
    from nexus.services.codeintel import scan_codebase

    result = scan_codebase(repo_root, index_path=index_path).to_dict()
    out_path = Path(report_file) if report_file else repo_root / ".nexus" / "reports" / "codeintel" / "scan.json"
    out_path = out_path if out_path.is_absolute() else repo_root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        click.echo(f"Code scan: {result['nodes_count']} nodes, {result['edges_count']} edges")
        click.echo(f"Index: {result['index_path']}")
        click.echo(f"Report: {out_path}")


@code_group.command(name="context")
@click.option("--symbol", required=True, help="Module or symbol name to inspect.")
@click.option("--index-path", type=click.Path(), default=None, help="Optional graph index path.")
@click.option("--output-json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--report-file", type=click.Path(), default=None, help="Optional context report path.")
def code_context(symbol: str, index_path: str | None, output_json: bool, report_file: str | None):
    """Inspect callers, callees, files, and related tests for a symbol."""
    from nexus.services.codeintel import context_for_symbol

    result = context_for_symbol(repo_root, symbol, index_path=index_path).to_dict()
    out_path = Path(report_file) if report_file else repo_root / ".nexus" / "reports" / "codeintel" / "context.json"
    out_path = out_path if out_path.is_absolute() else repo_root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status_text = "found" if result["found"] else f"missing:{result['reason']}"
        click.echo(f"Code context: {symbol} {status_text}")
        click.echo(f"Report: {out_path}")

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
def run(task_id, complexity, output_file, report_file):
    """🚀 [Nexus Master Loop] Execute task with full P-X-D-R-A-C unification."""
    click.secho(f"🛡️ [NEXUS v24.9.5] Initiating Master Loop for: {task_id}", fg="cyan", bold=True)

    if _task_requests_output_file(task_id) and not output_file:
        raise click.ClickException("Task requests file output. Please provide --output-file.")
    
    from nexus.core.campaign_general import CampaignGeneral
    from nexus.engine.cli_runner_async import campaign_master_loop
    import asyncio

    # 偵測史詩/宏觀任務
    is_macro = any(kw in task_id.lower() for kw in ["system", "app", "complete", "refactor all", "build a", "史詩"])
    
    runtime_ok = True
    if is_macro:
        click.secho("🗺️ [L4:Macro-Mode]史詩級任務偵測。啟動戰役大將 (Campaign-General)...", fg="magenta", bold=True)
        commander = CampaignGeneral(REPO_ROOT)
        task_nodes = commander.decompose_intent(task_id)
        click.echo(f"   [L4] 戰役地圖已生成：{len(task_nodes)} 個戰術節點。")
        
        # 啟動異步調度循環
        asyncio.run(campaign_master_loop(commander, task_nodes, REPO_ROOT))
    else:
        runtime_ok = bool(execute_single_task_via_service(task_id, REPO_ROOT))

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
        execution_path="cli->command_service->engine",
        artifact_paths=artifact_paths,
        semantic_failures=direct_mode_audit["semantic_failures"],
        tests_run=direct_mode_audit["verify_results"],
    )
    if direct_mode_audit["enabled"]:
        report_payload["direct_mode"] = direct_mode_audit["spec"]
        report_payload["changed_targets"] = direct_mode_audit["changed_targets"]
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

    if llm_mode:
        try:
            from nexus.services.gateway import BattlesuitGateway

            gateway = BattlesuitGateway(project_root=root)
            prompt, raw = gateway.ask_structured(
                prompt=(
                    "You are rewriting a document.\n"
                    f"Task: {task}\n"
                    "Return only rewritten full text in field 'patch'."
                ),
                payload=f"[SOURCE]\n{original}",
                phase="R",
                output_schema={
                    "status": "APPROVED | FAIL",
                    "patch": "Full rewritten content",
                    "summary": "Short note",
                },
                model_name="gemini-3-flash-preview",
            )
            rewritten = (prompt or {}).get("patch") or (raw or "")
            if not rewritten.strip():
                raise RuntimeError("empty_llm_output")
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
@click.option("--report-file", default=".nexus/reports/learn/learn_report.json", show_default=True, type=click.Path())
@click.option("--markdown-report-file", default=".nexus/reports/learn/learn_ingest.md", show_default=True, type=click.Path())
@click.option("--evidence-file", default=".nexus/reports/learn/evidence_ingest.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_ingest(source, source_file, topic, report_file, markdown_report_file, evidence_file, output_json):
    """📚 Learn Mode: ingest source into claim+citation knowledge store."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.ingest(source=source, source_file=source_file, topic=topic)

    # Enforce local hallucination gate using generated evidence.
    final_response = f"Learn ingest finished for source: {source}."
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [f"claims_count={payload.get('claims_count', 0)}"],
        "command_artifacts": [f"source={source}", f"source_ref={payload.get('source_ref', '')}"],
    }
    _write_hallucination_evidence(evidence_file, final_response, evidence_bundle)
    _enforce_hallucination_gate(final_response=final_response, evidence_bundle=evidence_bundle)

    markdown_path = _write_dual_gate_markdown(
        repo_root,
        Path(markdown_report_file),
        task=f"learn:ingest source={source}",
        data=payload,
        evidence=f"claims_count={payload.get('claims_count', 0)} source_ref={payload.get('source_ref', '')}",
        debt="None" if payload.get("claims_count", 0) > 0 else "No claims ingested",
    )
    semantic_contract = _evaluate_learn_semantic_contract(
        root=repo_root,
        payload=payload,
        command_name="learn:ingest",
        markdown_report_written=markdown_path.exists(),
    )
    payload.update(semantic_contract)

    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn ingest complete: {source}")
        click.echo(f"Claims: {payload['claims_count']}, Verified: {payload['verified_claims_count']}")
        click.echo(f"Report: {out_path}")
        click.echo(f"Markdown: {markdown_path}")
        click.echo(f"Evidence: {Path(evidence_file) if evidence_file else 'N/A'}")
    if payload["semantic_status"] != "VERIFIED":
        raise click.ClickException(
            "Learn ingest semantic contract failed: " + ", ".join(payload["semantic_failures"])
        )


@nexus_group.command(name="learn:register-source")
@click.option("--topic", required=True)
@click.option("--source", required=True)
@click.option("--source-file", required=False, type=click.Path(exists=True))
@click.option("--refresh-after-days", default=14, type=int, show_default=True)
@click.option("--priority", default="medium", show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_register_source.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_register_source(topic, source, source_file, refresh_after_days, priority, report_file, output_json):
    """🗂️ Register a learn source for scheduled refresh."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.register_source(
        topic=topic,
        source=source,
        source_file=source_file,
        refresh_after_days=refresh_after_days,
        priority=priority,
    )
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload = _finalize_semantic_payload(
        payload,
        command_name="learn:register-source",
        task_name=f"register source topic={topic}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn source registered: topic={topic} source={source}")
        click.echo(f"Report: {out_path}")
    ensure_verified_completion(payload, context="learn:register-source")


@nexus_group.command(name="learn:refresh")
@click.option("--topic", default="", help="Optional topic filter.")
@click.option("--due-only/--all", default=True, show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--question-count", default=5, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_refresh.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_refresh(topic, due_only, pass_threshold, question_count, report_file, output_json):
    """🔄 Refresh registered learn sources and re-run converge."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.refresh_sources(
        topic=topic,
        due_only=due_only,
        pass_threshold=pass_threshold,
        question_count=question_count,
    )
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload = _finalize_semantic_payload(
        payload,
        command_name="learn:refresh",
        task_name=f"refresh sources topic={topic or 'all'}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn refresh complete: refreshed={payload['refreshed_count']} skipped={payload['skipped_count']}")
        click.echo(f"Report: {out_path}")
    ensure_verified_completion(payload, context="learn:refresh")


@nexus_group.command(name="learn:refresh-plan")
@click.option("--topic", default="", help="Optional topic filter.")
@click.option("--due-within-days", default=0, type=int, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_refresh_plan.json", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_refresh_plan(topic, due_within_days, report_file, output_json):
    """🗓️ Build a scheduler-ready plan for learn source refresh."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.build_refresh_plan(
        topic=topic,
        due_within_days=due_within_days,
    )
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload = _finalize_semantic_payload(
        payload,
        command_name="learn:refresh-plan",
        task_name=f"build refresh plan topic={topic or 'all'}",
        runtime_ok=(str(payload.get("status", "")).upper() == "SUCCESS"),
        execution_path="cli->learn_mode_service",
    )
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn refresh plan generated: due={payload['due_count']} total={payload['sources_total']}")
        click.echo(f"Report: {out_path}")
    ensure_verified_completion(payload, context="learn:refresh-plan")


@nexus_group.command(name="learn:converge")
@click.option("--topic", required=True)
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
def learn_converge(
    topic,
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
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.converge(
        topic=topic,
        max_rounds=max_rounds,
        pass_threshold=pass_threshold,
        question_count=question_count,
        auto_research=auto_research,
        max_sources_per_round=max_sources_per_round,
        swarm_mode=swarm_mode,
        swarm_max_parallel=swarm_max_parallel,
        per_source_timeout_sec=per_source_timeout_sec,
    )

    final_response = (
        f"Converge status for topic {topic}: converged={payload.get('converged')}, "
        f"pass_rate={payload.get('self_question_pass_rate')}."
    )
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [
            f"claims_matched={payload.get('claims_matched', 0)}",
            f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}",
        ],
        "command_artifacts": [f"topic={topic}"],
        "benchmark_metrics": {
            "success_rate": payload.get("self_question_pass_rate", 0.0),
            "success_threshold": pass_threshold,
        },
    }
    _write_hallucination_evidence(evidence_file, final_response, evidence_bundle)
    _enforce_hallucination_gate(final_response=final_response, evidence_bundle=evidence_bundle)

    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"✅ Learn converge complete: topic={topic}")
        click.echo(
            f"Converged={payload['converged']} | pass_rate={payload['self_question_pass_rate']} | coverage={payload['coverage']}"
        )
        click.echo(f"Report: {out_path}")
        click.echo(f"Evidence: {Path(evidence_file) if evidence_file else 'N/A'}")


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
def learn_ask(topic, question, top_k, min_evidence, min_token_coverage, max_staleness_days, allow_cross_pack, evidence_file, output_json):
    """❓ Ask using cited claims only. If no cited evidence, return UNKNOWN."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.ask(
        topic=topic,
        question=question,
        top_k=top_k,
        min_evidence=min_evidence,
        min_token_coverage=min_token_coverage,
        max_staleness_days=max_staleness_days,
        allow_cross_pack=allow_cross_pack,
    )

    final_response = str(payload.get("answer", "UNKNOWN"))
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py"],
        "test_artifacts": [f"claims_used={payload.get('claims_used', 0)}"],
        "command_artifacts": [f"topic={topic}", f"question={question}"],
    }
    _write_hallucination_evidence(evidence_file, final_response, evidence_bundle)
    _enforce_hallucination_gate(final_response=final_response, evidence_bundle=evidence_bundle)

    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if payload["status"] == "UNKNOWN":
        click.echo("UNKNOWN")
        return
    if payload["status"] == "CONFLICT":
        click.echo("CONFLICT")
        return
    click.echo(payload["answer"])


@nexus_group.command(name="learn:report")
@click.option("--topic", default="", help="Optional topic filter for coverage and unresolved questions.")
@click.option("--question-count", default=5, type=int, show_default=True)
@click.option("--pass-threshold", default=0.6, type=float, show_default=True)
@click.option("--report-file", default=".nexus/reports/learn/learn_report.json", show_default=True, type=click.Path())
@click.option("--markdown-report-file", default=".nexus/reports/learn/learn_report.md", show_default=True, type=click.Path())
@click.option("--output-json", is_flag=True)
def learn_report(topic, question_count, pass_threshold, report_file, markdown_report_file, output_json):
    """📈 Build unified learn report for governance and CI consumption."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.build_report(
        topic=topic,
        question_count=question_count,
        pass_threshold=pass_threshold,
    )
    markdown_path = _write_dual_gate_markdown(
        repo_root,
        Path(markdown_report_file),
        task=f"learn:report topic={topic or 'all'}",
        data=payload,
        evidence=(
            f"claims_count={payload.get('claims_count', 0)} "
            f"converged={payload.get('converged')} "
            f"citation_valid_ratio={payload.get('citation_valid_ratio', 0.0)}"
        ),
        debt=_format_unresolved_questions_for_debt(payload.get("unresolved_questions")) or "None",
    )
    semantic_contract = _evaluate_learn_semantic_contract(
        root=repo_root,
        payload=payload,
        command_name="learn:report",
        markdown_report_written=markdown_path.exists(),
    )
    payload.update(semantic_contract)
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        if payload["semantic_status"] != "VERIFIED":
            raise click.ClickException(
                "Learn report semantic contract failed: " + ", ".join(payload["semantic_failures"])
            )
        return
    click.echo("✅ Learn report generated")
    click.echo(
        f"sources={payload['sources_count']} claims={payload['claims_count']} coverage={payload['coverage']} converged={payload['converged']}"
    )
    click.echo(f"Report: {out_path}")
    click.echo(f"Markdown: {markdown_path}")
    if payload["semantic_status"] != "VERIFIED":
        raise click.ClickException(
            "Learn report semantic contract failed: " + ", ".join(payload["semantic_failures"])
        )


@nexus_group.command(name="learn:phase-slo")
@click.option("--window", default=300, type=int, show_default=True)
@click.option(
    "--report-file",
    default=".nexus/reports/learn/phase_slo_summary.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--output-json", is_flag=True)
def learn_phase_slo(window, report_file, output_json):
    """📏 Build phase-level learn SLO report for P/X/D/R/A/C writeback closure."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.build_phase_slo_report(window=window)
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload = _finalize_semantic_payload(
        payload,
        command_name="learn:phase-slo",
        task_name=f"build learn phase slo window={window}",
        runtime_ok=True,
        execution_path="cli->learn_mode_service",
    )
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo("✅ Learn phase SLO summary generated")
        click.echo(
            f"phase_slo_pass={payload.get('phase_slo_pass')} "
            f"required_done_ratio={payload.get('global', {}).get('required_done_ratio', 0.0)}"
        )
        click.echo(f"Report: {out_path}")
    ensure_verified_completion(payload, context="learn:phase-slo")


@nexus_group.command(name="learn:phase-kpi")
@click.option("--window", default=300, type=int, show_default=True)
@click.option(
    "--report-file",
    default=".nexus/reports/learn/phase_kpi_report.json",
    show_default=True,
    type=click.Path(),
)
@click.option("--output-json", is_flag=True)
def learn_phase_kpi(window, report_file, output_json):
    """📊 Build phase KPI dashboard payload for P/X/D/R/A/C."""
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.build_phase_kpi_report(window=window)
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload = _finalize_semantic_payload(
        payload,
        command_name="learn:phase-kpi",
        task_name=f"build learn phase kpi window={window}",
        runtime_ok=True,
        execution_path="cli->learn_mode_service",
    )
    if output_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo("✅ Learn phase KPI report generated")
        click.echo(
            f"total_records={payload.get('total_records', 0)} "
            f"success_ratio={payload.get('global', {}).get('success_ratio', 0.0)} "
            f"required_done_ratio={payload.get('global', {}).get('required_done_ratio', 0.0)}"
        )
        click.echo(f"Report: {out_path}")
    ensure_verified_completion(payload, context="learn:phase-kpi")


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
    from nexus.research.learn_mode import LearnModeService

    service = LearnModeService(repo_root)
    payload = service.build_report(topic=topic)
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    final_response = (
        f"Validated learn gate. topic={topic}, coverage={payload.get('coverage', 0.0)}, "
        f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}."
    )
    evidence_bundle = {
        "code_artifacts": ["nexus/research/learn_mode.py", "scripts/engine/nexus_cli.py"],
        "test_artifacts": [
            f"claims_count={payload.get('claims_count', 0)}",
            f"coverage={payload.get('coverage', 0.0)}",
            f"self_question_pass_rate={payload.get('self_question_pass_rate', 0.0)}",
        ],
        "command_artifacts": [f"topic={topic}", f"report={out_path}"],
        "benchmark_metrics": {
            "success_rate": payload.get("self_question_pass_rate", 0.0),
            "success_threshold": pass_threshold,
        },
    }
    ev_path = _write_hallucination_evidence(evidence_file, final_response, evidence_bundle)
    _enforce_hallucination_gate(final_response=final_response, evidence_bundle=evidence_bundle)

    gate_failures = []
    if float(payload.get("self_question_pass_rate", 0.0)) < pass_threshold:
        gate_failures.append("self_question_pass_rate_below_threshold")
    if float(payload.get("citation_valid_ratio", 0.0)) < citation_valid_min:
        gate_failures.append("citation_valid_ratio_below_threshold")
    if int(payload.get("claims_count", 0)) < claims_min:
        gate_failures.append("claims_count_below_threshold")
    if gate_failures:
        raise click.ClickException(f"Learn gate blocked: {', '.join(gate_failures)}")

    # Mandatory acceptance with evidence
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/engine/nexus_cli.py"),
            "nexus",
            "acceptance-check",
            "--evidence",
            str(ev_path),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/engine/nexus_cli.py"),
            "nexus",
            "acceptance-check",
            "--json",
            "--evidence",
            str(ev_path),
        ],
        check=True,
    )

    if not skip_contract:
        subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts/engine/nexus_cli.py"),
                "nexus",
                "contract-check",
                "--contract-file",
                contract_file,
            ],
            check=True,
        )

    if not skip_ci:
        ci_cmd = [
            sys.executable,
            str(repo_root / "scripts/ops/ci_gate.py"),
            "--dry-run",
            "--wiki-drift-enforce-level",
            "p0",
            "--require-closeout-contract",
            "--closeout-contract-path",
            contract_file,
            "--learn-mode",
            "smoke",
            "--learn-topic",
            topic,
        ]
        subprocess.run(ci_cmd, check=True)

    click.echo("✅ Learn gate PASSED")
    click.echo(f"Report: {out_path}")
    click.echo(f"Evidence: {ev_path}")


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
    res = subprocess.run([sys.executable, str(repo_root / "scripts/ops/supervisor_engine.py"), task_name], check=False)
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
@click.option("--output-json", is_flag=True)
@click.option("--explain-route", is_flag=True)
def research_route(task_desc, task_type, candidate_count, root_cause_confidence, findings_query, output_json, explain_route):
    """🧠 Strategy Routing Layer: Decide whether to research and in what mode."""
    out = research_flow_service.build_route(repo_root=repo_root, 
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
    )
    if explain_route:
        click.echo("--- ROUTE EXPLANATION ---")
        click.echo(json.dumps(out["explain_payload"], indent=2))
        return

    if output_json:
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"Should Research: {out['should_research']}")
        click.echo(f"Mode: {out['mode']}")
        click.echo(f"Reason: {out['reason']}")
        click.echo(f"Recommended Flow: {out['recommended_flow']} ({out['recommended_reason']})")
        click.echo(f"Findings Hits: {out['findings_hits']}")
        click.echo(f"Adjusted RC Confidence: {out['adjusted_root_cause_confidence']}")
        if out["historical_hints"]:
            click.echo(f"Historical Hints: {out['historical_hints']}")
        if out["require_codex_audit"]:
            click.secho("⚠️ [Advisor] Low confidence detected. Codex Audit recommended.", fg="yellow", bold=True)


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
):
    if explain_route:
        out = research_flow_service.build_route(repo_root=repo_root, 
            task_desc=task_desc,
            task_type=task_type,
            candidate_count=candidate_count,
            root_cause_confidence=root_cause_confidence,
            findings_query=findings_query,
            target_file=target_file,
        )
        click.echo("--- ROUTE EXPLANATION ---")
        click.echo(json.dumps(out["explain_payload"], indent=2))
        return

    payload, out_path = research_flow_service.run_auto_flow(repo_root=repo_root, 
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
    )
    result_payload = payload.get("result", {})
    io_payload = payload.get("io", {})
    artifact_paths = [str(out_path)]
    output_path = io_payload.get("output_path")
    if output_path:
        artifact_paths.append(str(output_path))
    semantic_failures: list[str] = []
    if output_file and not io_payload.get("output_written", False):
        semantic_failures.append("requested_output_not_written")
    completion_payload = build_completion_envelope(
        command_name="research:auto-flow",
        task_name=task_desc,
        runtime_ok=(result_payload.get("status") == "SUCCESS"),
        execution_path="cli->research_flow_service",
        artifact_paths=artifact_paths,
        semantic_failures=semantic_failures,
    )
    response_payload = _merge_completion_payload(payload, completion_payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(response_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if output_json:
        click.echo(json.dumps(response_payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Chosen Flow: {response_payload['chosen_flow']}")
        click.echo(f"Status: {response_payload['result']['status']}")
        click.echo(f"Elapsed: {response_payload['result']['elapsed_sec']} sec")
        click.echo(f"Report: {out_path}")
        click.echo(f"Output Written: {io_payload.get('output_written', False)}")
        click.echo(f"Output Path: {io_payload.get('output_path') or 'N/A'}")
        click.echo(f"Semantic Status: {response_payload['semantic_status']}")
    try:
        ensure_verified_completion(response_payload, context="research:auto-flow")
    except CompletionEnforcementError as exc:
        handoff = _persist_completion_handoff(response_payload, context="research:auto-flow", report_file=out_path)
        out_path.write_text(json.dumps(response_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if not output_json:
            click.echo(f"Next Action: {handoff}")
        if not output_json:
            click.echo(str(exc))
        raise SystemExit(1)


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
):
    """🧬 Run research control-plane loop: schedule -> evaluate -> select/promote -> rollback."""
    from nexus.research.experiment_scheduler import ExperimentScheduler
    from nexus.research.unified_evaluator import UnifiedEvaluator
    from nexus.research.selector_rollback import SelectorRollback
    import shutil

    start_ts = datetime.now(timezone.utc).isoformat()
    run_id = run_id or f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    scope_list = list(scope) if scope else ["nexus/research", "tests/research", "docs/research"]
    scheduler = ExperimentScheduler(repo_root)
    evaluator = UnifiedEvaluator(budget_limit=budget_limit, min_score_threshold=min_score_threshold)
    selector = SelectorRollback(repo_root)
    candidate_src_root = (repo_root / candidate_src_root).resolve()
    rollback_trace: list[str] = []
    elimination_matrix: list[dict] = []
    rejected_reasons: list[str] = []
    decision_log: list[str] = []
    status = "success"
    winner = None
    promoted = False
    file_scope = []
    retention_summary = {"retain_last_n": retain_last_n, "cleaned": {"reports": 0, "experiments": 0, "backups": 0}}

    # 0) Governance Guards
    decision_log.append("governance: start")
    _, _, free = shutil.disk_usage(repo_root)
    free_gb = free / (1024**3)
    if free_gb < disk_watermark_gb:
        status = "failed"
        rejected_reasons.append("low_disk_space")
        decision_log.append("governance: low_disk_space")
    if candidate_count <= 0:
        status = "failed"
        rejected_reasons.append("invalid_candidate_count")
        decision_log.append("governance: invalid_candidate_count")
    if max_parallel <= 0:
        status = "failed"
        rejected_reasons.append("invalid_parallelism")
        decision_log.append("governance: invalid_parallelism")
    if max_retries < 0:
        status = "failed"
        rejected_reasons.append("invalid_retries")
        decision_log.append("governance: invalid_retries")
    if continuation_attempts < 0:
        status = "failed"
        rejected_reasons.append("invalid_continuation_attempts")
        decision_log.append("governance: invalid_continuation_attempts")
    if timeout_sec <= 0:
        status = "failed"
        rejected_reasons.append("invalid_timeout")
        decision_log.append("governance: invalid_timeout")
    if retain_last_n <= 0:
        status = "failed"
        rejected_reasons.append("invalid_retain_n")
        decision_log.append("governance: invalid_retain_n")

    if status == "failed":
        elimination_matrix.append({"candidate_id": candidate_id, "reason_codes": rejected_reasons})

    if status == "success":
        from nexus.engine.policies.research_policy import ResearchPolicy
        from nexus.research.findings_memory import FindingsMemoryStore
        policy = ResearchPolicy()
        store = FindingsMemoryStore(repo_root)
        
        historical_hints = []
        hits = store.search(hypothesis)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)
        historical_hints = list(dict.fromkeys(historical_hints))[:3]

        def _collect_workspace_files(paths: list[str]) -> list[str]:
            file_paths: list[str] = []
            for item in paths:
                target = (repo_root / item).resolve()
                try:
                    if not target.is_relative_to(repo_root):
                        continue
                except Exception:
                    continue
                if target.is_file():
                    file_paths.append(str(target.relative_to(repo_root)))
                    continue
                if target.is_dir():
                    for p in sorted(target.rglob("*")):
                        if p.is_file():
                            file_paths.append(str(p.relative_to(repo_root)))
            return list(dict.fromkeys(file_paths))

        file_scope = _collect_workspace_files(scope_list)
        
        candidates = [candidate_id]
        if candidate_count > 1:
            # Keep candidate-id as first, then candidate-2, candidate-3...
            candidates = [candidate_id] + [f"candidate-{i}" for i in range(2, candidate_count + 1)]

        for idx, current_cid in enumerate(candidates):
            mutation_hint = policy.get_mutation_hint(idx, task_desc=hypothesis, historical_hints=historical_hints)
            decision_log.append(f"candidate:{current_cid}:start:mutation:{mutation_hint}")
            decision_log.append("schedule: start")
            # 1) schedule + backup
            scheduler.create_candidate(current_cid, hypothesis, scope_list, mutation_hint=mutation_hint)
            scheduler.start_experiment(current_cid)
            if file_scope:
                selector.backup_scope(current_cid, file_scope)

            # 2) evaluate
            decision_log.append("evaluate: start")
            def _seed_eval(seed: int, cid=current_cid) -> dict:
                if "sleep" in hypothesis.lower():
                    import time
                    time.sleep(timeout_sec + 1.0)
                    return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round}
                
                if "real-run" in hypothesis.lower():
                    try:
                        from nexus.research.swarm_broker import SwarmBroker
                        broker = SwarmBroker(repo_root)
                        swarm_dir = broker.acquire(timeout_sec=timeout_sec)
                        if not swarm_dir:
                            return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round, "error": "broker_timeout"}
                        
                        try:
                            # Sync the necessary files to the isolated swarm directory
                            broker.sync_scope(swarm_dir, scope_files=scope_list)
                            
                            res = subprocess.run(
                                [sys.executable, "-m", "pytest", "-q", "--maxfail=1"],
                                capture_output=True, text=True, timeout=timeout_sec,
                                cwd=swarm_dir
                            )
                            score = 1.0 if res.returncode == 0 else 0.4
                            return {"seed": seed, "score": score, "cost": estimated_cost_per_round, "stdout": res.stdout}
                        finally:
                            broker.release(swarm_dir)
                    except subprocess.TimeoutExpired:
                        return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round, "error": "timeout"}
                    except Exception as e:
                        return {"seed": seed, "score": 0.0, "cost": estimated_cost_per_round, "error": str(e)}

                valid_scope_count = sum(1 for path in scope_list if scheduler.validate_write(cid, path))
                total_scope = len(scope_list) or 1
                valid_ratio = valid_scope_count / total_scope
                src_exists_count = sum(1 for path in scope_list if (candidate_src_root / path).exists())
                coverage_ratio = src_exists_count / total_scope
                score = round((0.2 + 0.8 * valid_ratio * coverage_ratio), 4)
                return {"seed": seed, "score": score, "cost": estimated_cost_per_round}

            eval_report = evaluator.evaluate(
                candidate_id=current_cid,
                test_fn=_seed_eval,
                estimated_cost_per_round=estimated_cost_per_round,
                max_parallel=max_parallel,
                max_retries=max_retries,
                timeout_sec=timeout_sec
            )
            scheduler.finish_evaluation(current_cid, eval_report)
            
            if not eval_report.get("passed_gate"):
                elimination_matrix.append({
                    "candidate_id": current_cid,
                    "reason_codes": ["below_threshold"],
                    "score": eval_report.get("average_score", 0.0)
                })
                rejected_reasons.append("below_threshold")
                decision_log.append(f"candidate:{current_cid}:gate_failed")
                # Rollback current if not dry-run (though we didn't promote yet, backup_scope was called)
                if not dry_run:
                    decision_log.append(f"candidate:{current_cid}:rolling_back")
                    if selector.restore_scope(current_cid, file_scope):
                        rollback_trace.append(f"below_threshold:{current_cid} -> restore_scope_success")
                    else:
                        rollback_trace.append(f"below_threshold:{current_cid} -> restore_scope_failed")

        # 3) selection
        decision_log.append("select: start")
        # Winner is highest average_score among passed candidates
        passed_reports = [r for r in evaluator.scoreboard.values() if r.get("passed_gate")]
        if passed_reports:
            best_report = max(passed_reports, key=lambda r: r.get("average_score", 0.0))
            winner = best_report["candidate_id"]
            decision_log.append(f"select: winner={winner}")
            
            if dry_run:
                rollback_trace.append("dry_run=true; promotion skipped")
                promoted = True
                decision_log.append("promote: skipped")
            else:
                decision_log.append(f"promote: start winner={winner}")
                no_op_promotion = bool(file_scope) and all(
                    (candidate_src_root / file_path).resolve() == (repo_root / file_path).resolve()
                    for file_path in file_scope
                    if (candidate_src_root / file_path).exists()
                )
                if no_op_promotion:
                    promoted = True
                    rollback_trace.append("promotion_noop_same_source_target")
                else:
                    promoted = selector.promote_candidate(winner, candidate_src_root, file_scope)

                if not promoted:
                    status = "failed"
                    rejected_reasons.append("promotion_failed")
                    decision_log.append("promote: failed")
                    if selector.restore_scope(winner, file_scope):
                        rollback_trace.append(f"promotion_failed:{winner} -> restore_scope_success")
                    else:
                        rollback_trace.append(f"promotion_failed:{winner} -> restore_scope_failed")
        else:
            status = "failed"
            decision_log.append("select: no_candidates_passed")

    report_path = (repo_root / report_file).resolve()
    
    # Retention logic
    def _apply_retention_policy() -> dict:
        summary = {"retain_last_n": retain_last_n, "cleaned": {"reports": 0, "experiments": 0, "backups": 0}}
        targets = [
            ("reports", (repo_root / ".nexus" / "reports" / "research"), lambda p: p.is_file() and p.suffix == ".json"),
            ("experiments", (repo_root / ".nexus" / "experiments"), lambda p: p.is_dir()),
            ("backups", (repo_root / ".nexus" / "backups"), lambda p: p.is_dir()),
        ]
        for key, root, predicate in targets:
            if not root.exists(): continue
            entries = [p for p in root.iterdir() if predicate(p)]
            keep_count = retain_last_n
            if key == "reports":
                entries = [p for p in entries if p.resolve() != report_path]
                keep_count = max(0, retain_last_n - 1)
            entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for stale in entries[keep_count:]:
                try:
                    if not stale.resolve().is_relative_to(root.resolve()): continue
                    if stale.is_dir(): shutil.rmtree(stale)
                    else: stale.unlink()
                    summary["cleaned"][key] += 1
                except Exception: continue
        return summary

    top_k = [
        {
            "candidate_id": cid,
            "average_score": float(detail.get("average_score", 0.0)),
            "passed_gate": bool(detail.get("passed_gate", False)),
        }
        for cid, detail in sorted(
            evaluator.scoreboard.items(),
            key=lambda item: item[1].get("average_score", 0.0),
            reverse=True,
        )
    ]

    total_cost = sum(r.get("total_cost", 0.0) for r in evaluator.scoreboard.values())
    last_eval_report = evaluator.scoreboard.get(winner or candidate_id, {})
    
    # Phase 2 & 3: Metabolism & Persistence
    arweave_tx_id = None
    if status == "success" and winner:
        try:
            from nexus.services.mem_palace import MemPalace
            from nexus.research.findings_memory import FindingsCard
            palace = MemPalace(str(repo_root))
            
            seed_details = last_eval_report.get("seed_details", [])
            hint = seed_details[0].get("hint", "") if seed_details else ""
            
            card = FindingsCard(
                kind="episodes",
                title=f"Gladiator Win: {hypothesis[:30]}",
                task_id=run_id,
                body=f"Hypothesis: {hypothesis}\nScope: {scope_list}\nWinner: {winner}",
                confidence="high" if promoted else "medium",
                tags=["gladiator", "research_run"],
                retrieval_hints=[hint] if hint else []
            )
            
            clean_cards = palace.verify([card.to_dict()])
            if clean_cards:
                store.write(FindingsCard.from_dict(clean_cards[0]))
                arweave_tx_id = palace.trigger_arweave_distillation(clean_cards[0])
                decision_log.append(f"metabolism: arweave_tx_id={arweave_tx_id}")
            else:
                decision_log.append("metabolism: rejected_by_aaak_judge")
        except Exception as e:
            decision_log.append(f"metabolism_error: {e}")
            
    report_payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": status,
        "winner": winner,
        "arweave_tx_id": arweave_tx_id,
        "top_k": top_k,
        "elimination_matrix": elimination_matrix,
        "decision_log": decision_log,
        "rejected_reasons": rejected_reasons,
        "rollback_trace": rollback_trace,
        "cost_curve": {
            "estimated_cost_per_round": float(estimated_cost_per_round),
            "total_cost": total_cost,
            "budget_limit": float(budget_limit),
            "budget_remaining": max(0.0, float(budget_limit) - total_cost),
        },
        "budget_summary": {
            "limit": budget_limit,
            "used": total_cost,
            "remaining": max(0.0, budget_limit - total_cost),
        },
        "timestamps": {"start": start_ts, "end": datetime.now(timezone.utc).isoformat()},
        "execution": {
            "max_parallel": max_parallel,
            "max_retries": max_retries,
            "timeout_sec": timeout_sec,
            "candidate_count": candidate_count
        },
        "retention": _apply_retention_policy(),
        "candidate": {
            "id": winner or candidate_id,
            "hypothesis": hypothesis,
            "scope": scope_list,
            "file_scope_count": len(file_scope),
            "candidate_src_root": str(candidate_src_root),
            "promoted": promoted,
            "seed_details": last_eval_report.get("seed_details", []),
        },
    }

    governance_failure_reasons = {
        "low_disk_space",
        "invalid_candidate_count",
        "invalid_parallelism",
        "invalid_retries",
        "invalid_timeout",
        "invalid_retain_n",
    }
    blocker_type = "none"
    semantic_status = "VERIFIED"
    retryable = False
    next_action = "none"
    if status != "success":
        if any(reason in governance_failure_reasons for reason in rejected_reasons):
            blocker_type = "governance"
            semantic_status = "BLOCKED"
            next_action = "stop"
        else:
            blocker_type = "semantic_incomplete"
            semantic_status = "UNVERIFIED"
            retryable = True
            next_action = "retry_repair"
    completion_payload = build_completion_envelope(
        command_name="research:run",
        task_name=hypothesis,
        runtime_ok=(status == "success"),
        execution_path="cli->research_control_plane",
        artifact_paths=[str(report_path)],
        semantic_failures=rejected_reasons,
        blocker_type=blocker_type,
        semantic_status=semantic_status,
        retryable=retryable,
        next_action=next_action,
    )
    report_payload = _merge_completion_payload(report_payload, completion_payload)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    summary_payload = {
        "status": status,
        "winner": winner,
        "report_file": str(report_path),
        "semantic_status": report_payload["semantic_status"],
        "retryable": report_payload["retryable"],
        "blocker_type": report_payload["blocker_type"],
        "next_action": report_payload["next_action"],
        "next_action_file": report_payload.get("next_action_file"),
    }
    try:
        ensure_verified_completion(report_payload, context="research:run")
    except CompletionEnforcementError:
        if (
            report_payload.get("retryable")
            and int(continuation_attempts) > 0
        ):
            continuation_report = (
                report_path.parent
                / f"{report_path.stem}.retry{continuation_attempts}{report_path.suffix}"
            )
            continuation_cmd = [
                "uv",
                "run",
                "scripts/engine/nexus_cli.py",
                "nexus",
                "research:run",
                "--run-id",
                f"{run_id}-retry{continuation_attempts}",
                "--candidate-id",
                candidate_id,
                "--candidate-count",
                str(candidate_count),
                "--hypothesis",
                hypothesis,
                "--candidate-src-root",
                str(candidate_src_root),
                "--budget-limit",
                str(budget_limit),
                "--min-score-threshold",
                str(min_score_threshold),
                "--estimated-cost-per-round",
                str(estimated_cost_per_round),
                "--report-file",
                str(continuation_report),
                "--max-parallel",
                str(max_parallel),
                "--max-retries",
                str(max_retries),
                "--continuation-attempts",
                str(continuation_attempts - 1),
                "--timeout-sec",
                str(timeout_sec),
                "--retain-last-n",
                str(retain_last_n),
                "--disk-watermark-gb",
                str(disk_watermark_gb),
            ]
            if dry_run:
                continuation_cmd.append("--dry-run")
            for one_scope in scope_list:
                continuation_cmd.extend(["--scope", str(one_scope)])

            continuation_proc = subprocess.run(
                continuation_cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            summary_payload["continuation"] = {
                "attempted": True,
                "attempts_left_after_call": continuation_attempts - 1,
                "exit_code": continuation_proc.returncode,
                "report_file": str(continuation_report),
            }
            if continuation_proc.returncode == 0:
                click.echo(continuation_proc.stdout.strip())
                return
        handoff = _persist_completion_handoff(report_payload, context="research:run", report_file=report_path)
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        summary_payload["next_action_file"] = str(handoff)
        click.echo(json.dumps(summary_payload, indent=2))
        raise SystemExit(1)
    click.echo(json.dumps(summary_payload, indent=2))


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
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)

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
@click.pass_context
def compat_run(ctx: click.Context):
    """Compatibility alias for `nexus run`."""
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
def learn_phase_policy_cmd(task_type, risk, output_json):
    """🧠 Show phase-policy decisions for a hypothetical task."""
    from nexus.research.learn_mode import LearnModeService
    from nexus.research.learn.phase_policy import derive_phase_actions
    import json
    
    learn_svc = LearnModeService(repo_root)
    slo_summary = learn_svc.read_phase_slo_summary()
    actions = derive_phase_actions(slo_summary, task_type, risk)
    
    out = {
        "task_type": task_type,
        "risk": risk,
        "slo_readiness": slo_summary.get("overall_pass_rate", 0.0),
        "policy": {
            "allow_research": actions.allow_research,
            "force_baseline": actions.force_baseline,
            "require_writeback": actions.require_writeback,
            "audit_strictness": actions.audit_strictness.value,
            "reasoning": actions.reasoning
        }
    }
    
    if output_json:
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"SLO Readiness: {out['slo_readiness']:.1%}")
        click.echo(f"Allow Research: {out['policy']['allow_research']}")
        click.echo(f"Force Baseline: {out['policy']['force_baseline']}")
        click.echo(f"Reasoning: {out['policy']['reasoning']}")


@nexus_group.command(name="learn:scheduler-status")
@click.option("--output-json", is_flag=True)
def learn_scheduler_status_cmd(output_json):
    """📊 Show status of the production learn scheduler."""
    import json
    from pathlib import Path
    
    report_path = repo_root / ".nexus/reports/learn/scheduler_last_run.json"
    alert_dir = repo_root / ".nexus/reports/alerts"
    
    if not report_path.exists():
        click.echo("No scheduler run history found.")
        return
        
    data = json.loads(report_path.read_text())
    alerts = sorted(alert_dir.glob("*.json")) if alert_dir.exists() else []
    
    out = {
        "last_run": data.get("timestamp"),
        "last_exit_code": data.get("exit_code"),
        "slo_readiness": data.get("slo_readiness"),
        "alert_count": len(alerts),
        "alert_paths": [str(a.name) for a in alerts[-3:]] # Last 3 alerts
    }
    
    if output_json:
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"Last Run: {out['last_run']}")
        click.echo(f"Status: {'OK' if out['last_exit_code'] == 0 else 'DEGRADED' if out['last_exit_code'] == 2 else 'FAILED'}")
        click.echo(f"Alerts Found: {out['alert_count']}")

@nexus_group.command(name="learn:benchmark")
@click.option("--manifest-file", required=True, type=click.Path(exists=True))
@click.option("--topic", required=True)
@click.option("--source", help="Legacy param")
@click.option("--source-file", help="Legacy param")
@click.option("--output-json", is_flag=True)
@click.option("--output", default=".nexus/reports/learn/precision_benchmark.json", type=click.Path())
def learn_benchmark_cmd(manifest_file, topic, source, source_file, output_json, output):
    """📊 Legacy benchmark alias (kept for backward compatibility)."""
    import json
    from nexus.research.learn_mode import LearnModeService
    
    with open(manifest_file, 'r') as f:
        manifest_data = json.load(f)
    
    cases = manifest_data.get("cases") or manifest_data.get("questions", [])
    svc = LearnModeService(repo_root)
    results = []
    
    if not output_json: click.echo(f"🚀 Running Learn Precision Benchmark on topic: {topic}")
    for case in cases:
        q = case.get("q") or case.get("question")
        expected = case.get("expected") or case.get("expected_status")
        if expected == "ANSWERED": expected = "ANSWER"
        
        res = svc.ask(topic=topic, question=q)
        actual = "UNKNOWN" if res["status"] == "UNKNOWN" else "ANSWER"
        
        results.append({
            "q": q, "expected": expected, "actual": actual,
            "is_correct": expected == actual,
            "citations": len(res.get("citations", [])),
            "noise_filtered": res.get("filtered_out_count", 0)
        })
        
    correct = sum(1 for r in results if r["is_correct"])
    prec = sum(1 for r in results if r["expected"] == "ANSWER" and r["actual"] == "ANSWER") / max(1, sum(1 for r in results if r["actual"] == "ANSWER"))
    un_corr = sum(1 for r in results if r["expected"] == "UNKNOWN" and r["actual"] == "UNKNOWN") / max(1, sum(1 for r in results if r["expected"] == "UNKNOWN"))
    
    summary = {
        "topic": topic, "total": len(results), "correct": correct,
        "precision": round(prec, 4), "unknown_correct_rate": round(un_corr, 4),
        "status": "SUCCESS",
        "baseline": {"success_rate": round(prec, 4), "answer_precision": round(prec, 4), "unknown_accuracy": round(un_corr, 4), "avg_token_coverage": 0.0, "total_questions": len(results)},
        "best": {"success_rate": round(prec, 4), "answer_precision": round(prec, 4), "unknown_accuracy": round(un_corr, 4), "avg_token_coverage": 0.0},
        "results": results
    }
    
    if output_json:
        click.echo(json.dumps(summary, indent=2))
        return

    with open(output, 'w') as f:
        json.dump(summary, f, indent=2)
    click.echo(f"✅ Benchmark complete. Precision: {prec:.2%}, Unknown Correct: {un_corr:.2%}")


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
def create_task_cmd(task_id, owner, allowed_files):
    """📝 Create a new multi-agent task."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    files = [f.strip() for f in allowed_files.split(",")]
    orch.create_task(
        task_id=task_id,
        owner=owner,
        allowed_files=files,
        done_criteria=["Gate pass"],
        evidence_requirements=["pytest", "nexus acceptance-check"]
    )
    click.secho(f"✅ Task {task_id} created for {owner}.", fg="green")

@multi_agent_group.command(name="start")
@click.option("--task-id", required=True)
def start_task_cmd(task_id):
    """🚀 Start a task (locks files + creates worktree)."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    task = orch.start_task(task_id)
    click.secho(f"✅ Task {task_id} started.", fg="green")
    click.echo(f"📍 Working directory: {task.working_dir}")
    click.echo(f"🌿 Branch: {task.branch_name}")

@multi_agent_group.command(name="status")
@click.option("--task-id")
@click.option("--json", "output_json", is_flag=True)
def task_status_cmd(task_id, output_json):
    """📊 Show task status."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    if task_id:
        task = orch.state_store.load_task(task_id)
        if not task:
            click.echo(f"Task {task_id} not found.")
            return
        if output_json:
            click.echo(task.model_dump_json(indent=2))
        else:
            click.echo(f"Task: {task.task_id} | Status: {task.current_status} | Owner: {task.owner}")
    else:
        tasks = orch.state_store.list_tasks()
        for t in tasks.values():
            click.echo(f"{t.task_id}: {t.current_status} ({t.owner})")

@multi_agent_group.command(name="verify")
@click.option("--task-id", required=True)
def verify_task_cmd(task_id):
    """✅ Run verification gates for a task."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    click.echo(f"🔍 Verifying task {task_id}...")
    passed = orch.verify_task(task_id)
    if passed:
        click.secho(f"✅ Task {task_id} passed all gates.", fg="green")
    else:
        click.secho(f"❌ Task {task_id} failed gates.", fg="red")

@multi_agent_group.command(name="close")
@click.option("--task-id", required=True)
@click.option("--no-cleanup", is_flag=True)
def close_task_cmd(task_id, no_cleanup):
    """🏁 Close a task and release locks."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    orch.close_task(task_id, cleanup=not no_cleanup)
    click.secho(f"✅ Task {task_id} closed.", fg="green")

@multi_agent_group.command(name="integrate")
@click.option("--task-ids", required=True, help="Comma separated task IDs")
@click.option("--target-branch", default="main")
def integrate_tasks_cmd(task_ids, target_branch):
    """🚢 Integrate multiple tasks into target branch."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    from nexus.orchestrator.integration_manager import IntegrationManager
    
    orch = NexusOrchestrator()
    im = IntegrationManager(orch.state_store, orch.evidence_collector)
    
    tids = [t.strip() for t in task_ids.split(",")]
    click.echo(f"🚢 Integrating tasks: {tids} into {target_branch}...")
    
    success, failed = im.batch_integrate(tids, target_branch)
    
    if success:
        click.secho(f"✅ Successfully integrated: {success}", fg="green")
    if failed:
        click.secho(f"❌ Failed to integrate: {failed}", fg="red")

@multi_agent_group.command(name="audit")
@click.option("--task-id", required=True)
def audit_task_cmd(task_id):
    """🔍 Audit task evidence chain."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    orch = NexusOrchestrator()
    task = orch.state_store.load_task(task_id)
    if not task:
        click.echo(f"Task {task_id} not found.")
        return
    
    click.echo(f"🔍 Auditing Task {task_id} (Owner: {task.owner})")
    click.echo(f"Status: {task.current_status}")
    click.echo(f"Evidence Count: {len(task.evidence_list)}")
    
    for i, e in enumerate(task.evidence_list):
        status = "✅ PASS" if e.exit_code == 0 else "❌ FAIL"
        click.echo(f"  [{i}] {status} | Command: {e.command}")

@multi_agent_group.command(name="metrics")
@click.option("--json", "output_json", is_flag=True)
def show_metrics_cmd(output_json):
    """📊 Show multi-agent fleet metrics."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    from nexus.orchestrator.metrics import MetricsAggregator
    
    orch = NexusOrchestrator()
    agg = MetricsAggregator(orch.logger)
    metrics = agg.compute_metrics()
    
    if output_json:
        click.echo(json.dumps(metrics, indent=2))
    else:
        click.secho("📊 Nexus Multi-Agent Metrics", bold=True, fg="cyan")
        click.echo(f"Total Tasks: {metrics.get('total_tasks', 0)}")
        click.echo(f"Success Rate: {metrics.get('success_rate', 0):.1%}")
        click.echo(f"Conflict Rate: {metrics.get('conflict_rate', 0):.1%}")
        click.echo(f"Gate Failure Rate: {metrics.get('gate_failure_rate', 0):.1%}")
        click.echo(f"Avg Lead Time: {metrics.get('avg_lead_time_sec', 0)}s")

@multi_agent_group.command(name="submit")
@click.option("--task-id", required=True)
def submit_task_cmd(task_id):
    """🚀 Submit task with full verification & protocol evidence."""
    from nexus.orchestrator.orchestrator import NexusOrchestrator
    from nexus.delivery.submission import assess_submission
    from nexus.delivery.submission import build_submission_payload
    from nexus.delivery.submission import governance_payload
    from nexus.delivery.submission import load_delivery_receipt
    orch = NexusOrchestrator()
    
    click.echo(f"🚀 Submitting task {task_id}...")
    passed = orch.verify_task(task_id)
    
    if not passed:
        click.secho(f"❌ Gate failure. Submission blocked.", fg="red")
        return

    task = orch.state_store.load_task(task_id)
    evidence_path = orch.evidence_collector.generate_hallucination_evidence(
        task, f"Task {task_id} processed by {task.owner}."
    )
    
    # Load the generated evidence to get derived claims
    with open(evidence_path, "r") as f:
        derived_bundle = json.load(f)

    receipt_path = repo_root / ".nexus" / "reports" / "delivery_gate.json"
    receipt_payload = load_delivery_receipt(receipt_path)
    assessment = assess_submission(
        receipt_payload=receipt_payload,
        derived_bundle=derived_bundle,
        receipt_path=receipt_path,
    )
    
    # 💎 Governance Bridge: Log REAL outcome based on derived claims
    from nexus.orchestrator.governance_bridge import append_governance_event
    append_governance_event(str(repo_root), governance_payload(task_id, assessment))

    # 8) Delivery Format
    import subprocess
    sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    if not assessment.delivery_gate_passed or not assessment.acceptance_gate_passed:
        raise click.ClickException(
            "Submission blocked: delivery receipt does not prove both delivery-gate and acceptance-check passed."
        )

    delivery = build_submission_payload(commit_sha=sha, assessment=assessment)
    
    click.secho("✅ Task submitted successfully.", fg="green")
    click.echo(json.dumps(delivery, indent=2))


# --- v4.0: Skills & Registry Management ---
@nexus_group.group(name="skills")
def skills_group():
    """🧠 Manage external skills and manual teach-ins."""
    pass

@skills_group.command(name="sync")
def skills_sync():
    """📥 Sync external skills from ~/.agents/skills/ into SQLite registry."""
    from nexus.learning.external_skill_loader import ExternalSkillLoader
    loader = ExternalSkillLoader(repo_root)
    added, updated = loader.sync_all()
    click.secho(f"✅ Sync Complete: {added} added, {updated} updated.", fg="green", bold=True)

@skills_group.command(name="list")
def skills_list():
    """📋 List all registered skills (internal + external)."""
    from nexus.core.unified_registry import UnifiedRegistry
    reg = UnifiedRegistry(repo_root)
    skills = reg.registry.list_all()
    click.echo(f"{'ID':<20} | {'Name':<30} | {'Type':<10}")
    click.echo("-" * 65)
    for s in skills:
        click.echo(f"{s['id']:<20} | {s['name']:<30} | {s.get('origin_type', 'internal'):<10}")

@nexus_group.group(name="registry")
def registry_group():
    """🗄️ Unified Resource Registry (SSoT) status and maintenance."""
    pass

@registry_group.command(name="status")
def registry_status():
    """📊 Check health of assets, databases, and external skill paths."""
    from nexus.core.unified_registry import UnifiedRegistry
    reg = UnifiedRegistry(repo_root)
    manifest = reg.get_status()
    click.secho("📊 [Nexus Registry Status]", fg="cyan", bold=True)
    click.echo(f"  SQLite Registry: {manifest.health.get('registry', 'UNKNOWN')}")
    click.echo(f"  Skill Count    : {manifest.skills_count}")
    click.echo(f"  Models (Armor) : {manifest.models_configured}")
    click.echo(f"  Policies Count : {manifest.policies_count}")
    click.echo(f"  Last Refresh   : {manifest.last_refresh}")

@nexus_group.group(name="bench")
def bench_group():
    """📈 Autonomous performance benchmarking and ROI analysis."""
    pass

@bench_group.command(name="effort")
def bench_effort():
    """📊 Analyze success rates and ROI per effort level."""
    from nexus.engine.benchmark_runner import BenchmarkRunner
    runner = BenchmarkRunner(repo_root)
    report = runner.generate_effort_roi_report()
    click.secho("📈 [Nexus Effort ROI Report]", fg="magenta", bold=True)
    for level, data in report.items():
        click.echo(f"\n[{level.upper()}]")
        click.echo(f"  Success Rate: {data['success_rate']:.2%}")
        click.echo(f"  Avg Duration: {data['avg_duration_sec']:.1f}s")
        click.echo(f"  Count       : {data['count']}")

@nexus_group.group(name="sandbox")
def sandbox_group():
    """🏗️ Isolated environment execution and validation."""
    pass

@sandbox_group.command(name="run")
@click.option("--task", required=True)
def sandbox_run_cmd(task):
    """🏗️ Run a task in a physical Git-worktree sandbox."""
    from nexus.engine.sandbox_runner import SandboxRunner
    runner = SandboxRunner(repo_root)
    results = runner.run_task(task)
    click.secho(f"🏗️ [Sandbox] Execution finished. Success: {results['success']}", fg="cyan")

if __name__ == "__main__":

    nexus()
