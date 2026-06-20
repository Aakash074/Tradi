"use client";

import { useEffect, useState } from "react";
import RiskMonitor from "@/components/dashboard/RiskMonitor";
import { fetchDashboard, fetchRisk } from "@/lib/api";

const RISK_LAYERS = [
  { key: "soft_halt", level: "20%", label: "Soft Halt", action: "Pause 24h, reduce sizes 50%" },
  { key: "medium_halt", level: "25%", label: "Medium Halt", action: "Pause 48h, manual review" },
  { key: "hard_halt", level: "28%", label: "Hard Halt", action: "Liquidate all, manual reset required" },
  { key: "dq_line", level: "30%", label: "DQ Line", action: "Disqualified (competition rule)" },
];

export default function RiskPage() {
  const [portfolio, setPortfolio] = useState({ drawdown_pct: 0, daily_pnl_pct: 0 });
  const [risk, setRisk] = useState({
    is_disqualified: false,
    requires_liquidation: false,
    active_breakers: [] as Array<{ type: string; reason: string; expires_at: string | null }>,
    max_drawdown_dq: 30,
    risk_layers: {} as Record<string, number>,
    reentry_throttle_hours: 4,
  });

  useEffect(() => {
    const load = async () => {
      try {
        const [dash, riskData] = await Promise.all([fetchDashboard(), fetchRisk()]);
        setPortfolio(dash.portfolio);
        setRisk({
          is_disqualified: riskData.is_disqualified,
          requires_liquidation: riskData.requires_liquidation ?? false,
          active_breakers: riskData.active_breakers,
          max_drawdown_dq: riskData.max_drawdown_dq,
          risk_layers: riskData.risk_layers ?? {},
          reentry_throttle_hours: riskData.reentry_throttle_hours ?? riskData.min_reentry_hours ?? 4,
        });
      } catch {
        /* backend offline */
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  const dd = portfolio.drawdown_pct / 100;

  return (
    <div className="p-6 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Risk Monitor</h1>
      <p className="mb-8 text-sm text-zinc-500">Multi-layer kill switch, reentry throttle, and dynamic risk budgeting</p>

      {risk.requires_liquidation && (
        <div className="mb-6 rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          HARD HALT ACTIVE — All positions must be liquidated. Manual reset required to resume.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <RiskMonitor
          drawdown={portfolio.drawdown_pct}
          maxDq={risk.max_drawdown_dq}
          activeBreakers={risk.active_breakers}
          isDisqualified={risk.is_disqualified}
        />

        <div className="card p-6">
          <p className="mb-4 text-sm font-medium text-zinc-400">Kill Switch Layers</p>
          <div className="space-y-3">
            {RISK_LAYERS.map((layer) => {
              const threshold = risk.risk_layers[layer.key] ?? parseFloat(layer.level) / 100;
              const triggered = dd >= threshold;
              return (
                <div
                  key={layer.key}
                  className={`flex items-center justify-between rounded-lg border px-4 py-3 ${
                    triggered
                      ? "border-red-500/30 bg-red-500/10"
                      : "border-zinc-800 bg-zinc-900/30"
                  }`}
                >
                  <div>
                    <p className="font-medium">
                      {layer.label} ({layer.level})
                    </p>
                    <p className="text-xs text-zinc-500">{layer.action}</p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      triggered ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"
                    }`}
                  >
                    {triggered ? "TRIGGERED" : "OK"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="card p-6">
          <p className="text-2xl font-bold text-accent">25%</p>
          <p className="text-sm text-zinc-500">Max single position</p>
        </div>
        <div className="card p-6">
          <p className="text-2xl font-bold">{risk.reentry_throttle_hours}h</p>
          <p className="text-sm text-zinc-500">Reentry throttle cooldown (2h)</p>
        </div>
        <div className="card p-6">
          <p className="text-2xl font-bold">15%</p>
          <p className="text-sm text-zinc-500">Dynamic risk budget base (scales with drawdown)</p>
        </div>
      </div>

      <div className="mt-6 card p-6">
        <p className="mb-4 text-sm font-medium text-zinc-400">Profit Protection Scaling</p>
        <div className="grid gap-3 md:grid-cols-3 text-sm">
          <div className="rounded-lg border border-zinc-800 p-3">
            <p className="font-medium text-green-400">+10% gain</p>
            <p className="text-zinc-500">Trim to 15% max exposure</p>
          </div>
          <div className="rounded-lg border border-zinc-800 p-3">
            <p className="font-medium text-green-400">+20% gain</p>
            <p className="text-zinc-500">Trim to 10% max exposure</p>
          </div>
          <div className="rounded-lg border border-zinc-800 p-3">
            <p className="font-medium text-green-400">+35% gain</p>
            <p className="text-zinc-500">Trim to 5% max exposure</p>
          </div>
        </div>
      </div>
    </div>
  );
}
