"use client";

interface GhostStats {
  ghost_win_rate: number;
  ghost_cumulative_pnl_pct: number;
  real_cumulative_pnl_pct: number;
  ghost_count: number;
  real_trade_count: number;
}

export default function GhostVsRealChart({ ghost }: { ghost?: GhostStats }) {
  const ghostPnl = ghost?.ghost_cumulative_pnl_pct ?? 0;
  const realPnl = ghost?.real_cumulative_pnl_pct ?? 0;
  const maxVal = Math.max(Math.abs(ghostPnl), Math.abs(realPnl), 1);

  return (
    <div className="card p-6">
      <p className="mb-1 text-sm font-medium text-zinc-400">Ghost vs Real PnL</p>
      <p className="mb-4 text-xs text-zinc-500">
        Shadow book validates signals before execution ({ghost?.ghost_count ?? 0} ghosts)
      </p>
      <div className="space-y-4">
        <div>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-purple-400">Ghost (all signals)</span>
            <span className={ghostPnl >= 0 ? "text-green-400" : "text-red-400"}>
              {ghostPnl >= 0 ? "+" : ""}
              {ghostPnl.toFixed(2)}%
            </span>
          </div>
          <div className="h-3 rounded-full bg-zinc-800">
            <div
              className="h-3 rounded-full bg-purple-500/70"
              style={{ width: `${Math.min(100, (Math.abs(ghostPnl) / maxVal) * 100)}%` }}
            />
          </div>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-accent">Real (executed)</span>
            <span className={realPnl >= 0 ? "text-green-400" : "text-red-400"}>
              {realPnl >= 0 ? "+" : ""}
              {realPnl.toFixed(2)}%
            </span>
          </div>
          <div className="h-3 rounded-full bg-zinc-800">
            <div
              className="h-3 rounded-full bg-accent/70"
              style={{ width: `${Math.min(100, (Math.abs(realPnl) / maxVal) * 100)}%` }}
            />
          </div>
        </div>
        <p className="text-xs text-zinc-500">
          Ghost win rate: {ghost?.ghost_win_rate ?? 0}% · Real trades: {ghost?.real_trade_count ?? 0}
        </p>
      </div>
    </div>
  );
}
