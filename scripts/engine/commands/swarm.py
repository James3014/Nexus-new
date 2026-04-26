#!/usr/bin/env python3
import sys
import click
import json
from pathlib import Path
from nexus.engine.canonical_task_seam import build_legacy_cli_service
from nexus.engine.completion_contract import build_completion_envelope
from nexus.engine.completion_contract import ensure_verified_completion
from nexus.engine.completion_contract import write_completion_envelope
from nexus.engine.completion_enforcer import CompletionEnforcementError


def execute(cli, args):
    """Legacy command entrypoint used by tests and older CLI adapters."""
    success = cli.service.execute_bug(
        args.task,
        delivery_mode=args.delivery_mode,
        verify_commands=list(args.verify or []),
        artifact_paths=list(args.artifact or []),
    )
    cli._print_delivery_summary("Swarm", args.delivery_mode)
    if success:
        print("✅ [Nexus:Swarm] Mission Succeeded.")
    else:
        print("❌ [Nexus:Swarm] Mission Failed.")
    return success

def register(nexus_group, REPO_ROOT):
    """
    🧬 註冊 Swarm 認知模組。
    負責任務分發與 $AWARENESS 注入。
    """
    @nexus_group.group(name="swarm")
    def swarm():
        """🧬 [v24.2] Multi-Agent Swarm with Self-Awareness Injection"""
        pass

    @swarm.command(name="run")
    @click.argument("task_name")
    @click.option("--verbose-prompt", is_flag=True, help="Display injected self-awareness prompt")
    @click.option("--delivery-mode", default="standard", help="Execution priority: low|standard|high")
    @click.option("--report-file", default=None, type=click.Path(path_type=Path), help="Optional completion envelope path.")
    @click.option("--output-json", is_flag=True)
    def swarm_run(task_name, verbose_prompt, delivery_mode, report_file, output_json):
        """🚀 Initiate swarm mission with cognitive awareness."""
        # 🛡️ 物理化任務 ID 安全化 (防止檔名衝突與特殊字元)
        import hashlib
        task_slug = task_name[:20].replace("/", "_").replace(" ", "_")
        task_hash = hashlib.md5(task_name.encode()).hexdigest()[:8]
        safe_task_id = f"swarm_{task_slug}_{task_hash}"
        
        print(f"🧬 [Nexus:Swarm] Initiating mission: {safe_task_id}")
        print(f"📄 Task Description: {task_name}")
        
        # 🛡️ 物理化認知注入 (Self-Awareness)
        if verbose_prompt:
            try:
                from nexus.core.agent_awareness import NexusSelfAwareness
                awareness = NexusSelfAwareness()
                print("--- DEBUG: Injected Self-Awareness Prompt ---")
                # 修正 API 呼叫名稱
                print(awareness.get_self_awareness_prompt())
                print("--------------------------------------------")
            except (ImportError, AttributeError) as e:
                print(f"⚠️  [Nexus:Swarm] Self-Awareness injection failed: {e}")

        report_target = report_file or f".nexus/reports/swarm/{safe_task_id}.json"

        # 🚀 執行真實任務 (接入 NexusEngine)
        try:
            service = build_legacy_cli_service(REPO_ROOT)
            
            print(f"📡 [Nexus:Swarm] Dispatching task '{safe_task_id}' to engine (Mode: {delivery_mode})...")
            # 使用安全 ID 呼叫引擎
            success = service.execute_bug(task_name, delivery_mode=delivery_mode, bug_id=safe_task_id)

            payload = build_completion_envelope(
                command_name="swarm:run",
                task_name=task_name,
                runtime_ok=bool(success),
                execution_path="cli->legacy_cli_service->command_service->engine",
            )
            written = write_completion_envelope(REPO_ROOT, report_target, payload)
            if output_json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if success:
                    print("✅ [Nexus:Swarm] Mission Succeeded.")
                else:
                    print("❌ [Nexus:Swarm] Mission Failed.")
                print(f"Report: {written}")
            ensure_verified_completion(payload, context="swarm:run")
        except CompletionEnforcementError as e:
            if not output_json:
                print(str(e))
            sys.exit(1)
        except Exception as e:
            payload = build_completion_envelope(
                command_name="swarm:run",
                task_name=task_name,
                runtime_ok=False,
                execution_path="cli->legacy_cli_service->command_service->engine",
                semantic_failures=[f"swarm_exception:{type(e).__name__}"],
                blocker_type="runtime_defect",
            )
            written = write_completion_envelope(REPO_ROOT, report_target, payload)
            if output_json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"❌ [Nexus:Swarm] Critical execution error: {e}")
                print(f"Report: {written}")
            sys.exit(1)
