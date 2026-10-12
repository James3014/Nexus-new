import asyncio
import json
import argparse
import sys
import os
from pathlib import Path
import sys

# Ensure nexus package is in path for metabolism
# scripts/ui-validator.py -> scripts/ -> root/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nexus.core.decorators import nexus_metabolize

__import__("warnings").warn(
    "ARCHIVED 2026-10-12 (#1850): always BLOCKED no_live_browser_session, CLI ui-validator removed; see ARCHIVED_2026-10-12.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

# Login credentials are never embedded in source; the operator supplies them.
USER_ENV_VAR = "NEXUS_UI_VALIDATOR_USER"
PASSWORD_ENV_VAR = "NEXUS_UI_VALIDATOR_PASSWORD"
FINISH_SUCCESS = "Sequence completed successfully."
FINISH_NO_CREDENTIALS = "credentials_not_configured"


def _configured_credentials():
    user = os.environ.get(USER_ENV_VAR, "")
    password = os.environ.get(PASSWORD_ENV_VAR, "")
    if not user or not password:
        return None
    return user, password


async def agent_get_action(task: str, dom_text: str) -> str:
    """
    Placeholder for Nexus LLM Agent. 
    (For this high-standard acceptance test, we use a heuristic RAG state-machine 
    that reads the actual DOM text to make logical decisions like an LLM).
    """
    import re
    print(f"\n🤖 [Agent:Processing] Goal: {task}")
    
    # Simple regex to parse elements from text: [1] <tag> text: "..." placeholder: "..."
    elements = {}
    for line in dom_text.split('\n'):
        match = re.match(r'\[(\d+)\]', line)
        if match:
            idx = match.group(1)
            elements[idx] = line
    
    print("Found Extracted Elements:")
    for k, v in elements.items():
        print(f"  {k}: {v}")

    def find_id_by_keyword(keyword):
        for idx, text in elements.items():
            if keyword.lower() in text.lower():
                return idx
        return None

    # E2E Logic Path:
    user_input = find_id_by_keyword("Enter Operator ID")
    pass_input = find_id_by_keyword("Passcode")
    auth_btn = find_id_by_keyword("Authenticate")
    proceed_btn = find_id_by_keyword("Proceed to Dashboard")
    
    if proceed_btn:
        print(f"🤖 [Agent:Thought] Authentication successful! Modal is visible. Clicking Proceed.")
        return json.dumps({"action": "click", "target_id": proceed_btn})
        
    if "Authenticating..." in dom_text:
        print(f"🤖 [Agent:Thought] System is processing. I should wait.")
        return json.dumps({"action": "wait", "value": "1.0"})

    if user_input and pass_input and auth_btn:
        credentials = _configured_credentials()
        if credentials is None:
            print(
                f"🤖 [Agent:Thought] Login form found but {USER_ENV_VAR} / "
                f"{PASSWORD_ENV_VAR} are not set. Stopping."
            )
            return json.dumps({"action": "finish", "value": FINISH_NO_CREDENTIALS})
        user, password = credentials
        has_user = user in dom_text
        has_pass = password in dom_text

        if not has_user:
            print(f"🤖 [Agent:Thought] Type operator ID.")
            return json.dumps({"action": "type", "target_id": user_input, "value": user})
        if not has_pass:
            print(f"🤖 [Agent:Thought] Type passcode.")
            return json.dumps({"action": "type", "target_id": pass_input, "value": password})
        
        print(f"🤖 [Agent:Thought] Credentials entered. Submitting.")
        return json.dumps({"action": "click", "target_id": auth_btn})

    if "Dashboard Loaded" in dom_text:
        print(f"🤖 [Agent:Thought] Dashboard loaded. Task is successfully finished.")
        return json.dumps({"action": "finish", "value": FINISH_SUCCESS})

    return json.dumps({"action": "finish", "value": "No elements found, ending session."})

@nexus_metabolize(task_name="UI Autonomous Exploration")
async def run_ui_validation(url, agentic_mode=False, task=None, max_steps=5):
    """
    執行 UI 驗證。支援傳統矩陣測試或自主代理模式。
    """
    from nexus.core.web_dom_mapper import WebDomMapper
    from nexus.core.web_action_executor import WebActionExecutor
    from playwright.async_api import async_playwright
    results = {
        "status": "pending",
        "task_id": f"ui-task-{os.getpid()}",
        "steps": [],
        "video_path": ""
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # ... remainder of run_ui_validation logic
        context = await browser.new_context(record_video_dir=".nexus/reports/videos")
        page = await context.new_page()
        
        print(f"🚀 [UI:Validator] Navigating to: {url}")
        await page.goto(url)
        
        status = "incomplete"
        if agentic_mode:
            print(f"🧠 [UI:Validator] Entering Agentic Mode. Task: {task}")
            executor = WebActionExecutor(page)
            
            for step_idx in range(max_steps):
                print(f"📍 [Step {step_idx+1}/{max_steps}] Mapping DOM...")
                dom_text = await WebDomMapper.inject_and_map_dom(page)
                
                # Get action from Agent
                action_json = await agent_get_action(task, dom_text)
                
                # Execute action
                print(f"🎬 [Action] Executing: {action_json}")
                action_result = await executor.execute_action(action_json)
                results["steps"].append(action_result)
                
                if action_result.get("status") == "finished":
                    print(f"🏁 [UI:Validator] Task Finished: {action_result.get('message')}")
                    # Only the agent's explicit success terminal counts as success.
                    if action_result.get("message") == FINISH_SUCCESS:
                        status = "success"
                    break
        else:
            # Traditional Mock Interaction: nothing is validated, so never report success.
            print("🧱 [UI:Validator] Running standard interaction matrix (Mock)")
            results["steps"].append({"action": "scan", "status": "simulated"})
            status = "simulated"

        video_path = await page.video.path() if page.video else ""
        results["video_path"] = video_path
        results["status"] = status
        
        await browser.close()
    
    return results

@nexus_metabolize(task_name="UI Validator CLI")
def main():
    parser = argparse.ArgumentParser(description="Nexus v0.9 UI Validator (Agentic Explorer)")
    parser.add_argument("--url", required=True)
    parser.add_argument("--agentic-mode", action="store_true", help="Enable autonomous agent mode")
    parser.add_argument("--task", type=str, help="Natural language task for the agent")
    parser.add_argument("--max-steps", type=int, default=5, help="Maximum steps for agent exploration")
    args = parser.parse_args()
    
    # 執行並輸出結果 JSON
    final_report = asyncio.run(run_ui_validation(
        args.url, 
        agentic_mode=args.agentic_mode, 
        task=args.task, 
        max_steps=args.max_steps
    ))
    print(json.dumps(final_report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

