"use client";

import React, { useState, useEffect } from 'react';
import { useTradingSystem } from '@/hooks/useTradingSystem';
import { TradeHistory } from '@/components/TradeHistory';
import { 
    ChevronLeft, 
    History, 
    Download, 
    Filter,
    Search,
    ShieldAlert,
    Calendar,
    Briefcase
} from 'lucide-react';
import Link from 'next/link';

export default function AuditHistoryPage() {
    const { fetchSessionHistory, portfolio, audit } = useTradingSystem();
    const [sessions, setSessions] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            const data = await fetchSessionHistory();
            if (data) setSessions(data);
            setLoading(false);
        };
        load();
    }, [fetchSessionHistory]);

    return (
        <main className="min-h-screen bg-[#080a0f] text-slate-300 font-sans p-6 selection:bg-blue-500/30 institutional-gradient">
            <div className="max-w-7xl mx-auto space-y-8">
                {/* Header */}
                <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div className="flex items-center gap-4">
                        <Link 
                            href="/expert"
                            className="p-2 bg-slate-900 border border-slate-800 rounded hover:bg-slate-800 transition-all text-slate-400 hover:text-white"
                        >
                            <ChevronLeft size={20} />
                        </Link>
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <History className="text-blue-500" size={18} />
                                <h1 className="text-xl font-black tracking-tighter text-white uppercase italic">
                                    Forensic Audit <span className="text-blue-500">History</span>
                                </h1>
                            </div>
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                                Comprehensive Logic Registry & Execution Logs
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <div className="relative group">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
                            <input 
                                type="text" 
                                placeholder="SEARCH TRACE ID..."
                                className="bg-black/40 border border-white/5 rounded px-10 py-2 text-[10px] font-bold uppercase tracking-widest focus:outline-none focus:border-blue-500/50 transition-all w-64"
                            />
                        </div>
                        <button className="p-2 bg-slate-900 border border-slate-800 rounded hover:bg-slate-800 text-slate-400">
                            <Filter size={16} />
                        </button>
                        <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-black text-[10px] uppercase tracking-widest transition-all">
                            <Download size={14} /> Export Audit
                        </button>
                    </div>
                </header>

                {/* Dashboard Stats */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <AuditStat icon={<Briefcase size={14}/>} label="Total Sessions" value={sessions.length.toString()} color="text-blue-400" />
                    <AuditStat icon={<ShieldAlert size={14}/>} label="Risk Violations" value="0" color="text-emerald-400" />
                    <AuditStat icon={<Calendar size={14}/>} label="Last Audit" value="TODAY" color="text-white" />
                    <AuditStat icon={<History size={14}/>} label="Trace Fidelity" value="100%" color="text-amber-400" />
                </div>

                {/* Active Portfolio Context */}
                <div className="glass border border-white/5 rounded-lg overflow-hidden">
                    <div className="px-4 py-3 border-b border-[#1e222d] bg-black/20 flex justify-between items-center">
                         <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-400">Current Session Real-time Stream</h3>
                         <span className="text-[8px] font-bold text-slate-500">LIVE SYNC ACTIVE</span>
                    </div>
                    <div className="p-4">
                        <TradeHistory trades={audit?.trades || []} />
                    </div>
                </div>

                {/* Session List */}
                <div className="space-y-4">
                     <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 px-4">Archived Forensic Sessions</h3>
                     <div className="grid grid-cols-1 gap-3">
                        {loading ? (
                            <div className="h-64 flex items-center justify-center border border-white/5 bg-black/20 rounded">
                                <span className="text-[10px] font-bold animate-pulse uppercase tracking-[0.5em] text-blue-500">Retrieving Secure Archives...</span>
                            </div>
                        ) : sessions.length > 0 ? (
                            sessions.map((s) => (
                                <div key={s.session_id} className="group glass border border-white/5 p-4 rounded-lg hover:border-blue-500/30 transition-all flex justify-between items-center cursor-pointer">
                                    <div className="flex items-center gap-6">
                                        <div className="w-10 h-10 rounded bg-[#2962ff]/10 border border-[#2962ff]/20 flex items-center justify-center text-blue-500 font-black italic">
                                            {s.mode[0]}
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-3 mb-1">
                                                <h4 className="text-xs font-black text-white uppercase tracking-tighter">{s.session_id}</h4>
                                                <span className={`px-1.5 py-0.5 rounded text-[7px] font-black uppercase ${
                                                    s.mode === 'LIVE' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                                }`}>
                                                    {s.mode}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-4 text-[8px] font-bold text-slate-500 uppercase tracking-widest">
                                                <span>{new Date(s.start_time).toLocaleString()}</span>
                                                <span className="w-1 h-1 bg-slate-800 rounded-full" />
                                                <span>{s.summary?.trade_count ?? 0} Trades</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className={`text-sm font-black italic mb-1 ${
                                            (s.summary?.total_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                        }`}>
                                            {(s.summary?.total_pnl ?? 0) >= 0 ? '+' : ''}${Math.abs(s.summary?.total_pnl ?? 0).toFixed(2)}
                                        </div>
                                        <div className="text-[8px] font-black text-slate-600 uppercase tracking-widest">REALIZED PNL</div>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="h-48 border border-dashed border-white/10 flex flex-col items-center justify-center text-slate-600 gap-4">
                                <History size={32} opacity={0.2} />
                                <span className="text-[10px] font-black uppercase tracking-widest">No forensic data archived.</span>
                            </div>
                        )}
                     </div>
                </div>
            </div>
        </main>
    );
}

function AuditStat({ icon, label, value, color }: { icon: React.ReactNode, label: string, value: string, color: string }) {
    return (
        <div className="glass border border-white/5 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2 text-slate-500">
                {icon}
                <span className="text-[8px] font-black uppercase tracking-widest">{label}</span>
            </div>
            <div className={`text-xl font-black italic tracking-tighter ${color}`}>
                {value}
            </div>
        </div>
    );
}
