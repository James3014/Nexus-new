import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface DecisionEntry {
  id: string;
  taskId: string;
  decisionId: string;
  action: string;
  actor: string;
  targetJson: string;
  reason?: string;
  evidenceRefsJson: string;
  ts: string;
}

interface Props {
  taskId: string;
}

export const DecisionLedgerPanel: React.FC<Props> = ({ taskId }) => {
  const [entries, setEntries] = useState<DecisionEntry[]>([]);

  useEffect(() => {
    if (taskId) {
      invoke<DecisionEntry[]>('list_decisions', { taskId })
        .then(setEntries)
        .catch(console.error);
    }
  }, [taskId]);

  return (
    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm flex flex-col h-full shadow-2xl">
      <div className="bg-[#0f0f0f] p-3 border-b border-[#1a1a1a] flex justify-between items-center px-4">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
          <span className="text-[10px] font-black text-[#555] uppercase tracking-widest">Decision Ledger (Append-Only)</span>
        </div>
        <span className="text-[9px] text-[#444] font-mono">ID Trace Ready</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar">
        {entries.length === 0 ? (
          <div className="text-center py-10 opacity-20 text-[10px] font-mono uppercase">No Decisions Recorded</div>
        ) : (
          entries.map(entry => (
            <div key={entry.id} className="relative pl-4 border-l border-blue-900/30 group">
              <div className="absolute left-[-4.5px] top-1.5 w-2 h-2 bg-blue-500 rounded-full scale-0 group-hover:scale-100 transition-all" />
              <div className="flex justify-between items-start mb-1">
                <span className="text-[10px] font-mono text-blue-400">{entry.decisionId.slice(0, 8)}</span>
                <span className="text-[9px] text-[#444]">{new Date(entry.ts).toLocaleTimeString()}</span>
              </div>
              <div className="flex items-center gap-2 mb-1">
                <span className={`px-1.5 py-0.5 rounded-sm text-[8px] font-black uppercase ${
                  entry.actor === 'human' ? 'bg-amber-900/20 text-amber-500 border border-amber-500/30' : 'bg-blue-900/20 text-blue-500 border border-blue-500/30'
                }`}>
                  {entry.actor}
                </span>
                <span className="text-sm font-bold text-white tracking-tight">{entry.action}</span>
              </div>
              {entry.reason && (
                <div className="text-[11px] text-[#888] italic mb-2 leading-relaxed">
                  » {entry.reason}
                </div>
              )}
              <div className="flex flex-wrap gap-2 opacity-50 group-hover:opacity-100 transition-opacity">
                <span className="text-[8px] font-mono bg-[#151515] px-1.5 py-0.5 border border-[#222]">Evidence Index: Linked</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
