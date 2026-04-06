import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Percent, Activity, Shield } from 'lucide-react';

interface SimSnapshot {
  equity: number;
  cash: number;
  realized_pnl: number;
  total_commissions: number;
  position_value: number;
  current_price: number;
  open_positions: any[];
  trade_history: any[];
  adaptive: any;
}

interface ExpertStatsProps {
  snapshot: SimSnapshot;
}

export const ExpertStats: React.FC<ExpertStatsProps> = ({ snapshot }) => {
  const sessionGrowth = ((snapshot.equity - 1000) / 1000) * 100;
  const unrealizedPnL = snapshot.position_value !== 0 ? snapshot.equity - snapshot.cash - snapshot.realized_pnl : 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-px bg-[#1e222d] border border-[#1e222d] rounded-lg overflow-hidden shadow-2xl">
      <StatItem 
        label="BTC Price" 
        value={`$${snapshot.current_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} 
        subValue="Live WebSocket"
        color="text-blue-400"
        icon={<Activity size={18} className="text-blue-400 animate-pulse" />}
      />
      <StatItem 
        label="Total Equity" 
        value={`$${snapshot.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} 
        subValue="Account Balance"
        icon={<DollarSign size={18} className="text-blue-400" />}
      />
      <StatItem 
        label="Cash" 
        value={`$${snapshot.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} 
        subValue="Available Margin"
        icon={<Activity size={18} className="text-slate-400" />}
      />
      <StatItem 
        label="Realized PnL" 
        value={`${snapshot.realized_pnl >= 0 ? '+' : ''}$${snapshot.realized_pnl.toFixed(2)}`} 
        subValue="Closed Trades"
        color={snapshot.realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
        icon={snapshot.realized_pnl >= 0 ? <TrendingUp size={18} className="text-emerald-400" /> : <TrendingDown size={18} className="text-rose-400" />}
      />
      <StatItem 
        label="Unrealized PnL" 
        value={`${unrealizedPnL >= 0 ? '+' : ''}$${unrealizedPnL.toFixed(2)}`} 
        subValue="Open Risk"
        color={unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}
        icon={<Activity size={18} className="text-amber-400" />}
      />
      <StatItem 
        label="Total Fees" 
        value={`$${snapshot.total_commissions.toFixed(2)}`} 
        subValue="Brokerage Cost"
        icon={<Percent size={18} className="text-rose-400" />}
      />
      <StatItem 
        label="Exp. Value (EV)" 
        value={`${snapshot.adaptive.expected_value >= 0 ? '+' : ''}${snapshot.adaptive.expected_value.toFixed(4)}`} 
        subValue="Profit per Trade"
        color={snapshot.adaptive.expected_value >= 0 ? 'text-emerald-400' : 'text-rose-400'}
        icon={<Shield size={18} className="text-blue-400" />}
      />
      <StatItem 
        label="Growth Rate" 
        value={`${sessionGrowth >= 0 ? '+' : ''}${sessionGrowth.toFixed(2)}%`} 
        subValue="Session Performance"
        color={sessionGrowth >= 0 ? 'text-emerald-400' : 'text-rose-400'}
        icon={<TrendingUp size={18} className="text-emerald-400" />}
      />
    </div>
  );
};

function StatItem({ label, value, subValue, color = 'text-white', icon }: { label: string, value: string, subValue: string, color?: string, icon?: React.ReactNode }) {
  return (
    <div className="bg-[#161a25] p-5 border-r border-b border-[#1e222d] last:border-r-0">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-[11px] font-black uppercase tracking-widest text-slate-500">{label}</span>
      </div>
      <div className={`text-xl font-black tracking-tighter ${color}`}>{value}</div>
      <div className="text-[10px] text-slate-600 font-medium uppercase mt-1 px-1 border-l-2 border-slate-800 ml-0.5">{subValue}</div>
    </div>
  );
}
