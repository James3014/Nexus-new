import React from 'react';
import { FieldResolution } from '../types/DeskViewModel';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  trace: FieldResolution[];
}

export const ResolutionDrawer: React.FC<Props> = ({ isOpen, onClose, trace }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-[#0a0a0a] border-l border-[#333] shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
      <div className="p-4 border-b border-[#333] flex justify-between items-center bg-[#111]">
        <h3 className="text-sm font-bold text-white tracking-widest">
          🛡️ 數據真理溯源 (RESOLUTION TRACE)
        </h3>
        <button onClick={onClose} className="text-[#666] hover:text-white">✕</button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {trace.length === 0 && (
          <div className="text-[#444] text-xs text-center py-10">查無當前仲裁數據</div>
        )}
        
        {trace.map((item, index) => (
          <div key={index} className="bg-[#151515] border border-[#222] p-3 rounded-sm space-y-2">
            <div className="flex justify-between items-start">
              <span className="text-[10px] text-[#888] font-mono uppercase">Field: {item.fieldName}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                item.sourcePriority === 'P0' ? 'bg-blue-900/40 text-blue-400' : 'bg-orange-900/40 text-orange-400'
              }`}>
                {item.sourcePriority}
              </span>
            </div>
            
            <div className="text-sm text-cyan-400 font-mono break-all line-clamp-1">{item.resolvedValue}</div>
            
            <div className="pt-2 space-y-1">
              <div className="text-[10px] text-[#666] flex items-center gap-1">
                <span>📁</span> 
                <span className="truncate">{item.sourceFile}</span>
                {item.fallbackUsed && <span className="bg-yellow-900/20 text-yellow-600 px-1 rounded">FALLBACK</span>}
              </div>
              <div className="text-[9px] text-[#444] font-mono truncate">{item.sourcePath}</div>
            </div>

            <div className="bg-black/40 p-2 text-[10px] text-[#888] border-l-2 border-[#333]">
              {item.resolutionNote}
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 bg-[#111] border-t border-[#333]">
        <div className="text-[9px] text-[#555] uppercase tracking-tighter">
          Engine Reference: v22.0 Eternal Neural Swarm
        </div>
      </div>
    </div>
  );
};
