"use client";

import React from 'react';
import { Target, Activity, Shield, TrendingUp, TrendingDown, Clock, Zap, Layers } from 'lucide-react';

interface Position {
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss: number;
  take_profit: number;
  entry_time: string;
}

interface ForensicPositionsProps {
  positions: Position[];
}

export const ForensicPositions: React.FC<ForensicPositionsProps> = ({ positions }) => {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded overflow-hidden shadow-2xl flex flex-col h-full font-mono">
      {/* HEADER */}
      <div className="flex items-center justify-between p-2 border-b border-[#1e222d] bg-black/40">
        <div className="flex items-center gap-2">
          <Layers size={14} className="text-blue-500 animate-pulse" />
          <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-100 italic">
            Active Forensic Inventory <span className="text-blue-500">v3.0</span>
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[8px] font-black text-slate-500 uppercase tracking-tighter">
            {positions.length} VECTOR{positions.length !== 1 ? 'S' : ''} DETECTED
          </span>
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-lg shadow-emerald-500/50" />
        </div>
      </div>

      {/* POSITIONS LIST */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3 custom-scrollbar">
        {positions.length > 0 ? (
          positions.map((pos, idx) => (
            <div key={`${pos.symbol}-${idx}`} className="group relative">
              {/* Background Glow */}
              <div className={`absolute -inset-1 rounded-lg opacity-10 group-hover:opacity-20 transition-all duration-500 ${
                pos.unrealized_pnl >= 0 ? 'bg-emerald-500' : 'bg-rose-500'
              }`} />
              
              <div className="relative bg-black/60 border border-[#1e222d] rounded-lg p-2 overflow-hidden">
                {/* Side Indicator Bar */}
                <div className={`absolute top-0 left-0 bottom-0 w-1 ${
                  pos.side === 'BUY' ? 'bg-emerald-500' : 'bg-rose-500'
                }`} />

                <div className="flex flex-col gap-2 pl-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-black text-white">{pos.symbol}</span>
                        <span className={`text-[8px] font-black px-1 py-0.5 rounded ${
                          pos.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                        }`}>
                          {pos.side}
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-500 mt-1 uppercase flex items-center gap-1.0">
                         <Zap size={10} className="text-amber-500" />
                         QTY: <span className="text-slate-300">{pos.quantity.toFixed(4)}</span>
                      </div>
                    </div>
                    
                    <div className="text-right">
                      <div className={`text-[12px] font-black items-center flex justify-end gap-1 ${
                        pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {pos.unrealized_pnl >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)} USD
                      </div>
                      <div className={`text-[9px] font-bold ${
                        pos.unrealized_pnl >= 0 ? 'text-emerald-500/60' : 'text-rose-500/60'
                      }`}>
                        {pos.unrealized_pnl_pct.toFixed(2)}% ROI
                      </div>
                    </div>
                  </div>

                  {/* PROGRESS BAR (Distance to SL/TP) */}
                  <div className="space-y-1 mt-1">
                    <div className="flex justify-between text-[7px] font-black uppercase text-slate-600">
                       <span>SL: {pos.stop_loss.toFixed(1)}</span>
                       <span>TP: {pos.take_profit.toFixed(1)}</span>
                    </div>
                    <div className="relative h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-white/5">
                        {/* Current Price Marker Offset */}
                        {/* Simplified Logic: Assuming pos starts between SL and TP */}
                        {(() => {
                           const total = pos.take_profit - pos.stop_loss;
                           if (total <= 0) return null;
                           const progress = ((pos.current_price - pos.stop_loss) / total) * 100;
                           const clampedProgress = Math.min(Math.max(progress, 0), 100);
                           return (
                             <>
                               <div className="bg-slate-700/50 absolute top-0 bottom-0 left-[50%] w-[1px] z-10" />
                               <div 
                                 className={`h-full transition-all duration-1000 ${
                                   pos.unrealized_pnl >= 0 ? 'bg-emerald-500/40 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-rose-500/40 shadow-[0_0_8px_rgba(244,63,94,0.5)]'
                                 }`} 
                                 style={{ width: `${clampedProgress}%` }} 
                               />
                               <div 
                                 className="absolute top-0 bottom-0 w-[2px] bg-white shadow-[0_0_10px_white] z-20"
                                 style={{ left: `${clampedProgress}%` }}
                               />
                             </>
                           );
                        })()}
                    </div>
                  </div>

                  <div className="flex justify-between items-center text-[7px] text-slate-500 pt-1 border-t border-white/5">
                    <div className="flex items-center gap-1">
                       <Clock size={8} /> 
                       T.I.T: <span className="text-slate-400">
                         {new Date(pos.entry_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                       </span>
                    </div>
                    <div className="flex items-center gap-1">
                       <Target size={8} />
                       ENTRY: <span className="text-slate-400">${pos.entry_price.toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-700 space-y-4 opacity-40 py-20 border-2 border-dashed border-[#1e222d] rounded-lg">
             <Activity size={48} className="animate-pulse" />
             <div className="text-center">
               <p className="text-[10px] font-black uppercase tracking-widest mb-1">Zero Exposure Detected</p>
               <p className="text-[8px] font-bold uppercase italic">Awaiting Alpha Trigger Cluster...</p>
             </div>
          </div>
        )}
      </div>
      
      {/* TACTICAL FOOTER */}
      <div className="p-1 px-2 border-t border-[#1e222d] bg-black/20 flex justify-between items-center text-[7px] font-black uppercase tracking-tighter text-slate-600">
         <div className="flex items-center gap-2">
            <span className="flex items-center gap-1"><Shield size={8} className="text-blue-500" /> RISK_VAL: PASS</span>
            <span className="flex items-center gap-1"><Shield size={8} className="text-emerald-500" /> MARGIN: NOMINAL</span>
         </div>
         <span className="text-blue-500/50 italic font-mono">QUANT_RECON_ACTIVE</span>
      </div>
    </div>
  );
};
