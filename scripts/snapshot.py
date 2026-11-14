#!/usr/bin/env python3
"""Bitnxs public market snapshot (read-only, no API key). stdlib only.
Usage: python3 snapshot.py [BTC ETH SOL ...]   (--json for machine output)"""
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://api.bitnxs.com"
TPE = timezone.utc

def info(body, retries=3):
    data = json.dumps(body).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(f"{BASE}/info", data=data, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "bitnxs-snapshot/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            # 4xx = bad request (plain-text error body) -> don't retry
            raise RuntimeError(f"{body.get('type')}: HTTP {e.code}: {e.read()[:200].decode(errors='replace')}")
        except Exception:
            if i == retries - 1: raise
            time.sleep(1 + i)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    meta = info({"type": "meta"})
    listed = list(meta["assetToId"].keys())          # e.g. BTC, ETH, SOL
    coins = [c.upper() for c in args] or listed
    mids = info({"type": "allMids"})
    rows = []
    for c in coins:
        if c not in listed:                            # unknown coins return all-zero summaries, so check first
            rows.append({"coin": c, "error": "not listed"}); continue
        s = info({"type": "marketSummary", "coin": c})
        book = info({"type": "l2Book", "coin": c})
        bid = float(book["bids"][0][0]) if book["bids"] else None
        ask = float(book["asks"][0][0]) if book["asks"] else None
        fr_pct = float(s["fundingRate"])                # percent per 1h interval
        rows.append({
            "coin": c, "mid": float(mids.get(c, "nan")), "mark": float(s["markPrice"]),
            "index": float(s["indexPrice"]), "chg24h_abs": float(s["change24hAbs"]),
            "chg24h_pct": float(s["change24hPct"]), "funding_pct_1h": fr_pct,
            "funding_apr_pct": fr_pct * 24 * 365, "funding_estimated": s["fundingIsEstimated"],
            "next_funding_min": round(s["nextFundingSeconds"] / 60, 1),
            "oi_usd": float(s["openInterest"]), "vol24h_usd": float(s["volume24h"]),
            "best_bid": bid, "best_ask": ask,
            "spread_bps": ((ask - bid) / ((ask + bid) / 2) * 1e4) if bid and ask else None,
        })
    if as_json:
        print(json.dumps(rows, indent=2)); return
    print(f"Bitnxs market snapshot  {datetime.now(TPE):%Y-%m-%d %H:%M:%S} (UTC)")
    hdr = f"{'coin':<5}{'mark':>12}{'24h%':>8}{'fund/1h':>10}{'APR':>8}{'OI($)':>12}{'vol24h($)':>12}{'spread':>9}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        if "error" in r: print(f"{r['coin']:<5} {r['error']}"); continue
        sp = f"{r['spread_bps']:.1f}bp" if r["spread_bps"] is not None else "-"
        print(f"{r['coin']:<5}{r['mark']:>12,.2f}{r['chg24h_pct']:>+7.2f}%{r['funding_pct_1h']:>9.4f}%"
              f"{r['funding_apr_pct']:>7.1f}%{r['oi_usd']:>12,.0f}{r['vol24h_usd']:>12,.0f}{sp:>9}")
    nf = next((r["next_funding_min"] for r in rows if "error" not in r), None)
    if nf is not None: print(f"next funding in ~{nf} min (hourly funding)")

if __name__ == "__main__":
    main()
