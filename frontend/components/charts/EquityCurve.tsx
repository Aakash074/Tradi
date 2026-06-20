"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

interface EquityCurveProps {
  data: Array<{ time: string; value: number }>;
}

export default function EquityCurve({ data }: EquityCurveProps) {
  if (!data.length) {
    return (
      <div className="card flex h-64 items-center justify-center p-6">
        <p className="text-zinc-500">No equity data yet</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <p className="mb-4 text-sm font-medium text-zinc-400">Equity Curve</p>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f0b90b" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#f0b90b" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" stroke="#52525b" fontSize={11} tickLine={false} />
          <YAxis stroke="#52525b" fontSize={11} tickLine={false} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #27272a",
              borderRadius: "8px",
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#f0b90b"
            fill="url(#equityGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
