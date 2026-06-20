"use client";

import { useEffect, useState } from "react";
import { fetchDashboard } from "@/lib/api";

export default function HistoryPage() {
  const [trades, setTrades] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchDashboard();
        setTrades(data.trade_history ?? []);
      } catch {
        /* backend offline */
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Trade History</h1>
      <p className="mb-8 text-sm text-zinc-500">Closed and open trades with eligibility status</p>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-500">
              <th className="p-4">Time</th>
              <th className="p-4">Strategy</th>
              <th className="p-4">Action</th>
              <th className="p-4">Pair</th>
              <th className="p-4">Amount</th>
              <th className="p-4">Eligible</th>
              <th className="p-4">Tx</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-zinc-500">
                  No trades yet — run a cycle to execute
                </td>
              </tr>
            ) : (
              trades.map((trade, i) => (
                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50">
                  <td className="p-4 font-mono text-xs">
                    {trade.timestamp
                      ? new Date(String(trade.timestamp)).toLocaleString()
                      : "—"}
                  </td>
                  <td className="p-4">
                    <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs">
                      {String(trade.strategy)}
                    </span>
                  </td>
                  <td className="p-4">{String(trade.action)}</td>
                  <td className="p-4">
                    {String(trade.token_from)} → {String(trade.token_to)}
                  </td>
                  <td className="p-4">${Number(trade.amount_usd).toFixed(2)}</td>
                  <td className="p-4">
                    <span
                      className={
                        trade.eligible ? "text-green-400" : "text-red-400"
                      }
                    >
                      {trade.eligible ? "YES" : "NO"}
                    </span>
                  </td>
                  <td className="p-4 font-mono text-xs text-zinc-500">
                    {trade.tx_hash ? String(trade.tx_hash).slice(0, 12) + "..." : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
