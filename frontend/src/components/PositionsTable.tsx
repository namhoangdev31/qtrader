"use client";

import React from 'react';
import { Layers, ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface Position {
  symbol: string;
  quantity: number;
  average_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

interface PositionsTableProps {
  positions: Position[];
}

export const PositionsTable: React.FC<PositionsTableProps> = ({ positions }) => {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg overflow-hidden shadow-lg">
      <div className="flex items-center gap-2 p-4 border-b border-[#1e222d] bg-[#1c222e]">
        <Layers size={18} className="text-[#2962ff]" />
        <h2 className="font-bold text-slate-200">Open Positions</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-[#0a0c10] text-[#848e9c] uppercase text-xs font-bold border-b border-[#1e222d]">
              <th className="px-6 py-3">Symbol</th>
              <th className="px-6 py-3">Size</th>
              <th className="px-6 py-3">Avg Price</th>
              <th className="px-6 py-3">PnL ($)</th>
              <th className="px-6 py-3">PnL (%)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e222d]">
            {positions.length > 0 ? (
              positions.map((pos) => (
                <tr key={pos.symbol} className="hover:bg-[#1e222d] transition-colors group">
                  <td className="px-6 py-4 font-bold text-slate-100">{pos.symbol}</td>
                  <td className="px-6 py-4 text-slate-200 font-medium">{pos.quantity.toFixed(4)}</td>
                  <td className="px-6 py-4 text-slate-400">$ {pos.average_price.toLocaleString()}</td>
                  <td className={`px-6 py-4 font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    <div className="flex items-center gap-1">
                      {pos.unrealized_pnl >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      $ {pos.unrealized_pnl.toLocaleString()}
                    </div>
                  </td>
                  <td className={`px-6 py-4 font-bold ${pos.unrealized_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-slate-500 italic">
                  No active exposure. Marketplace is flat.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
