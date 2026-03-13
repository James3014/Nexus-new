import streamlit as st
import pandas as pd
import os
import re
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

# --- Configuration ---
VAULT_BASE = "/Users/jameschen/Downloads/obsidian/知識庫"
CRYSTALS_PATH = Path(VAULT_BASE) / "01_Operations/Inbox/Raw_Crystals"
DAILY_LOG = Path(VAULT_BASE) / "01_Operations/Daily_Log.md"

st.set_page_config(
    page_title="Brain-B | Operation Cockpit v5.3 Stability",
    page_icon="🧠",
    layout="wide",
)

# --- CSS Styles ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stMetric { background: rgba(30, 41, 59, 0.5); padding: 0.5rem; border-radius: 8px; border: 1px solid #334155; }
    .stMetricValue { font-size: 1.4rem !important; font-weight: 700 !important; color: #60A5FA !important; }
    .stMetricLabel { font-size: 0.75rem !important; color: #94A3B8 !important; }
    .card { padding: 0.8rem; border-radius: 10px; background-color: #1E293B; border: 1px solid #334155; margin-bottom: 0.6rem; }
    .card:hover { border-color: #3B82F6; }
    .summary-text { color: #94A3B8; font-size: 0.85rem; margin-top: 4px; line-height: 1.4; }
    .divergence-high { color: #F87171; font-weight: 700; }
    .divergence-med { color: #FBBF24; font-weight: 600; }
    .divergence-low { color: #34D399; }
</style>
""", unsafe_allow_html=True)

# --- Data Engine (Concentrated View-Model) ---

class StatusEvaluator:
    @staticmethod
    def get_stage(status_code):
        stages = {
            "optimal":   {"icon": "🟢", "desc": "運行完善 (Optimal)", "color": "#10B981"},
            "healthy":   {"icon": "🔵", "desc": "心跳正常 (Healthy)", "color": "#3B82F6"},
            "degraded":  {"icon": "🟡", "desc": "性能下降 (Degraded)", "color": "#FBBF24"},
            "stalled":   {"icon": "🟠", "desc": "進程停滯 (Stalled)", "color": "#F59E0B"},
            "failed":    {"icon": "🔴", "desc": "服務失敗 (Failed)", "color": "#EF4444"}
        }
        return stages.get(str(status_code).lower(), stages["stalled"])

@st.cache_data(ttl=20)
def get_real_service_status(service_id):
    try:
        res = subprocess.run(["launchctl", "list", service_id], capture_output=True, text=True, timeout=1)
        if res.returncode != 0: return "STALLED"
        return "OPERATIONAL" if ('"PID"' in res.stdout or "PID" in res.stdout) else "PULSING"
    except: return "STALLED"

@st.cache_data(ttl=5)
def fetch_agents_data():
    evolve_status = get_real_service_status("com.musecore.brainb.evolve")
    sub_status = get_real_service_status("com.musecore.subconscious")
    return [
        {"id": "TGBRIDGE", "mode": "Stream", "heartbeat": "2s", "errors": 0, "latency": "45ms", "status": "optimal"},
        {"id": "DREAM", "mode": "Batch", "heartbeat": "45s", "errors": 0, "latency": "1.2s", "status": "healthy"},
        {"id": "PUSH", "mode": "Sync", "heartbeat": "3m", "errors": 1, "latency": "8.5s", "queue": 42, "status": "degraded", "stall_reason": "Throughput bottleneck detected"},
        {
            "id": "EVOLVE", "mode": "Real-time", "heartbeat": "Stalled", "errors": 0, "status": "stalled" if evolve_status != "OPERATIONAL" else "optimal",
            "stall_reason": "Process Not Responding (Probe Timeout)" if evolve_status != "OPERATIONAL" else None
        },
        {
            "id": "THINK", "mode": "Real-time", "heartbeat": "Stalled", "errors": 0, "status": "stalled" if sub_status != "OPERATIONAL" else "optimal",
            "stall_reason": "No Progress in thinking chain" if sub_status != "OPERATIONAL" else None
        },
    ]

@st.cache_data(ttl=60)
def fetch_events_data():
    events = []
    if not CRYSTALS_PATH.exists(): return pd.DataFrame()
    for f in CRYSTALS_PATH.glob("[[]Brain-B]*"):
        if f.suffix != ".md": continue
        try:
            content = f.read_text(encoding="utf-8")
            etype = "DREAM" if "DREAM" in f.name else ("THINK" if "THINK" in f.name else "REALITY_CHECK")
            div = None
            if etype == "DREAM":
                m = re.search(r"\*\*分歧係數\*\*.*?\|.*?\|\s*\*\*([\d\.]+)\s*\(.*?\)\*\*", content, re.DOTALL)
                if m: div = float(m.group(1))
            elif etype == "REALITY_CHECK":
                m = re.search(r"Reality Signal.*?\s*(\d+)", content, re.I)
                if m: div = float(m.group(1)) / 100.0
            
            ts_m = re.search(r"(\d{8})_(\d{6})", f.name)
            ts = datetime.strptime(f"{ts_m.group(1)} {ts_m.group(2)}", "%Y%m%d %H%M%S") if ts_m else datetime.fromtimestamp(f.stat().st_mtime)
            
            risk = "LOW"
            if (div or 0) > 0.85 or etype == "REALITY_CHECK": risk = "CRITICAL"
            elif (div or 0) > 0.6: risk = "HIGH"
            
            verdict = "Pending"
            if "VERIFIED" in content: verdict = "Verified"
            elif "CONFLICT" in content: verdict = "Conflicted"

            events.append({
                "id": f"{ts.strftime('%m%d%H')}-{etype[:2].upper()}-{len(events)+1:03d}",
                "type": etype, "title": f.name[:50], "ts": ts, "time": ts.strftime("%H:%M"),
                "divergence": div, "risk": risk, "verdict": verdict, "file": str(f), "summary": "Legacy data..."
            })
        except: continue
    return pd.DataFrame(events).sort_values("ts", ascending=False) if events else pd.DataFrame()

def get_dashboard_state():
    """集中所有資料來源與統計，確保 View 層無邏輯。"""
    agents = fetch_agents_data()
    df_events = fetch_events_data()
    
    high_risks = len(df_events[df_events["risk"].isin(["CRITICAL", "HIGH"])]) if not df_events.empty else 0
    stalled_count = sum(1 for a in agents if a.get("status") == "stalled")
    avg_div = df_events["divergence"].dropna().mean() if not df_events.empty else 0.0
    
    # 🛡️ Formula: 10 - (Critical*0.5) - (Stalled*0.3) - (AvgDiv*1.0)
    perf_score = max(0.0, 10.0 - (high_risks * 0.5) - (stalled_count * 0.3) - (avg_div * 1.0))
    
    return {
        "agents": agents,
        "events": df_events,
        "summary": {
            "total_events": len(df_events),
            "high_risks": high_risks,
            "stalled_count": stalled_count,
            "avg_div": avg_div,
            "performance_score": perf_score
        }
    }

# --- Main Logic Flow ---
state = get_dashboard_state()
agents = state.get("agents", [])
df_events = state.get("events", pd.DataFrame())
summary = state.get("summary", {})

# --- Render Header ---
col_t, col_s = st.columns([7, 3])
col_t.markdown(f"## 🧠 BRAIN-B Cockpit <small>v5.3 Stability</small>", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("TOTAL EVENTS", summary.get("total_events", 0))
m2.metric("GOVERNANCE RISK", summary.get("high_risks", 0))
m3.metric("DIV AVG", f"{summary.get('avg_div', 0):.2f}")
m4.metric("SYS PERFORMANCE", f"{summary.get('performance_score', 0):.1f}/10")

# --- Render Agents ---
st.markdown("### ⚛️ Agents Status")
scols = st.columns(len(agents)) if agents else []
for i, a in enumerate(agents):
    info = StatusEvaluator.get_stage(a.get("status"))
    with scols[i]:
        st.markdown(f"""
        <div style='border: 1px solid #334155; padding: 10px; border-radius: 8px; background: {info['color']}11;'>
            <div style='font-weight: bold;'>{a.get('id')} {info['icon']}</div>
            <div style='font-size: 0.7rem; color: {info['color']}'>{info['desc']}</div>
            <div style='font-size: 0.6rem; color: #94A3B8; margin-top: 5px;'>Mode: {a.get('mode')}</div>
            <div style='font-size: 0.6rem; color: #94A3B8;'>Heartbeat: {a.get('heartbeat')}</div>
        </div>
        """, unsafe_allow_html=True)
        if a.get("stall_reason"):
            st.error(f"🚨 {a.get('stall_reason')}", icon="⚠️")

# --- Render Events ---
st.markdown("---")
l_col, r_col = st.columns([7, 3])
with l_col:
    st.subheader("⚡️ Events Stream")
    if df_events.empty:
        st.info("No events found.")
    else:
        for _, row in df_events.head(10).iterrows():
            st.markdown(f"""
            <div class="card">
                <div style="font-size: 0.6rem; color: #60A5FA;">{row.get('type')} · {row.get('risk')} · {row.get('time')} (ID: {row.get('id')})</div>
                <div style="font-weight: bold;">{row.get('title')}</div>
                <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 5px;">Verdict: {row.get('verdict')}</div>
            </div>
            """, unsafe_allow_html=True)

with r_col:
    st.subheader("🛠 Operations")
    if st.button("🔄 Sync Brain", use_container_width=True):
        st.write("Syncing...")

st.caption(f"Last Refreshed: {datetime.now().strftime('%H:%M:%S')}")
