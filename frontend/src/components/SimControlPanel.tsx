"use client";

import React, { useState } from 'react';
import { Play, Square, RotateCcw, Settings, Shield, Target } from 'lucide-react';

interface SimControlPanelProps {
  slPct: number;
  tpPct: number;
  onConfigChange: (sl: number, tp: number) => void;
}

export const SimControlPanel: React.FC<SimControlPanelProps> = ({
  slPct,
  tpPct,
  onConfigChange,
}) => {
  const [showConfig, setShowConfig] = useState(false);
  const [slInput, setSlInput] = useState(slPct.toString());
  const [tpInput, setTpInput] = useState(tpPct.toString());

  const handleConfigSave = () => {
    const sl = parseFloat(slInput);
    const tp = parseFloat(tpInput);
    if (!isNaN(sl) && sl > 0 && sl < 50 && !isNaN(tp) && tp > 0 && tp < 50) {
      onConfigChange(sl, tp);
      setShowConfig(false);
    }
  };

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg p-4 shadow-xl">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#1e222d]">
        <div className="flex items-center gap-2">
          <Settings size={18} className="text-slate-400" />
          <h2 className="font-bold text-slate-200">Simulation Control</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* SL/TP Display */}
        <div className="grid grid-cols-2 gap-3 pb-1">
          <div className="bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1">
              <Shield size={12} className="text-rose-400" />
              <span className="text-[10px] uppercase font-bold text-slate-500">Stop Loss</span>
            </div>
            <span className="text-sm font-bold text-rose-400 font-mono">-{slPct.toFixed(2)}%</span>
          </div>
          <div className="bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1">
              <Target size={12} className="text-emerald-400" />
              <span className="text-[10px] uppercase font-bold text-slate-500">Take Profit</span>
            </div>
            <span className="text-sm font-bold text-emerald-400 font-mono">+{tpPct.toFixed(2)}%</span>
          </div>
        </div>

        <div className="pt-1">
          {/* Config Toggle */}
          <button
            onClick={() => setShowConfig(!showConfig)}
            className="w-full py-2.5 rounded border border-[#1e222d] text-xs font-bold text-slate-400 hover:text-slate-200 hover:bg-[#1e222d] hover:border-slate-500 transition-all flex items-center justify-center gap-2"
          >
            <Settings size={14} />
            {showConfig ? 'HIDE PARAMETERS' : 'CONFIGURE SL/TP'}
          </button>
        </div>

        {showConfig && (
          <div className="space-y-2 pt-2 border-t border-[#1e222d] animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="space-y-1">
              <label className="text-[10px] uppercase font-bold text-slate-500">Stop Loss %</label>
              <input
                type="number"
                value={slInput}
                onChange={(e) => setSlInput(e.target.value)}
                step="0.1"
                min="0.1"
                max="50"
                className="w-full bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2 text-sm text-rose-400 font-mono focus:border-rose-500 outline-none"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] uppercase font-bold text-slate-500">Take Profit %</label>
              <input
                type="number"
                value={tpInput}
                onChange={(e) => setTpInput(e.target.value)}
                step="0.1"
                min="0.1"
                max="50"
                className="w-full bg-[#0a0c10] border border-[#1e222d] rounded px-3 py-2 text-sm text-emerald-400 font-mono focus:border-emerald-500 outline-none"
              />
            </div>
            <button
              onClick={handleConfigSave}
              className="w-full py-2 rounded bg-[#2962ff] hover:bg-[#1e50e0] text-white font-bold text-xs transition-all active:scale-95"
            >
              Apply & Restart
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
