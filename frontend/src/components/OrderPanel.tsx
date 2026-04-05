"use client";

import React, { useState } from 'react';
import { TrendingUp, TrendingDown, DollarSign, Package } from 'lucide-react';

interface OrderPanelProps {
  onOrder?: (side: 'BUY' | 'SELL', qty: number) => void;
}

export const OrderPanel: React.FC<OrderPanelProps> = ({ onOrder }) => {
  const [qty, setQty] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("BTC-USD");

  const handleSubmit = (side: 'BUY' | 'SELL') => {
    const q = parseFloat(qty);
    if (isNaN(q) || q <= 0) {
      alert("Please enter a valid quantity.");
      return;
    }
    if (onOrder) onOrder(side, q);
    setQty("");
  };

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-4 flex flex-col gap-4 shadow-xl">
      <div className="flex items-center gap-2 pb-2 border-b border-[#1e222d]">
        <Package size={18} className="text-slate-400" />
        <h2 className="font-bold text-slate-200">Execution Panel</h2>
      </div>

      <div className="space-y-3">
        <div className="space-y-1">
          <label className="text-xs uppercase font-bold text-slate-500">Asset</label>
          <select 
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2 text-sm focus:border-blue-500 outline-none transition-colors"
          >
            <option value="BTC-USD">BTC-USD</option>
            <option value="ETH-USD">ETH-USD</option>
          </select>
        </div>

        <div className="space-y-1">
          <label className="text-xs uppercase font-bold text-slate-500">Amount</label>
          <div className="relative">
            <input 
              type="number" 
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="0.00"
              className="w-full bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2 text-sm focus:border-blue-500 outline-none pr-12 transition-colors"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 font-medium">BTC</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 pt-2">
          <button 
            onClick={() => handleSubmit('BUY')}
            className="bg-[#26a69a] hover:bg-[#2bbbad] text-white font-bold py-3 rounded flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-emerald-900/20"
          >
            <TrendingUp size={18} />
            BUY
          </button>
          <button 
            onClick={() => handleSubmit('SELL')}
            className="bg-[#ef5350] hover:bg-[#ff5a5a] text-white font-bold py-3 rounded flex items-center justify-center gap-2 transition-all active:scale-95 shadow-lg shadow-rose-900/20"
          >
            <TrendingDown size={18} />
            SELL
          </button>
        </div>
      </div>
    </div>
  );
};
