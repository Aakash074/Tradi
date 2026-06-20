"use client";

import { TrendingDown, TrendingUp } from "lucide-react";

interface PnLCardProps {
  totalReturn: number;
  totalValue: number;
  dailyPnl: number;
}

export default function PnLCard({ totalReturn, totalValue, dailyPnl }: PnLCardProps) {
  const isPositive = totalReturn >= 0;
  const dailyPositive = dailyPnl >= 0;

  return (
    <div className="card glow-accent p-6">
      <p className="text-sm text-zinc-500">Total Return</p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className={`text-3xl font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}>
          {isPositive ? "+" : ""}
          {totalReturn.toFixed(2)}%
        </span>
        {isPositive ? (
          <TrendingUp className="h-5 w-5 text-green-400" />
        ) : (
          <TrendingDown className="h-5 w-5 text-red-400" />
        )}
      </div>
      <div className="mt-4 flex justify-between text-sm">
        <div>
          <p className="text-zinc-500">Portfolio Value</p>
          <p className="font-medium">${totalValue.toLocaleString()}</p>
        </div>
        <div className="text-right">
          <p className="text-zinc-500">Daily PnL</p>
          <p className={dailyPositive ? "text-green-400" : "text-red-400"}>
            {dailyPositive ? "+" : ""}
            {dailyPnl.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  );
}
