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
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg overflow-hidden shadow-lg">
      <div className="flex items-center gap-2 p-4 border-b border-[#1e222d] bg-[#1c222e]">
        <Layers size={18} className="text-[#2962ff]" />
        <h2 className="font-bold text-slate-200">Open Positions</h2>
        {positions.length > 0 && (
          <span className="ml-auto bg-[#2962ff]/10 text-[#2962ff] text-xs font-bold px-2 py-0.5 rounded">
            {positions.length} active
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-[#0a0c10] text-[#848e9c] uppercase text-xs font-bold border-b border-[#1e222d]">
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Entry</th>
              <th className="px-4 py-3">Current</th>
              <th className="px-4 py-3">PnL</th>
              <th className="px-4 py-3">SL / TP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e222d]">
            {positions.length > 0 ? (
              positions.map((pos, i) => (
                <tr key={i} className="hover:bg-[#1e222d] transition-colors">
                  <td className="px-4 py-3 font-bold text-slate-100">{pos.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                      pos.side === 'BUY' 
                        ? 'bg-emerald-500/10 text-emerald-400' 
                        : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {pos.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                    ${pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                    ${pos.current_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {pos.unrealized_pnl >= 0 ? (
                        <ArrowUpRight size={14} className="text-emerald-400" />
                      ) : (
                        <ArrowDownRight size={14} className="text-rose-400" />
                      )}
                      <span className={`font-bold text-xs ${
                        pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                        <span className="text-slate-500 ml-1">({pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%)</span>
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 text-xs font-mono">
                      <span className="flex items-center gap-0.5 text-rose-400">
                        <Shield size={10} />
                        {pos.stop_loss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className="text-slate-600">/</span>
                      <span className="flex items-center gap-0.5 text-emerald-400">
                        <Target size={10} />
                        {pos.take_profit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
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
