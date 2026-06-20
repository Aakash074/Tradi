"use client";

import { useEffect, useState } from "react";
import { fetchDashboard } from "@/lib/api";
import RegimeBanner from "@/components/dashboard/RegimeBanner";
import GhostVsRealChart from "@/components/dashboard/GhostVsRealChart";
import KellyGauge from "@/components/dashboard/KellyGauge";
import RegimeRadar from "@/components/dashboard/RegimeRadar";

export default function StrategiesPage() {
  const [data, setData] = useState<{
    regime_mode: string;
    regime_display: string;
    confluence: Record<string, unknown> | null;
    ghost: Record<string, unknown> | null;
    kelly_gauge: { optimal_pct: number } | null;
    strategies: Array<{ name: string; weight: string }>;
  }>({
    regime_mode: "NORMAL",
    regime_display: "",
    confluence: null,
    ghost: null,
    kelly_gauge: null,
    strategies: [],
  });

  useEffect(() => {
    const load = async () => {
      try {
        const dash = await fetchDashboard();
        setData({
          regime_mode: dash.regime_mode ?? dash.confluence?.regime_mode ?? "NORMAL",
          regime_display: dash.regime_display ?? "",
          confluence: dash.confluence ?? null,
          ghost: dash.ghost ?? dash.confluence?.ghost ?? null,
          kelly_gauge: dash.kelly_gauge ?? null,
          strategies: dash.strategies ?? [],
        });
      } catch {
        /* backend offline */
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const strategies = data.strategies.length
    ? data.strategies.map((s) => ({
        name: s.name,
        allocation: s.weight,
        description: getDescription(s.name),
        active: true,
      }))
    : [
        {
          name: "Momentum Pullback",
          allocation: "100%",
          description: "Buy RSI pullbacks (30–45) in uptrends above 20 EMA with volume confirmation",
          active: true,
        },
      ];

  return (
    <div className="p-6 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Strategies</h1>
      <p className="mb-6 text-sm text-zinc-500">Three-Layer Confluence model with ghost validation</p>

      <div className="mb-8">
        <RegimeBanner
          regime={data.regime_mode}
          activeStrategy="Three-Layer Confluence"
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

      <div className="grid gap-6 lg:grid-cols-3">
        <GhostVsRealChart ghost={data.ghost as Parameters<typeof GhostVsRealChart>[0]["ghost"]} />
        <KellyGauge
          optimalPct={data.kelly_gauge?.optimal_pct ?? 0}
          regimeMode={data.regime_mode}
        />
        <RegimeRadar
          mode={data.regime_mode}
          metrics={(data.confluence?.regime_metrics as Record<string, number>) ?? undefined}
        />
      </div>
    </div>
  );
}

function getDescription(name: string): string {
  const map: Record<string, string> = {
    "Momentum Pullback": "RSI pullback in uptrend above 20 EMA",
    "Funding Flow": "Deprecated — replaced by momentum pullback",
    "Microstructure MR": "Deprecated",
    "Kelly Momentum": "Deprecated",
  };
  return map[name] ?? "V2 momentum strategy";
}
