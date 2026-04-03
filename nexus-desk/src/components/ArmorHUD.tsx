import { useEffect, useState } from 'react'
import { Shield, AlertCircle, CheckCircle2 } from 'lucide-react'
import { safeInvoke } from '../lib/bridge'

interface Identity {
  armor: string
  sha: string
  acceptance: any
  timestamp: string
}

export const ArmorHUD = () => {
  const [identity, setIdentity] = useState<Identity | null>(null)

  const fetchIdentity = async () => {
    try {
      const data: Identity = await safeInvoke('get_nexus_identity')
      setIdentity(data)
    } catch (error) {
      console.error('HUD 偵測失敗:', error)
    }
  }

  useEffect(() => {
    fetchIdentity()
    const interval = setInterval(fetchIdentity, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex items-center justify-between p-5 bg-gradient-to-r from-cyan-950/40 via-purple-950/40 to-cyan-950/40 
                    backdrop-blur-xl border-b-2 border-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.15)] text-white">
      <div className="flex items-center gap-5">
        <div className="relative group">
          <div className="absolute inset-0 bg-cyan-500 rounded-xl blur opacity-25 group-hover:opacity-50 transition-opacity"></div>
          <div className="relative w-14 h-14 bg-slate-900 border border-cyan-500/50 rounded-xl flex items-center justify-center">
            <Shield className="w-8 h-8 text-cyan-400 group-hover:drop-shadow-[0_0_10px_rgba(34,211,238,0.8)]" />
          </div>
        </div>
        
        <div className="space-y-0.5">
          <div className="text-2xl font-bold tracking-tighter text-cyan-50 drop-shadow-sm">
            {identity?.armor || '偵測核心中...'}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded border border-cyan-500/30 uppercase tracking-widest font-bold">SHA link</span>
            <span className="text-xs font-mono text-cyan-500/70">{identity?.sha || '--------'}</span>
          </div>
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        {(identity?.acceptance?.status === 'PASSED' || identity?.acceptance?.status === 'PASS') ? (
          <div className="flex items-center gap-3 bg-emerald-500/10 px-6 py-2.5 rounded-full border border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.1)] transition-all">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <span className="text-sm font-bold text-emerald-100 tracking-wide">✅ 治理門檻通過</span>
          </div>
        ) : (
          <div className="flex items-center gap-3 bg-amber-500/10 px-6 py-2.5 rounded-full border border-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.1)] animate-pulse">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            <span className="text-sm font-bold text-amber-100 tracking-wide">
              {identity?.acceptance?.status === 'NO_REPORT' ? '待稽核' : '⚠️ 門檻未通過'}
            </span>
          </div>
        )}
        
        <div className="flex items-center gap-2 pl-4 border-l border-slate-800">
           <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Local-Time</p>
           <p className="text-lg font-mono text-cyan-400 font-bold">{identity?.timestamp || '00:00:00'}</p>
        </div>
      </div>
    </div>
  )
}
