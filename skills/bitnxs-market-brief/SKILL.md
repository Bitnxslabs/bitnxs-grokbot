---
name: bitnxs-market-brief
description: >-
  Use when the user asks about Bitnxs market data (price, 24h change, funding,
  open interest, order book, candles, trades) or a routine needs a Bitnxs market
  brief or alert. Read-only, no API key.
---
# Bitnxs market brief (read-only, no API key)

This skill is read-only: it never places orders or needs an API key (trading lives in the bitnxs-trading skill). Give no trading advice. Report data with its source and time; reply in the user's language and time zone.

## API basics
- Every public read: `POST https://api.bitnxs.com/info`, JSON body `{"type": ...}`. Header `Content-Type: application/json` is required (else HTTP 415). Always set a custom `User-Agent` (Python's default urllib UA gets HTTP 403).
- WebSocket: `wss://api.bitnxs.com/ws`. Subscribe `{"method":"subscribe","subscription":{"type":"allMids"}}`; ping `{"method":"ping"}`.
- Numbers are decimal strings; timestamps are UTC milliseconds. Errors are plain text (422/400), not JSON.
- Reads are not rate-limited, but poll politely (at most 1-2 requests/s).
- Docs: https://www.bitnxs.com/#/docs (JS-rendered; these notes reflect tested server behavior).

## Endpoints
- `{"type":"meta"}`: listed coins in `assetToId`. Unknown coins return zeros instead of errors, so check this list first. Size/tick fields are integer base units.
- `{"type":"allMids"}`: map coin to price (equals mark price).
- `{"type":"marketSummary","coin":"BTC"}`: one coin per call. `markPrice`, `indexPrice`, `change24hAbs`, `change24hPct` (percent), `fundingRate` (percent per hour; 0.0100 = 0.01%/h, about 87.6%/yr), `fundingIsEstimated`, `nextFundingSeconds` (hourly funding), `openInterest` and `volume24h` (USD).
- `{"type":"l2Book","coin":"BTC"}`: `bids`/`asks` as `[price, size_in_coin]`; ignore `levels`.
- `{"type":"candleSnapshot","req":{"coin":"BTC","interval":"1h","startTime":<ms>,"endTime":<ms>}}`: both times required, integer ms, camelCase (not start_time). Intervals 1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1mo; unknown intervals silently return 5m. Candles `t,o,h,l,c,v(coin),q(USD)`, ascending; the last one is still forming. Daily candles open 00:00 UTC.
- `{"type":"recentTrades","coin":"BTC","limit":100}`: `limit` required (max 500), oldest first; `side` is the taker side.
- `{"type":"fundingHistory","coin":"BTC"}`: last 168 hourly rates, ascending; ignores time params. Use `fundingRate` (percent).
- `{"type":"feeSchedule"}`: maker/taker/liquidation fees in bps.
- WebSocket `candle` channel does not respond: fetch candles over REST. WS `trades` pushes one object per trade; `l2Book` pushes full snapshots.

## Snapshot script
Save once to `scripts/snapshot.py` if missing, then run `python3 scripts/snapshot.py [BTC ETH ...] [--json]`:
```python
import json,sys,time,urllib.request
B="https://api.bitnxs.com/info"
def info(b):
    for i in range(3):
        try:
            r=urllib.request.Request(B,json.dumps(b).encode(),{"Content-Type":"application/json","User-Agent":"bitnxs-brief/1.0"})
            return json.loads(urllib.request.urlopen(r,timeout=15).read())
        except urllib.error.HTTPError as e: raise RuntimeError(f"{b['type']}: {e.code} {e.read()[:200]}")
        except Exception:
            if i==2: raise
            time.sleep(1+i)
listed=list(info({"type":"meta"})["assetToId"])
coins=[a.upper() for a in sys.argv[1:] if not a.startswith("--")] or listed
rows=[]
for c in coins:
    if c not in listed: rows.append({"coin":c,"error":"not listed"}); continue
    s=info({"type":"marketSummary","coin":c}); k=info({"type":"l2Book","coin":c})
    bid=float(k["bids"][0][0]) if k["bids"] else None; ask=float(k["asks"][0][0]) if k["asks"] else None
    f=float(s["fundingRate"])
    rows.append({"coin":c,"mark":float(s["markPrice"]),"index":float(s["indexPrice"]),"chg24h_pct":float(s["change24hPct"]),"funding_pct_1h":f,"funding_apr_pct":f*8760,"next_funding_min":round(s["nextFundingSeconds"]/60,1),"oi_usd":float(s["openInterest"]),"vol24h_usd":float(s["volume24h"]),"spread_bps":(ask-bid)/((ask+bid)/2)*1e4 if bid and ask else None})
print(json.dumps(rows,indent=2))
```

## Writing a brief
1. Run the snapshot. Add candles (for example 24 x 1h) when the user wants trend, range, or levels.
2. Lead with price and 24h change per coin, then funding (hourly and yearly equivalent), OI, 24h volume, and spread. Include the time of the data in the user's zone.
3. There is no public liquidation feed. If asked for liquidation zones, offer only a clearly labeled estimate (for example, approximate liquidation prices at common leverage levels from the current price and `meta` max leverage), never as observed data. Use the web UI's formula with a fixed 0.5% maintenance margin: long ≈ px × (1 − 1/lev + 0.005), short ≈ px × (1 + 1/lev − 0.005) (isolated). Live-tested within about 0.02% of an actual liquidation, but still an estimate.
4. Alerts: compare against the thresholds the user set (stored in memory), and stay silent when nothing crossed.
