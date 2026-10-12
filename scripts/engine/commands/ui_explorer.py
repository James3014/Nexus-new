import sys
import subprocess
import click
import os

def register(nexus_group, REPO_ROOT):
    """
    🔗 為 Nexus 指令群組註冊 ui-validator。
    這確保了 CLI 本體保持精簡，而功能模組化。
    """
    @nexus_group.group(name="ui-validator")
    def ui_validator():
        """🌐 [v24.1] Autonomous Web UI Explorer & Validator"""
        pass

    @ui_validator.command(name="run")
    @click.option("--url", required=True, help="Target URL or local HTML path")
    @click.option("--agentic-mode", is_flag=True, help="Enable autonomous agent mode")
    @click.option("--task", type=str, help="Natural language task for the agent")
    @click.option("--max-steps", type=int, default=5, help="Maximum steps for agent exploration")
    def ui_validator_run(url, agentic_mode, task, max_steps):
        """🚀 Run UI validation with optional agentic exploration."""
        import sys
        # 這裡我們將執行權交還給專門的處理腳本
        cmd = [sys.executable, str(REPO_ROOT / "scripts/ui-validator.py"), "--url", url]
        if agentic_mode:
            cmd.append("--agentic-mode")
        if task:
            cmd.extend(["--task", task])
        cmd.extend(["--max-steps", str(max_steps)])
        
        click.echo(f"🌐 [UI:Validator] Launching {'Agentic' if agentic_mode else 'Standard'} Mode via External Module...")
        subprocess.run(cmd, check=True)
