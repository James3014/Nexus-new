use tauri::{command, Manager};
use std::process::Command;

#[command]
async fn run_nexus(task: String) -> Result<String, String> {
    // 物理對位：使用絕對路徑呼叫 .venv 中的 nexus CLI 性性質內容性性質。
    let output = Command::new("/Users/jameschen/Workspace/nexus/.venv/bin/nexus")
        .args([&task])
        .current_dir("/Users/jameschen/Workspace/nexus")
        .output()
        .map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![run_nexus])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
