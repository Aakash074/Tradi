"use client";

interface HeatmapRow {
  token: string;
  funding_rate: number;
  funding_signal: string;
  flow_signal: string;
  book_imbalance: number;
}

export default function MicrostructureHeatmap({ data }: { data?: HeatmapRow[] }) {
  const rows = data ?? [];

  const cellColor = (signal: string) => {
    if (signal.includes("BULLISH") || signal === "ACCUMULATION") return "bg-green-500/30 text-green-300";
    if (signal.includes("BEARISH") || signal === "DISTRIBUTION") return "bg-red-500/30 text-red-300";
    return "bg-zinc-800 text-zinc-500";
  };

  return (
    <div className="card p-6">
      <p className="mb-1 text-sm font-medium text-zinc-400">Microstructure Heatmap</p>
      <p className="mb-4 text-xs text-zinc-500">Funding · flows · order book imbalance</p>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-zinc-500">
              <th className="pb-2">Token</th>
              <th className="pb-2">Funding</th>
              <th className="pb-2">Flow</th>
              <th className="pb-2">Book</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-4 text-zinc-500">
                  No heatmap data — start backend
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.token} className="border-t border-zinc-800">
                  <td className="py-2 font-mono">{r.token}</td>
                  <td className="py-2">
                    <span className={`rounded px-1.5 py-0.5 ${cellColor(r.funding_signal)}`}>
                      {(r.funding_rate * 100).toFixed(3)}%
                    </span>
                  </td>
                  <td className="py-2">
                    <span className={`rounded px-1.5 py-0.5 ${cellColor(r.flow_signal)}`}>
                      {r.flow_signal.slice(0, 4)}
                    </span>
                  </td>
                  <td className="py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 ${
                        r.book_imbalance > 0.3
                          ? "bg-green-500/30 text-green-300"
                          : r.book_imbalance < -0.3
                            ? "bg-red-500/30 text-red-300"
                            : "bg-zinc-800 text-zinc-500"
                      }`}
                    >
                      {r.book_imbalance.toFixed(2)}
                    </span>
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
