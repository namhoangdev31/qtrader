import React from 'react';
import { Activity, ShieldAlert, CheckCircle2, AlertOctagon, Timer } from 'lucide-react';

interface SystemHealthHUDProps {
  moduleTraces: Record<string, any>;
  overallStatus?: string;
}

export const SystemHealthHUD: React.FC<SystemHealthHUDProps> = ({ moduleTraces = {}, overallStatus = 'OK' }) => {
  const modules = Object.values(moduleTraces);
  
  // Calculate Metrics
  const totalModules = modules.length;
  const anomalies = modules.filter(m => m.is_anomaly || (m.latency_ms > (m.budget_ms || 999)) || m.status === 'ERROR' || m.status === 'DANGER');
  const slaCompliance = totalModules > 0 ? ((totalModules - anomalies.length) / totalModules) * 100 : 100;
  
  const recon = moduleTraces['Reconciliation'] || {};
  const isReconOk = recon.status === 'OK' || !recon.status; // Default to OK if no data yet to avoid false-pos

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-1.5 mb-2">
      {/* SLA COMPLIANCE */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded p-1 flex items-center justify-between shadow-lg">
        <div className="flex flex-col">
          <span className="text-[7px] font-black text-slate-500 uppercase tracking-widest mb-0.5">SLA-C</span>
          <span className={`text-[12px] font-black ${slaCompliance < 90 ? 'text-rose-500' : 'text-emerald-500'}`}>
            {slaCompliance.toFixed(1)}%
          </span>
        </div>
        <Timer size={16} className={slaCompliance < 90 ? 'text-rose-900/50' : 'text-emerald-900/50'} />
      </div>

      {/* RECONCILIATION RADAR */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded p-1 flex items-center justify-between shadow-lg">
        <div className="flex flex-col">
          <span className="text-[7px] font-black text-slate-500 uppercase tracking-widest mb-0.5">RECON</span>
          <span className={`text-[10px] font-black uppercase ${isReconOk ? 'text-emerald-400' : 'text-rose-500 animate-pulse'}`}>
             {isReconOk ? 'SYNC' : 'MISMATCH'}
          </span>
          <span className="text-[7px] font-bold text-slate-600">D: {recon.mismatch_count || 0} Sym</span>
        </div>
        <RotateCcw className={isReconOk ? 'text-emerald-900/50' : 'text-rose-900/50'} size={16} />
      </div>

      {/* ANOMALY COUNTER */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded p-1 flex items-center justify-between shadow-lg">
        <div className="flex flex-col">
          <span className="text-[7px] font-black text-slate-500 uppercase tracking-widest mb-0.5">ANOMALY</span>
          <span className={`text-[12px] font-black ${anomalies.length > 0 ? 'text-rose-500 animate-bounce-slow' : 'text-slate-400'}`}>
            {anomalies.length}
          </span>
        </div>
        <AlertOctagon size={16} className={anomalies.length > 0 ? 'text-rose-900/50' : 'text-slate-900/50'} />
      </div>

      {/* SYSTEM INTEGRITY */}
      <div className="bg-[#161a25] border border-[#1e222d] rounded p-1 flex items-center justify-between shadow-lg">
        <div className="flex flex-col">
          <span className="text-[7px] font-black text-slate-500 uppercase tracking-widest mb-0.5">INTEGRITY</span>
          <div className="flex items-center gap-1">
            <span className={`text-[10px] font-black uppercase ${overallStatus === 'OK' ? 'text-emerald-400' : 'text-rose-400'}`}>
              {overallStatus}
            </span>
            {overallStatus === 'OK' ? <CheckCircle2 size={10} className="text-emerald-500" /> : <ShieldAlert size={10} className="text-rose-500" />}
          </div>
        </div>
        <Activity size={16} className="text-blue-900/30" />
      </div>
    </div>
  );
};

function RotateCcw(props: any) {
    return (
      <svg
        {...props}
        xmlns="http://www.w3.org/2000/svg"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
        <path d="M3 3v5h5" />
      </svg>
    )
  }
