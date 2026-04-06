import React from 'react';
import { Terminal, Cpu, Zap, Activity, Info } from 'lucide-react';

interface ThinkingRecord {
  timestamp: string;
  action: string;
  confidence: number;
  explanation: string;
  thinking: string;
}

interface ThinkingTerminalProps {
  history: ThinkingRecord[];
}

export const ThinkingTerminal: React.FC<ThinkingTerminalProps> = ({ history }) => {
  const reversed = [...history].reverse();

  return (
    <div className="bg-[#0a0c11] border border-[#1e222d] rounded-lg overflow-hidden flex flex-col h-full min-h-[400px] shadow-2xl">
      <div className="px-4 py-3 bg-[#1c222e] border-b border-[#1e222d] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Terminal size={16} className="text-blue-500" />
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-400">Tactical Thinking Log</h3>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shadow-lg shadow-blue-500/50" />
          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">REALTIME STREAM</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-hide font-mono text-[11px] leading-relaxed">
        {reversed.length > 0 ? (
          reversed.map((record, i) => (
            <div key={i} className="animate-in fade-in slide-in-from-bottom-2 duration-500 border-l-2 border-[#1e222d] pl-4 hover:border-blue-500/30 transition-all">
              <div className="flex items-center gap-3 mb-2">
                <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter ${
                  record.action === 'BUY' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                  record.action === 'SELL' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                  'bg-slate-800 text-slate-500'
                }`}>
                  {record.action}
                </span>
                <span className="text-blue-400 font-bold tracking-widest">{record.confidence}% CONF</span>
                <span className="text-slate-600 ml-auto">{new Date(record.timestamp).toLocaleTimeString()}</span>
              </div>
              
              <div className="text-slate-300 mb-2 leading-snug italic">
                {">"} {record.explanation}
              </div>

              <div className="bg-[#161a25]/50 p-2 rounded border border-white/5 text-blue-300/60 leading-normal">
                <div className="flex items-center gap-2 mb-1 opacity-50">
                  <Cpu size={10} />
                  <span className="text-[8px] font-black uppercase">Internal Trace</span>
                </div>
                {record.thinking}
              </div>
            </div>
          ))
        ) : (
          <div className="h-full flex flex-col items-center justify-center opacity-20 space-y-4">
            <Zap size={32} className="text-blue-500 animate-pulse" />
            <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-500 italic">No historical traces detected</p>
          </div>
        )}
      </div>

      <div className="px-4 py-2 bg-black/40 border-t border-[#1e222d] flex items-center justify-between text-[9px] font-bold text-slate-600">
        <div className="flex items-center gap-2">
          <Info size={12} />
          <span>MODEL: Llama3-8B-Atomic-Trio-v2</span>
        </div>
        <span>CRC-32: OK</span>
      </div>
    </div>
  );
};
