// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{command, Manager};
use tauri_plugin_shell::ShellExt;
use serde_json::json;
use std::process::Command;
use chrono::Utc;

#[command]
fn get_nexus_identity() -> Result<serde_json::Value, String> {
    let nexus_root = "/Users/jameschen/Workspace/nexus";
    
    // 1. 偵測 Git SHA
    let sha_output = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(nexus_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    let sha_full = String::from_utf8_lossy(&sha_output.stdout).trim().to_string();
    let sha_short = sha_full.chars().take(8).collect::<String>();

    // 2. 偵測戰甲模式 (基於目前分支或目錄)
    // 簡化邏輯：優先檢查是否在 v22 rust 分支
    let branch_output = Command::new("git")
        .args(["rev-parse", "--abbrev-ref", "HEAD"])
        .current_dir(nexus_root)
        .output()
        .map_err(|e| e.to_string())?;
    let branch = String::from_utf8_lossy(&branch_output.stdout).trim().to_string();
    
    let armor_label = if branch == "main" || branch.contains("rust") {
        "🛡️ RUST v22 主力戰甲"
    } else {
        "🐍 PYTHON 基礎戰備"
    };

    // 3. 讀取治理門檻報告 (acceptance_check.json)
    let acceptance_path = format!("{}/.nexus/reports/acceptance_check.json", nexus_root);
    let acceptance = if std::path::Path::new(&acceptance_path).exists() {
        match std::fs::read_to_string(&acceptance_path) {
            Ok(content) => serde_json::from_str(&content).unwrap_or(json!({"status": "READ_ERROR"})),
            Err(_) => json!({"status": "IO_ERROR"}),
        }
    } else {
        json!({"status": "NO_REPORT"})
    };

    Ok(json!({
        "armor": armor_label,
        "sha": sha_short,
        "acceptance": acceptance,
        "timestamp": Utc::now().format("%H:%M:%S").to_string()
    }))
}

#[command]
async fn spawn_nexus_pty(_app: tauri::AppHandle, cmd: String) -> Result<String, String> {
    // Phase 2 完整實作 PTY 橋接邏輯
    // 目前先作為 Command 代理，Day 2 將替換為 full-pty stream
    let nexus_root = "/Users/jameschen/Workspace/nexus";
    let output = Command::new("uv")
        .args(["run", "scripts/engine/nexus_cli.py", &cmd])
        .current_dir(nexus_root)
        .output()
        .map_err(|e| e.to_string())?;
    
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![get_nexus_identity, spawn_nexus_pty])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
