import { useEffect, useRef } from "react"
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal as TerminalIcon, Sparkles } from 'lucide-react'
import 'xterm/css/xterm.css'

export const TerminalPane = () => {
  const termRef = useRef<HTMLDivElement>(null)
  const term = useRef<Terminal | undefined>(undefined)

  useEffect(() => {
    if (!termRef.current) return

    // 初始化 xterm.js
    term.current = new Terminal({
      cursorBlink: true,
      cursorStyle: 'bar',
      fontSize: 13,
      fontFamily: '"Fira Code", monospace',
      theme: {
        background: '#0a0c10',
        foreground: '#e2e8f0',
        cursor: '#22d3ee',
        selectionBackground: 'rgba(34, 211, 238, 0.3)',
        cyan: '#22d3ee',
        green: '#10b981',
        blue: '#3b82f6',
        magenta: '#a855f7'
      }
    })

    const fitAddon = new FitAddon()
    term.current.loadAddon(fitAddon)
    term.current.open(termRef.current)
    fitAddon.fit()

    // 啟動歡迎詞 (中文)
    term.current.writeln('\x1b[1;36m[NEXUS COCKPIT v0.1 CONNECTED]\x1b[0m')
    term.current.writeln('\x1b[32m>> 指揮艙終端已就緒，等待指令對位...\x1b[0m')
    term.current.writeln('')

    const handleResize = () => fitAddon.fit()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      term.current?.dispose()
    }
  }, [])

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
      <div className="flex items-center justify-between px-5 py-3 bg-slate-800/40 border-b border-slate-800">
        <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs uppercase tracking-widest">
          <TerminalIcon size={14} /> Output Stream / 輸出串流
        </div>
        <div className="flex items-center gap-2 text-slate-500">
            <Sparkles size={14} className="animate-spin-slow" />
            <span className="text-[10px] font-mono">STATUS: SYNCED</span>
        </div>
      </div>
      
      <div className="flex-1 p-4 relative group">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/30 pointer-events-none" />
          <div ref={termRef} className="h-full w-full xterm-container" />
      </div>
    </div>
  )
}
