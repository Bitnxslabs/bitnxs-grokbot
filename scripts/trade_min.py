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

def info(t, **kw): return post("/info", {"type": t, **kw})

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
    cmd("selftest")
    a = p.parse_args(); DRY = a.dry_run
    if a.cmd == "selftest":
        k = "0x" + "11" * 32; sg = sign_challenge("nexus-session:x:1:0", k)
        ok = Account._recover_hash(keccak(text="nexus-session:x:1:0"), vrs=(sg["v"] + 27, int(sg["r"], 16), int(sg["s"], 16))) == Account.from_key(k).address
        print("selftest", "ok" if ok and dec("0.0001", 8, "x") == "0.0001" else "FAIL"); return
    if not (USER.startswith("0x") and len(USER) == 42): raise SystemExit("bad BITNXS_USER")
    if a.cmd in ("place", "tpsl") and a.side not in ("buy", "sell", "long", "short"): raise SystemExit("bad side")
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
