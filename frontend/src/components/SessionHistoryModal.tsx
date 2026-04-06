"use client";

import React from 'react';
import { X, Calendar, Activity, ChevronRight, BarChart2 } from 'lucide-react';

interface SessionHistoryModalProps {
  history: any[];
  onClose: () => void;
  onViewReport: (session: any) => void;
}

export const SessionHistoryModal: React.FC<SessionHistoryModalProps> = ({ history, onClose, onViewReport }) => {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="bg-[#0d1117] border border-[#1e222d] rounded-2xl w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-300">
        
        {/* Header */}
        <div className="p-6 border-b border-[#1e222d] flex items-center justify-between bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400">
              <Activity size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white uppercase tracking-tight">Performance History</h2>
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Audit Trail & Forensic Archives</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-4">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] font-black text-slate-500 uppercase tracking-widest border-b border-[#1e222d]">
                <th className="px-4 py-3">Start Time</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3">PnL</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e222d]/50">
              {history.map((session, i) => {
                const startTime = new Date(session.start_time);
                const endTime = session.end_time ? new Date(session.end_time) : null;
                const duration = endTime 
                  ? Math.round((endTime.getTime() - startTime.getTime()) / 60000)
                  : 0;
                const pnl = session.summary?.metrics?.total_pnl || 0;

                return (
                  <tr key={i} className="group hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        <Calendar size={14} className="text-slate-600" />
                        <span className="text-sm font-mono text-slate-300">
                          {startTime.toLocaleDateString()} {startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-500 font-medium">
                      {duration} MINS
                    </td>
                    <td className={`px-4 py-4 text-sm font-black font-mono ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                    </td>
                    <td className="px-4 py-4 text-right">
                      <button 
                        onClick={() => onViewReport(session)}
                        className="text-[10px] font-black uppercase tracking-widest text-blue-400 hover:text-blue-300 flex items-center gap-1 ml-auto group-hover:translate-x-1 transition-all"
                      >
                        Auditing <ChevronRight size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
              {history.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-20 text-center text-slate-600 italic text-sm">
                    No historical session data detected in database.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
