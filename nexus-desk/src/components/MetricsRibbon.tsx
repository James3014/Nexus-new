import React from 'react';

interface PhaseCost {
  tokens: number;
  cost: number;
}

interface Props {
  totalTokens: number;
  phaseCosts: Record<string, PhaseCost>;
}

export const MetricsRibbon: React.FC<Props> = ({ totalTokens, phaseCosts }) => {
  const totalCost = Object.values(phaseCosts).reduce((acc, curr) => acc + curr.cost, 0);
  const phases = ["P", "X", "D", "R", "A", "C"];

  return (
    <div className="flex items-center gap-4 bg-[#0a0a0a] border border-[#1a1a1a] p-3 rounded-sm shadow-xl">
      <div className="flex flex-col border-r border-[#222] pr-6">
        <span className="text-[9px] text-[#555] font-black uppercase tracking-widest">Session Total</span>
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-black text-white">${totalCost.toFixed(3)}</span>
          <span className="text-[10px] text-emerald-500 font-mono">({(totalTokens / 1000).toFixed(1)}k tokens)</span>
        </div>
      </div>
      
      <div className="flex-1 flex items-center gap-3 overflow-x-auto no-scrollbar py-1">
        {phases.map(p => {
          const cost = phaseCosts[p] || { tokens: 0, cost: 0 };
          const hasCost = cost.tokens > 0;
          
          return (
            <div key={p} className={`flex flex-col gap-1 min-w-[60px] p-2 rounded-sm border transition-all ${
              hasCost ? 'bg-blue-900/10 border-blue-500/30' : 'bg-transparent border-[#151515] opacity-30'
            }`}>
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-black text-[#555]">{p}</span>
                {hasCost && <div className="w-1 h-1 bg-blue-400 rounded-full animate-pulse" />}
              </div>
              <span className={`text-[11px] font-mono font-bold ${hasCost ? 'text-blue-400' : 'text-[#333]'}`}>
                {cost.tokens.toLocaleString()}t
              </span>
            </div>
          );
        })}
      </div>
      
      {/* Dynamic Sparkline Simulation */}
      <div className="hidden lg:flex items-end gap-1 h-8 px-4 opacity-50">
        {[40, 70, 30, 90, 50, 60, 45, 80].map((h, i) => (
          <div key={i} style={{ height: `${h}%` }} className="w-1 bg-cyan-600 rounded-t-[1px]" />
        ))}
      </div>
    </div>
  );
};
