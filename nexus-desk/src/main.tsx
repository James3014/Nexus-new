import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";

/**
 * 🛡️ Global Error Boundary
 * Catching all React root-level crashes for the Nexus Cockpit.
 */
class GlobalErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: any}> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("Critical Render Failure:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen bg-black flex items-center justify-center p-10 font-mono">
          <div className="max-w-2xl w-full border border-red-500/50 bg-[#0a0505] p-8 shadow-[0_0_50px_rgba(239,68,68,0.2)]">
            <h1 className="text-red-500 text-2xl font-black uppercase tracking-widest mb-4">Nexus System Panic</h1>
            <p className="text-red-300 text-sm mb-6 leading-relaxed">
              A root-level exception occurred in the Nexus Desk. The cockpit has been locked to prevent governance drift.
            </p>
            <div className="bg-black/50 p-4 border border-red-500/20 text-red-400 text-[10px] break-all mb-8 overflow-y-auto max-h-40">
              {this.state.error?.toString() || "Unknown Interrupt"}
            </div>
            <div className="flex gap-4">
                <button 
                    onClick={() => window.location.reload()} 
                    className="flex-1 py-3 border border-red-500/50 text-red-500 hover:bg-red-500/10 uppercase font-black text-xs transition-all"
                >
                    Hard Reboot
                </button>
                <button 
                    onClick={() => window.location.href = "/"} 
                    className="flex-1 py-3 bg-red-500/10 border border-red-500/50 text-red-400 hover:bg-red-500/20 uppercase font-black text-xs transition-all"
                >
                    Clear State
                </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <GlobalErrorBoundary>
      <App />
    </GlobalErrorBoundary>
  </React.StrictMode>,
);
