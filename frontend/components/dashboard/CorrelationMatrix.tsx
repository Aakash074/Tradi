"use client";

interface CorrelationEntry {
  a: string;
  b: string;
  corr: number;
}

export default function CorrelationMatrix({ matrix }: { matrix?: CorrelationEntry[] }) {
  const entries = matrix ?? [];

  const corrColor = (c: number) => {
    if (c > 0.8) return "text-red-400";
    if (c < -0.3) return "text-green-400";
    return "text-zinc-400";
  };

  return (
    <div className="card p-6">
      <p className="mb-1 text-sm font-medium text-zinc-400">Correlation Guard</p>
      <p className="mb-4 text-xs text-zinc-500">Position hedging · reject corr &gt; 0.8</p>
      {entries.length === 0 ? (
        <p className="text-sm text-zinc-500">No open positions to correlate</p>
      ) : (
        <div className="space-y-2">
          {entries.map((e) => (
            <div
              key={`${e.a}-${e.b}`}
              className="flex items-center justify-between rounded border border-zinc-800 px-3 py-2 text-sm"
            >
              <span className="font-mono text-xs">
                {e.a} / {e.b}
              </span>
              <span className={`font-semibold ${corrColor(e.corr)}`}>{e.corr.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
