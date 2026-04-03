import React from 'react';

interface Props {
  sourceString: string;
  score: number;
}

export const SignalChip: React.FC<Props> = ({ sourceString, score }) => {
  // 解析 "實體訊號: signals.fixsuccessrate" 這種格式
  const signalName = sourceString.includes('signals.') 
    ? sourceString.split('signals.')[1] 
    : 'general';

  const getColorClass = () => {
    if (score >= 90) return 'border-emerald-500/50 text-emerald-400 bg-emerald-900/10';
    if (score >= 70) return 'border-yellow-500/50 text-yellow-400 bg-yellow-900/10';
    return 'border-red-500/50 text-red-400 bg-red-900/10';
  };

  return (
    <div className="flex flex-col gap-1">
      <div className={`flex items-center gap-1.5 px-2 py-0.5 border rounded-full self-start transition-all hover:scale-105 cursor-help ${getColorClass()}`}>
        <span className="text-[10px] font-black uppercase tracking-tighter">SIGNAL:</span>
        <span className="text-[11px] font-mono font-bold">{signalName}</span>
        <span className="text-[9px] font-bold opacity-80 backdrop-blur-md">[{score}%]</span>
      </div>
      <div className="text-[9px] text-[#444] font-medium ml-1">
        Source: {sourceString.replace('實體訊號: ', '')}
      </div>
    </div>
  );
};
