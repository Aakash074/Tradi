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
    cash_usd?: number;
    unrealized_pnl_pct?: number;
    unrealized_pnl_usd?: number;
    realized_pnl_usd?: number;
    wallet_synced?: boolean;
    trades_today: number;
    consecutive_losses: number;
  };
  regime?: string;
  regime_mode?: string;
  active_strategy?: string;
  regime_display?: string;
  regime_metrics?: Record<string, number>;
  confluence?: {
    regime_mode: string;
    regime_metrics: Record<string, number>;
    ghost: {
      ghost_win_rate: number;
      ghost_cumulative_pnl_pct: number;
      real_cumulative_pnl_pct: number;
      ghost_count: number;
      real_trade_count: number;
    };
    russian_doll: {
      position_size_multiplier: number;
      max_positions: number;
      trading_halted: boolean;
    };
    strategies: string[];
  };
  ghost?: DashboardState["confluence"] extends { ghost: infer G } ? G : never;
  kelly_gauge?: { optimal_pct: number; regime_multiplier: string };
  microstructure_heatmap?: Array<{
    token: string;
    funding_rate: number;
    funding_signal: string;
    flow_signal: string;
    book_imbalance: number;
  }>;
  correlation_matrix?: Array<{ a: string; b: string; corr: number }>;
  strategies?: Array<{ name: string; weight: string }>;
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
