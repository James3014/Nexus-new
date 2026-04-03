import React, { useEffect, useRef } from 'react';
import Ansi from 'ansi-to-react';

interface Props {
  logs: string[];
  height: number;
}

export const LogStreamPanel: React.FC<Props> = ({ logs, height }) => {
  const listRef = useRef<HTMLDivElement | null>(null);

  // 自動捲動到底部
  useEffect(() => {
    if (listRef.current && logs.length > 0) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="bg-[#050505] border border-[#1a1a1a] rounded-sm overflow-hidden flex flex-col shadow-inner">
      <div className="bg-[#0a0a0a] p-2 border-b border-[#1a1a1a] flex justify-between items-center px-4">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-pulse" />
          <span className="text-[10px] font-bold text-[#555] uppercase tracking-widest">Live Log Stream</span>
        </div>
        <div className="flex gap-3 items-center">
          <span className="text-[9px] text-[#333] font-mono uppercase">Buffer: {logs.length}/5000</span>
          <button className="text-[9px] text-[#444] hover:text-white uppercase font-bold transition-colors">Clear</button>
        </div>
      </div>
      
      <div
        ref={listRef}
        className="flex-1 overflow-y-auto scrollbar-thin"
        style={{ height }}
      >
        {logs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-[10px] font-mono text-[#333] uppercase tracking-widest">
            No log lines yet
          </div>
        ) : (
          logs.map((line, index) => (
            <div key={`${index}-${line.slice(0, 24)}`} className="px-4 py-0.5 border-l border-blue-900/20 hover:bg-blue-900/5 transition-colors">
              <div className="flex gap-3 text-[11px] font-mono leading-relaxed">
                <span className="text-[#333] select-none text-[9px] w-8">{(index + 1).toString().padStart(4, '0')}</span>
                <span className="text-[#666] selection:text-white break-all">
                  <Ansi>{line}</Ansi>
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="bg-[#0a0a0a] h-1 border-t border-cyan-900/20" />
    </div>
  );
};
