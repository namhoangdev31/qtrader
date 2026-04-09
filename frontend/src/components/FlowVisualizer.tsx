import React, { useEffect, useState } from 'react';
import { Database, Zap, ShieldAlert, ShoppingCart, Activity } from 'lucide-react';

interface FlowVisualizerProps {
  lastTickTimestamp?: string;
  lastSignal?: any;
  simRunning: boolean;
  liveTrace?: any;
  currentPrice?: number;
}

export const FlowVisualizer: React.FC<FlowVisualizerProps> = ({ lastTickTimestamp, lastSignal, simRunning, liveTrace, currentPrice }) => {
  const [activeStage, setActiveStage] = useState<number>(-1);

  useEffect(() => {
    if (lastTickTimestamp) {
      // Trigger animation sequence
      setActiveStage(0);
      const timer1 = setTimeout(() => setActiveStage(1), 300);
      const timer2 = setTimeout(() => setActiveStage(2), 600);
      const timer3 = setTimeout(() => lastSignal ? setActiveStage(3) : setActiveStage(-1), 900);
      
      const resetTimer = setTimeout(() => setActiveStage(-1), 2000);
      
      return () => {
        clearTimeout(timer1);
        clearTimeout(timer2);
        clearTimeout(timer3);
        clearTimeout(resetTimer);
      };
    }
  }, [lastTickTimestamp, lastSignal]);

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded p-2 flex flex-col items-center justify-between h-full min-h-[120px]">
      <div className="w-full flex items-center justify-between mb-2">
        <h3 className="text-[8px] font-black uppercase tracking-widest text-blue-500 flex items-center gap-1.5">
          <Activity size={12} /> Execution Flow
        </h3>
        <div className={`px-1.5 py-0.5 rounded text-[7px] font-black border ${
          simRunning ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}>
          {simRunning ? 'LIVE' : 'IDLE'}
        </div>
      </div>

      <div className="flex items-center justify-center w-full relative">
        <StageItem 
          icon={<Database size={16} />} 
          label="Data" 
          active={activeStage >= 0} 
          subLabel={
            currentPrice ? `$${currentPrice.toFixed(2)}` : 
            (liveTrace?.ingestion ? `$${liveTrace.ingestion.price.toFixed(2)}` : "TICK")
          }
        />
        <Connector active={activeStage >= 1} />
        <StageItem 
          icon={<Zap size={16} />} 
          label="Alpha" 
          active={activeStage >= 1} 
          subLabel={liveTrace?.alpha ? `RSI: ${liveTrace.alpha.indicators.rsi.toFixed(0)}` : "TRIO"}
          highlight={lastSignal?.action !== 'HOLD'}
        />
        <Connector active={activeStage >= 2} />
        <StageItem 
          icon={<ShieldAlert size={16} />} 
          label="Risk" 
          active={activeStage >= 2} 
          subLabel={liveTrace?.risk ? `SL: ${liveTrace.risk.initial_stop_loss.toFixed(0)}` : "GUARD"}
          type={lastSignal?.action === 'HOLD' ? 'warning' : 'success'}
        />
        <Connector active={activeStage >= 3} />
        <StageItem 
          icon={<ShoppingCart size={16} />} 
          label="Exec" 
          active={activeStage >= 3} 
          subLabel={liveTrace?.execution ? `S: ${liveTrace.execution.slippage_bps.toFixed(1)}` : "ROUTE"}
          highlight={lastSignal?.action === 'BUY' || lastSignal?.action === 'SELL'}
        />
      </div>

      <div className="w-full mt-2 grid grid-cols-2 gap-2">
        <div className="bg-black/20 p-1.5 rounded border border-[#1e222d]">
          <p className="text-[7px] font-black text-slate-500 uppercase">Pulse</p>
          <p className="text-[8px] font-mono text-blue-300 truncate">{lastTickTimestamp || 'NONE'}</p>
        </div>
        <div className="bg-black/20 p-1.5 rounded border border-[#1e222d]">
          <p className="text-[7px] font-black text-slate-500 uppercase">Signal</p>
          <p className="text-[8px] font-mono text-emerald-300">{lastSignal?.action || 'HOLD'}</p>
        </div>
      </div>
    </div>
  );
};

function StageItem({ icon, label, active, subLabel, highlight, type = 'success' }: { 
  icon: React.ReactNode, 
  label: string, 
  active: boolean, 
  subLabel: string, 
  highlight?: boolean, 
  type?: 'success' | 'warning' | 'error' 
}) {
  return (
    <div className={`flex flex-col items-center gap-1.5 transition-all duration-500 relative ${active ? 'scale-110 opacity-100' : 'opacity-40 scale-100'}`}>
      <div className={`p-2 rounded border shadow-2xl transition-all duration-300 ${
        highlight 
          ? 'bg-blue-500 border-blue-400 text-white shadow-blue-500/50' 
          : active 
            ? 'bg-blue-500/20 border-blue-500/80 text-blue-400 shadow-blue-500/20' 
            : 'bg-slate-800 border-slate-700 text-slate-500'
      }`}>
        {icon}
      </div>
      <div className="text-center">
        <div className={`text-[8px] font-black uppercase tracking-widest ${active ? 'text-white' : 'text-slate-600'}`}>
          {label}
        </div>
        <div className={`text-[7px] font-bold uppercase mt-0.5 whitespace-nowrap ${
          active ? (type === 'success' ? 'text-emerald-400' : 'text-amber-400') : 'text-slate-700'
        }`}>
          {subLabel}
        </div>
      </div>
    </div>
  );
}

function Connector({ active }: { active: boolean }) {
  return (
    <div className="flex-1 h-[2px] min-w-[30px] mx-2 relative bg-slate-800">
      <div className={`absolute inset-0 bg-blue-500 transition-all duration-500 ${active ? 'w-full shadow-lg shadow-blue-500/50' : 'w-0'}`} />
    </div>
  );
}
