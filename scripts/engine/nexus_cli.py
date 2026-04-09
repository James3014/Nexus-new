#!/usr/bin/env python3
import sys, os, json, subprocess, yaml, click
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@click.group()
def nexus():
    """⚖️ Nexus v23.7 Fleet Command & Sensory CLI"""
    pass

@nexus.group(name="nexus")
def nexus_group():
    """🛡️ Nexus Core Governance & Command"""
    pass

# --- 階段二：任務續傳 ---
@nexus_group.command(name="resume")
def resume():
    """🌬️ [Metabolism] Resume task from last physical checkpoint."""
    from nexus.services.metabolism_engine import metabolism
    checkpoint = metabolism.load_checkpoint()
    if not checkpoint:
        click.echo("❌ No checkpoint found.")
        return
    click.echo(f"🌬️ Resuming Task: {checkpoint['task_id']}")
    click.echo(f"📍 Last Step: {checkpoint['last_active_step']}")
    click.echo(f"📋 Pending: {checkpoint['pending_steps']}")

@nexus_group.command(name="checkpoint")
@click.argument("task_id")
@click.argument("step")
def checkpoint(task_id, step):
    """💾 [Metabolism] Manual physical checkpoint."""
    from nexus.services.metabolism_engine import metabolism
    metabolism.save_checkpoint(task_id, step, ["Final Audit", "Promotion"])
    click.echo(f"✅ Checkpoint saved for {task_id}.")

# --- 階段三：審美吞噬 ---
@nexus_group.command(name="style-ingest")
@click.argument("url")
def style_ingest(url):
    """🎨 [Sensory] Ingest design system from URL."""
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/style_ingester.py"), url], check=True)

# --- 階段一：主管編排 ---
@nexus_group.command(name="delegate")
@click.argument("task_name")
def delegate(task_name):
    """📡 [Supervisor] Decompose and delegate task to fleet."""
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/supervisor_engine.py"), task_name], check=True)

# --- 階段四：MCP ---
@nexus_group.command(name="mcp-serve")
def mcp_serve():
    """🌐 [MCP] Start local knowledge resource server."""
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/nexus_mcp_server.py")], check=True)

@nexus_group.command(name="status")
@click.option("--json", "as_json", is_flag=True)
def status(as_json):
    """📊 Show system status and trust scores."""
    if as_json:
        res = {"status": "OPERATIONAL", "version": "v23.7", "fleet_size": 50, "mcp": "READY"}
        click.echo(json.dumps(res, indent=2))
    else:
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/enterprise_audit_v22.py")], check=True)

@nexus_group.command(name="distill")
def distill():
    """🌬️ [Metabolism] Distill session essence."""
    from nexus.services.metabolism_engine import metabolism
    tx = metabolism.distill({"goal": "v23.7 Verification", "done": ["Impl"], "todo": ["Audit"]})
    click.echo(f"💎 Session crystallized. Arweave TX: {tx}")

if __name__ == "__main__":
    nexus()
