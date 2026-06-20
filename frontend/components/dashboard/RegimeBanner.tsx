"use client";

import { motion } from "framer-motion";

const regimeColors: Record<string, string> = {
  DEFENSIVE: "border-red-500/40 bg-red-500/10 text-red-400",
  NORMAL: "border-blue-500/40 bg-blue-500/10 text-blue-400",
  AGGRESSIVE: "border-green-500/40 bg-green-500/10 text-green-400",
  TRENDING: "border-green-500/40 bg-green-500/10 text-green-400",
  RANGING: "border-blue-500/40 bg-blue-500/10 text-blue-400",
  VOLATILE: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  ACCUMULATION: "border-purple-500/40 bg-purple-500/10 text-purple-400",
};

interface RegimeBannerProps {
  regime: string;
  activeStrategy: string;
  regimeDisplay?: string;
}

export default function RegimeBanner({ regime, activeStrategy, regimeDisplay }: RegimeBannerProps) {
  const colorClass = regimeColors[regime] || regimeColors.ACCUMULATION;
  const display = regimeDisplay || `Market State: ${regime} — Using ${activeStrategy}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border px-6 py-4 ${colorClass}`}
    >
      <p className="text-lg font-semibold">{display}</p>
      <p className="mt-1 text-sm opacity-80">
        Vol ratio + Fear &amp; Greed · DEFENSIVE / NORMAL / AGGRESSIVE sizing
      </p>
    </motion.div>
  );
}
