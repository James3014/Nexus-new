import React from 'react';

interface Props {
  isVisible: boolean;
  message: string;
  reason?: string;
}

export const CriticalBanner: React.FC<Props> = ({ isVisible, message, reason }) => {
  if (!isVisible) return null;

  return (
    <div className="bg-red-900/90 border-b border-red-500 p-2 flex items-center justify-center gap-4 animate-pulse">
      <div className="flex items-center gap-2">
        <span className="text-xl">⚠️</span>
        <span className="text-sm font-black text-white uppercase tracking-widest">
          SYSTEM RESTRICTED: {message}
        </span>
      </div>
      {reason && (
        <div className="bg-black/40 px-2 py-0.5 rounded border border-red-500/50">
          <span className="text-[10px] text-red-300 font-mono">
            {reason}
          </span>
        </div>
      )}
      <div className="text-[10px] text-red-200/60 font-bold uppercase underline">
        Manual Review Required
      </div>
    </div>
  );
};
