import React from 'react';
import Ansi from 'ansi-to-react';
import Editor from '@monaco-editor/react';

interface Snapshot {
  id: string;
  phase: string;
  ts: string;
  logWindow: string[];
  diffPreview: string;
  metrics: {
    tokens: number;
    cost: number;
  };
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  snapshot: Snapshot | null;
}

export const ReplaySnapshotModal: React.FC<Props> = ({ isOpen, onClose, snapshot }) => {
  if (!isOpen || !snapshot) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-8 animate-in fade-in duration-300">
      <div className="w-full max-w-6xl h-4/5 bg-[#050505] border border-blue-900/40 rounded-sm flex flex-col shadow-[0_0_100px_rgba(30,58,138,0.2)]">
        <div className="bg-[#0a0a0a] p-4 border-b border-[#222] flex justify-between items-center">
          <div className="flex items-center gap-4">
            <div className="bg-blue-600 px-3 py-1 rounded-sm text-[10px] font-black italic tracking-widest text-white uppercase">Historical Snapshot</div>
            <span className="text-sm font-bold text-white tracking-widest uppercase">Phase {snapshot.phase} · {new Date(snapshot.ts).toLocaleString()}</span>
          </div>
          <button onClick={onClose} className="text-white hover:text-red-500 transition-colors text-xl font-bold">×</button>
        </div>

        <div className="flex-1 overflow-hidden grid grid-cols-12 gap-1 p-1">
          {/* Logs Window */}
          <div className="col-span-5 flex flex-col bg-[#080808] border border-[#1a1a1a] overflow-hidden">
            <div className="p-2 border-b border-[#222] text-[9px] font-black text-[#444] uppercase tracking-widest px-4">Log Snapshot</div>
            <div className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-[10px] no-scrollbar">
              {snapshot.logWindow.map((line, i) => (
                <div key={i} className="text-[#888]"><Ansi>{line}</Ansi></div>
              ))}
            </div>
          </div>

          {/* Diff Preview */}
          <div className="col-span-4 flex flex-col bg-[#080808] border border-[#1a1a1a] overflow-hidden">
             <div className="p-2 border-b border-[#222] text-[9px] font-black text-[#444] uppercase tracking-widest px-4">Code Context</div>
             <div className="flex-1 min-h-0">
               <Editor 
                 height="100%"
                 theme="vs-dark"
                 language="diff"
                 value={snapshot.diffPreview}
                 options={{ readOnly: true, minimap: { enabled: false }, fontSize: 11 }}
               />
             </div>
          </div>

          {/* Metrics & Decision Sidebar */}
          <div className="col-span-3 flex flex-col gap-1 overflow-hidden">
            <div className="bg-[#0c0c0c] border border-[#1a1a1a] p-6 flex flex-col items-center justify-center text-center">
               <span className="text-[10px] text-[#555] font-black uppercase mb-1">Phase Cost</span>
               <span className="text-2xl font-black text-white tracking-tighter">${snapshot.metrics.cost.toFixed(3)}</span>
               <span className="text-[10px] text-emerald-500 font-mono mt-1">{snapshot.metrics.tokens.toLocaleString()} tokens used</span>
            </div>
            
            <div className="flex-1 bg-[#0c0c0c] border border-[#1a1a1a] p-4">
              <span className="text-[10px] text-[#555] font-black uppercase mb-3 block">Decision Lineage</span>
              <div className="space-y-3">
                 <div className="text-[11px] text-[#888] italic border-l-2 border-blue-900 px-3 py-1">
                   No specific human decision recorded for this timestamp.
                 </div>
              </div>
            </div>

            <button 
              onClick={onClose}
              className="w-full py-3 bg-blue-600/10 text-blue-400 border border-blue-500/30 text-[10px] font-black uppercase tracking-widest hover:bg-blue-600 hover:text-white transition-all shadow-lg"
            >
              Close Investigation
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
