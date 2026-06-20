"use client";

const MODES = ["DEFENSIVE", "NORMAL", "AGGRESSIVE"] as const;

const modeStyles: Record<string, string> = {
  DEFENSIVE: "bg-red-500/30 border-red-500 text-red-300",
  NORMAL: "bg-blue-500/30 border-blue-500 text-blue-300",
  AGGRESSIVE: "bg-green-500/30 border-green-500 text-green-300",
};

interface RegimeRadarProps {
  mode?: string;
  metrics?: Record<string, number>;
}

export default function RegimeRadar({ mode = "NORMAL", metrics }: RegimeRadarProps) {
  return (
    <div className="card p-6">
      <p className="mb-1 text-sm font-medium text-zinc-400">Regime Radar</p>
      <p className="mb-4 text-xs text-zinc-500">Layer 1: Vol ratio + Fear &amp; Greed</p>
      <div className="flex justify-center gap-3">
        {MODES.map((m) => (
          <div
            key={m}
            className={`rounded-lg border px-3 py-2 text-center text-xs font-semibold transition-all ${
              m === mode ? modeStyles[m] : "border-zinc-800 bg-zinc-900 text-zinc-600"
            }`}
          >
            {m}
          </div>
        ))}
      </div>
      {metrics && (
        <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div>
            <dt className="text-zinc-500">Vol ratio</dt>
            <dd>{metrics.vol_ratio?.toFixed(2) ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Fear &amp; Greed</dt>
            <dd>{metrics.fear_greed?.toFixed(0) ?? "—"}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
