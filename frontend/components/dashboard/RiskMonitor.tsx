"use client";

interface RiskMonitorProps {
  drawdown: number;
  maxDq: number;
  activeBreakers: Array<{ type: string; reason: string; expires_at: string | null }>;
  isDisqualified: boolean;
}

export default function RiskMonitor({
  drawdown,
  maxDq,
  activeBreakers,
  isDisqualified,
}: RiskMonitorProps) {
  const haltLine = 25;
  const dqLine = maxDq || 30;
  const dangerZone = drawdown >= 20;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-500">Max Drawdown</p>
        {isDisqualified && (
          <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-xs text-red-400">
            DISQUALIFIED
          </span>
        )}
      </div>
      <p className={`mt-2 text-3xl font-bold ${dangerZone ? "text-red-400" : "text-zinc-100"}`}>
        {drawdown.toFixed(2)}%
      </p>

      <div className="relative mt-4 h-3 overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full transition-all ${
            drawdown >= haltLine ? "bg-red-500" : drawdown >= 20 ? "bg-amber-500" : "bg-green-500"
          }`}
          style={{ width: `${Math.min(100, (drawdown / dqLine) * 100)}%` }}
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-amber-500/80"
          style={{ left: `${(haltLine / dqLine) * 100}%` }}
          title="25% halt line"
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-red-500"
          style={{ left: "100%", transform: "translateX(-2px)" }}
          title="30% DQ line"
        />
      </div>
      <div className="mt-2 flex justify-between text-xs text-zinc-500">
        <span>0%</span>
        <span className="text-amber-500">25% halt</span>
        <span className="text-red-500">{dqLine}% DQ</span>
      </div>

      {activeBreakers.length > 0 && (
        <div className="mt-4 space-y-2">
          {activeBreakers.map((b) => (
            <div key={b.type} className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">
              <span className="font-medium">{b.type}</span>: {b.reason}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
