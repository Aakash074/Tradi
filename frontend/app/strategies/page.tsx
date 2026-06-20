"use client";

import { useEffect, useState } from "react";
import { fetchDashboard } from "@/lib/api";
import RegimeBanner from "@/components/dashboard/RegimeBanner";

export default function StrategiesPage() {
  const [data, setData] = useState<{
    regime: string;
    active_strategy: string;
    regime_display: string;
    whales: Array<Record<string, unknown>>;
    momentum: Record<string, unknown> | null;
  }>({
    regime: "ACCUMULATION",
    active_strategy: "DCA Strategy",
    regime_display: "",
    whales: [],
    momentum: null,
  });

  useEffect(() => {
    const load = async () => {
      try {
        const dash = await fetchDashboard();
        setData({
          regime: dash.regime,
          active_strategy: dash.active_strategy ?? "DCA Strategy",
          regime_display: dash.regime_display ?? "",
          whales: dash.whales ?? [],
          momentum: dash.momentum ?? null,
        });
      } catch {
        /* backend offline */
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const strategies = [
    {
      name: "Market State Adapter",
      allocation: "60%",
      description: "Adapts tactics by market state: TRENDING/RANGING/VOLATILE/ACCUMULATION",
      active: true,
    },
    {
      name: "Smart Money Shadow",
      allocation: "—",
      description: "Disabled until BSC on-chain whale indexer is integrated (simulated signals removed)",
      active: false,
    },
    {
      name: "Momentum Breakout",
      allocation: "15%",
      description:
        "Buy high-momentum eligible tokens breaking 20-period highs with volume confirmation",
      active: true,
    },
  ];

  return (
    <div className="p-6 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Strategies</h1>
      <p className="mb-6 text-sm text-zinc-500">Three adaptive strategies with regime-aware selection</p>

      <div className="mb-8">
        <RegimeBanner
          regime={data.regime}
          activeStrategy={data.active_strategy}
          regimeDisplay={data.regime_display}
        />
      </div>

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        {strategies.map((s) => (
          <div key={s.name} className="card p-6">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{s.name}</h3>
              <span className="rounded-full bg-accent/20 px-2 py-0.5 text-xs text-accent">
                {s.allocation}
              </span>
            </div>
            <p className="mt-3 text-sm text-zinc-500">{s.description}</p>
            <p className={`mt-4 text-xs ${s.active ? "text-green-400" : "text-zinc-500"}`}>
              {s.active ? "● Active" : "○ Disabled"}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <h3 className="mb-4 font-semibold">Whale Watchlist</h3>
          <div className="space-y-3">
            {data.whales.map((w, i) => (
              <div key={i} className="flex justify-between rounded-lg border border-zinc-800 p-3 text-sm">
                <div>
                  <p className="font-mono">{String(w.address)}</p>
                  <p className="text-xs text-zinc-500">{String(w.category)}</p>
                </div>
                <div className="text-right">
                  <p>{(Number(w.win_rate) * 100).toFixed(0)}% win</p>
                  <p className={`text-xs ${w.active ? "text-green-400" : "text-zinc-500"}`}>
                    {w.active ? "Active" : "Paused"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h3 className="mb-4 font-semibold">Momentum Breakout Scanner</h3>
          {data.momentum ? (
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-zinc-500">Eligible tokens scanned</dt>
                <dd>{Number(data.momentum.scan_tokens)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Position size</dt>
                <dd>{Number(data.momentum.position_size_pct)}%</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Hard stop</dt>
                <dd>{Number(data.momentum.stop_loss_pct)}%</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-zinc-500">Max hold</dt>
                <dd>{Number(data.momentum.max_hold_hours)}h</dd>
              </div>
              <div className="mt-4">
                <p className="text-xs text-zinc-500 mb-2">Scan universe (eligible only):</p>
                <div className="flex flex-wrap gap-1">
                  {(data.momentum.eligible_tokens_scanned as string[] | undefined)?.map((t) => (
                    <span key={t} className="rounded bg-zinc-800 px-2 py-0.5 text-xs">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-zinc-500">Loading momentum scanner...</p>
          )}
        </div>
      </div>
    </div>
  );
}
