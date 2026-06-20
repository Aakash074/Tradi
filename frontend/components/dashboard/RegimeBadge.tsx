"use client";

import { motion } from "framer-motion";

const regimeColors: Record<string, string> = {
  DEFENSIVE: "bg-red-500/20 text-red-400 border-red-500/30",
  NORMAL: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  AGGRESSIVE: "bg-green-500/20 text-green-400 border-green-500/30",
  TRENDING: "bg-green-500/20 text-green-400 border-green-500/30",
  RANGING: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  VOLATILE: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  ACCUMULATION: "bg-purple-500/20 text-purple-400 border-purple-500/30",
};

interface RegimeBadgeProps {
  regime: string;
  activeStrategy?: string;
}

export default function RegimeBadge({ regime, activeStrategy }: RegimeBadgeProps) {
  const colorClass = regimeColors[regime] || regimeColors.ACCUMULATION;

  return (
    <motion.div
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="card p-6"
    >
      <p className="text-sm text-zinc-500">Current Regime</p>
      <span
        className={`mt-3 inline-block rounded-full border px-4 py-1.5 text-sm font-semibold ${colorClass}`}
      >
        {regime}
      </span>
      {activeStrategy && (
        <p className="mt-3 text-xs text-zinc-400">Using {activeStrategy}</p>
      )}
    </motion.div>
  );
}
