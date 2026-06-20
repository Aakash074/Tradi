"use client";

import { Play, Square, RefreshCw } from "lucide-react";

interface AgentControlsProps {
  mode: string;
  onStart: () => void;
  onStop: () => void;
  onCycle: () => void;
  loading?: boolean;
}

export default function AgentControls({
  mode,
  onStart,
  onStop,
  onCycle,
  loading,
}: AgentControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs uppercase tracking-wide text-zinc-400">
        {mode} mode
      </span>
      <button
        onClick={onStart}
        disabled={loading}
        className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
      >
        <Play className="h-4 w-4" /> Start Agent
      </button>
      <button
        onClick={onStop}
        disabled={loading}
        className="flex items-center gap-2 rounded-lg bg-red-600/80 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
      >
        <Square className="h-4 w-4" /> Stop
      </button>
      <button
        onClick={onCycle}
        disabled={loading}
        className="flex items-center gap-2 rounded-lg border border-accent/50 bg-accent/10 px-4 py-2 text-sm font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Run Cycle
      </button>
    </div>
  );
}
