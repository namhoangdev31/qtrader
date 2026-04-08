"use client";

import React from 'react';
import { Layers, ArrowUpRight, ArrowDownRight, Target, Shield } from 'lucide-react';

interface SimPosition {
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

interface SimPositionsTableProps {
  positions: SimPosition[];
}

export const SimPositionsTable: React.FC<SimPositionsTableProps> = ({ positions }) => {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded overflow-hidden shadow-lg">
      <div className="flex items-center gap-1.5 p-1.5 border-b border-[#1e222d] bg-[#1c222e]">
        <Layers size={14} className="text-[#2962ff]" />
        <h2 className="font-bold text-slate-200 text-[9px] uppercase tracking-widest">Inventory</h2>
        {positions.length > 0 && (
          <span className="ml-auto bg-[#2962ff]/10 text-[#2962ff] text-[7px] font-black px-1 py-0.5 rounded uppercase tracking-tighter">
            {positions.length} ACTIVE
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-[8px]">
          <thead>
            <tr className="bg-[#0a0c10] text-[#848e9c] uppercase text-[7px] font-black border-b border-[#1e222d]">
              <th className="px-2 py-1">Symbol</th>
              <th className="px-2 py-1">Side</th>
              <th className="px-2 py-1">Entry</th>
              <th className="px-2 py-1">PnL</th>
              <th className="px-2 py-1">SL/TP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e222d]">
            {positions.length > 0 ? (
              positions.map((pos, i) => (
                <tr key={i} className="hover:bg-[#1e222d] transition-colors">
                  <td className="px-2 py-1 font-bold text-slate-100">{pos.symbol}</td>
                  <td className="px-2 py-1">
                    <span className={`px-1 py-0.5 rounded text-[7px] font-black ${
                      pos.side === 'BUY' 
                        ? 'bg-emerald-500/10 text-emerald-400' 
                        : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {pos.side}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-slate-300 font-mono">
                    ${pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-2 py-1">
                    <div className="flex items-center gap-0.5">
                      <span className={`font-bold ${
                        pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="px-2 py-1">
                    <div className="flex items-center gap-1 text-[7px] font-mono">
                      <span className="text-rose-400">{pos.stop_loss.toFixed(2)}</span>
                      <span className="text-slate-600">/</span>
                      <span className="text-emerald-400">{pos.take_profit.toFixed(2)}</span>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-500 italic">
                  No active positions. Waiting for trading signals...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
