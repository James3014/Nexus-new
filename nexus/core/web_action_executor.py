import json
import asyncio
from typing import Dict, Any, Optional

try:
    from playwright.async_api import Page
except ImportError:
    Page = Any  # type: ignore[misc,assignment]

class WebActionExecutor:
    """
    WebActionExecutor translates high-level agent actions into physical Playwright operations.
    It also handles evidence collection (screenshots) for each step.
    """

    def __init__(self, page: Page, report_dir: str = ".nexus/reports/screenshots"):
        self.page = page
        self.report_dir = report_dir
        import os
        os.makedirs(self.report_dir, exist_ok=True)

    async def execute_action(self, action_json: str) -> Dict[str, Any]:
        """
        Parses the action JSON and executes it on the page.
        Example action: {"action": "click", "target_id": "12"}
        """
        try:
            data = json.loads(action_json)
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON format from Agent."}

        action_type = data.get("action")
        target_id = data.get("target_id")
        value = data.get("value")

        result = {"status": "success", "action": action_type, "target_id": target_id}

        try:
            if action_type == "click":
                await self._do_click(target_id)
            elif action_type == "type":
                await self._do_type(target_id, value)
            elif action_type == "hover":
                await self._do_hover(target_id)
            elif action_type == "scroll":
                await self._do_scroll(value or "down")
            elif action_type == "wait":
                await asyncio.sleep(float(value or 1.0))
            elif action_type == "finish":
                result["status"] = "finished"
                result["message"] = value or "Task completed."
            else:
                result["status"] = "error"
                result["message"] = f"Unknown action type: {action_type}"
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)

        # Collect evidence after action (or even if error)
        screenshot_path = await self._capture_evidence(action_type, target_id)
        result["screenshot"] = screenshot_path

        return result

    async def _do_click(self, target_id: str):
        selector = f"[nexus-index='{target_id}']"
        await self.page.click(selector)

    async def _do_type(self, target_id: str, value: str):
        selector = f"[nexus-index='{target_id}']"
        await self.page.fill(selector, value)

    async def _do_hover(self, target_id: str):
        selector = f"[nexus-index='{target_id}']"
        await self.page.hover(selector)

    async def _do_scroll(self, direction: str):
        if direction == "down":
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        elif direction == "up":
            await self.page.evaluate("window.scrollBy(0, -window.innerHeight)")

    async def _capture_evidence(self, action: str, target_id: str) -> str:
        """Captures a screenshot and returns the file path."""
        import time
        timestamp = int(time.time() * 1000)
        filename = f"action_{action}_{target_id}_{timestamp}.png"
        path = f"{self.report_dir}/{filename}"
        await self.page.screenshot(path=path)
        return path
