"use client";

import { CheckCircle, XCircle } from "lucide-react";

interface EligibilityMonitorProps {
  tokenCount: number;
  positionsCompliant: boolean;
  recentRejections: number;
}

export default function EligibilityMonitor({
  tokenCount,
  positionsCompliant,
  recentRejections,
}: EligibilityMonitorProps) {
  return (
    <div className="card p-6">
      <p className="text-sm text-zinc-500">Eligible Token Validation</p>
      <div className="mt-3 flex items-center gap-3">
        {positionsCompliant ? (
          <CheckCircle className="h-8 w-8 text-green-400" />
        ) : (
          <XCircle className="h-8 w-8 text-red-400" />
        )}
        <div>
          <p className="font-medium">
            {positionsCompliant ? "All positions compliant" : "Compliance issue detected"}
          </p>
          <p className="text-sm text-zinc-500">{tokenCount} eligible BEP-20 tokens</p>
        </div>
      </div>
      {recentRejections > 0 && (
        <p className="mt-3 text-xs text-amber-400">
          {recentRejections} ineligible trade(s) rejected today
        </p>
      )}
    </div>
  );
}
