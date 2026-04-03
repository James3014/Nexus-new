import React from 'react';

const PHASES = ["P", "X", "D", "R", "A", "C"];
const PHASE_LABELS: Record<string, string> = {
  P: "Plan", X: "Execute", D: "Diagnose", R: "Repair", A: "Accept", C: "Crystal"
};

interface Props {
  currentPhase: string;
  phaseStatus: Record<string, "success" | "fail" | "active" | "pending">;
  onClick?: (phase: string) => void;
}

export const PhaseTimeline: React.FC<Props> = ({ currentPhase, phaseStatus, onClick }) => {
  return (
    <div className="flex items-center justify-between w-full px-4 py-6 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm">
      {PHASES.map((p, i) => {
        const status = phaseStatus[p] || (p === currentPhase ? "active" : "pending");
        const isActive = p === currentPhase;
        
        return (
          <React.Fragment key={p}>
            <div className="flex flex-col items-center gap-2 relative group">
              <button 
                onClick={() => onClick?.(p)}
                className={`w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-black border-2 transition-all duration-500 cursor-pointer ${
                status === "success" ? "bg-emerald-900/40 border-emerald-500 text-emerald-400" :
                status === "fail" ? "bg-red-900/40 border-red-500 text-red-500 animate-pulse" :
                status === "active" ? "bg-blue-600 border-blue-400 text-white shadow-[0_0_15px_rgba(59,130,246,0.6)]" :
                "bg-transparent border-[#222] text-[#444]"
              }`}>
                {p}
              </button>
              <span className={`text-[9px] uppercase font-bold tracking-tighter ${isActive ? 'text-white' : 'text-[#444]'}`}>
                {PHASE_LABELS[p]}
              </span>
              
              <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-black border border-[#333] px-2 py-1 rounded text-[8px] opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-20">
                Phase {p}: {PHASE_LABELS[p]} ({status})
              </div>
            </div>
            
            {i < PHASES.length - 1 && (
              <div className={`flex-1 h-[2px] mx-2 transition-colors duration-1000 ${
                PHASES.indexOf(currentPhase) > i ? 'bg-emerald-900' : 'bg-[#1a1a1a]'
              }`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
