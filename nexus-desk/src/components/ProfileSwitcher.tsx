import React, { useState } from 'react';
import { safeInvoke } from '../lib/bridge';

interface Props {
  currentProfile: string;
  onProfileChange: (name: string) => void;
}

export const ProfileSwitcher: React.FC<Props> = ({ currentProfile, onProfileChange }) => {
  const [profiles] = useState<string[]>(["prod", "high", "full", "standard", "quick"]);
  const [isApplying, setIsApplying] = useState(false);

  const handleSwitch = async (name: string) => {
    setIsApplying(true);
    try {
      await safeInvoke("apply_profile", { name });
      onProfileChange(name);
    } catch (e) {
      alert(`Drift Detected or Apply Failed: ${e}`);
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div className="flex items-center gap-3 bg-[#0d0d0d] border border-[#222] px-3 py-1.5 rounded-sm">
      <div className="flex flex-col">
        <span className="text-[9px] text-[#444] font-black uppercase tracking-widest">Active Armor</span>
        <select 
          value={currentProfile}
          onChange={(e) => handleSwitch(e.target.value)}
          disabled={isApplying}
          className="bg-transparent text-xs font-bold text-white border-none outline-none cursor-pointer hover:text-blue-400 transition-colors"
        >
          {profiles.map(p => (
            <option key={p} value={p} className="bg-[#0d0d0d]">{p}</option>
          ))}
        </select>
      </div>
      {isApplying && <div className="w-2 h-2 bg-blue-500 rounded-full animate-ping" />}
    </div>
  );
};
