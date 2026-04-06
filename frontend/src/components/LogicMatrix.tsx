import React from 'react';
import { Shield, Zap, Target, Truck, Activity, RotateCw, AlertTriangle, Clock } from 'lucide-react';

interface ModuleTrace {
  name?: string;
  status?: string;
  latency_ms?: number;
  budget_ms?: number;
  is_anomaly?: boolean;
  reason?: string;
  reasoning?: string;
  [key: string]: any;
}

interface LogicMatrixProps {
  moduleTraces?: Record<string, ModuleTrace>;
}

const renderTraceValue = (v: any): React.ReactNode => {
  if (v === null || v === undefined) return 'N/A';
  if (typeof v === 'number') return v > 1000 ? v.toFixed(0) : v.toFixed(4);
  if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
  if (Array.isArray(v)) return `[${v.join(', ')}]`;
  if (typeof v === 'object') {
    return (
      <div className="flex flex-col gap-0.5 mt-1">
        {Object.entries(v).map(([sk, sv]) => (
          <div key={sk} className="flex justify-between items-center bg-black/30 px-2 py-1 rounded border border-slate-800/30">
            <span className="text-[8px] text-slate-500 uppercase font-black">{sk}</span>
            <span className="text-[10px] text-blue-300 font-bold truncate max-w-24">{String(sv)}</span>
          </div>
        ))}
      </div>
    );
  }
  return String(v);
};

export const LogicMatrix: React.FC<LogicMatrixProps> = ({ moduleTraces = {} }) => {
  const getIcon = (key: string) => {
    switch (key.toLowerCase()) {
      case 'risk':
      case 'riskguard':
        return <Shield className="text-rose-500" size={14} />;
      case 'alpha':
      case 'alphaengine':
        return <Zap className="text-amber-500" size={14} />;
      case 'portfolio':
      case 'positionsizer':
        return <Target className="text-blue-500" size={14} />;
      case 'execution':
        return <Truck className="text-emerald-500" size={14} />;
      case 'reconciliation':
        return <RotateCw className="text-purple-500" size={14} />;
      case 'strategy':
        return <Activity className="text-indigo-400" size={14} />;
      default:
        return <Activity className="text-slate-500" size={14} />;
    }
  };

  const modules = Object.entries(moduleTraces);

  if (modules.length === 0) {
    return (
      <div className="bg-[#161a25]/50 border border-[#1e222d] rounded-lg p-6 flex items-center justify-center h-full">
        <p className="text-slate-500 text-xs font-black uppercase tracking-widest text-center">
          Awaiting Forensic Logic Pulse...
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 h-full overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
      {modules.map(([key, trace]) => {
        const isLatencyBreach = (trace.latency_ms || 0) > (trace.budget_ms || 999);
        const isAnomaly = trace.is_anomaly || isLatencyBreach || trace.status === 'ERROR' || trace.status === 'DANGER';

        return (
          <div 
            key={key} 
            className={`bg-[#1c212d] border rounded-lg p-6 flex flex-col gap-5 shadow-xl transition-all duration-300 min-h-[350px] max-h-[750px] overflow-hidden
              ${isAnomaly ? 'border-rose-500/50 shadow-rose-900/20 animate-pulse-slow' : 'border-[#2a2f3e] hover:border-blue-500/50'}
            `}
          >
            <div className="flex items-center justify-between border-b border-[#2a2f3e] pb-2">
              <div className="flex items-center gap-2">
                {getIcon(key)}
                <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-300">
                  {key}
                </h4>
              </div>
              <div className="flex items-center gap-2">
                {trace.latency_ms !== undefined && (
                   <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] font-black border ${
                     isLatencyBreach ? 'bg-rose-500/10 border-rose-500/50 text-rose-400' : 'bg-slate-800 border-slate-700 text-slate-400'
                   }`}>
                     <Clock size={8} />
                     {trace.latency_ms.toFixed(1)}ms
                   </div>
                )}
                <div className={`text-[8px] px-1.5 py-0.5 rounded font-black uppercase ${
                  isAnomaly ? 'bg-rose-500/20 text-rose-400' : 'bg-emerald-500/20 text-emerald-400'
                }`}>
                  {trace.status || (isAnomaly ? 'ANOMALY' : 'HEALTHY')}
                </div>
              </div>
            </div>
            
              <div className="grid grid-cols-1 gap-3 mt-1 border-t border-slate-700/30 pt-4 overflow-y-auto min-h-[250px] max-h-[650px]">
                {Object.entries(trace)
                  .filter(([k]) => !['status', 'name', 'reason', 'reasoning', 'latency_ms', 'budget_ms', 'is_anomaly'].includes(k))
                  .length > 0 ? (
                    Object.entries(trace)
                      .filter(([k]) => !['status', 'name', 'reason', 'reasoning', 'latency_ms', 'budget_ms', 'is_anomaly'].includes(k))
                      .map(([k, v]) => (
                        <div key={k} className="flex flex-col gap-2 p-3 rounded bg-black/40 border border-slate-800/50">
                          <span className="text-[11px] text-slate-500 font-black uppercase tracking-[0.2em]">{k.replace('_', ' ')}</span>
                          <div className="text-blue-400 font-mono text-sm break-all leading-relaxed font-bold">
                            {renderTraceValue(v)}
                          </div>
                        </div>
                      ))
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 opacity-30 text-center gap-4">
                      <div className="w-12 h-12 rounded-full border border-dashed border-slate-600 animate-spin-slow flex items-center justify-center">
                        <Activity size={20} className="text-slate-600" />
                      </div>
                      <span className="text-xs font-black uppercase tracking-[0.4em] text-slate-500">Awaiting Pulse...</span>
                    </div>
                  )}
              </div>

            {isAnomaly && isLatencyBreach && (
              <div className="mt-1 flex items-center gap-1.5 text-rose-400 text-[9px] font-bold uppercase">
                <AlertTriangle size={10} className="animate-pulse" /> SLA Breach
              </div>
            )}

            {(trace.reason || trace.reasoning) && (
              <div className="mt-auto pt-2 border-t border-[#2a2f3e]">
                 <p className="text-[8px] font-black text-blue-500 uppercase mb-1">Logic Trace</p>
                 <p className="text-[9px] italic text-slate-400 line-clamp-2 leading-relaxed">
                   "{trace.reason || trace.reasoning}"
                 </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
