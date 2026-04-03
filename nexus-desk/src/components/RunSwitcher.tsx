import React from 'react';

interface Props {
  activeTaskId: string;
  onTaskChange: (id: string) => void;
}

export const RunSwitcher: React.FC<Props> = ({ activeTaskId, onTaskChange }) => {
  // 這裡之後會接 invoke("list_runs")
  const recentRuns = [
    { taskId: activeTaskId, status: "ACTIVE", health: 95 },
    { taskId: "run-rev-098", status: "APASSED", health: 100 },
    { taskId: "run-rev-097", status: "TAMPERED", health: 42 },
  ];

  return (
    <div className="flex items-center gap-3 bg-[#0d0d0d] border border-[#222] px-3 py-1.5 rounded-sm">
      <div className="flex flex-col">
        <span className="text-[9px] text-[#444] font-black uppercase tracking-widest">Task Monitor</span>
        <select 
          value={activeTaskId}
          onChange={(e) => onTaskChange(e.target.value)}
          className="bg-transparent text-xs font-bold text-cyan-500 border-none outline-none cursor-pointer hover:text-cyan-400 transition-colors"
        >
          {recentRuns.map(r => (
            <option key={r.taskId} value={r.taskId} className="bg-[#0d0d0d]">
              {r.taskId} ({r.status})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};
