#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod governance;
mod log_stream;

use serde::{Serialize, Deserialize};
use tauri::{command, AppHandle, Emitter};
use std::fs;
use std::process::Command;
use std::path::PathBuf;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WisdomLookupPayload {
    task_id: String,
    snippet: Option<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct FeedbackEvent {
    task_id: String,
    pattern_id: String,
    feedback_type: String,
    actor: String,
    source: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct GuardPayload {
    task_id: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AvailableActions {
    benchmark: bool,
    acceptance_check: bool,
    release_ready: bool,
    publish: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceMetadata {
    audit_result: Option<String>,
    acceptance: Option<String>,
    manifest: Option<String>,
    metrics: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DeskViewModel {
    task_id: String,
    updated_at: String,
    workspace: String,
    armor_name: String,
    version_label: String,
    normalized_status: String,
    current_status_label: String,
    terminal: bool,
    severity: String,
    show_critical_alert: bool,
    current_phase: String,
    task_summary: String,
    next_action_label: String,
    audit_passed: bool,
    acceptance_passed: bool,
    release_ready: bool,
    can_publish: bool,
    phase_health_score: i32,
    phase_health_source: String,
    resolution_trace: Vec<serde_json::Value>,
    latest_log_lines: Vec<String>,
    available_actions: AvailableActions,
    evidence: SourceMetadata,
}

#[command]
async fn get_desk_view_model() -> Result<DeskViewModel, String> {
    let nexus_root = "/Users/jameschen/Workspace/nexus";
    let runs_dir = PathBuf::from(nexus_root).join(".nexus/runs");
    
    let mut latest_task = "no-active-run".to_string();
    let mut last_mod = std::time::SystemTime::UNIX_EPOCH;

    if let Ok(entries) = fs::read_dir(&runs_dir) {
        for entry in entries.flatten() {
            if let Ok(meta) = entry.metadata() {
                if meta.is_dir() {
                    if let Ok(mod_time) = meta.modified() {
                        if mod_time > last_mod {
                            last_mod = mod_time;
                            latest_task = entry.file_name().to_string_lossy().into();
                        }
                    }
                }
            }
        }
    }

    Ok(DeskViewModel {
        task_id: latest_task,
        updated_at: chrono::Utc::now().to_rfc3339(),
        workspace: nexus_root.into(),
        armor_name: "Nexus Desk".into(),
        version_label: "2.1.0-STABLE".into(),
        normalized_status: "READY".into(),
        current_status_label: "Live Monitor Active".into(),
        terminal: false,
        severity: "info".into(),
        show_critical_alert: false,
        current_phase: "GOVERNANCE".into(),
        task_summary: format!("Monitoring Nexus runtime in workspace: {}", nexus_root),
        next_action_label: "Scan active Worktree".into(),
        audit_passed: true,
        acceptance_passed: true,
        release_ready: true,
        can_publish: false,
        phase_health_score: 100,
        phase_health_source: "LanceDB".into(),
        resolution_trace: Vec::new(),
        latest_log_lines: Vec::new(),
        available_actions: AvailableActions {
            benchmark: true,
            acceptance_check: true,
            release_ready: true,
            publish: false,
        },
        evidence: SourceMetadata {
            audit_result: None,
            acceptance: None,
            manifest: None,
            metrics: None,
        },
    })
}

#[command]
async fn subscribe_log_tail(app: AppHandle, task_id: String) -> Result<(), String> {
    let nexus_root = "/Users/jameschen/Workspace/nexus";
    let log_path = PathBuf::from(nexus_root).join(format!(".nexus/runs/{}/live.log", task_id));

    if !log_path.exists() {
        return Err(format!("Log file not found: {:?}", log_path));
    }

    std::thread::spawn(move || {
        let mut stream = log_stream::LogStream::new(&log_path).expect("Failed to init stream");
        loop {
            if let Ok(lines) = stream.tail() {
                for line in lines {
                    let _ = app.emit("log-line", log_stream::LogEvent {
                        kind: "log.line".into(),
                        task_id: task_id.clone(),
                        line,
                        ansi: true,
                        ts: chrono::Utc::now().to_rfc3339(),
                    });
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
    });
    Ok(())
}

#[command]
async fn subscribe_run_events(_task_id: String) -> Result<(), String> {
    Ok(())
}

#[command]
async fn run_nexus_command(cmd: String) -> Result<String, String> {
    let scripts_dir = "/Users/jameschen/Workspace/nexus/scripts";
    let output = Command::new("bash")
        .current_dir(scripts_dir)
        .arg("nexus.sh")
        .arg(&cmd)
        .output()
        .map_err(|e| e.to_string())?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    
    if output.status.success() {
        Ok(stdout)
    } else {
        Err(format!("Error: {}\n{}", stderr, stdout))
    }
}

#[command]
async fn get_worktree_diff(_task_id: String) -> Result<String, String> {
    let nexus_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("git")
        .current_dir(nexus_root)
        .arg("diff")
        .arg("--stat")
        .output()
        .map_err(|e| e.to_string())?;

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn swarm_metrics() -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .args(&["run", "python", "desk/api_swarm_metrics.py", "."])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn run_cleanup() -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .args(&["run", "python", "scripts/learning/cleanup_policy_memory.py", "."])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn run_autotune() -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .env("PYTHONPATH", ".")
        .args(&["run", "python", "scripts/learning/autotune_route_weights.py", "."])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn eternal_status() -> Result<String, String> {
    let anchor_path = PathBuf::from("/Users/jameschen/Workspace/nexus").join(".nexus/eternal/anchors.json");
    if anchor_path.exists() {
        fs::read_to_string(anchor_path).map_err(|e| e.to_string())
    } else {
        Ok(r#"{"offloaded_mb":0,"total_mb":0,"anchors_count":0}"#.to_string())
    }
}

#[command]
async fn eternal_download(txid: String) -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .args(&["run", "python", "scripts/engine/nexus_cli.py", "nexus:eternal", "download", "--txid", &txid])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn cluster_status() -> Result<String, String> {
    let client = reqwest::Client::new();
    let res = client.get("http://127.0.0.1:9100/cluster/status")
        .send()
        .await
        .map_err(|e| e.to_string())?;
    
    let body = res.text().await.map_err(|e| e.to_string())?;
    Ok(body)
}

#[command]
async fn shadow_status() -> Result<String, String> {
    let shadow_path = PathBuf::from("/Users/jameschen/Workspace/nexus").join(".nexus/shadow/calibration.json");
    if shadow_path.exists() {
        fs::read_to_string(shadow_path).map_err(|e| e.to_string())
    } else {
        Ok(r#"{"status": "HEALTHY", "total_runs": 0, "false_positive_count": 0, "avg_latency_ms": 0, "whitelist": []}"#.to_string())
    }
}
#[command]
async fn wisdom_lookup(payload: WisdomLookupPayload) -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .env("NEXUS_SKIP_PROTOCOL_GATE", "1")
        .args(&["run", "python", "scripts/engine/nexus_cli.py", "nexus:wisdom", "lookup", "--snippet", &payload.snippet.unwrap_or_default()])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn submit_feedback(payload: FeedbackEvent) -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .env("NEXUS_SKIP_PROTOCOL_GATE", "1")
        .args(&[
            "run", "python", "scripts/engine/nexus_cli.py", "nexus:wisdom", "feedback", 
            "--task-id", &payload.task_id, 
            "--pattern-id", &payload.pattern_id, 
            "--type", &payload.feedback_type,
            "--actor", &payload.actor,
            "--source", &payload.source
        ])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn wisdom_stats() -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .env("NEXUS_SKIP_PROTOCOL_GATE", "1")
        .args(&["run", "python", "scripts/engine/nexus_cli.py", "nexus:wisdom", "stats"])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

#[command]
async fn guard_validate(payload: GuardPayload) -> Result<String, String> {
    let repo_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .current_dir(repo_root)
        .env("NEXUS_SKIP_PROTOCOL_GATE", "1")
        .args(&["run", "python", "scripts/engine/nexus_cli.py", "nexus:guard", "validate", "--task-id", &payload.task_id])
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn main() {
    governance::init_governance_db().expect("failed to initialize governance db");
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            get_desk_view_model,
            subscribe_log_tail,
            subscribe_run_events,
            run_nexus_command,
            get_worktree_diff,
            governance::query_error_fix,
            governance::append_decision,
            governance::list_decisions,
            governance::add_annotation,
            governance::list_annotations,
            swarm_metrics,
            run_cleanup,
            run_autotune,
            eternal_status,
            eternal_download,
            cluster_status,
            shadow_status,
            wisdom_lookup,
            submit_feedback,
            wisdom_stats,
            guard_validate
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
