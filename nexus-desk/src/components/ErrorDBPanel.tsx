import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface ErrorFix {
  id: number;
  pattern: string;
  fix_command: string;
  success_rate: number;
}

interface Props {
  errorCode: number;
  traceback: string;
  onApply: (cmd: string) => void;
}

export const ErrorDBPanel: React.FC<Props> = ({ errorCode, traceback, onApply }) => {
  const [fixes, setFixes] = useState<ErrorFix[]>([]);

  useEffect(() => {
    if (errorCode || traceback) {
      invoke<ErrorFix[]>('query_error_fix', { exitCode: errorCode, traceback })
        .then(setFixes)
        .catch(console.error);
    }
  }, [errorCode, traceback]);

  if (fixes.length === 0) return null;

  return (
    <div className="bg-[#120505] border border-red-900/30 rounded-sm p-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
        <span className="text-[10px] font-black text-red-400 uppercase tracking-widest">Known Fixes Detected ({fixes.length})</span>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {fixes.map(fix => (
          <div key={fix.id} className="bg-[#0a0a0a] border border-[#222] p-3 hover:border-red-500/50 transition-all group">
            <div className="flex justify-between items-start mb-2">
              <span className="text-xs font-bold text-white">{fix.pattern}</span>
              <span className="text-[10px] font-mono text-emerald-500">Confidence: {Math.round(fix.success_rate * 100)}%</span>
            </div>
            <div className="bg-black p-2 rounded-sm mb-3">
              <code className="text-[10px] text-red-300 font-mono">{fix.fix_command}</code>
            </div>
            <button 
              onClick={() => onApply(fix.fix_command)}
              className="w-full py-1.5 bg-red-900/20 text-red-400 border border-red-500/30 text-[10px] font-black uppercase hover:bg-red-500 hover:text-white transition-all"
            >
              Apply Recommended Fix
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
