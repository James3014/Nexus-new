import json, os
from pathlib import Path

class NexusMCPServer:
    """🛡️ v23.7 Nexus MCP Server: Knowledge as Resources."""
    def __init__(self):
        self.root = Path(__file__).resolve().parents[2]
        self.knowledge_base = self.root / ".nexusknowledge"

    def list_resources(self):
        """列出所有知識資源"""
        print("🌐 [MCP] Listing Knowledge Resources...")
        resources = [
            {"uri": "nexus://beliefs", "name": "Global Belief Base"},
            {"uri": "nexus://artifacts", "name": "Physical Artifact Registry"},
            {"uri": "nexus://lessons", "name": "Codex Lessons"}
        ]
        return resources

    def read_resource(self, uri: str):
        """讀取特定資源內容"""
        print(f"📖 [MCP] Reading Resource: {uri}")
        if "beliefs" in uri:
            path = self.knowledge_base / "beliefs.jsonl"
        elif "artifacts" in uri:
            path = self.knowledge_base / "artifacts.jsonl"
        else:
            return "Resource not found."
        
        if path.exists():
            return path.read_text().splitlines()[-5:] # 返回最後 5 筆
        return "Empty."

if __name__ == "__main__":
    server = NexusMCPServer()
    print(server.list_resources())
    print(server.read_resource("nexus://beliefs"))
