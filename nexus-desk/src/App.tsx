import { useState, useEffect, useRef } from "react";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { DeskViewModel } from "./types/DeskViewModel";
import { LogEvent, PhaseEvent, DeskEvent } from "./types/DeskEvent";
import { CriticalBanner } from "./components/CriticalBanner";
import { ResolutionDrawer } from "./components/ResolutionDrawer";
import { ActionButtons } from "./components/ActionButtons";
import { LogStreamPanel } from "./components/LogStreamPanel";
import { PhaseTimeline } from "./components/PhaseTimeline";
import { ProfileSwitcher } from "./components/ProfileSwitcher";
import { RunSwitcher } from "./components/RunSwitcher";
import { DiffViewer } from "./components/DiffViewer";
import { MetricsRibbon } from "./components/MetricsRibbon";
import { ErrorDBPanel } from "./components/ErrorDBPanel";
import { DecisionLedgerPanel } from "./components/DecisionLedgerPanel";
import { ReviewSidebar } from "./components/ReviewSidebar";
import { ReplaySnapshotModal } from "./components/ReplaySnapshotModal";
import ArmorStatsPanel from "./components/ArmorStatsPanel";

// 🛡️ [BRIDGE] Safe Multi-Mode Invocation
import { safeInvoke, isTauriEnv } from "./lib/bridge";

function App() {
  const [data, setData] = useState<DeskViewModel | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [phaseStatus, setPhaseStatus] = useState<Record<string, "success" | "fail" | "active" | "pending">>({});
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [currentProfile, setCurrentProfile] = useState("prod");
  
  // Replay State
  const [activeSnapshot, setActiveSnapshot] = useState<any>(null);
  const [isSnapshotOpen, setIsSnapshotOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"standard" | "swarm">("standard");

  const unlistenLogRef = useRef<UnlistenFn | null>(null);
  const unlistenEventRef = useRef<UnlistenFn | null>(null);

  const fetchData = async () => {
    try {
      // 🛡️ [SAFE] Use abstraction
      const res = await safeInvoke<DeskViewModel>("get_desk_view_model");
      setData(res);
      setBootError(null);
      if (res.showCriticalAlert && !isDrawerOpen) {
        setIsDrawerOpen(true);
      }
    } catch (e) {
      console.error("Fetch Error:", e);
      setBootError(e instanceof Error ? e.message : String(e));
    }
  };

  const logDecision = async (action: string, actor: string, reason?: string) => {
    if (!data?.taskId) return;
    try {
      await safeInvoke("append_decision", {
        taskId: data.taskId,
        action,
        actor,
        targetJson: JSON.stringify({ currentPhase: data.currentPhase }),
        reason,
        evidenceRefsJson: JSON.stringify(["manifest.json", "auditresult.json"])
      });
    } catch (e) {
      console.error("Ledger Error:", e);
    }
  };

  const startSubscriptions = async (taskId: string) => {
    if (!isTauriEnv()) return; // Subscription requires IPC
    
    if (unlistenLogRef.current) unlistenLogRef.current();
    if (unlistenEventRef.current) unlistenEventRef.current();

    try {
      await safeInvoke("subscribe_log_tail", { taskId });
      await safeInvoke("subscribe_run_events", { taskId });

      unlistenLogRef.current = await listen<LogEvent>("log-line", (event) => {
        if (event.payload.taskId === taskId) {
          setLogs(prev => [...prev.slice(-4999), event.payload.line]);
        }
      });

      unlistenEventRef.current = await listen<DeskEvent>("run-event", (event) => {
        const payload = event.payload;
        if (payload.taskId === taskId) {
          if (payload.kind === "phase.start" || payload.kind === "phase.complete") {
            const e = payload as PhaseEvent;
            setPhaseStatus(prev => ({ 
              ...prev, 
              [e.phase]: e.kind === "phase.start" ? "active" : (e.status === "fail" ? "fail" : "success") 
            }));
          }
          fetchData();
        }
      });
    } catch (e) {
      console.error("Subscription Error:", e);
      setBootError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    // 🛡️ [URL-Switch] Check for Swarm Mode
    const params = new URLSearchParams(window.location.search);
    if (params.get('mode') === 'swarm') {
        setViewMode('swarm');
    }
    
    fetchData();
    const timer = setInterval(fetchData, 5000);
    return () => {
      clearInterval(timer);
      if (unlistenLogRef.current) unlistenLogRef.current();
      if (unlistenEventRef.current) unlistenEventRef.current();
    };
  }, []);

  useEffect(() => {
    if (data?.taskId) {
      startSubscriptions(data.taskId);
    }
  }, [data?.taskId]);

  const handleAction = async (cmd: string) => {
    try {
      await logDecision(`COMMAND_EXEC: ${cmd}`, 'human');
      
      // 🛡️ v23 Wisdom Feedback Integration
      if (cmd.startsWith('wisdom_')) {
        const typeMap: Record<string, string> = {
          'wisdom_correct': 'correct',
          'wisdom_fp': 'false_positive',
          'wisdom_missed': 'unsafe_missed'
        };
        
        const feedbackEvent = {
          task_id: data?.taskId || "manual-entry",
          pattern_id: "auto-detect", // 這裡未來可由 UI 傳入具體 Pattern ID
          feedback_type: typeMap[cmd],
          actor: "commander",
          source: "desk_ui"
        };
        
        const { submitFeedback } = await import("./lib/bridge");
        const res = await submitFeedback(feedbackEvent);
        console.log("Wisdom Feedback Submitted:", res);
        alert(`Wisdom Feedback Sent: ${typeMap[cmd]}`);
      } else {
        await safeInvoke("run_nexus_command", { cmd });
      }
      
      fetchData();
    } catch (e) {
      alert(`Command Error: ${e}`);
    }
  };

  const handleApplyFix = async (fixCmd: string) => {
    await logDecision(`FIX_APPLY: ${fixCmd}`, 'human', 'Applying suggested fingerprint fix.');
    handleAction(fixCmd);
  };

  const handleProfileChange = async (p: string) => {
     setCurrentProfile(p);
     await logDecision(`PROFILE_SWITCH: ${p}`, 'human');
  };

  const onPhaseClick = (phase: string) => {
    const snapshot = {
      id: `snap-${phase}`,
      phase,
      ts: new Date().toISOString(),
      logWindow: logs.slice(-20),
      diffPreview: "--- Replay Code Context ---\n+ Fixed memory leak\n- legacy code",
      metrics: { tokens: 1200, cost: 0.05 }
    };
    setActiveSnapshot(snapshot);
    setIsSnapshotOpen(true);
  };

  const handleAddAnnotation = async (body: string, severity: string) => {
    if (!data?.taskId) return;
    try {
      await safeInvoke("add_annotation", {
        taskId: data.taskId,
        targetType: 'TASK',
        targetRefJson: JSON.stringify({ taskId: data.taskId }),
        severity,
        body,
        author: 'Commander'
      });
      await logDecision('ANNOTATION_ADD', 'human', `Added ${severity} review note.`);
    } catch (e) {
      console.error(e);
    }
  };

  if (!data) {
    return (
      <div className="h-screen bg-black flex items-center justify-center px-6">
        <div className="max-w-3xl w-full border border-cyan-900/40 bg-[#050505] p-6 font-mono">
          <div className="text-cyan-500 text-sm tracking-widest uppercase">
            Nexus Governance Boot
          </div>
          <div className="mt-4 text-cyan-400 animate-pulse">
            NEXUS_GOVERNANCE_SYSTEM_BOOT...
          </div>
          {bootError && (
            <div className="mt-6 border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300 whitespace-pre-wrap break-words">
              {bootError}
            </div>
          )}
        </div>
      </div>
    );
  }

  const isLocked = data.showCriticalAlert || ["TAMPERED", "VERIFYFATAL"].includes(data.normalizedStatus);
  const isError = data.severity === "danger" && data.normalizedStatus !== "INIT";

  return (
    <div className="h-screen flex flex-col bg-[#050505] text-[#ccc] font-sans selection:bg-blue-900/30 scanline overflow-hidden">
      <CriticalBanner 
        isVisible={isLocked} 
        message={data.normalizedStatus} 
        reason={data.showCriticalAlert ? "LOCKED BY GOVERNANCE SPINE: TAMPERED" : "FATAL STATE LOCK"} 
      />

      <header className="px-4 py-2 border-b border-[#222] bg-[#0a0a0a] flex justify-between items-center z-10 shrink-0">
        <div className="flex items-center gap-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-[#555] font-black uppercase tracking-tighter">Governance Unit</span>
            <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white tracking-widest">{data.armorName}</span>
                {!isTauriEnv() && (
                    <span className="bg-amber-900/40 border border-amber-500/30 text-amber-500 text-[8px] px-1 px-1.5 rounded uppercase font-black animate-pulse">
                        Mock Mode
                    </span>
                )}
            </div>
          </div>
          <div className="h-8 w-px bg-[#222]" />
          <ProfileSwitcher currentProfile={currentProfile} onProfileChange={handleProfileChange} />
          <RunSwitcher activeTaskId={data.taskId} onTaskChange={() => fetchData()} />
        </div>
        
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setViewMode(viewMode === "standard" ? "swarm" : "standard")} 
            className={`text-[10px] border px-3 py-1 rounded-sm transition-all uppercase font-bold ${
                viewMode === "swarm" ? "bg-amber-900/30 text-amber-500 border-amber-500/50" : "bg-blue-900/20 text-blue-400 border-blue-500/30"
            }`}
          >
            {viewMode === "standard" ? "Switch to Swarm" : "Switch to Core"}
          </button>
          <button onClick={() => setIsDrawerOpen(true)} className="text-[10px] bg-blue-900/20 text-blue-400 border border-blue-500/30 px-3 py-1 rounded-sm hover:bg-blue-500 transition-all uppercase font-bold">Reality Audit</button>
          <div className={`w-2 h-2 rounded-full animate-pulse ${isLocked ? 'bg-red-500 shadow-[0_0_10px_red]' : 'bg-green-500 shadow-[0_0_10px_green]'}`} />
        </div>
      </header>

      <main className="flex-1 p-3 flex flex-col gap-3 overflow-hidden">
        {viewMode === "standard" ? (
            <div className="flex-1 flex flex-col gap-3 overflow-hidden">
                <div className="shrink-0 space-y-3">
                    <MetricsRibbon totalTokens={2730} phaseCosts={{P: {tokens: 420, cost: 0.02}}} />
                    <PhaseTimeline currentPhase={data.currentPhase} phaseStatus={phaseStatus} onClick={onPhaseClick} />
                </div>

                <div className="flex-1 grid grid-cols-12 gap-3 overflow-hidden">
                    {/* Fact Source (Logs + Diff) */}
                    <div className="col-span-12 lg:col-span-8 grid grid-rows-2 gap-3 overflow-hidden">
                        <LogStreamPanel logs={logs} height={300} />
                        <DiffViewer taskId={data.taskId} />
                    </div>

                    {/* Decision & Governance Column */}
                    <div className="col-span-12 lg:col-span-4 flex flex-col gap-3 overflow-hidden">
                        <div className="h-1/2 flex flex-col overflow-hidden text-white">
                            <DecisionLedgerPanel taskId={data.taskId} />
                        </div>
                        <div className="flex-1 flex flex-col overflow-hidden">
                            <ReviewSidebar taskId={data.taskId} onAddAnnotation={handleAddAnnotation} />
                        </div>
                    </div>
                </div>
            </div>
        ) : (
            <div className="flex-1 overflow-hidden">
                <ArmorStatsPanel />
            </div>
        )}

        {/* 🛡️ Global Action Lock bar (RESTORED) */}
        <section className="bg-[#0d0d0d] p-4 border border-[#222] shadow-2xl relative shrink-0">
          {isError && (
              <div className="mb-4">
                 <ErrorDBPanel errorCode={1} traceback="demo" onApply={handleApplyFix} />
              </div>
          )}
          <ActionButtons actions={data.availableActions || {}} isLocked={isLocked} onAction={handleAction} lockReason={isLocked ? "GOVERNANCE LOCK: CANNOT ESCAPE" : undefined} />
        </section>
      </main>

      <ResolutionDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} trace={data.resolutionTrace} />
      <ReplaySnapshotModal isOpen={isSnapshotOpen} onClose={() => setIsSnapshotOpen(false)} snapshot={activeSnapshot} />
    </div>
  );
}

export default App;
