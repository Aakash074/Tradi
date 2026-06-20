"use client";

interface KellyGaugeProps {
  optimalPct?: number;
  regimeMode?: string;
  multiplier?: number;
}

export default function KellyGauge({ optimalPct = 0, regimeMode = "NORMAL", multiplier }: KellyGaugeProps) {
  const pct = Math.min(100, optimalPct);
  const regimeMult = regimeMode === "AGGRESSIVE" ? 1.0 : regimeMode === "NORMAL" ? 0.5 : 0;

  return (
    <div className="card p-6">
      <p className="mb-1 text-sm font-medium text-zinc-400">Kelly Sizing Gauge</p>
      <p className="mb-4 text-xs text-zinc-500">Half-Kelly optimal bet vs regime multiplier</p>
      <div className="relative mx-auto h-32 w-32">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle cx="50" cy="50" r="42" fill="none" stroke="#27272a" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="#f0b90b"
            strokeWidth="8"
            strokeDasharray={`${pct * 2.64} 264`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold">{optimalPct.toFixed(1)}%</span>
          <span className="text-xs text-zinc-500">of portfolio</span>
        </div>
      </div>
      <dl className="mt-4 space-y-2 text-xs">
        <div className="flex justify-between">
          <dt className="text-zinc-500">Regime multiplier</dt>
          <dd>{multiplier ?? regimeMult}x ({regimeMode})</dd>
        </div>
      </dl>
    </div>
  );
}
