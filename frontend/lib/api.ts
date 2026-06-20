const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchDashboard() {
  const res = await fetch(`${API_URL}/api/dashboard`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function fetchRisk() {
  const res = await fetch(`${API_URL}/api/risk`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch risk");
  return res.json();
}

export async function fetchEligibleTokens() {
  const res = await fetch(`${API_URL}/api/eligible-tokens`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch tokens");
  return res.json();
}

export async function runCycle() {
  const res = await fetch(`${API_URL}/api/agent/cycle`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to run cycle");
  return res.json();
}

export async function startAgent() {
  const res = await fetch(`${API_URL}/api/agent/start`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to start agent");
  return res.json();
}

export async function stopAgent() {
  const res = await fetch(`${API_URL}/api/agent/stop`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to stop agent");
  return res.json();
}

export type DashboardState = {
  agent_name: string;
  mode: string;
  portfolio: {
    total_value_usd: number;
    total_return_pct: number;
    drawdown_pct: number;
    daily_pnl_pct: number;
    trades_today: number;
    consecutive_losses: number;
  };
  regime: string;
  active_strategy?: string;
  regime_display?: string;
  regime_metrics?: Record<string, number>;
  risk: {
    is_disqualified: boolean;
    requires_liquidation?: boolean;
    position_size_multiplier: number;
    risk_layers?: Record<string, number>;
    reentry_throttle_hours?: number;
    min_reentry_hours?: number;
    active_breakers: Array<{
      type: string;
      reason: string;
      expires_at: string | null;
      requires_manual_reset?: boolean;
    }>;
  };
  open_positions: Array<Record<string, unknown>>;
  trade_history: Array<Record<string, unknown>>;
  activity_log: Array<{
    timestamp: string;
    strategy: string;
    action: string;
    token: string;
    message: string;
    eligible: boolean;
  }>;
  whales: Array<Record<string, unknown>>;
  momentum?: {
    strategy: string;
    scan_tokens: number;
    position_size_pct: number;
    stop_loss_pct: number;
    max_hold_hours: number;
    eligible_tokens_scanned: string[];
  };
  eligible_token_count: number;
  x402_stats: { payments_count: number; total_cost_usd: number };
  wallet_address: string | null;
  twak_registered: boolean;
  agent_id: string | null;
};
