"use client";

import { useCallback, useEffect, useState } from "react";
import PnLCard from "@/components/dashboard/PnLCard";
import RiskMonitor from "@/components/dashboard/RiskMonitor";
import EligibilityMonitor from "@/components/dashboard/EligibilityMonitor";
import RegimeBadge from "@/components/dashboard/RegimeBadge";
import RegimeBanner from "@/components/dashboard/RegimeBanner";
import ActivityFeed from "@/components/dashboard/ActivityFeed";
import AgentControls from "@/components/dashboard/AgentControls";
import EquityCurve from "@/components/charts/EquityCurve";
import GhostVsRealChart from "@/components/dashboard/GhostVsRealChart";
import KellyGauge from "@/components/dashboard/KellyGauge";
import RegimeRadar from "@/components/dashboard/RegimeRadar";
import MicrostructureHeatmap from "@/components/dashboard/MicrostructureHeatmap";
import CorrelationMatrix from "@/components/dashboard/CorrelationMatrix";
import {
  fetchDashboard,
  startAgent,
  stopAgent,
  runCycle,
  type DashboardState,
} from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [equityHistory, setEquityHistory] = useState<Array<{ time: string; value: number }>>([]);

  const regimeMode = data?.regime_mode ?? data?.confluence?.regime_mode ?? "NORMAL";

  const load = useCallback(async () => {
    try {
      const state = await fetchDashboard();
      setData(state);
      setError(null);
      setEquityHistory((prev) => {
        const point = {
          time: new Date().toLocaleTimeString(),
          value: state.portfolio.total_value_usd,
        };
        const next = [...prev, point];
        return next.slice(-30);
      });
    } catch {
      setError("Backend unavailable — start the FastAPI server on port 8000");
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const handleAction = async (action: () => Promise<unknown>) => {
    setLoading(true);
    try {
      await action();
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const rejections =
    data?.activity_log.filter((l) => !l.eligible && l.action === "REJECTED").length ?? 0;

  const ghost = data?.ghost ?? data?.confluence?.ghost;

  return (
    <div className="p-6 md:p-8">
      <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-zinc-500">
            Three-Layer Confluence · BNB Hackathon Track 1
          </p>
        </div>
        <AgentControls
          mode={data?.mode ?? "paper"}
          onStart={() => handleAction(startAgent)}
          onStop={() => handleAction(stopAgent)}
          onCycle={() => handleAction(runCycle)}
          loading={loading}
        />
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          {error}
        </div>
      )}

      <div className="mb-6">
        <RegimeBanner
          regime={regimeMode}
          activeStrategy="Three-Layer Confluence"
          regimeDisplay={data?.regime_display}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <PnLCard
          totalReturn={data?.portfolio.total_return_pct ?? 0}
          totalValue={data?.portfolio.total_value_usd ?? 10000}
          dailyPnl={data?.portfolio.daily_pnl_pct ?? 0}
          unrealizedPnl={data?.portfolio.unrealized_pnl_pct ?? 0}
          cashUsd={data?.portfolio.cash_usd}
        />
        <RiskMonitor
          drawdown={data?.portfolio.drawdown_pct ?? 0}
          maxDq={30}
          activeBreakers={data?.risk.active_breakers ?? []}
          isDisqualified={data?.risk.is_disqualified ?? false}
        />
        <RegimeBadge regime={regimeMode} activeStrategy="Confluence Engine" />
        <div className="card p-6">
          <p className="text-sm text-zinc-500">Today&apos;s Trades</p>
          <p className="mt-2 text-3xl font-bold">{data?.portfolio.trades_today ?? 0}</p>
          <p className="mt-2 text-xs text-zinc-500">Minimum 1 trade/day required</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EquityCurve data={equityHistory} />
        </div>
        <EligibilityMonitor
          tokenCount={data?.eligible_token_count ?? 149}
          positionsCompliant
          recentRejections={rejections}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <GhostVsRealChart ghost={ghost} />
        <KellyGauge
          optimalPct={data?.kelly_gauge?.optimal_pct ?? 0}
          regimeMode={regimeMode}
          multiplier={data?.confluence?.russian_doll?.position_size_multiplier}
        />
        <RegimeRadar mode={regimeMode} metrics={data?.confluence?.regime_metrics} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <MicrostructureHeatmap data={data?.microstructure_heatmap} />
        <CorrelationMatrix matrix={data?.correlation_matrix} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ActivityFeed logs={data?.activity_log ?? []} />
        <div className="card p-6">
          <p className="mb-4 text-sm font-medium text-zinc-400">Agent Status</p>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-zinc-500">Wallet</dt>
              <dd className="font-mono text-xs text-zinc-300">
                {data?.wallet_address
                  ? `${data.wallet_address.slice(0, 8)}...${data.wallet_address.slice(-6)}`
                  : "—"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Russian Doll</dt>
              <dd className="text-xs text-zinc-300">
                {data?.confluence?.russian_doll?.trading_halted
                  ? "HALTED"
                  : `${((data?.confluence?.russian_doll?.position_size_multiplier ?? 1) * 100).toFixed(0)}% size`}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">TWAK Registered</dt>
              <dd className={data?.twak_registered ? "text-green-400" : "text-zinc-500"}>
                {data?.twak_registered ? "Yes" : "No"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Agent ID (ERC-8004)</dt>
              <dd className="font-mono text-xs text-zinc-300">{data?.agent_id ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Open Positions</dt>
              <dd>{data?.open_positions.length ?? 0}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
