// src/lib/bridge.ts
import { invoke } from "@tauri-apps/api/core";

// 🛡️ High-Fidelity Mocks for Browser-Safe Development
const mockResponses: Record<string, any> = {
  get_desk_view_model: {
    taskId: "mock-task-123",
    armorName: "NEXUS-MOCK-PILOT",
    currentPhase: "REPAIR",
    normalizedStatus: "STABLE",
    severity: "info",
    showCriticalAlert: false,
    availableActions: {
      benchmark: true,
      acceptanceCheck: true,
      releaseReady: false,
      publish: false
    },
    resolutionTrace: "Initialization successful."
  },
  swarm_metrics: {
    block_rate: 0.042,
    route_count: 12,
    policy_size_mb: 24.5,
    total_decisions: 1240,
    top_routes: [
      { route: "nexus:swarm:router_v1", usage: 450 },
      { route: "nexus:swarm:self_heal_p1", usage: 320 },
      { route: "nexus:swarm:audit_agent", usage: 210 }
    ],
    weights: {
      "nexus:swarm:router_v1": { base_weight: 0.85, success_rate: 0.98 }
    }
  },
  get_nexus_identity: {
    armor: "NEXUS-V22-PROD",
    sha: "dcf7751",
    acceptance: { status: "PASSED" },
    timestamp: new Date().toLocaleTimeString()
  },
  get_worktree_diff: `--- a/scripts/engine/nexus_cli.py
+++ b/scripts/engine/nexus_cli.py
@@ -10,1 +10,1 @@
-    print("Booting...")
+    print("NEXUS_V22_READY")`,
    
  list_decisions: [
    { id: "d1", decisionId: "dec-001", action: "PHASE_START", actor: "system", ts: new Date().toISOString(), reason: "Auto-trigger" },
    { id: "d2", decisionId: "dec-002", action: "GIT_COMMIT", actor: "human", ts: new Date().toISOString(), reason: "Manual seal" }
  ],
  
  list_annotations: [
    { id: "a1", severity: "HIGH", body: "Mock audit passed.", author: "System", createdAt: new Date().toISOString(), status: "RESOLVED" }
  ],

  list_profiles: ["prod", "high", "full", "standard", "quick"],
  get_active_runs: [
    { taskId: "mock-task-123", armorName: "NEXUS-MOCK-PILOT", status: "STABLE" }
  ],

  query_error_fix: [
    { id: 1, pattern: "IO_TIMEOUT", fix_command: "nexus-fix --io", success_rate: 0.95 }
  ],

  eternal_status: {
    offloaded_mb: 12.4,
    total_mb: 96.8,
    anchors_count: 42,
    latest_anchor: "9xK_mock_tx_id_abc123",
    last_updated: new Date().toLocaleTimeString()
  },

  cluster_status: {
    manager_id: "nexus-manager-mock",
    total_nodes: 3,
    healthy_nodes: 2,
    nodes: [
      { node_id: "node-local-1", region: "local", cpu_percent: 45.2, memory_percent: 62.1, active_tasks: 2, last_seen_unix: Date.now()/1000, health: "HEALTHY" },
      { node_id: "node-remote-2", region: "asia-east1", cpu_percent: 12.8, memory_percent: 34.5, active_tasks: 0, last_seen_unix: Date.now()/1000, health: "HEALTHY" },
      { node_id: "node-stale-3", region: "us-west1", cpu_percent: 0, memory_percent: 0, active_tasks: 0, last_seen_unix: (Date.now()/1000) - 120, health: "STALE" }
    ]
  },
  shadow_status: {
    status: "HEALTHY",
    total_runs: 28,
    false_positive_count: 1,
    avg_latency_ms: 1250,
    whitelist: ["1", "2", "305"]
  },
  eternal_download: "Mock Download: Success.",
  apply_profile: "Mock: Profile applied.",
  run_cleanup: "Mock Cleanup: 140 entries purged.",
  run_autotune: "Mock Autotune: Weights updated.",
  append_decision: "Mock Ledger: Decision logged.",
  subscribe_log_tail: "Mock Log: Subscribed.",
  subscribe_run_events: "Mock Event: Subscribed.",
  add_annotation: "Mock Annotation: Saved.",
  run_nexus_command: "Mock: Command executed."
};

/**
 * Executes a Tauri command safely, falling back to mock data if not in a Tauri environment.
 */
export async function safeInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const isTauri = 
    typeof window !== "undefined" && 
    (window.hasOwnProperty("__TAURI_INTERNALS__") || window.hasOwnProperty("__TAURI__"));

  if (!isTauri) {
    console.warn(`[SafeInvoke] Env: Browser. Mocking command: ${cmd}`);
    // Simulate network delay
    await new Promise(r => setTimeout(r, 400));
    return (mockResponses[cmd] ?? {}) as T;
  }

  try {
    return await invoke<T>(cmd, args);
  } catch (error) {
    console.error(`[SafeInvoke] Command Failed: ${cmd}`, error);
    throw error;
  }
}

/**
 * Utility to check if currently in a Tauri container.
 */
export function isTauriEnv(): boolean {
   return typeof window !== "undefined" && 
    (window.hasOwnProperty("__TAURI_INTERNALS__") || window.hasOwnProperty("__TAURI__"));
}
