"use client";

import React from 'react';
import { Shield, Zap, Target, Cpu, TrendingUp, AlertCircle, Info } from 'lucide-react';

interface AIControlPanelProps {
  config: Record<string, any>;
}

export const AIControlPanel: React.FC<AIControlPanelProps> = ({ config }) => {
  // Define parameters we want to track specifically
  const trackedParams = [
    { key: 'min_confidence', label: 'MIN CONFIDENCE', icon: <Target size={10} />, format: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: 'stop_loss_pct', label: 'STOP LOSS', icon: <Shield size={10} />, format: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: 'take_profit_pct', label: 'TAKE PROFIT', icon: <TrendingUp size={10} />, format: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: 'position_size_pct', label: 'POS SIZE MAX', icon: <Zap size={10} />, format: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: 'ml_weight', label: 'ML WEIGHT', icon: <Cpu size={10} />, format: (v: number) => `${(v * 100).toFixed(1)}%` },
  ];

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded overflow-hidden shadow-2xl flex flex-col h-full font-mono">
      {/* HEADER */}
      <div className="flex items-center justify-between p-2 border-b border-[#1e222d] bg-black/40">
        <div className="flex items-center gap-2">
          <Cpu size={14} className="text-amber-500 animate-pulse" />
          <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-100 italic">
            Neural Control Center <span className="text-amber-500">v2.0</span>
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[8px] font-black text-slate-500 uppercase tracking-tighter">
            AI OVERRIDE ACTIVE
          </span>
          <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shadow-lg shadow-amber-500/50" />
        </div>
      </div>

      {/* PARAMETERS GRID */}
      <div className="flex-1 overflow-y-auto p-2 grid grid-cols-2 gap-2 content-start">
        {trackedParams.map((param) => {
          const val = config[param.key];
          const isOverridden = val !== undefined; // In a real scenario, compare with base defaults
          
          return (
            <div key={param.key} className={`relative bg-black/40 border border-[#1e222d] rounded p-2 overflow-hidden group hover:border-amber-500/30 transition-colors`}>
              {isOverridden && (
                <div className="absolute top-0 right-0 p-0.5 bg-amber-500/10 rounded-bl">
                   <Info size={8} className="text-amber-500" />
                </div>
              )}
              
              <div className="flex items-center gap-1.5 text-[8px] font-black text-slate-500 uppercase mb-1">
                {param.icon}
                {param.label}
              </div>
              
              <div className="flex items-baseline justify-between">
                <span className={`text-[11px] font-black ${isOverridden ? 'text-amber-400' : 'text-slate-300'}`}>
                  {val !== undefined ? param.format(val) : '---'}
                </span>
                <span className="text-[7px] text-slate-600 italic">
                   {isOverridden ? 'ADAPTIVE' : 'BASE'}
                </span>
              </div>
              
              {/* Micro Sparkline / Progress Placeholder */}
              <div className="mt-1.5 h-1 w-full bg-slate-900 rounded-full overflow-hidden">
                 <div 
                   className={`h-full transition-all duration-1000 ${isOverridden ? 'bg-amber-500/60' : 'bg-slate-700'}`} 
                   style={{ width: `${(val || 0.5) * 100}%` }} 
                 />
              </div>
            </div>
          );
        })}
      </div>

      {/* LOWER STATUS */}
      <div className="p-1 px-2 border-t border-[#1e222d] bg-black/20 flex flex-col gap-1">
         <div className="flex justify-between items-center text-[7px] font-black uppercase tracking-tighter">
            <span className="text-slate-500">Atomic Trio Confidence Gate</span>
            <span className="text-emerald-400">ENABLED</span>
         </div>
         <div className="flex gap-1">
            <div className="flex-1 h-1 bg-emerald-500/20 rounded-full overflow-hidden">
               <div className="h-full bg-emerald-500 w-[75%] animate-pulse" />
            </div>
         </div>
      </div>
    </div>
  );
};
