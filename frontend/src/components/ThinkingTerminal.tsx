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
      <div className="px-2 py-1.5 bg-[#1c222e] border-b border-[#1e222d] flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Terminal size={12} className="text-blue-500" />
          <h3 className="text-[8px] font-black uppercase tracking-[0.2em] text-blue-400">Tactical Thinking Log</h3>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-1 h-1 rounded-full bg-blue-500 animate-pulse shadow-lg shadow-blue-500/50" />
          <span className="text-[7.5px] font-bold text-slate-500 uppercase tracking-widest">LIVE</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2.5 scrollbar-hide font-mono text-[9px] leading-relaxed">
        {reversed.length > 0 ? (
          reversed.map((record, i) => (
            <div key={i} className="animate-in fade-in slide-in-from-bottom-2 duration-500 border-l-2 border-[#1e222d] pl-2 hover:border-blue-500/30 transition-all">
              <div className="flex items-center gap-1.5 mb-1">
                <span className={`px-1 py-0.5 rounded text-[7px] font-black uppercase tracking-tighter ${
                  record.action === 'BUY' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                  record.action === 'SELL' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                  'bg-slate-800 text-slate-500'
                }`}>
                  {record.action}
                </span>
                <span className="text-blue-400 font-bold tracking-widest text-[8px]">{record.confidence}% CONF</span>
                <span className="text-slate-600 ml-auto text-[7px]">{new Date(record.timestamp).toLocaleTimeString()}</span>
              </div>
              
              <div className="text-slate-300 mb-1 leading-tight italic text-[9px]">
                {">"} {record.explanation}
              </div>

              <div className="bg-[#161a25]/50 p-1 rounded border border-white/5 text-blue-300/60 leading-normal text-[8px]">
                <div className="flex items-center gap-1 mb-0.5 opacity-50">
                  <Cpu size={7} />
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
