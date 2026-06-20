"use client";

interface ActivityFeedProps {
  logs: Array<{
    timestamp: string;
    strategy: string;
    action: string;
    token: string;
    message: string;
    eligible: boolean;
  }>;
}

export default function ActivityFeed({ logs }: ActivityFeedProps) {
  if (!logs.length) {
    return (
      <div className="card p-6">
        <p className="text-sm font-medium text-zinc-400">Activity Feed</p>
        <p className="mt-4 text-sm text-zinc-500">Waiting for agent activity...</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <p className="mb-4 text-sm font-medium text-zinc-400">Activity Feed</p>
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {logs.map((log, i) => {
          const time = new Date(log.timestamp).toLocaleTimeString();
          return (
            <div
              key={i}
              className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-3 py-2 font-mono text-xs"
            >
              <span className="text-zinc-500">{time}</span>{" "}
              <span className="text-accent">[{log.strategy}]</span>{" "}
              <span className="font-medium">{log.action}</span>{" "}
              <span className="text-zinc-300">{log.token}</span>{" "}
              <span className="text-zinc-500">{log.message}</span>{" "}
              <span className={log.eligible ? "text-green-400" : "text-red-400"}>
                [ELIGIBLE: {log.eligible ? "YES" : "NO"}]
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
