import React, { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { invoke } from '@tauri-apps/api/core';

interface Props {
  taskId: string;
}

export const DiffViewer: React.FC<Props> = ({ taskId }) => {
  const [diff, setDiff] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const fetchDiff = async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const res = await invoke<string>('get_worktree_diff', { taskId });
      setDiff(res || "NO_CHANGES_DETECTED");
    } catch (e) {
      setDiff(`DIFF_ERROR: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDiff();
  }, [taskId]);

  return (
    <div className="flex flex-col bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm overflow-hidden shadow-2xl h-full">
      <div className="bg-[#0f0f0f] p-2 border-b border-[#1a1a1a] flex justify-between items-center px-4">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
          <span className="text-[10px] font-bold text-[#555] uppercase tracking-widest">Worktree Diff</span>
        </div>
        <button 
          onClick={fetchDiff}
          className="text-[9px] text-cyan-500 hover:text-white uppercase font-bold transition-colors"
        >
          Refresh
        </button>
      </div>
      
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          defaultLanguage="diff"
          value={diff}
          theme="vs-dark"
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 12,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            padding: { top: 10 }
          }}
        />
      </div>
      
      {loading && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center backdrop-blur-sm z-30">
          <div className="text-[10px] font-mono text-emerald-500 animate-pulse">GENERATING_DIFF...</div>
        </div>
      )}
    </div>
  );
};
