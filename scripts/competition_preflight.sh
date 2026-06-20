#!/usr/bin/env bash
# Competition readiness checks for Tradi (BNB Hackathon Track 1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass=0
warn=0
fail=0

ok()   { echo -e "${GREEN}✓${NC} $1"; pass=$((pass + 1)); }
warn() { echo -e "${YELLOW}!${NC} $1"; warn=$((warn + 1)); }
bad()  { echo -e "${RED}✗${NC} $1"; fail=$((fail + 1)); }

is_placeholder() {
  local v="$1"
  [[ -z "$v" ]] && return 0
  [[ "$v" == your_* ]] && return 0
  [[ "$v" == *your_* ]] && return 0
  [[ "$v" == secure_password ]] && return 0
  return 1
}

echo "=== Tradi Competition Preflight ==="
echo "Project: $ROOT"
echo ""

# --- .env ---
if [[ -f .env ]]; then
  ok ".env found"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  bad ".env missing — copy from .env.example"
fi

# --- TWAK CLI ---
TWAK_BIN=""
if command -v twak >/dev/null 2>&1; then
  TWAK_BIN="twak"
elif [[ -x "$HOME/.nvm/versions/node/v25.9.0/bin/twak" ]]; then
  TWAK_BIN="$HOME/.nvm/versions/node/v25.9.0/bin/twak"
  export PATH="$(dirname "$TWAK_BIN"):$PATH"
fi

if [[ -n "$TWAK_BIN" ]]; then
  ok "TWAK CLI: $($TWAK_BIN --version 2>/dev/null | tail -1 || echo installed)"
else
  bad "TWAK CLI not found — run: curl -fsSL https://agent-kit.trustwallet.com/install.sh | bash"
fi

# --- TWAK wallet ---
if [[ -n "$TWAK_BIN" ]]; then
  if $TWAK_BIN wallet status 2>/dev/null | grep -q "configured"; then
    ok "TWAK wallet configured"
    ADDR=$($TWAK_BIN wallet address --chain smartchain 2>/dev/null | grep -Eo '0x[a-fA-F0-9]{40}' | head -1 || true)
    if [[ -n "$ADDR" ]]; then
      echo "    Address: $ADDR"
    else
      warn "Could not read BSC wallet address"
    fi
  else
    bad "TWAK wallet not configured — run: twak wallet create --password <password>"
  fi
fi

# --- TWAK competition registration ---
if [[ -n "$TWAK_BIN" ]]; then
  COMPETE_OUT=$($TWAK_BIN compete status 2>/dev/null || true)
  if echo "$COMPETE_OUT" | grep -qE 'registered:\s*true'; then
    ok "TWAK competition registered"
  else
    bad "TWAK competition NOT registered — run: twak compete register --password <password>"
    echo "$COMPETE_OUT" | sed 's/^/    /'
  fi
fi

# --- Env vars ---
if is_placeholder "${TWAK_AGENT_PASSWORD:-}"; then
  bad "TWAK_AGENT_PASSWORD not set (use the password from twak wallet create)"
else
  ok "TWAK_AGENT_PASSWORD set"
fi

if is_placeholder "${CMC_API_KEY:-}"; then
  bad "CMC_API_KEY not set — required for live market data"
else
  ok "CMC_API_KEY set"
fi

if is_placeholder "${TWAK_ACCESS_ID:-}"; then
  warn "TWAK_ACCESS_ID not set (optional for CLI; may be needed for hosted APIs)"
else
  ok "TWAK_ACCESS_ID set"
fi

if is_placeholder "${TWAK_HMAC_SECRET:-}"; then
  warn "TWAK_HMAC_SECRET not set (optional for CLI)"
else
  ok "TWAK_HMAC_SECRET set"
fi

# BNB SDK API key is not required — open-source bnbagent uses WALLET_PASSWORD
ok "BNB SDK: no API key required (open-source bnbagent SDK)"

if [[ "${AGENT_MODE:-paper}" == "competition" ]]; then
  ok "AGENT_MODE=competition"
elif [[ "${AGENT_MODE:-paper}" == "paper" ]]; then
  warn "AGENT_MODE=paper (switch to competition for the hackathon week)"
else
  ok "AGENT_MODE=${AGENT_MODE}"
fi

# --- Python / backend ---
if [[ -d backend/.venv ]]; then
  ok "Python venv: backend/.venv"
  # shellcheck disable=SC1091
  source backend/.venv/bin/activate 2>/dev/null || true
else
  warn "backend/.venv not found — run ./scripts/setup.sh"
fi

if python3 -c "import fastapi, yaml" 2>/dev/null; then
  ok "Python dependencies importable"
else
  bad "Python deps missing — cd backend && pip install -r requirements.txt"
fi

# --- Project files ---
if [[ -f ELIGIBLE_TOKENS.json ]]; then
  COUNT=$(python3 -c "import json; d=json.load(open('ELIGIBLE_TOKENS.json')); print(len(d['tokens'] if isinstance(d,dict) and 'tokens' in d else d))" 2>/dev/null || echo "?")
  ok "ELIGIBLE_TOKENS.json ($COUNT tokens)"
  if [[ "$COUNT" != "?" && "$COUNT" -lt 149 ]]; then
    warn "Expected 149 eligible tokens, found $COUNT"
  fi
else
  bad "ELIGIBLE_TOKENS.json missing"
fi

if [[ -f config/tournament_week.yaml ]]; then
  ok "config/tournament_week.yaml"
else
  bad "config/tournament_week.yaml missing"
fi

# --- Live CMC smoke test ---
if ! is_placeholder "${CMC_API_KEY:-}"; then
  CMC_HTTP=$(curl -s -o /tmp/tradi_cmc_test.json -w "%{http_code}" \
    -H "X-CMC_PRO_API_KEY: ${CMC_API_KEY}" \
    "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol=BNB" || echo "000")
  if [[ "$CMC_HTTP" == "200" ]]; then
    ok "CMC API reachable (HTTP 200)"
  else
    bad "CMC API failed (HTTP $CMC_HTTP) — check key/plan"
  fi
fi

# --- Wallet balance (optional) ---
if [[ -n "$TWAK_BIN" ]] && $TWAK_BIN wallet status 2>/dev/null | grep -q "configured"; then
  BAL_OUT=$($TWAK_BIN wallet balance --chain smartchain 2>/dev/null || true)
  if echo "$BAL_OUT" | grep -qiE 'bnb|balance'; then
    echo ""
    echo "Wallet balance (BSC):"
    echo "$BAL_OUT" | sed 's/^/  /'
    if echo "$BAL_OUT" | grep -qE '0(\.0+)?\s*(BNB|bnb)'; then
      warn "BNB balance may be zero — fund wallet for gas before competition"
    fi
  fi
fi

# --- Summary ---
echo ""
echo "=== Summary ==="
echo -e "  ${GREEN}Pass:${NC} $pass  ${YELLOW}Warn:${NC} $warn  ${RED}Fail:${NC} $fail"
echo ""

if [[ $fail -gt 0 ]]; then
  echo "Not competition-ready. Fix failures above, then re-run:"
  echo "  bash scripts/competition_preflight.sh"
  exit 1
fi

if [[ $warn -gt 0 ]]; then
  echo "Ready with warnings — review items above before June 22."
  exit 0
fi

echo "All checks passed. Start competition dry-run:"
echo "  python -m tradi.agent --mode competition --config config/tournament_week.yaml --live-cmc --duration 2h"
exit 0
