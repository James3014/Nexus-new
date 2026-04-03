import React, { useState, useEffect } from 'react';

// 🛡️ [BRIDGE] Safe Multi-Mode Invocation
import { safeInvoke } from "../lib/bridge";

interface SwarmMetrics {
  block_rate: number;
  route_count: number;
  policy_size_mb: number;
  total_decisions: number;
  top_routes: Array<{route: string; usage: number}>;
  weights: Record<string, {base_weight: number; success_rate: number}>;
}

interface EternalStatus {
  offloaded_mb: number;
  total_mb: number;
  anchors_count: number;
  latest_anchor?: string;
  last_updated?: string;
}

const ArmorStatsPanel: React.FC = () => {
  const [metrics, setMetrics] = useState<SwarmMetrics | null>(null);
  const [eternal, setEternal] = useState<EternalStatus>({
    offloaded_mb: 0,
    total_mb: 0,
    anchors_count: 0
  });
  const [cluster, setCluster] = useState<any>(null);
  const [federation, setFederation] = useState<any>(null);
  const [shadow, setShadow] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string>("");

  const fetchMetrics = async () => {
    try {
      // 🛡️ [SAFE] Use abstraction
      const res = await safeInvoke<SwarmMetrics>('swarm_metrics');
      setMetrics(res);
      
      const eternalData = await safeInvoke<any>('eternal_status');
      setEternal(typeof eternalData === 'string' ? JSON.parse(eternalData) : eternalData);

      const clusterData = await safeInvoke<any>('cluster_status');
      setCluster(typeof clusterData === 'string' ? JSON.parse(clusterData) : clusterData);

      const shadowData = await safeInvoke<any>('shadow_status');
      setShadow(typeof shadowData === 'string' ? JSON.parse(shadowData) : shadowData);

      const fedData = await safeInvoke<any>('federation_status');
      setFederation(typeof fedData === 'string' ? JSON.parse(fedData) : fedData);
      
      setErrorMsg(null);
    } catch (error) {
      console.error('Swarm metrics failed:', error);
      setErrorMsg(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (cmd: 'run_cleanup' | 'run_autotune') => {
      setStatusMsg(`Executing ${cmd}...`);
      try {
          // 🛡️ [SAFE] Use abstraction
          const res = await safeInvoke<string>(cmd);
          console.log(res);
          setStatusMsg(`${cmd} completed.`);
          fetchMetrics();
      } catch (e) {
          setStatusMsg(`Error: ${e}`);
          setErrorMsg(`Action Failed: ${e}`);
      }
  };

  if (errorMsg) {
      return (
          <div className="flex flex-col items-center justify-center h-full bg-[#050505] border border-red-900/30 rounded-lg p-10">
              <div className="text-red-500 font-black text-2xl mb-2 tracking-tighter uppercase">Swarm Breach Detected</div>
              <div className="text-[#555] font-mono text-[10px] break-all max-w-md text-center">{errorMsg}</div>
              <button onClick={fetchMetrics} className="mt-6 px-4 py-2 border border-red-500/50 text-red-400 text-[10px] uppercase font-bold hover:bg-red-500/10 transition-all">Retry Link</button>
          </div>
      );
  }

  if (loading || !metrics) {
    return (
        <div className="flex flex-col gap-6 p-4 h-full animate-pulse">
            <div className="h-20 bg-[#111] rounded border border-[#222]" />
            <div className="grid grid-cols-4 gap-4">
                {[1,2,3,4].map(i => <div key={i} className="h-16 bg-[#111] border border-[#222] rounded" />)}
            </div>
            <div className="flex-1 bg-[#111] border border-[#222] rounded" />
        </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 h-full overflow-y-auto custom-scrollbar">
      <div className="flex justify-between items-center bg-[#0a0a0a] border border-[#222] p-4 rounded-lg">
        <div>
          <h2 className="text-xl font-black text-white tracking-widest uppercase flex items-center gap-3">
            <span className="w-2 h-2 bg-blue-500 rounded-full animate-ping" />
            Swarm Intelligence Cockpit
          </h2>
          <p className="text-[10px] text-[#555] mt-1 font-mono uppercase">Production Stability & Route Governance (v22)</p>
        </div>
        <div className={`px-4 py-1 rounded-sm text-[10px] font-black uppercase tracking-tighter ${
          (metrics?.block_rate || 0) < 0.1 ? 'bg-green-900/20 text-green-500 border border-green-500/30' :
          'bg-red-900/20 text-red-500 border border-red-500/30'
        }`}>
          { ((metrics?.block_rate || 0) * 100).toFixed(1) }% Block Rate
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
            { label: "Active Routes", val: metrics?.route_count || 0, unit: "Nodes" },
            { label: "Policy Memory", val: (metrics?.policy_size_mb || 0).toFixed(1), unit: "MB" },
            { label: "Decisions (7d)", val: (metrics?.total_decisions || 0).toLocaleString(), unit: "Count" },
            { label: "Stability Index", val: ((1 - (metrics?.block_rate || 0)) * 100).toFixed(1), unit: "%" }
        ].map((stat, i) => (
            <div key={i} className="bg-[#0a0a0a] border border-[#222] p-4 rounded-md">
                <div className="text-[9px] text-[#555] uppercase font-black tracking-widest">{stat.label}</div>
                <div className="flex items-baseline gap-2 mt-1">
                    <span className="text-2xl font-bold text-white leading-none">{stat.val}</span>
                    <span className="text-[10px] text-[#444] font-mono">{stat.unit}</span>
                </div>
            </div>
        ))}
      </div>

      {/* 🛡️ Federation Status (6A) */}
      {federation && (
        <div className="bg-gradient-to-r from-violet-900/10 to-indigo-900/10 border border-violet-500/20 p-4 rounded-lg">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-[10px] text-violet-400 font-black uppercase tracking-widest flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-pulse" />
              Multi-cluster Federation (SFP v0.1)
            </h3>
            <span className="text-[9px] bg-violet-900/30 text-violet-300 px-2 py-0.5 border border-violet-500/30 rounded uppercase font-mono">
              {federation.peer_clusters?.length || 0} Peers
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-black/20 p-3 rounded border border-white/5">
              <div className="text-xl font-bold text-white tracking-widest">
                {federation.local_cluster?.leader ? "👑 LEADER" : "FOLLOWER"}
              </div>
              <div className="text-[8px] text-violet-300/50 uppercase font-mono mt-1">
                Local Cluster: {federation.local_cluster?.id || "N/A"}
              </div>
            </div>
            <div className="bg-black/20 p-3 rounded border border-white/5">
              <div className="text-sm font-bold text-indigo-400 truncate">
                Global Leader: {federation.global_leader || "Seeking Consensus..."}
              </div>
              <div className="text-[8px] text-indigo-300/50 uppercase font-mono mt-1">
                Active Terms: {federation.current_term || 0} | Load: {federation.total_capacity || 0}%
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-4 flex-1">
        <div className="col-span-12 lg:col-span-7 bg-[#0a0a0a] border border-[#222] p-6 rounded-lg flex flex-col min-h-[400px]">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-[10px] text-[#555] font-black uppercase tracking-widest">🛡️ Swarm Cluster Heatmap (4A)</h3>
            <span className="text-[9px] bg-emerald-900/20 text-emerald-400 px-2 py-0.5 border border-emerald-500/30 rounded uppercase font-mono">
              {cluster?.healthy_nodes || 0}/{cluster?.total_nodes || 0} Healthy
            </span>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 flex-1 overflow-y-auto pr-2 custom-scrollbar">
            {(cluster?.nodes || []).map((node: any) => (
              <div 
                key={node.node_id} 
                className={`p-4 bg-[#0d0d0d] border rounded transition-all hover:bg-[#111] group relative ${
                  node.health === 'HEALTHY' ? 'border-[#222] hover:border-emerald-500/30' : 'border-orange-900/30 opacity-60'
                }`}
              >
                <div className="flex justify-between items-start mb-3">
                   <div className="min-w-0">
                      <div className="text-[9px] text-[#444] font-mono truncate">{node.node_id}</div>
                      <div className="text-xs font-bold text-white mt-1 uppercase tracking-tighter">{node.region}</div>
                   </div>
                   <div className={`w-2 h-2 rounded-full ${node.health === 'HEALTHY' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-orange-500 animate-pulse'}`} />
                </div>
                
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-[8px] text-[#555] uppercase mb-1">
                      <span>CPU Utilization</span>
                      <span className="text-emerald-400">{node.cpu_percent}%</span>
                    </div>
                    <div className="h-1 bg-black rounded-full overflow-hidden">
                       <div className="h-full bg-emerald-500 transition-all duration-1000" style={{ width: `${node.cpu_percent}%` }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-[8px] text-[#555] uppercase mb-1">
                      <span>Memory Load</span>
                      <span className="text-blue-400">{node.memory_percent}%</span>
                    </div>
                    <div className="h-1 bg-black rounded-full overflow-hidden">
                       <div className="h-full bg-blue-500 transition-all duration-1000" style={{ width: `${node.memory_percent}%` }} />
                    </div>
                  </div>
                </div>
                
                <div className="mt-3 pt-3 border-t border-[#1a1a1a] flex justify-between items-center">
                   <div className="text-[8px] text-[#444] font-mono">Tasks: {node.active_tasks}</div>
                   <div className="text-[8px] text-[#444] font-mono">Liveness: {Math.max(0, Math.floor(Date.now()/1000 - node.last_seen_unix))}s</div>
                </div>
              </div>
            ))}
            {!cluster?.nodes?.length && (
              <div className="col-span-full flex flex-col items-center justify-center text-[#333] border-2 border-dashed border-[#111] rounded-xl h-40">
                <div className="text-2xl font-black mb-1">NO NODES</div>
                <div className="text-[9px] font-mono">Awaiting gRPC Heartbeat...</div>
              </div>
            )}
          </div>
        </div>
        
        <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">
          {/* 🛡️ Shadow Audit Monitor (4B) */}
          <div className={`bg-[#0a0a0a] border p-6 rounded-lg flex flex-col ${
             shadow?.status === 'DEGRADED' ? 'border-orange-500/50' : 'border-[#222]'
          }`}>
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${shadow?.status === 'DEGRADED' ? 'bg-orange-500 animate-pulse' : 'bg-emerald-500'}`} />
                <h3 className="text-[10px] text-zinc-300 font-black uppercase tracking-widest">👁️ Shadow Audit Pipeline (4B)</h3>
              </div>
              <div className="text-[8px] bg-white/5 text-zinc-500 border border-white/10 px-1.5 py-0.5 rounded uppercase font-mono">
                {shadow?.status || 'HEALTHY'}
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-4">
               <div className="bg-black/40 border border-[#1a1a1a] p-3 rounded">
                  <div className="text-xl font-bold text-white">{shadow?.total_runs || 0}</div>
                  <div className="text-[8px] text-[#555] uppercase font-black">Total Audits</div>
               </div>
               <div className="bg-black/40 border border-[#1a1a1a] p-3 rounded text-right">
                  <div className="text-xl font-bold text-red-500 font-mono">
                    {shadow?.total_runs > 0 ? ((shadow.false_positive_count / shadow.total_runs) * 100).toFixed(1) : '0.0'}%
                  </div>
                  <div className="text-[8px] text-[#555] uppercase font-black">FP Rate</div>
               </div>
            </div>

            <div className="flex justify-between text-[8px] text-[#444] font-mono mb-4 px-1">
               <span>Avg Latency: {shadow?.avg_latency_ms || 0}ms</span>
               <span className="text-emerald-500">Whitelist: {shadow?.whitelist?.length || 0}</span>
            </div>
            
            <div className="p-3 bg-white/5 border border-white/10 rounded flex items-center gap-3">
               <div className="flex-1 text-[9px] text-zinc-400 font-mono italic truncate">
                  {shadow?.last_updated ? `Latest: ${new Date(shadow.last_updated).toLocaleTimeString()}` : "Waiting for PR trigger..."}
               </div>
            </div>
          </div>

          {/* 🏆 Eternal Memory Card */}
          <div className="bg-[#0a0a0a] border border-[#222] p-6 rounded-lg flex flex-col flex-1">
            <h3 className="text-[10px] text-[#555] font-black uppercase tracking-widest mb-4">🏆 Eternal Memory (Arweave)</h3>
            
            <div className="flex-1 flex flex-col justify-center space-y-6">
              <div className="grid grid-cols-2 gap-4">
                 <div>
                    <div className="text-3xl font-bold text-white font-mono tracking-tighter">{eternal.offloaded_mb.toFixed(1)}</div>
                    <div className="text-[9px] text-purple-400 font-black uppercase tracking-widest">MB Offloaded</div>
                 </div>
                 <div>
                    <div className="text-3xl font-bold text-white font-mono tracking-tighter">{eternal.anchors_count}</div>
                    <div className="text-[9px] text-purple-400 font-black uppercase tracking-widest">Anchors (TX)</div>
                 </div>
              </div>

              <div className="space-y-1.5">
                 <div className="flex justify-between text-[8px] font-black text-[#444] uppercase tracking-widest">
                    <span>Persistence Progress</span>
                    <span>{((eternal.offloaded_mb / (eternal.total_mb || 100)) * 100).toFixed(1)}%</span>
                 </div>
                 <div className="h-1.5 bg-black border border-[#1a1a1a] rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 shadow-[0_0_10px_rgba(139,92,246,0.5)]" 
                         style={{ width: `${(eternal.offloaded_mb / (eternal.total_mb || 100)) * 100}%` }} />
                 </div>
              </div>

              {eternal.latest_anchor && (
                 <div className="bg-[#0d0d12] border border-purple-900/30 p-4 rounded flex items-center justify-between group/anchor">
                    <div className="min-w-0">
                       <div className="text-[8px] text-purple-400 font-black uppercase mb-1">Latest Anchor Link</div>
                       <code className="text-[11px] text-zinc-400 font-mono truncate block">{eternal.latest_anchor}</code>
                    </div>
                    <button 
                      onClick={() => safeInvoke("eternal_download", { txid: eternal.latest_anchor })}
                      className="px-3 py-1.5 bg-purple-900/20 border border-purple-500/40 text-[10px] text-white font-black hover:bg-purple-600 hover:text-white transition-all uppercase"
                    >
                      Pull
                    </button>
                 </div>
              )}
            </div>
            
            <div className="mt-6 flex items-center gap-2">
               <div className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse" />
               <span className="text-[9px] text-[#444] font-mono uppercase">Node: https://arweave.net</span>
            </div>
          </div>
        </div>
      </div>
      
      <div className="bg-[#0a0a0a] border border-[#222] p-4 rounded-lg">
        <div className="flex justify-between items-center mb-4">
            <h3 className="text-[10px] text-[#555] font-black uppercase tracking-widest">⚙️ Swarm Maintenance Ops</h3>
            <span className="text-[9px] text-blue-500 font-mono animate-pulse uppercase">{statusMsg}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-white">
          <button onClick={() => handleAction('run_cleanup')} className="bg-[#0d0d0d] border border-[#222] hover:bg-[#111] hover:border-blue-500/50 text-[#888] hover:text-white py-2 px-4 rounded font-mono text-[10px] uppercase transition-all tracking-widest">
            🧹 Cleanup_Policy
          </button>
          <button onClick={() => handleAction('run_autotune')} className="bg-[#0d0d0d] border border-[#222] hover:bg-[#111] hover:border-emerald-500/50 text-[#888] hover:text-white py-2 px-4 rounded font-mono text-[10px] uppercase transition-all tracking-widest">
            🧠 Autotune_Weights
          </button>
          <button onClick={fetchMetrics} className="bg-[#0d0d0d] border border-[#222] hover:bg-[#111] hover:border-purple-500/50 text-[#888] hover:text-white py-2 px-4 rounded font-mono text-[10px] uppercase transition-all tracking-widest">
            📊 Sync_Scrutiny
          </button>
        </div>
      </div>
    </div>
  );
};

export default ArmorStatsPanel;
