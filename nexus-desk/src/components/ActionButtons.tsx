import React from 'react';
import { AvailableActions } from '../types/DeskViewModel';

interface Props {
  actions: AvailableActions;
  isLocked: boolean;
  onAction: (cmd: string) => void;
  lockReason?: string;
}

export const ActionButtons: React.FC<Props> = ({ actions, isLocked, onAction, lockReason }) => {
  const Button = ({ label, cmd, active, primary }: { label: string; cmd: string; active: boolean; primary?: boolean }) => {
    const disabled = isLocked || !active;
    const title = isLocked ? `Locked: ${lockReason}` : !active ? "待先決條件完成" : "";

    return (
      <button
        onClick={() => onAction(cmd)}
        disabled={disabled}
        title={title}
        className={`flex-1 px-4 py-2 text-xs font-bold transition-all border rounded-sm flex items-center justify-center gap-2 group whitespace-nowrap
          ${disabled 
            ? 'opacity-20 cursor-not-allowed border-[#333] text-[#666] bg-transparent' 
            : primary 
              ? 'bg-blue-600 border-blue-400 text-white hover:bg-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.4)]'
              : 'bg-[#111] border-[#333] text-[#aaa] hover:border-[#666] hover:text-white'
          }`}
      >
        <span className="font-mono opacity-50 text-[10px] truncate group-hover:opacity-100">nexus-{cmd}</span>
        <span className="font-sans uppercase tracking-widest">{label}</span>
      </button>
    );
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Button label="效能測試" cmd="benchmark" active={actions.benchmark} />
      <Button label="執行稽核" cmd="acceptance-check" active={actions.acceptanceCheck} />
      <Button label="發布就緒" cmd="release-ready" active={actions.releaseReady} />
      <Button label="正式發布" cmd="publish" active={actions.publish} primary />
    </div>
  );
};
