"use client";

import React from 'react';
import { AdvancedRealTimeChart } from "react-ts-tradingview-widgets";

export const TradingChart: React.FC = () => {
  return (
    <div className="relative w-full h-[600px] border border-[#1e222d] rounded-lg overflow-hidden bg-[#0a0c10] shadow-2xl">
      <AdvancedRealTimeChart 
        symbol="COINBASE:BTCUSD"
        theme="dark"
        autosize
        interval="1"
        timezone="Etc/UTC"
        style="1"
        locale="en"
        toolbar_bg="#131722"
        enable_publishing={false}
        allow_symbol_change={true}
        container_id="tradingview_qtrader"
      />
    </div>
  );
};
