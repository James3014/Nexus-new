#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod governance;
mod log_stream;

use serde::Serialize;
use tauri::{command, AppHandle, Emitter};

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
    Ok(DeskViewModel {
        task_id: "demo-task".into(),
        updated_at: chrono::Utc::now().to_rfc3339(),
        workspace: "/Users/jameschen/Workspace/nexus".into(),
        armor_name: "Nexus Desk".into(),
        version_label: "2.1.0".into(),
        normalized_status: "READY".into(),
        current_status_label: "Operational".into(),
        terminal: false,
        severity: "info".into(),
        show_critical_alert: false,
        current_phase: "P0".into(),
        task_summary: "Governance console initialized.".into(),
        next_action_label: "Awaiting command".into(),
        audit_passed: true,
        acceptance_passed: true,
        release_ready: false,
        can_publish: false,
        phase_health_score: 100,
        phase_health_source: "bootstrap".into(),
        resolution_trace: Vec::new(),
        latest_log_lines: Vec::new(),
        available_actions: AvailableActions {
            benchmark: false,
            acceptance_check: false,
            release_ready: false,
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
    let log_path = std::path::PathBuf::from(nexus_root).join(format!(".nexus/runs/{}/live.log", task_id));

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
async fn run_nexus_command(cmd: String) -> Result<(), String> {
    if cmd.trim().is_empty() {
        return Err("Command cannot be empty".into());
    }
    Ok(())
}

#[command]
async fn get_worktree_diff(task_id: String) -> Result<String, String> {
    Ok(format!("diff unavailable for task {task_id}"))
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
            governance::list_annotations
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
