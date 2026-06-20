# Tradi Competition Compliance

## Eligible Tokens

Only the 149 BEP-20 tokens in `ELIGIBLE_TOKENS.json` may be traded. Every trade validates **both** FROM and TO tokens before execution.

## Trading Constraints

| Rule | Tradi Implementation |
|------|---------------------|
| Venue | PancakeSwap V2/V3 spot only via TWAK |
| No leverage/perps | Spot swaps only |
| Max position 34% | Hard cap at 25% in `risk_manager.py` |
| Min 1 trade/day | Keepalive logic at 20:00 UTC |
| Registration | `twak compete register` via API init |

## Risk Gates (Hard Coded)

| Threshold | Action |
|-----------|--------|
| 20% drawdown | Halt 24h, reduce sizes 50% |
| 25% drawdown | Halt 48h, manual review |
| 30% drawdown | DISQUALIFIED |
| 10% daily loss | Halt until next UTC day |
| 3 consecutive losses | Halt 4 hours |

## Validation Flow

```
Signal → token_validator.is_eligible() → validate_pair() → risk_manager.validate_trade() → TWAK execute
```

Rejected trades are logged with `[ELIGIBLE: NO]` in the activity feed.

## Pre-Launch Checklist

- [ ] All strategies generate signals in paper mode
- [ ] Non-eligible tokens blocked
- [ ] Circuit breakers trigger on simulated drawdown
- [ ] TWAK registration successful
- [ ] Dashboard shows real-time compliance status
- [ ] Wallet keys backed up
