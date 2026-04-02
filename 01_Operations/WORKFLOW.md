# 🎼 Muse-Core Agent Routing Index (v22 Hardened)
# [MANDATORY] agent: MUST read /Users/jameschen/Workspace/nexus/docs/AGENT_MANDATORY_PROTOCOL.md first.
# [MANDATORY] 回報 SHA + CI 狀態及開場白。

# === 核心路徑 ===
paths:
  protocol: "docs/AGENT_MANDATORY_PROTOCOL.md"
  registry: "01_Operations/03_Automation_Functional_Registry.md"
  focus: "01_Operations/00_Current_Focus.md"

# === 模式路由 ===
modes:
  default:
    required_actions:
      - "read docs/AGENT_MANDATORY_PROTOCOL.md"
      - "report armor identity + CI status"
