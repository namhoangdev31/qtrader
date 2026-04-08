"use client";

import React from 'react';
import { TickerTape, MiniChart } from "react-ts-tradingview-widgets";

export const MiniTradingView: React.FC = () => {
  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded overflow-hidden shadow-lg flex flex-col gap-0.5">
      <div className="h-[40px] opacity-80 overflow-hidden">
        <TickerTape 
          colorTheme="dark"
          symbols={[
            { proName: "COINBASE:BTCUSD", title: "BTC/USD" },
            { proName: "COINBASE:ETHUSD", title: "ETH/USD" },
            { proName: "BINANCE:SOLUSDT", title: "SOL/USDT" }
          ]}
          displayMode="compact"
        />
      </div>
      <div className="h-[250px] w-full bg-black/40">
        <MiniChart 
          symbol="COINBASE:BTCUSD"
          colorTheme="dark"
          width="100%"
          height={250}
          dateRange="1D"
          trendLineColor="#2962ff"
          underLineColor="rgba(41, 98, 255, 0.3)"
          isTransparent
          autosize
        />
      </div>
    </div>
  );
};
