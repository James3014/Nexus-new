import { useState, useEffect } from 'react';
import { safeInvoke } from '../lib/bridge';

interface Annotation {
  id: string;
  targetType: string;
  targetRefJson: string;
  severity: string;
  status: string;
  author: string;
  body: string;
  createdAt: string;
}

interface Props {
  taskId: string;
  onAddAnnotation: (body: string, severity: string) => void;
}

export const ReviewSidebar: React.FC<Props> = ({ taskId, onAddAnnotation }) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [newBody, setNewBody] = useState('');
  const [severity, setSeverity] = useState('MEDIUM');

  const fetchAnnotations = async () => {
    if (taskId) {
      try {
        const res = await safeInvoke<Annotation[]>('list_annotations', { taskId });
        setAnnotations(res);
      } catch (e) {
        console.error(e);
      }
    }
  };

  useEffect(() => {
    fetchAnnotations();
  }, [taskId]);

  const handleSubmit = async () => {
    if (!newBody.trim()) return;
    onAddAnnotation(newBody, severity);
    setNewBody('');
    setTimeout(fetchAnnotations, 500); // Poll for update
  };

  return (
    <aside className="w-full h-full flex flex-col bg-[#080808] border-l border-[#1a1a1a] shadow-inner">
      <div className="p-4 border-b border-[#1a1a1a] bg-[#0c0c0c] flex justify-between items-center">
        <span className="text-[10px] font-black text-[#555] uppercase tracking-widest">Review Annotations</span>
        <div className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar">
        {annotations.map(a => (
          <div key={a.id} className="bg-[#121212] border border-[#222] p-3 rounded-sm group hover:border-amber-500/30 transition-all">
            <div className="flex justify-between items-center mb-2">
              <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-sm ${
                a.severity === 'HIGH' ? 'bg-red-900/20 text-red-500' : 'bg-amber-900/20 text-amber-500'
              }`}>
                {a.severity}
              </span>
              <span className="text-[8px] text-[#444] font-mono">{a.author} · {new Date(a.createdAt).toLocaleDateString()}</span>
            </div>
            <div className="text-[11px] text-[#bbb] leading-relaxed mb-2">{a.body}</div>
            <div className="flex items-center gap-2">
              <div className="w-1 h-1 bg-emerald-500 rounded-full" />
              <span className="text-[9px] text-emerald-500 font-bold uppercase tracking-tighter">{a.status}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 bg-[#0c0c0c] border-t border-[#1a1a1a]">
        <textarea 
          placeholder="Enter review note..."
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          className="w-full h-24 bg-black border border-[#222] rounded-sm p-3 text-xs text-white focus:border-amber-500/50 transition-all outline-none resize-none mb-3"
        />
        <div className="flex items-center gap-3">
          <select 
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            className="flex-1 bg-black border border-[#222] text-[10px] p-2 text-[#888] outline-none"
          >
            <option value="LOW">LOW RISK</option>
            <option value="MEDIUM">MEDIUM RISK</option>
            <option value="HIGH">CRITICAL ALERT</option>
          </select>
          <button 
            onClick={handleSubmit}
            className="px-4 py-2 bg-amber-600 text-white text-[10px] font-black uppercase hover:bg-amber-500 transition-all"
          >
            Post Annotation
          </button>
        </div>
      </div>
    </aside>
  );
};
