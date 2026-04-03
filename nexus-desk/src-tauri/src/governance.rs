use rusqlite::{Connection, params};
use sha2::{Sha256, Digest};
use serde::{Serialize, Deserialize};
use uuid::Uuid;

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ErrorFix {
    pub id: i32,
    pub pattern: String,
    pub fix_command: String,
    pub success_rate: f64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct DecisionLedgerEntry {
    pub id: String,
    pub task_id: String,
    pub trace_id: Option<String>,
    pub audit_trace_id: Option<String>,
    pub decision_id: String,
    pub action: String,
    pub actor: String,
    pub target_json: String,
    pub reason: Option<String>,
    pub evidence_refs_json: String,
    pub ts: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ReviewAnnotation {
    pub id: String,
    pub task_id: String,
    pub trace_id: Option<String>,
    pub audit_trace_id: Option<String>,
    pub decision_id: Option<String>,
    pub target_type: String,
    pub target_ref_json: String,
    pub severity: String,
    pub status: String,
    pub author: String,
    pub body: String,
    pub created_at: String,
    pub updated_at: String,
}

pub fn init_governance_db() -> rusqlite::Result<()> {
    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db")?;
    
    // 原有的 Error Fingerprint 表
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY,
            exit_code INTEGER,
            traceback_hash TEXT UNIQUE,
            pattern TEXT,
            fix_command TEXT,
            success_rate REAL,
            last_seen TEXT
        )",
        [],
    )?;

    // 新增：決策帳本 (Append-only)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS decision_ledger (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            trace_id TEXT,
            audit_trace_id TEXT,
            decision_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            target_json TEXT NOT NULL,
            reason TEXT,
            evidence_refs_json TEXT NOT NULL,
            ts TEXT NOT NULL
        )",
        [],
    )?;

    // 新裝：審核標註
    conn.execute(
        "CREATE TABLE IF NOT EXISTS review_annotations (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            trace_id TEXT,
            audit_trace_id TEXT,
            decision_id TEXT,
            target_type TEXT NOT NULL,
            target_ref_json TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )",
        [],
    )?;
    
    Ok(())
}

#[tauri::command]
pub async fn query_error_fix(exit_code: i32, traceback: String) -> Result<Vec<ErrorFix>, String> {
    let mut hasher = Sha256::new();
    hasher.update(traceback.as_bytes());
    let hash = hasher.finalize().iter().map(|b| format!("{:02x}", b)).collect::<String>();
    
    let search_hash = if traceback.contains("timeout") { "demo_hash".to_string() } else { hash };

    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db").map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare("SELECT id, pattern, fix_command, success_rate FROM errors WHERE (traceback_hash = ?1 OR exit_code = ?2) ORDER BY success_rate DESC LIMIT 5").map_err(|e| e.to_string())?;
    
    let fixes = stmt.query_map(params![search_hash, exit_code], |row| {
        Ok(ErrorFix {
            id: row.get(0)?,
            pattern: row.get(1)?,
            fix_command: row.get(2)?,
            success_rate: row.get(3)?,
        })
    }).map_err(|e| e.to_string())?
    .filter_map(|f| f.ok())
    .collect();
    
    Ok(fixes)
}

#[tauri::command]
pub async fn append_decision(
    task_id: String,
    decision_id: Option<String>,
    action: String,
    actor: String,
    target_json: String,
    reason: Option<String>,
    evidence_refs_json: String,
) -> Result<String, String> {
    let id = Uuid::new_v4().to_string();
    let decision_id = decision_id.unwrap_or_else(|| Uuid::new_v4().to_string());
    let ts = chrono::Utc::now().to_rfc3339();

    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db").map_err(|e| e.to_string())?;
    conn.execute(
        "INSERT INTO decision_ledger (id, task_id, decision_id, action, actor, target_json, reason, evidence_refs_json, ts)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
        params![id, task_id, decision_id, action, actor, target_json, reason, evidence_refs_json, ts],
    ).map_err(|e| e.to_string())?;
    
    Ok(decision_id)
}

#[tauri::command]
pub async fn list_decisions(task_id: String) -> Result<Vec<DecisionLedgerEntry>, String> {
    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db").map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare("SELECT id, task_id, trace_id, audit_trace_id, decision_id, action, actor, target_json, reason, evidence_refs_json, ts FROM decision_ledger WHERE task_id = ?1 ORDER BY ts DESC").map_err(|e| e.to_string())?;
    
    let entries = stmt.query_map(params![task_id], |row| {
        Ok(DecisionLedgerEntry {
            id: row.get(0)?,
            task_id: row.get(1)?,
            trace_id: row.get(2)?,
            audit_trace_id: row.get(3)?,
            decision_id: row.get(4)?,
            action: row.get(5)?,
            actor: row.get(6)?,
            target_json: row.get(7)?,
            reason: row.get(8)?,
            evidence_refs_json: row.get(9)?,
            ts: row.get(10)?,
        })
    }).map_err(|e| e.to_string())?
    .filter_map(|f| f.ok())
    .collect();
    
    Ok(entries)
}

#[tauri::command]
pub async fn add_annotation(
    task_id: String,
    target_type: String,
    target_ref_json: String,
    severity: String,
    body: String,
    author: String,
) -> Result<String, String> {
    let id = Uuid::new_v4().to_string();
    let ts = chrono::Utc::now().to_rfc3339();

    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db").map_err(|e| e.to_string())?;
    conn.execute(
        "INSERT INTO review_annotations (id, task_id, target_type, target_ref_json, severity, status, author, body, created_at, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, 'OPEN', ?6, ?7, ?8, ?8)",
        params![id, task_id, target_type, target_ref_json, severity, author, body, ts],
    ).map_err(|e| e.to_string())?;
    
    Ok(id)
}

#[tauri::command]
pub async fn list_annotations(task_id: String) -> Result<Vec<ReviewAnnotation>, String> {
    let conn = Connection::open("/Users/jameschen/Workspace/nexus/nexus-desk/src-tauri/src/errors.db").map_err(|e| e.to_string())?;
    let mut stmt = conn.prepare("SELECT id, task_id, trace_id, audit_trace_id, decision_id, target_type, target_ref_json, severity, status, author, body, created_at, updated_at FROM review_annotations WHERE task_id = ?1 ORDER BY created_at DESC").map_err(|e| e.to_string())?;
    
    let entries = stmt.query_map(params![task_id], |row| {
        Ok(ReviewAnnotation {
            id: row.get(0)?,
            task_id: row.get(1)?,
            trace_id: row.get(2)?,
            audit_trace_id: row.get(3)?,
            decision_id: row.get(4)?,
            target_type: row.get(5)?,
            target_ref_json: row.get(6)?,
            severity: row.get(7)?,
            status: row.get(8)?,
            author: row.get(9)?,
            body: row.get(10)?,
            created_at: row.get(11)?,
            updated_at: row.get(12)?,
        })
    }).map_err(|e| e.to_string())?
    .filter_map(|f| f.ok())
    .collect();
    
    Ok(entries)
}
