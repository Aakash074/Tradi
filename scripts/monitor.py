#!/usr/bin/env python3
"""CLI monitor for Tradi agent status."""

import argparse
import json
import sys
import urllib.request


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Monitor Tradi trading agent")
    parser.add_argument("--api", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    args = parser.parse_args()

    import time

    while True:
        try:
            data = fetch(f"{args.api}/api/dashboard")
            p = data["portfolio"]
            print(f"\n--- Tradi Status ---")
            print(f"Mode: {data['mode']} | Regime: {data['regime']}")
            print(f"Portfolio: ${p['total_value_usd']:,.2f} ({p['total_return_pct']:+.2f}%)")
            print(f"Drawdown: {p['drawdown_pct']:.2f}% | Trades today: {p['trades_today']}")
            print(f"Eligible tokens: {data['eligible_token_count']}")
            if data["risk"]["active_breakers"]:
                print("ACTIVE BREAKERS:")
                for b in data["risk"]["active_breakers"]:
                    print(f"  - {b['type']}: {b['reason']}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if not args.watch:
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
