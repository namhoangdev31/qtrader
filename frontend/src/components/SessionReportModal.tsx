"use client";

import React from 'react';
import { X, Award, AlertTriangle, TrendingUp, Brain, ShieldAlert, Clock, BarChart3, PieChart, Activity, Lightbulb, Zap, Target, ArrowRight } from 'lucide-react';

interface SessionReportModalProps {
  report: any;
  onClose: () => void;
}

export const SessionReportModal: React.FC<SessionReportModalProps> = ({ report, onClose }) => {
  if (!report || report.status === 'NO_TRADES') {
    return (
      <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
        <div className="bg-[#0d1117] border border-[#1e222d] rounded-2xl w-full max-w-md p-8 text-center shadow-2xl animate-in zoom-in-95 duration-300">
          <AlertTriangle className="mx-auto text-amber-400 mb-4" size={48} />
          <h2 className="text-xl font-bold text-white mb-2 uppercase tracking-tight">NULL_SESSION_DATA</h2>
          <p className="text-slate-500 text-xs font-mono mb-6 uppercase tracking-widest">Post-mortem failed: No trade execution detected in window.</p>
          <button onClick={onClose} className="w-full py-3 bg-slate-800 hover:bg-slate-700 rounded-xl font-black text-[10px] text-white uppercase tracking-[0.2em] transition-all">Close Pipeline</button>
        </div>
      </div>
    );
  }

  const metrics = report?.metrics || {};

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 backdrop-blur-md p-4 overflow-y-auto">
      <div className="bg-[#0d1117] border border-[#1e222d] rounded-2xl w-full max-w-6xl shadow-2xl flex flex-col max-h-[95vh] overflow-hidden animate-in fade-in slide-in-from-bottom-8 duration-700">
        
        {/* ACTIONABLE AUDIT HEADER */}
        <div className="p-8 border-b border-[#1e222d] bg-white/[0.02] flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3 text-slate-500">
              <Activity size={16} />
              <span className="text-[10px] font-black uppercase tracking-[0.4em]">Tactical Forensic Audit</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tighter uppercase">Audit Engine: Session Analysis</h1>
            <div className="flex items-center gap-4 pt-2">
                <span className="text-[10px] font-mono text-slate-500 bg-slate-800/50 px-2 py-0.5 rounded">ID: {report?.session_id || 'UNKNOWN_SESSION'}</span>
                <span className="text-[10px] font-mono text-slate-500 flex items-center gap-1 font-bold">
                  <Clock size={10} /> {report?.timestamp ? new Date(report.timestamp).toLocaleString() : new Date().toLocaleString()}
                </span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg text-slate-500 hover:text-white transition-all">
            <X size={24} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-8 bg-[#0d1117] space-y-10">
          
          {/* SECTION 1: EXECUTION & AI HEALTH */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
            <div className="lg:col-span-2 space-y-6">
               <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em] flex items-center gap-2">
                  <BarChart3 size={12} /> Execution Performance
               </h3>
               <div className="bg-[#161a25]/30 border border-[#1e222d] rounded-xl overflow-hidden shadow-inner">
                  <table className="w-full text-left">
                    <tbody className="divide-y divide-[#1e222d]/50">
                      <MetricRow label="Market Move (Gross)" value={`$${(metrics?.total_gross_pnl || 0).toFixed(2)}`} color={(metrics?.total_gross_pnl || 0) >= 0 ? "emerald" : "rose"} />
                      <MetricRow label="Net Realized" value={`$${(metrics?.total_pnl || 0).toFixed(2)}`} color={(metrics?.total_pnl || 0) >= 0 ? "emerald" : "rose"} subValue="Market + Fees" />
                      <MetricRow label="Win Rate" value={`${((metrics?.win_rate || 0) * 100).toFixed(1)}%`} subValue={`${metrics?.win_count || 0}W / ${metrics?.loss_count || 0}L`} />
                      <MetricRow label="Sharpe (Session)" value={(metrics?.sharpe_ratio || 0).toFixed(2)} color="blue" />
                      <MetricRow label="Comm. Drain" value={`-$${(metrics?.total_commissions || 0).toFixed(2)}`} subValue={`${(metrics?.commission_impact_pct || 0).toFixed(2)}% overall`} color="rose" />
                    </tbody>
                  </table>
               </div>
            </div>

            <div className="space-y-6">
              <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em] flex items-center gap-2">
                <ShieldAlert size={12} /> Model Integrity
              </h3>
              <div className="bg-[#161a25] border border-[#1e222d] rounded-xl p-6 space-y-6">
                <AnalystMetric label="AI Thinking Errors" value={metrics?.ai_thinking_errors || 0} status={(metrics?.ai_thinking_errors || 0) > 2 ? "FAIL" : "PASS"} />
                <AnalystMetric label="Execution Drift" value={`${((metrics?.pnl_error || 0) * 100).toFixed(2)}%`} status={(metrics?.pnl_error || 0) > 0.03 ? "VAR" : "OK"} />
                <div className="pt-4 border-t border-[#1e222d]/50">
                   <div className="flex justify-between items-center mb-1.5">
                     <span className="text-[9px] font-black text-slate-500 uppercase">Avg Confidence</span>
                     <span className="text-xs font-mono font-bold text-blue-400">{((metrics?.avg_ai_confidence || 0) * 100).toFixed(1)}%</span>
                   </div>
                   <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
                     <div className="bg-blue-500 h-full" style={{ width: `${(metrics?.avg_ai_confidence || 0) * 100}%` }} />
                   </div>
                </div>
              </div>
            </div>
          </div>

          {/* SECTION 2: TACTICAL RECOMMENDATIONS (ACTIONABLE) */}
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-blue-500/10 rounded-lg text-blue-400">
                <Lightbulb size={18} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-tight">Tactical Recommendations</h3>
                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Optimized Parameter Divergence</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {report.recommendations?.map((rec: any, i: number) => (
                <div key={i} className="p-5 rounded-2xl border border-blue-500/10 bg-blue-500/5 space-y-3 hover:border-blue-500/30 transition-all">
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] font-black px-2 py-1 bg-blue-500/10 text-blue-400 rounded uppercase">{rec.type}</span>
                    <Target size={14} className="text-blue-500/40" />
                  </div>
                  <div className="text-xs font-black text-white uppercase tracking-tight flex items-center gap-2 group cursor-default">
                    <ArrowRight size={14} className="text-blue-400 group-hover:translate-x-1 transition-transform" />
                    {rec.action}
                  </div>
                  <p className="text-[11px] text-slate-500 leading-relaxed font-medium">{rec.reason}</p>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 3: CRITICAL FAILURE AUDIT (BOTCHED CALLS) */}
          <div className="space-y-6">
            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em] flex items-center gap-2">
              <AlertTriangle size={12} className="text-rose-500" /> AI Logic Failure Logs
            </h3>
            <div className="space-y-3">
              {report?.botched_calls?.map((call: any, i: number) => (
                <div key={i} className="bg-[#161a25] border-l-2 border-rose-500/50 p-5 rounded-r-xl space-y-3">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-4">
                      <span className="text-[10px] font-mono text-slate-500">{call.timestamp ? new Date(call.timestamp).toLocaleTimeString() : 'N/A'}</span>
                      <span className="text-[10px] font-black text-rose-400 uppercase">BOTCHED CALL [{( (call.confidence || 0) * 100).toFixed(0)}% CONF]</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    <div>
                      <span className="text-[9px] font-black text-slate-600 uppercase block mb-1">AI Thinking (Raw)</span>
                      <p className="text-[11px] font-mono text-slate-400 leading-relaxed italic">"{call.thinking || 'No thinking log available'}"</p>
                    </div>
                    <div>
                      <span className="text-[9px] font-black text-rose-600 uppercase block mb-1">Forensic Verdict</span>
                      <p className="text-[11px] font-bold text-rose-200 leading-relaxed flex items-center gap-2">
                        <ShieldAlert size={12} /> {call.logical_error || 'Systemic degradation detected'}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
              {(!report.botched_calls || report.botched_calls.length === 0) && (
                <div className="py-10 text-center border border-dashed border-[#1e222d] rounded-xl text-slate-600 text-xs italic">
                  No critical AI logic failures detected this session. Integrity remains high.
                </div>
              )}
            </div>
          </div>

          {/* SECTION 4: STRATEGY SWOT */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
            <div className="space-y-4">
               <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em]">Session Strengths</h3>
               <div className="space-y-2">
                  <StrengthItem text="High Execution Consistency" />
                  <StrengthItem text="Robust Slippage Control" />
                  <StrengthItem text="Optimal Data Fidelity" />
               </div>
            </div>
            <div className="space-y-4">
               <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em]">Session Weaknesses</h3>
               <div className="space-y-2">
                  <WeaknessItem text="Fee Over-exposure" />
                  <WeaknessItem text="Convexity Decay in Reversals" />
                  <WeaknessItem text="Stop-loss Sensitivity" />
               </div>
            </div>
          </div>

        </div>

        {/* FOOTER */}
        <div className="p-6 border-t border-[#1e222d] bg-white/[0.02] flex justify-end">
          <button 
            onClick={onClose}
            className="px-10 py-3 bg-[#2962ff] hover:bg-blue-500 text-white rounded-xl font-black text-[10px] uppercase tracking-[0.2em] shadow-lg shadow-blue-900/20 transition-all border border-blue-400/20 active:scale-95"
          >
            Confirm Tactical Audit
          </button>
        </div>
      </div>
    </div>
  );
};

function MetricRow({ label, value, subValue, color }: any) {
  const colors: any = {
    emerald: "text-emerald-400 font-bold",
    rose: "text-rose-400 font-bold",
    blue: "text-blue-400 font-bold",
    amber: "text-amber-400 font-bold",
    slate: "text-slate-400",
  };
  
  return (
    <tr className="hover:bg-white/[0.01]">
      <td className="px-6 py-4 text-[11px] font-bold text-slate-400 uppercase tracking-tight">{label}</td>
      <td className="px-6 py-4 text-right">
        <div className={`text-xs font-mono font-bold ${colors[color] || 'text-white'}`}>{value}</div>
        {subValue && <div className="text-[9px] font-black text-slate-600 uppercase tracking-tighter mt-0.5">{subValue}</div>}
      </td>
    </tr>
  );
}

function AnalystMetric({ label, value, status }: any) {
  const statusColors: any = {
    PASS: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    FAIL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    VAR: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    NEU: "bg-slate-700/50 text-slate-400 border-white/10",
  };

  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-bold text-slate-300 tracking-tight">{label}</span>
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono font-bold text-white">{value}</span>
        <span className={`px-2 py-0.5 rounded text-[8px] font-black border ${statusColors[status]}`}>
          {status}
        </span>
      </div>
    </div>
  );
}

function StrengthItem({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 text-xs font-bold text-emerald-400/80 bg-emerald-500/5 border border-emerald-500/10 p-3 rounded-lg">
      <Target size={14} /> {text}
    </div>
  );
}

function WeaknessItem({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 text-xs font-bold text-rose-400/80 bg-rose-500/5 border border-rose-500/10 p-3 rounded-lg">
      <AlertTriangle size={14} /> {text}
    </div>
  );
}
