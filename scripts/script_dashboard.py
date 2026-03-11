#!/usr/bin/env python3
# /// script
# dependencies = ["fastapi", "uvicorn", "starlette", "pydantic"]
# ///
"""
🚀 Muse-Core 戰情室 Pro Max (Lvl 15.5 Final Hardened)
功能: 視覺化執行腳本，整合 Dr. Claw 自動自癒、Cron 管理、即時搜尋。
"""

import ast
import asyncio
import os
import sys
import re
from collections import defaultdict
from pathlib import Path
from pydantic import BaseModel

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from cron_utils import CronManager
except ImportError:
    CronManager = None

app = FastAPI(title="Muse-Core 戰情室 Pro Max")

# 安全配置
TARGET_DIR = Path(__file__).parent.resolve()
ACCESS_TOKEN = os.getenv("MUSE_DASHBOARD_TOKEN")
if not ACCESS_TOKEN:
    ACCESS_TOKEN = "PROTECTED_STATE_UNCONFIGURED"


class ToggleJobRequest(BaseModel):
    raw_job: str
    enable: bool


class TestJobRequest(BaseModel):
    command: str


# --- API Routes ---


@app.get("/api/cron")
def get_cron_jobs():
    if not CronManager:
        return {"error": "CronManager not found."}
    return CronManager.get_all_jobs()


@app.post("/api/cron/toggle")
def toggle_cron_job(req: ToggleJobRequest):
    if not CronManager:
        return {"success": False, "error": "CronManager not initialized"}
    success = CronManager.toggle_job(req.raw_job, req.enable)
    return {"success": success}


@app.post("/api/cron/test")
async def test_cron_job(req: TestJobRequest):
    if not CronManager:
        return {"success": False, "error": "CronManager not initialized"}
    result = CronManager.test_job(req.command)
    diagnosis_output = None
    heal_msg = ""
    is_healed = False

    if result["status"] == "failed" or result["status"] == "timeout":
        try:
            error_report = f"[FAILED] Cron Execution Error:\n{result['error']}"
            diag_script = TARGET_DIR / "core" / "diagnoser.py"
            if diag_script.exists():
                diag_process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(diag_script),
                    "--audit",
                    error_report,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(
                    diag_process.communicate(), timeout=60
                )
                diagnosis_output = stdout.decode(errors="replace")
                heal_res = await asyncio.to_thread(
                    CronManager.auto_heal,
                    req.command,
                    result["error"],
                    diagnosis_output,
                )
                if heal_res["status"] == "healed":
                    is_healed = True
                    result["status"] = "success"
                    result["output"] = heal_res["output"]
                    heal_msg = "🚨 自動修復成功並通過審查！"
                else:
                    heal_msg = f"⚠️ 修復失敗: {heal_res.get('reason')}"
        except Exception as e:
            diagnosis_output = f"異常: {e}"
            heal_msg = "⚠️ 系統異常。"

    return {
        "success": result["status"] == "success",
        "result": result,
        "diagnosis": diagnosis_output,
        "heal_msg": heal_msg,
        "is_healed": is_healed,
    }


@app.get("/api/scripts")
def get_scripts() -> dict:
    data_by_view = {
        "tools": defaultdict(list),
        "protocols": defaultdict(list),
        "intel": defaultdict(list),
    }

    # 支援遞迴掃描子目錄 (Rglob)
    for entry in TARGET_DIR.rglob("*"):
        # 排除規則
        if (
            not entry.is_file()
            or entry.name == Path(__file__).name
            or entry.name.startswith(".")
            or "archive" in str(entry).lower()
            or "__pycache__" in str(entry)
        ):
            continue

        rel_name = str(entry.relative_to(TARGET_DIR))

        # 取得目錄分類
        if entry.parent != TARGET_DIR:
            # 如果在子目錄，以目錄名作為分類 (Linus 原則: 物理路徑即語義)
            cat = f"📁 {entry.parent.name.upper()}"
        else:
            cat = get_category(entry.name)

        if entry.name.endswith(".py"):
            info = parse_python_file(entry)
            info["name"] = rel_name
            info["ext"] = "Python"
            data_by_view["tools"][cat].append(info)
        elif entry.name.endswith(".sh"):
            info = {
                "name": rel_name,
                "status": "✅ 正常",
                "desc": "Shell 工具",
                "ext": "Shell",
                "details": [],
            }
            data_by_view["tools"][cat].append(info)

    ROOT_PATH = TARGET_DIR.parent.parent
    AGENT_DIRS = [
        (ROOT_PATH / "00_System_Knowledge" / "01_Persona", "🤖 核心人格"),
        (
            ROOT_PATH / "00_System_Knowledge" / "02_Arsenal" / "Skills_Library",
            "🛠️ 技能庫",
        ),
    ]
    for d, default_cat in AGENT_DIRS:
        if d.exists():
            for entry in d.iterdir():
                if entry.name.endswith(".md"):
                    info = parse_markdown_agent(entry)
                    info["name"] = entry.name
                    info["ext"] = "MD"
                    info["type"] = "protocol"
                    data_by_view["protocols"][default_cat].append(info)

    INTEL_FILES = {
        "01_Operations/Daily_Log.md": "📅 戰情日誌",
        "01_Operations/00_Current_Focus.md": "🎯 當前焦點",
        "01_Operations/PIPELINE.md": "🛠️ 任務管線",
    }
    for rel, cat in INTEL_FILES.items():
        p = ROOT_PATH / rel
        if p.exists():
            info = parse_markdown_agent(p)
            info["name"] = p.name
            info["ext"] = "Intel"
            info["type"] = "intel"
            info["path"] = str(p)
            data_by_view["intel"][cat].append(info)
    return {k: dict(v) for k, v in data_by_view.items()}


@app.post("/api/run/{script_name:path}")
async def run_script(script_name: str) -> dict:
    try:
        # 安全處理路徑，防止目錄遍歷攻擊
        target_path = (TARGET_DIR / script_name).resolve()
        if not str(target_path).startswith(str(TARGET_DIR)):
            return {"success": False, "output": "非法路徑訪問"}

        cmd = (
            [sys.executable, str(target_path)]
            if script_name.endswith(".py")
            else ["bash", str(target_path)]
        )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(TARGET_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        return {
            "success": process.returncode == 0,
            "output": (stdout + stderr).decode(errors="replace"),
        }
    except Exception as e:
        return {"success": False, "output": str(e)}


# --- Helpers ---


def get_category(name: str) -> str:
    name_lower = name.lower()
    if any(
        k in name_lower
        for k in [
            "sweep",
            "actuator",
            "swarm",
            "dispatch",
            "conflict",
            "intel_bridge",
            "pipeline",
        ]
    ):
        return "👔 幕僚長戰略管線"
    if any(
        k in name_lower
        for k in [
            "brain",
            "memory",
            "crystallize",
            "prune",
            "repair",
            "synthesize",
            "ingest",
            "search",
        ]
    ):
        return "🧠 記憶與知識庫管理"
    if any(k in name_lower for k in ["ski", "tagger", "diagnosis"]):
        return "⛷️ 滑雪與物理領域"
    if any(
        k in name_lower
        for k in ["email", "content", "curate", "morning", "wrap_up", "broadcast"]
    ):
        return "📧 內容與日常操作"
    if any(
        k in name_lower
        for k in ["codex", "quality", "checker", "audit", "guard", "verify"]
    ):
        return "🛡️ 品質與驗證系統"
    if any(
        k in name_lower
        for k in ["persona", "soul", "agent", "router", "spawner", "bridge"]
    ):
        return "🤖 代理與人格核心"
    if any(k in name_lower for k in ["skill", "tool"]):
        return "🛠️ 技能與工具管理"
    return "⚙️ 其他系統腳本"


def parse_python_file(path: Path) -> dict:
    info = {
        "status": "✅ 正常",
        "desc": "無描述",
        "details": [],
        "allowed": True,
        "is_locked": False,
    }
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        doc = ast.get_docstring(tree)
        if doc:
            info["desc"] = doc.strip().splitlines()[0]
        funcs = [
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]
        if funcs:
            info["details"] = funcs[:5]
    except:
        pass
    return info


def parse_markdown_agent(path: Path) -> dict:
    info = {
        "status": "✅ 正常",
        "desc": "Markdown 協定檔案",
        "details": [],
        "allowed": True,
        "is_locked": False,
        "type": "protocol",
    }
    try:
        content = path.read_text(encoding="utf-8")
        content_clean = re.sub(r"^---.*?---", "", content, flags=re.DOTALL)
        lines = content_clean.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "desc:" in line.lower():
                info["desc"] = line.split(":", 1)[1].strip()
                break
            if not line.startswith("#") and len(line) > 5:
                info["desc"] = line[:80] + "..."
                break
    except:
        pass
    return info


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Muse-Core War Room Pro Max</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { 
            --bg: #0F172A; --sidebar-bg: rgba(15, 23, 42, 0.9); --card: #1E293B; --text: #F8FAFC; 
            --muted: #94A3B8; --accent: #3B82F6; --border: rgba(255, 255, 255, 0.06);
            --ok: #22C55E; --warning: #F59E0B; --error: #EF4444; --sidebar-width: 280px;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Outfit', sans-serif; background: var(--bg); color: var(--text); margin: 0; display: flex; height: 100vh; overflow: hidden; }
        aside { width: var(--sidebar-width); height: 100vh; background: var(--sidebar-bg); backdrop-filter: blur(20px); border-right: 1px solid var(--border); padding: 2rem 1.5rem; display: flex; flex-direction: column; z-index: 1000; }
        .logo { font-size: 1.5rem; font-weight: 700; background: linear-gradient(135deg, #60A5FA, #A78BFA); -webkit-background-clip: text; -webkit-fill-color: transparent; margin-bottom: 2rem; display: flex; align-items: center; gap: 12px; }
        .heartbeat { width: 12px; height: 12px; background: var(--ok); border-radius: 2px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        
        /* 【核心修復】徹底加固所有 Tab 按鈕，防禦圓形截斷 */
        .segmented-control { 
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px; 
            background: rgba(0,0,0,0.25); border-radius: 12px; padding: 6px; 
            border: 1px solid var(--border); margin-bottom: 2rem; width: 100%;
        }
        .segmented-control button { 
            background: transparent; border: none; color: var(--muted); 
            padding: 0.6rem 0.5rem; border-radius: 8px !important; cursor: pointer; 
            font-size: 0.85rem; font-weight: 600; transition: all 0.2s ease; 
            white-space: nowrap; text-align: center; 
            width: 100% !important; height: auto !important;
            display: block !important; overflow: visible !important;
        }
        .segmented-control button.active,
        #btn-tools.active,
        #btn-cron.active,
        #btn-protocols.active,
        #btn-intel.active { 
            background: var(--accent) !important; color: white !important; 
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
            border-radius: 8px !important; width: auto !important;
            height: auto !important; padding: 0.6rem 1rem !important;
            overflow: visible !important; white-space: nowrap !important;
            min-width: 4.5rem !important; max-width: none !important;
        }

        .side-nav { list-style: none; padding: 0; margin: 0; overflow-y: auto; flex: 1; }
        .nav-item { padding: 0.75rem 1rem; border-radius: 10px; margin-bottom: 0.25rem; cursor: pointer; color: var(--muted); font-size: 0.9rem; transition: 0.2s; }
        .nav-item:hover { background: rgba(255,255,255,0.04); color: white; }
        .nav-item.active { background: rgba(59, 130, 246, 0.1); color: var(--accent); }

        main { flex: 1; padding: 3rem 4rem; overflow-y: auto; }
        .search-container { position: relative; margin-bottom: 3rem; max-width: 600px; }
        .search-input { width: 100%; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 1rem 1rem 1rem 3rem; color: white; font-size: 1rem; }
        .search-icon { position: absolute; left: 1.25rem; top: 50%; transform: translateY(-50%); color: var(--muted); }

        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1.5rem; }
        .card { background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 16px; padding: 1.5rem; transition: 0.3s; position: relative; }
        .card:hover { transform: translateY(-6px); box-shadow: 0 20px 40px rgba(0,0,0,0.4); border-color: rgba(255,255,255,0.1); }
        .badge-ext { position: absolute; top: 1rem; right: 1rem; font-size: 0.6rem; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; color: var(--muted); }
        .card h3 { margin: 0 0 0.75rem 0; font-size: 1.1rem; font-family: 'JetBrains Mono'; }
        .card-desc { font-size: 0.9rem; color: var(--muted); margin-bottom: 1rem; line-height: 1.5; }
        .btn-run { background: rgba(59, 130, 246, 0.1); color: var(--accent); border: 1px solid rgba(59, 130, 246, 0.2); padding: 0.5rem 1.25rem; border-radius: 8px; cursor: pointer; font-weight: 600; transition: 0.2s; }
        .btn-run:hover:not(:disabled) { background: var(--accent); color: white; }
        
        .cron-card { background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--ok); border-radius: 16px; padding: 1.5rem; margin-bottom: 1.5rem; }
        .cron-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
        .cron-schedule { font-family: 'JetBrains Mono'; color: var(--accent); font-weight: 700; background: rgba(59,130,246,0.1); padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; }
        .cron-command { font-family: 'JetBrains Mono'; font-size: 0.8rem; color: #94A3B8; background: rgba(0,0,0,0.3); padding: 0.75rem; border-radius: 8px; margin-bottom: 1.5rem; word-break: break-all; }
        .cron-actions { display: flex; justify-content: space-between; align-items: center; }
        .switch-wrapper { display: flex; align-items: center; gap: 10px; cursor: pointer; user-select: none; }
        .switch { width: 44px; height: 22px; background: rgba(255,255,255,0.1); border-radius: 11px; position: relative; transition: 0.3s; }
        .switch::after { content:''; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; background: white; border-radius: 50% !important; transition: 0.3s; }
        .switch.on { background: var(--ok); }
        .switch.on::after { left: 24px; }
        .diag-box { margin-top: 1rem; padding: 1.25rem; background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 12px; display: none; }
        .diag-box pre { font-family: 'JetBrains Mono'; font-size: 0.8rem; color: #FCA5A5; white-space: pre-wrap; margin: 0; }
    </style>
</head>
<body>
    <aside>
        <div class="logo"><div class="heartbeat"></div> Muse-Core</div>
        <div class="segmented-control">
            <button id="btn-tools" class="active" onclick="switchView('tools')">Tools</button>
            <button id="btn-cron" onclick="switchView('cron')">Cron</button>
            <button id="btn-protocols" onclick="switchView('protocols')">Agents</button>
            <button id="btn-intel" onclick="switchView('intel')">Intel</button>
            <button id="btn-brainb" onclick="window.open('http://localhost:8081', '_blank')">Brain-B 🌀</button>
        </div>
        <ul id="sidebar-nav" class="side-nav"></ul>
    </aside>
    <main>
        <div class="search-container">
            <span class="search-icon">🔍</span>
            <input type="text" id="search-input" class="search-input" placeholder="搜尋腳本、指令或代理人 (⌘K)..." oninput="handleSearch()">
        </div>
        <h1 id="view-title" style="margin-bottom: 2rem;">腳本工具 (Tools)</h1>
        <div id="app"></div>
    </main>
    <script>
        let scriptData = { tools: {}, protocols: {}, intel: {} }; let cronData = []; let currentView = 'tools';
        async function init() {
            await fetchAllData(); renderView();
            document.addEventListener('keydown', (e) => { if (e.metaKey && e.key === 'k') { e.preventDefault(); document.getElementById('search-input').focus(); } });
        }
        async function fetchAllData() {
            try {
                const [sRes, cRes] = await Promise.all([fetch('/api/scripts').then(r => r.json()), fetch('/api/cron').then(r => r.json())]);
                scriptData = sRes; cronData = Array.isArray(cRes) ? cRes : [];
            } catch (err) { console.error("Init failed", err); }
        }
        function switchView(view) {
            currentView = view;
            document.querySelectorAll('.segmented-control button').forEach(b => b.classList.remove('active'));
            document.getElementById('btn-' + (view === 'protocols' ? 'protocols' : view)).classList.add('active');
            const titles = { 'tools': '腳本工具 (Tools)', 'cron': '背景排程管家 (Cron)', 'protocols': '代理協定 (Agents)', 'intel': '情報監控 (Intel)' };
            document.getElementById('view-title').textContent = titles[view];
            handleSearch();
        }
        function renderView(filter = '') {
            const app = document.getElementById('app'); const sideNav = document.getElementById('sidebar-nav');
            app.innerHTML = ''; sideNav.innerHTML = '';
            if (currentView === 'cron') { renderCronView(filter); return; }
            const data = scriptData[currentView] || {};
            Object.keys(data).sort().forEach((cat, idx) => {
                const items = data[cat].filter(s => s.name.toLowerCase().includes(filter.toLowerCase()) || (s.desc && s.desc.toLowerCase().includes(filter.toLowerCase())));
                if (items.length === 0) return;
                const navId = `cat-${idx}`;
                const navItem = document.createElement('li'); navItem.className = 'nav-item';
                navItem.innerHTML = `◆ ${cat}`;
                navItem.onclick = () => document.getElementById(navId).scrollIntoView({behavior:'smooth'});
                sideNav.appendChild(navItem);
                const section = document.createElement('div'); section.id = navId;
                section.innerHTML = `<div style="font-size:1.1rem; font-weight:700; color:var(--accent); margin:2rem 0 1rem 0;">${cat}</div>`;
                const grid = document.createElement('div'); grid.className = 'grid';
                items.forEach(s => {
                    const card = document.createElement('div'); card.className = 'card';
                    card.innerHTML = `<span class="badge-ext">${s.ext}</span><h3>${s.name}</h3><div class="card-desc">${s.desc}</div><button class="btn-run" onclick="handleRun('${s.name}')">▶ 執行</button>`;
                    grid.appendChild(card);
                });
                section.appendChild(grid); app.appendChild(section);
            });
        }
        function renderCronView(filter = '') {
            const app = document.getElementById('app');
            const filtered = cronData.filter(j => j.name.toLowerCase().includes(filter.toLowerCase()) || j.command.toLowerCase().includes(filter.toLowerCase()));
            let html = '<div style="max-width:900px;">';
            filtered.forEach(j => {
                html += `<div class="cron-card ${j.enabled ? '' : 'disabled'}">
                    <div class="cron-header"><h3>${j.name}</h3><span class="cron-schedule">${j.schedule}</span></div>
                    <div class="cron-command"><code>${j.command}</code></div>
                    <div class="cron-actions">
                        <div class="switch-wrapper" onclick="toggleCron('${encodeURIComponent(j.raw)}', ${!j.enabled})">
                            <div class="switch ${j.enabled ? 'on' : ''}"></div><span>${j.enabled ? '運行中' : '已停用'}</span>
                        </div>
                        <button id="test-${j.id}" class="btn-run" onclick="testCron(${j.id}, '${encodeURIComponent(j.command)}')" style="border-color:var(--warning); color:var(--warning);">🧪 測試並自癒</button>
                    </div>
                    <div id="diag-${j.id}" class="diag-box"></div>
                </div>`;
            });
            app.innerHTML = html + '</div>';
        }
        async function handleRun(name) {
            const btn = event.target; const oldText = btn.textContent; btn.disabled = true; btn.textContent = '⏳ ...';
            try {
                const res = await fetch(`/api/run/${encodeURIComponent(name)}`, { method: 'POST' });
                const data = await res.json(); btn.textContent = data.success ? '✅' : '❌';
                setTimeout(() => { btn.disabled = false; btn.textContent = oldText; }, 3000);
            } catch { btn.disabled = false; btn.textContent = 'ERR'; }
        }
        async function toggleCron(raw, enable) {
            await fetch('/api/cron/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw_job: decodeURIComponent(raw), enable: enable }) });
            await fetchAllData(); renderView(document.getElementById('search-input').value);
        }
        async function testCron(id, cmd) {
            const btn = document.getElementById('test-' + id); const box = document.getElementById('diag-' + id);
            btn.disabled = true; btn.textContent = '⏳ ...'; box.style.display = 'none';
            try {
                const res = await fetch('/api/cron/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: decodeURIComponent(cmd) }) });
                const data = await res.json();
                btn.disabled = false; btn.textContent = '🧪 測試並自癒'; box.style.display = 'block';
                if (data.success) {
                    box.innerHTML = `<div style="color:var(--ok); font-weight:700;">${data.is_healed ? '🛠️ 自癒成功' : '✅ 測試通過'}</div><pre>${data.diagnosis || '無異狀'}</pre>`;
                } else {
                    box.innerHTML = `<div style="color:var(--error); font-weight:700;">🚨 失敗</div><pre>${data.diagnosis || (data.result ? data.result.error : '未知錯誤')}</pre>`;
                }
            } catch { btn.disabled = false; btn.textContent = 'ERR'; }
        }
        function handleSearch() { renderView(document.getElementById('search-input').value); }
        async function updateFeed() {
            try {
                const res = await fetch('/api/feed'); const events = await res.json();
                const list = document.getElementById('feed-list');
                if (events.length > 0) { list.innerHTML = events.map(ev => `<div style="background:rgba(255,255,255,0.03); padding:0.75rem; border-radius:10px; border-left:3px solid var(--accent);"><div style="font-size:0.7rem; font-weight:700; color:var(--accent);">${ev.agent}</div><div style="font-size:0.85rem;">${ev.msg}</div></div>`).join(''); }
            } catch {}
        }
        init(); setInterval(updateFeed, 5000);
    </script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
