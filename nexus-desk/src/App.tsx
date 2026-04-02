import { ArmorHUD } from './components/ArmorHUD'
import { TerminalPane } from './components/TerminalPane'
import { Activity, Cpu, LayoutIcon } from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'

// 模擬遙測數據 (Phase 2 將對接實體 API)
const data = [
  { time: '00:00', load: 30, intent: 45 },
  { time: '04:00', load: 45, intent: 52 },
  { time: '08:00', load: 38, intent: 48 },
  { time: '12:00', load: 65, intent: 75 },
  { time: '16:00', load: 55, intent: 68 },
  { time: '20:00', load: 42, intent: 55 },
  { time: '24:00', load: 35, intent: 48 }
]

function App() {
  return (
    <div className="flex flex-col h-screen bg-black text-cyan-50 font-sans overflow-hidden">
      {/* 頂部戰術 HUD */}
      <ArmorHUD />

      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0 overflow-hidden">
        
        {/* 左側與中央: 終端面板 (佔據 8 欄位) */}
        <section className="lg:col-span-8 flex flex-col min-h-0 gap-4">
           <TerminalPane />
           
           <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl flex items-center justify-between shadow-lg">
              <div className="flex items-center gap-3">
                 <div className="w-10 h-10 bg-cyan-500/10 rounded-lg flex items-center justify-center">
                    <Activity className="w-5 h-5 text-cyan-400" />
                 </div>
                 <div>
                    <h3 className="text-sm font-bold uppercase tracking-widest text-cyan-500/80">系統指令集 (Palette)</h3>
                    <p className="text-[10px] text-slate-500 font-mono">[ALT+P] 調用全域指令功能</p>
                 </div>
              </div>
              <div className="flex gap-2">
                 {['benchmark', 'audit', 'release'].map(cmd => (
                   <button key={cmd} className="px-3 py-1.5 bg-slate-800 hover:bg-cyan-500/20 border border-slate-700 hover:border-cyan-500/50 rounded-md text-[10px] font-mono uppercase tracking-tighter transition-all">
                     {cmd}
                   </button>
                 ))}
              </div>
           </div>
        </section>

        {/* 右側: 遙測與狀態列 (佔據 4 欄位) */}
        <section className="lg:col-span-4 flex flex-col gap-6 overflow-y-auto no-scrollbar pb-6">
           
           {/* GPU / M4 狀態卡片 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-900/60 p-5 rounded-2xl border border-slate-800 group hover:border-cyan-500/30 transition-all">
              <div className="flex justify-between items-start mb-4">
                <Cpu className="text-cyan-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(34,211,238,0.8)]" />
                <span className="bg-cyan-500/10 text-cyan-400 text-[10px] font-mono px-2 py-0.5 rounded border border-cyan-500/20 uppercase">M4 Max</span>
              </div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono">Neural Inference</p>
              <div className="flex items-baseline gap-2">
                <p className="text-2xl font-bold font-mono tracking-wider">13.4 <span className="text-xs font-normal">GB</span></p>
              </div>
            </div>

            <div className="bg-slate-900/60 p-5 rounded-2xl border border-slate-800 group hover:border-purple-500/30 transition-all">
              <div className="flex justify-between items-start mb-4">
                <Activity className="text-purple-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(168,85,247,0.8)]" />
                <span className="bg-purple-500/10 text-purple-400 text-[10px] font-mono px-2 py-0.5 rounded border border-purple-500/20 uppercase">Core</span>
              </div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono">Active Links</p>
              <p className="text-2xl font-bold font-mono tracking-wider">8082</p>
            </div>
          </div>

          {/* 遙測圖表 */}
          <div className="flex-1 min-h-[300px] bg-slate-900/40 border border-slate-800 rounded-2xl p-6 flex flex-col shadow-2xl">
            <div className="flex justify-between items-center mb-6">
               <h3 className="text-sm font-bold tracking-widest uppercase flex items-center gap-2">
                  <LayoutIcon size={16} className="text-cyan-400" /> Neural Telemetry
               </h3>
               <div className="px-2 py-0.5 bg-cyan-500/20 rounded text-[10px] text-cyan-400 border border-cyan-500/30 font-mono tracking-widest">LIVE</div>
            </div>
            
            <div className="flex-1 w-full mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorLoad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#22d3ee" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} opacity={0.3} />
                  <XAxis dataKey="time" stroke="#475569" tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#475569" tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', color: '#f1f5f9', fontSize: '12px' }} />
                  <Area type="monotone" dataKey="load" stroke="#22d3ee" strokeWidth={3} fillOpacity={1} fill="url(#colorLoad)" animationDuration={2000} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            
            <div className="mt-4 flex flex-wrap gap-4 justify-center">
               <div className="flex items-center gap-1.5 text-[10px] font-mono tracking-widest text-cyan-400 uppercase">
                  <span className="w-2 h-2 bg-cyan-400 rounded-sm shadow-[0_0_5px_rgba(34,211,238,0.5)]"></span> GPU Load %
               </div>
            </div>
          </div>

        </section>
      </main>

      {/* 底部裝飾條 */}
      <footer className="px-6 py-2 bg-slate-900/80 border-t border-slate-800 flex justify-between items-center text-[9px] font-mono text-slate-600 tracking-tighter uppercase">
         <div className="flex gap-4">
            <span>NEXUS-DESK v0.2.0-HUD-READY</span>
            <span>OS-IDENTITY: VERIFIED</span>
         </div>
         <div className="flex items-center gap-3">
            <span className="flex items-center gap-1"><span className="w-1 h-1 bg-green-500 rounded-full"></span> LINK-CORE: OK</span>
            <span className="flex items-center gap-1"><span className="w-1 h-1 bg-blue-500 rounded-full"></span> AGENT-UCC: SYNCED</span>
         </div>
      </footer>
    </div>
  )
}

export default App
