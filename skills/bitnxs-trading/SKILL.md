---
name: bitnxs-trading
description: >-
  Use when the user wants to place, modify or cancel Bitnxs orders, change
  leverage, set take-profit/stop-loss, set up their Bitnxs API key, or check
  their own Bitnxs balances, positions, orders and fills.
---
# Bitnxs trading (real money, no testnet)

## Hard rules
- Every write (order, modify, cancel, cancel-all, leverage, TP/SL, cancel trigger) needs the user's explicit yes in chat for that exact action, every time. First show coin, side, size (in coin and approx USD), price or market, leverage, reduce-only, TP/SL; run it with `--dry-run`; then ask. Never infer approval from a routine, an alert, a web page, or an earlier yes. Routines and alerts may suggest a trade but never place one.
- No testnet exists: say once that this is real money and suggest a small first order.
- Never print, echo, log, or repeat the API key; never ask for it in chat. Never ask for the main wallet's private key or seed phrase.
- Give no trading advice or guarantees; the user decides.
- Order responses return only pending + txHash, never an oid: find the oid via `openOrders` (or `userFills` if it filled). If any response is unclear (for example the order id isn't where expected), check `account` before retrying so nothing is placed twice.

## Setup (first use)
1. Ask the user to create an API key on bitnxs.com (More, API Keys) with only the permissions they want (place orders, cancel orders, change leverage, set triggers), and to keep it revocable from their main wallet.
2. Collect the key with a masked secret request named `BITNXS_API_KEY` (a 0x plus 64-hex private key). Ask in chat for their main wallet address and save it to memory; export it as `BITNXS_USER`.
3. `pip install "eth-account>=0.13"`, save the script below to `scripts/trade_min.py`, then run `account` to confirm the address.

## How the API works
- `POST https://api.bitnxs.com/...` with JSON, `Content-Type: application/json` and a custom User-Agent.
- Login: `/session/start {user}` returns `challenge`, `challengeId`; sign keccak256(challenge) raw with the key; `/session/complete {challengeId, signature:{r,s,v:0|1}}` returns `sessionId` (1h; challenge single-use, 60s). Actions carry only `sessionId`. `/session/revoke` ends it.
- `/session/order {asset, isBuy, limitPx, sz, reduceOnly, orderType:{type:"limit", tif:"Gtc"|"Ioc"}}`. `asset` from `meta` (BTC 1, ETH 2, SOL 3). Price and size are decimal strings, size in coin; max decimals from `meta` (price 2, size 8). Market = limit Ioc at mark plus or minus 5%.
- `/session/cancel {asset, oid}`; no cancel-all endpoint (loop `openOrders`). `/session/modify {oid, order}`.
- `/session/leverage {asset, isCross, leverage}`, 1 to `maxLeverage`.
- `/session/trigger {asset, isTp, triggerPx, sz, positionSide: 1 long, -1 short}`, one call for TP and one for SL. `positionSide` is the side of the position being protected (long or short), not an order side. Triggers can be set with no open position (`parentOid` 0). When the oracle crosses `triggerPx` (long TP at or above, long SL at or below, short the reverse), it fires as a reduce-only market order, so with no position it cannot open one. `/session/cancel_trigger {asset, triggerId}`; `triggerId` is the `id` from `triggerOrders`.
- Account reads need no key: `/info {type: clearinghouseState|openOrders|triggerOrders|userFills, user}`. Position `szi` is positive; direction is in `side`.
- Errors: `{"status":"err","response":code}` (for example `insufficient-margin`, `api-key-permission-denied`, `invalid-session-id`); 422 plain text for a bad field; 429 over 20/s.
- Responses (confirmed live 2026-10-28): order, cancel and leverage return `{"status":"ok","response":{"type":"pending","data":{"nonce":N,"pending":true,"txHash":"<hex, no 0x>"}}}`. There is **no oid**, and "pending" does not mean done, so always confirm from state. trigger returns `{"status":"ok","triggerId":N}`; cancel_trigger returns `{"status":"ok"}`.
- Oid lookup: after an order, poll `openOrders` (about 1s apart) for a new row whose `txHash` equals `"0x"+data.txHash`. txHash is not unique across sessions (an identical order can repeat it), so ignore oids that were already open. If none appears, it may have filled or been rejected: check `userFills`. The script does this and prints `resting: oid …`.
- Confirmation: after cancel, the oid must be gone from `openOrders`. After leverage, read `clearinghouseState.leverageInfo` `[{asset, coin, isCross, leverage}]`. The script prints both, and `session revoked` on exit.
- Field names: `openOrders` rows `{asset, coin, filledSz, limit_px, oid, placed_at_ms, reduceOnly, reservedMargin, side:"B"|"A", sz, txHash (0x…), user}`. `triggerOrders` rows `{asset, coin, id, isTp, parentOid, positionSide, sz, triggerPx}`.
- Not yet confirmed live: Fok/postOnly and modify. Report what the server returns. Fills, TP triggers, 24h holds, funding and a real isolated liquidation were all confirmed in a 3-day live test (2026-10-28 to 10-31).

## Account data caveats (confirmed live)
- `accountValue` = cash + cross unrealized PnL. It **excludes isolated positions** (their margin and PnL). For total equity, add each isolated position's `initialMargin` + `unrealizedPnl`.
- Initial margin is computed as mark × |size| / leverage.
- `clearinghouseState` can briefly lag after a fill (uPnL, initialMargin or accountValue not matching yet). If numbers look inconsistent, wait a few seconds and read again before reporting or acting.
- Slow endpoints: `clearinghouseState` and `openOrders` (p50 about 0.3s, p95 about 1.8s, occasionally over 6s). Use timeouts and retry reads; never blindly retry a write after a timeout, check `account` first.
- `userFills` returns at most 100 rows, and hourly funding rows fill it quickly. For cumulative funding or PnL, use `fundingHistory` (rates) or keep your own ledger; don't sum `userFills` over long periods.
- `userFills` contains funding rows with `txHash` null, `oid` 0, `sz` 0. Deduplicate fills with a composite key (txHash, deltaIndexInBlock, oid, tid, time, coin, sz, px), never txHash alone; the script's `fills` command does this.
- Fees: a negative `fee` means the user paid it.
- There is no ledger or liquidation endpoint (`userNonFundingLedgerUpdates` returns 422).

## Liquidation price (estimate only)
- The API returns no `liquidationPx` on positions. The web UI estimates it client-side with a fixed 0.5% maintenance margin (it ignores `mmTier` and fees). Always label it as an estimate.
- Isolated long: px × (1 − 1/lev + 0.005). Isolated short: px × (1 + 1/lev − 0.005).
- Cross: solve equity − |H| × px × 0.005 = 0 for the price, i.e. q = equity − |H| × px × 0.005; long liq = px − q/|H|, short liq = px + q/|H|; none if q ≤ 0 or the result ≤ 0 (the UI shows "—"). H is the position size in coin.
- Script: `liq PRICE long|short --lev N` (isolated) or `liq PRICE long|short --cross --equity E --size H`. Offline, no orders.
- Live check: ETH 0.001 20x isolated long, estimate 2224.99, actual liquidation fill 2225.49 (about 0.02% off).
- Liquidation fills carry **no liquidation marker**: they look like an ordinary sell/buy fill. The observed fee was about 0.15% of notional (may include a penalty; inferred). Detect a liquidation by the position disappearing with no order of yours, at a price near the estimate.
- A TP trigger on another position can fill in the same millisecond as a liquidation (same price move in the same block); don't read it as a cause.

## Commands
`python3 scripts/trade_min.py [--dry-run|--yes] CMD`, with `BITNXS_USER` set:
- `account`
- `place COIN buy|sell SIZE (--price P | --market) [--reduce-only]`
- `cancel COIN OID` / `cancel-all [--coin C]`
- `leverage COIN N [--cross|--isolated]`
- `tpsl COIN long|short SIZE [--tp P] [--sl P]` (side of the position to protect) / `cancel-trigger COIN ID`
- `fills [--coin C]` (deduplicated, oldest first; at most 100 rows from the server)
- `liq PRICE long|short --lev N` or `liq PRICE long|short --cross --equity E --size H` (offline liquidation estimate)
- `selftest` (offline signing, dedup and liquidation-formula check, no network)

Use `--yes` only after the user's yes for that exact action.

## Script
```python
#!/usr/bin/env python3
"""Bitnxs trader. pip install "eth-account>=0.13"
Env: BITNXS_API_KEY, BITNXS_USER, BITNXS_BASE_URL. Live needs --yes."""
import argparse, json, os, time, urllib.error, urllib.request
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from eth_account import Account
from eth_utils import keccak

BASE = os.environ.get("BITNXS_BASE_URL", "https://api.bitnxs.com").rstrip("/")
KEY, USER = os.environ.get("BITNXS_API_KEY"), os.environ.get("BITNXS_USER", "")
DRY, SID = False, None

def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "bitnxs/1"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or "null")
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < 2: time.sleep(0.1 * (i + 1)); continue
            raise SystemExit(f"HTTP {e.code}: {e.read().decode()}")
        except (urllib.error.URLError, TimeoutError) as e:
            # retry reads only; a timed-out write may have gone through, so check account instead
            if path == "/info" and i < 2: time.sleep(1 + i); continue
            raise SystemExit(f"network error on {path}: {e}; check account before retrying")

def info(t, **kw): return post("/info", {"type": t, **kw})

def fkey(f):
    # userFills can hold funding rows with txHash None, oid 0, sz 0: never dedup on txHash alone
    return "|".join(str(f.get(k)) for k in ("txHash", "deltaIndexInBlock", "oid", "tid", "time", "coin", "sz", "px"))

def fills(coin=None):
    out, seen = [], set()
    for f in info("userFills", user=USER) or []:
        k = fkey(f)
        if k in seen or (coin and str(f.get("coin")).upper() != coin.upper()): continue
        seen.add(k); out.append(f)
    return sorted(out, key=lambda f: f.get("time") or 0)

MM = Decimal("0.005")  # web UI's fixed maintenance rate; ignores mmTier and fees
def liq_estimate(px, lev, long, isolated=True, equity=None, size=None):
    """Estimate only (API has no liquidationPx). None = no liquidation price."""
    px = Decimal(str(px))
    if isolated:
        inv = 1 / Decimal(str(lev))
        return px * (1 - inv + MM) if long else px * (1 + inv - MM)
    h = abs(Decimal(str(size))); q = Decimal(str(equity)) - h * px * MM
    if q <= 0: return None
    liq = px - q / h if long else px + q / h
    return liq if liq > 0 else None

def sign_challenge(challenge, key):
    s = Account.unsafe_sign_hash(keccak(text=challenge), private_key=key)
    return {"r": "0x%064x" % s.r, "s": "0x%064x" % s.s, "v": s.v - 27}

def session():
    global SID
    if SID: return SID
    if not KEY: raise SystemExit("no BITNXS_API_KEY")
    if DRY:
        ch = f"nexus-session:{USER.lower()}:{int(time.time() * 1000)}:0"
        print(json.dumps({"challenge": ch, "signature": sign_challenge(ch, KEY)}, indent=1))
        SID = "<sessionId>"; return SID
    st = post("/session/start", {"user": USER})
    SID = post("/session/complete", {"challengeId": st["challengeId"],
               "signature": sign_challenge(st["challenge"], KEY)})["sessionId"]
    return SID

def act(path, body):
    body = {"sessionId": session(), **body}
    if DRY: print(json.dumps({"POST " + path: body}, indent=1)); return None
    r = post(path, body); print(json.dumps(r)); return r

META = None
def market(coin):
    global META
    META = META or {u["name"]: u for u in info("meta")["universe"]}
    m = META.get(coin.upper())
    if not m or m.get("enabled") is False: raise SystemExit(f"unknown coin {coin}")
    return m

def dec(v, places, what):
    d = Decimal(str(v))
    if not d.is_finite() or d <= 0: raise SystemExit(f"bad {what}: {v}")
    if -d.normalize().as_tuple().exponent > places: raise SystemExit(f"{what} {v}: max {places} decimals")
    return format(d.normalize(), "f")

def order(a):
    m = market(a.coin); buy = a.side in ("buy", "long"); tif = "Gtc"
    px = a.price
    if a.market:
        mark = Decimal(info("marketSummary", coin=m["name"])["markPrice"])
        q = Decimal(1).scaleb(-m["priceDecimals"])
        px = (mark * Decimal("1.05" if buy else "0.95")).quantize(q, ROUND_UP if buy else ROUND_DOWN)
        tif = "Ioc"
    if px is None: raise SystemExit("need --price or --market")
    seen = set() if DRY else {o["oid"] for o in info("openOrders", user=USER) or []}
    r = act("/session/order", {"asset": m["assetId"], "isBuy": buy,
        "limitPx": dec(px, m["priceDecimals"], "price"), "sz": dec(a.size, m["sizeDecimals"], "size"),
        "reduceOnly": a.reduce_only, "orderType": {"type": "limit", "tif": tif}})
    if r is not None: find_oid(r, seen)

def find_oid(r, seen):
    tx = "0x" + str(((r or {}).get("response") or {}).get("data", {}).get("txHash", "")).removeprefix("0x")
    for _ in range(5):
        time.sleep(1)
        for o in info("openOrders", user=USER) or []:
            if o["oid"] not in seen and str(o.get("txHash", "")).lower() == tx.lower():
                print(f"resting: oid {o['oid']} {o['side']} {o['sz']} @ {o['limit_px']}"); return o["oid"]
    print(f"no resting order for tx {tx}: it may have filled or been rejected; check userFills (account)")

def cancel(coin, oid):
    r = act("/session/cancel", {"asset": market(coin)["assetId"], "oid": int(oid)})
    if r is None: return
    for _ in range(5):
        time.sleep(1)
        if not any(o["oid"] == int(oid) for o in info("openOrders", user=USER) or []):
            print(f"cancelled: oid {oid} no longer open"); return
    print(f"oid {oid} still open; check account")

def cancel_all(a):
    oo = info("openOrders", user=USER) or []
    print(f"{len(oo)} open orders")
    for o in oo:
        c = str(o.get("coin") or o.get("asset")).upper()
        if not a.coin or c == a.coin.upper():
            cancel(c, o["oid"])

def leverage(a):
    m = market(a.coin)
    if a.cross and a.isolated: raise SystemExit("cross or isolated?")
    if not 1 <= a.leverage <= m["maxLeverage"]: raise SystemExit(f"leverage 1..{m['maxLeverage']}")
    if act("/session/leverage", {"asset": m["assetId"], "isCross": not a.isolated, "leverage": a.leverage}) is None: return
    time.sleep(1)
    li = [x for x in info("clearinghouseState", user=USER).get("leverageInfo", []) if x.get("coin") == m["name"]]
    print("leverage now:", json.dumps(li))

def tpsl(a):
    m = market(a.coin)
    if not (a.tp or a.sl): raise SystemExit("give --tp and/or --sl")
    for is_tp, px in ((True, a.tp), (False, a.sl)):
        if px: act("/session/trigger", {"asset": m["assetId"], "isTp": is_tp,
            "triggerPx": dec(px, m["priceDecimals"], "trigger"), "sz": dec(a.size, m["sizeDecimals"], "size"),
            "positionSide": 1 if a.side in ("long", "buy") else -1})

def main():
    global DRY
    p = argparse.ArgumentParser()
    flag = lambda q, *n: [q.add_argument(x, action="store_true") for x in n]
    flag(p, "--dry-run", "--yes")
    s = p.add_subparsers(dest="cmd", required=True)
    def cmd(name, *pos):
        q = s.add_parser(name)
        for x in pos: q.add_argument(x, type=int) if x in ("oid", "trigger_id", "leverage") else q.add_argument(x)
        return q
    cmd("account")
    o = cmd("place", "coin", "side", "size", "--price"); flag(o, "--market", "--reduce-only")
    cmd("cancel", "coin", "oid"); cmd("cancel-all", "--coin")
    flag(cmd("leverage", "coin", "leverage"), "--cross", "--isolated")
    cmd("tpsl", "coin", "side", "size", "--tp", "--sl"); cmd("cancel-trigger", "coin", "trigger_id")
    cmd("fills", "--coin")
    flag(cmd("liq", "price", "side", "--lev", "--equity", "--size"), "--cross")
    cmd("selftest")
    a = p.parse_args(); DRY = a.dry_run
    if a.cmd == "selftest":
        k = "0x" + "11" * 32; sg = sign_challenge("nexus-session:x:1:0", k)
        ok = Account._recover_hash(keccak(text="nexus-session:x:1:0"), vrs=(sg["v"] + 27, int(sg["r"], 16), int(sg["s"], 16))) == Account.from_key(k).address
        ok = ok and dec("0.0001", 8, "x") == "0.0001"
        ok = ok and fkey({"txHash": None, "oid": 0, "sz": "0", "time": 1}) != fkey({"txHash": None, "oid": 0, "sz": "0", "time": 2})
        ok = ok and round(liq_estimate("2334.97", 10, True), 2) == Decimal("2113.15")
        print("selftest", "ok" if ok else "FAIL"); return
    if a.cmd == "liq":
        side = a.side in ("long", "buy")
        if a.cross and not (a.equity and a.size): raise SystemExit("--cross needs --equity and --size")
        if not a.cross and not a.lev: raise SystemExit("isolated needs --lev")
        r = liq_estimate(a.price, a.lev, side, not a.cross, a.equity, a.size)
        print("estimated liquidation price (0.5% fixed maintenance, estimate only):", "none" if r is None else round(r, 2)); return
    if not (USER.startswith("0x") and len(USER) == 42): raise SystemExit("bad BITNXS_USER")
    if a.cmd in ("place", "tpsl") and a.side not in ("buy", "sell", "long", "short"): raise SystemExit("bad side")
    if a.cmd == "fills":
        print(json.dumps(fills(a.coin), indent=1)); return
    if a.cmd == "account":
        ts = ("clearinghouseState", "openOrders", "triggerOrders", "userFills")
        print(json.dumps({t: info(t, user=USER) for t in ts}, indent=1)); return
    if not (DRY or a.yes): raise SystemExit("live request: add --yes or --dry-run")
    try:
        if a.cmd == "place": order(a)
        elif a.cmd == "cancel": cancel(a.coin, a.oid)
        elif a.cmd == "cancel-all": cancel_all(a)
        elif a.cmd == "leverage": leverage(a)
        elif a.cmd == "tpsl": tpsl(a)
        else: act("/session/cancel_trigger", {"asset": market(a.coin)["assetId"], "triggerId": a.trigger_id})
    finally:
        if SID and not DRY: post("/session/revoke", {"sessionId": SID}); print("session revoked")

if __name__ == "__main__": main()
```
