import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { 
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area
} from 'recharts';
import { Activity, Shield, Brain, Terminal, Play, Cpu, Zap, Radio } from 'lucide-react';

const data = [
  { time: '00:00', load: 12, intent: 98 }, { time: '00:05', load: 45, intent: 95 },
  { time: '00:10', load: 92, intent: 90 }, { time: '00:15', load: 85, intent: 95 },
  { time: '00:20', load: 30, intent: 99 }, { time: '00:25', load: 15, intent: 100 },
];

function App() {
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [systemTime, setSystemTime] = useState("");

  useEffect(() => {
    const timer = setInterval(() => {
      const d = new Date();
      setSystemTime(`${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')} ${d.getMilliseconds().toString().padStart(3, '0')}`);
    }, 47);
    return () => clearInterval(timer);
  }, []);

  async function handleRunTask() {
    setLoading(true);
    try {
      const res = await invoke("run_nexus", { task: "status" });
      setOutput(res as string);
    } catch (e) {
      setOutput("Error: " + e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto min-h-screen flex flex-col gap-6 text-cyan-50 hud-font selection:bg-cyan-500/30">
      
      {/* HUD Header */}
      <header className="flex items-center justify-between border-b border-cyan-900/50 pb-4">
        <div className="flex items-center gap-4">
          <div className="bg-cyan-500 w-12 h-12 rounded-lg flex items-center justify-center animate-[pulse-glow_4s_ease-in-out_infinite]">
            <Brain size={28} className="text-black" />
          </div>
          <div>
            <h1 className="text-3xl font-black tracking-widest bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-600">NEXUS SINGULARITY</h1>
            <p className="text-cyan-500/70 font-mono tracking-widest text-sm flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              SYS.OS.v100.ONLINE
            </p>
          </div>
        </div>
        <div className="text-right font-mono text-cyan-400/80">
          <p className="text-xl tracking-wider">{systemTime}</p>
          <p className="text-xs uppercase tracking-[0.2em] opacity-50">Local Coordinate</p>
        </div>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glow-panel p-5 flex flex-col justify-between group">
          <div className="flex justify-between items-start mb-4">
            <Brain className="text-cyan-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(34,211,238,0.8)] transition-all" />
            <span className="bg-cyan-950/50 text-cyan-400 text-[10px] uppercase font-mono px-2 py-1 rounded border border-cyan-800">Primary</span>
          </div>
          <div>
            <p className="text-xs text-cyan-500/70 uppercase tracking-widest font-mono mb-1">Brain Core</p>
            <p className="text-2xl font-bold tracking-wider text-white">27B.Q3</p>
          </div>
        </div>

        <div className="glow-panel p-5 flex flex-col justify-between group">
          <div className="flex justify-between items-start mb-4">
            <Shield className="text-purple-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(192,132,252,0.8)] transition-all" />
            <span className="bg-purple-950/50 text-purple-400 text-[10px] uppercase font-mono px-2 py-1 rounded border border-purple-800">Neural</span>
          </div>
          <div>
            <p className="text-xs text-cyan-500/70 uppercase tracking-widest font-mono mb-1">Sentinel</p>
            <p className="text-2xl font-bold tracking-wider text-white">0.5B</p>
          </div>
        </div>

        <div className="glow-panel p-5 flex flex-col justify-between group">
          <div className="flex justify-between items-start mb-4">
            <Cpu className="text-blue-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(96,165,250,0.8)] transition-all" />
            <span className="bg-blue-950/50 text-blue-400 text-[10px] uppercase font-mono px-2 py-1 rounded border border-blue-800">M4 SOC</span>
          </div>
          <div>
            <p className="text-xs text-cyan-500/70 uppercase tracking-widest font-mono mb-1">V-RAM Load</p>
            <div className="flex items-baseline gap-2">
              <p className="text-2xl font-bold tracking-wider text-white">13.4</p>
              <p className="text-sm text-cyan-500 font-mono">GB</p>
            </div>
          </div>
        </div>

        <div className="glow-panel p-5 flex flex-col justify-between group">
          <div className="flex justify-between items-start mb-4">
            <Zap className="text-green-400 w-6 h-6 group-hover:drop-shadow-[0_0_10px_rgba(74,222,128,0.8)] transition-all" />
            <span className="bg-green-950/50 text-green-400 text-[10px] uppercase font-mono px-2 py-1 rounded border border-green-800">Active</span>
          </div>
          <div>
            <p className="text-xs text-cyan-500/70 uppercase tracking-widest font-mono mb-1">Ports</p>
            <p className="text-2xl font-bold tracking-wider text-white font-mono">8080/8082</p>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
        
        {/* Left Column - Console */}
        <div className="lg:col-span-1 flex flex-col gap-4">
          <div className="glow-panel p-1 flex-1 flex flex-col">
            <div className="bg-cyan-950/30 px-4 py-3 border-b border-cyan-900/50 flex justify-between items-center rounded-t-2xl">
              <div className="flex items-center gap-2 text-cyan-400 font-mono tracking-widest text-xs uppercase">
                <Terminal size={14}/> Output Stream
              </div>
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/80"></div>
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80"></div>
                <div className="w-2.5 h-2.5 rounded-full bg-green-500/80"></div>
              </div>
            </div>
            <div className="flex-1 p-4 font-mono text-sm overflow-y-auto relative">
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/50 pointer-events-none" />
              <div className="space-y-2 relative z-10">
                <p className="text-cyan-500/50">Nexus ~ % initialize_link</p>
                <p className="text-green-400">{'[OK] Connection to core established.'}</p>
                <p className="text-cyan-500/50">Nexus ~ % listen_hologram</p>
                <pre className="text-cyan-300 whitespace-pre-wrap break-words">
                  {output || ">> WAITING FOR DIRECTIVE..."}
                  <span className="animate-pulse">_</span>
                </pre>
              </div>
            </div>
          </div>
          <button 
            onClick={handleRunTask} 
            disabled={loading} 
            className="hud-button flex items-center justify-center gap-3 w-full group relative"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 opacity-0 group-hover:opacity-100 transition-opacity"></div>
            {loading ? (
              <Radio size={18} className="animate-spin text-cyan-300" />
            ) : (
              <Play size={18} className="group-hover:translate-x-1 transition-transform" />
            )}
            {loading ? "EXECUTING SYNC..." : "INITIATE DIAGNOSTIC"}
          </button>
        </div>

        {/* Right Column - Timeline Chart */}
        <div className="lg:col-span-2 glow-panel p-6 flex flex-col">
          <div className="flex justify-between items-center mb-8">
            <div>
              <h2 className="text-xl font-bold tracking-widest text-cyan-50 flex items-center gap-3">
                <Activity size={22} className="text-cyan-400"/> NEURAL TELEMETRY
              </h2>
              <p className="text-xs text-cyan-500/60 font-mono tracking-widest mt-1 uppercase">Real-time Intent vs Load Analysis</p>
            </div>
            <div className="px-3 py-1.5 border border-cyan-800 bg-cyan-950/30 rounded text-xs font-mono text-cyan-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]"></span>
              LIVE
            </div>
          </div>
          
          <div className="flex-1 min-h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorLoad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorIntent" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#c084fc" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#c084fc" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#164e63" vertical={false} opacity={0.5} />
                <XAxis dataKey="time" stroke="#0891b2" tick={{ fill: '#0891b2', fontSize: 12, fontFamily: 'monospace' }} axisLine={false} tickLine={false} /> 
                <YAxis stroke="#0891b2" tick={{ fill: '#0891b2', fontSize: 12, fontFamily: 'monospace' }} axisLine={false} tickLine={false} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'rgba(8, 20, 33, 0.9)', 
                    border: '1px solid rgba(8, 145, 178, 0.5)',
                    backdropFilter: 'blur(8px)',
                    borderRadius: '8px',
                    color: '#cffafe',
                    fontFamily: 'monospace'
                  }} 
                  itemStyle={{ color: '#22d3ee' }}
                />
                <Area type="monotone" dataKey="load" stroke="#22d3ee" strokeWidth={2} fillOpacity={1} fill="url(#colorLoad)" />
                <Area type="monotone" dataKey="intent" stroke="#c084fc" strokeWidth={2} fillOpacity={1} fill="url(#colorIntent)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-6 mt-4 justify-center">
            <div className="flex items-center gap-2 text-xs font-mono tracking-widest text-cyan-400">
              <span className="w-3 h-3 bg-cyan-400 rounded-sm"></span> GPU Load %
            </div>
            <div className="flex items-center gap-2 text-xs font-mono tracking-widest text-purple-400">
              <span className="w-3 h-3 bg-purple-400 rounded-sm"></span> Intent Safety (GBNF)
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
