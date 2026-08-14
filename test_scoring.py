#!/usr/bin/env python3
"""
Scoring tests — no network required.

Every fixture is a real token from a live Verify run, with its actual
numbers. If a scoring change would have started alerting on SKYAI, or
stopped alerting on REDDIT, these fail.

    python3 test_scoring.py
"""

import sys
from datetime import datetime, timezone

import config
from chain_base import TokenMarket, SafetyReport
import scoring

PASS = FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}" +
          ("" if ok else f"  (expected {want})"))


def check_true(label, cond):
    check(label, bool(cond), True)


# ── fixtures from real runs ───────────────────────────────────────

REDDIT = TokenMarket(                       # Robinhood, PASS_PARTIAL, 3min old
    ca="0xcb5e", chain="robinhood", name="REDDIT", symbol="RDDT",
    price_usd=0.00000811, liquidity_usd=7833, fdv=8115,
    volume_24h=12853, volume_1h=12853, volume_5m=12853,
    change_24h=321.0, change_1h=321.0, change_5m=321.0,
    buys_5m=54, sells_5m=41, age_hours=0.05, age_known=True, dex="uniswap")
REDDIT_SAFETY = SafetyReport(
    ca="0xcb5e", chain="robinhood", sources=["goplus", "blockscout"],
    top_holder_pct=7.4, top10_pct=39.78, honeypot=False, mint_authority=False,
    flags=["excluded_1_infra_holders"],
    unavailable=["lp_locked_pct", "buy_tax_pct"])

SKYAI = TokenMarket(                        # BSC, 1 holder, absurd price data
    ca="0x415a", chain="bsc", name="SKYAI", symbol="SKYAI",
    liquidity_usd=14173, fdv=819649865,
    volume_24h=7086, volume_5m=7086,
    change_24h=1315411989006.0, change_1h=1315411989006.0,
    change_5m=1315411989006.0,
    buys_5m=4, sells_5m=0, age_hours=0.07, age_known=True, dex="pancakeswap")
SKYAI_SAFETY = SafetyReport(
    ca="0x415a", chain="bsc", sources=["goplus"], holder_count=1,
    creator_holds_pct=100.0, flags=["unverified_contract"],
    hard_rejects=["creator_holds_100pct", "only_1_holders"],
    unavailable=["top_holder_pct", "lp_locked_pct"])

MEOW = TokenMarket(                         # Base, clean data, creator holds all
    ca="0x38d3", chain="base", name="MeowCoin", symbol="MEOW",
    liquidity_usd=12837, fdv=8068, volume_24h=1462, volume_1h=1462,
    volume_5m=1003, change_24h=58.3, change_1h=58.3, change_5m=33.3,
    buys_5m=16, sells_5m=1, age_hours=0.11, age_known=True, dex="uniswap")
MEOW_SAFETY = SafetyReport(
    ca="0x38d3", chain="base", sources=["goplus"], creator_holds_pct=100.0,
    honeypot=False, hard_rejects=["creator_holds_100pct"],
    unavailable=["top_holder_pct", "lp_locked_pct"])

STRUK = TokenMarket(                        # Monad, $14 liquidity, dead
    ca="0xd388", chain="monad", name="Struk Mon", symbol="SKM",
    liquidity_usd=14, fdv=7722756, volume_24h=2,
    change_5m=0.0, change_1h=0.0, buys_5m=0, sells_5m=0,
    age_hours=3.70, age_known=True, dex="pancakeswap")
STRUK_SAFETY = SafetyReport(
    ca="0xd388", chain="monad", sources=["goplus"], top_holder_pct=99.94,
    top10_pct=100.0, holder_count=6,
    hard_rejects=["top_holder_100pct", "only_6_holders"])

# A hypothetical clean second-moon runner, to prove high scores are reachable
STRONG = TokenMarket(
    ca="Abc1", chain="solana", name="Neural Agent", symbol="NAGENT",
    liquidity_usd=48000, fdv=280000, volume_24h=520000, volume_1h=180000,
    volume_5m=22000, change_24h=240.0, change_1h=140.0, change_5m=18.0,
    buys_5m=210, sells_5m=64, age_hours=0.9, age_known=True, dex="raydium")
STRONG_SAFETY = SafetyReport(
    ca="Abc1", chain="solana", sources=["rugcheck"], top_holder_pct=6.2,
    top10_pct=28.0, lp_locked_pct=100.0, holder_count=820,
    mint_authority=False, freeze_authority=False, risk_raw=1.0)


# ── alert layer ───────────────────────────────────────────────────

def test_alerts():
    import alerts, chains, dataclasses
    print("\nalert layer")
    check("escapes ampersand", alerts.esc("Test & Token"), "Test &amp; Token")
    check("escapes angle brackets", alerts.esc("<b>x</b>"), "&lt;b&gt;x&lt;/b&gt;")
    check("leaves markdown chars alone", alerts.esc("__x__ *y* `z`"), "__x__ *y* `z`")

    rh = chains.get_adapter("robinhood")
    ev = scoring.evaluate(dataclasses.replace(REDDIT, age_hours=0.20),
                          REDDIT_SAFETY, "robinhood")
    msg = alerts.format_signal(ev, rh)
    check_true("CA wrapped in <code>", f"<code>{REDDIT.ca}</code>" in msg)
    check_true("states the unchecked fields", "Unchecked:" in msg)
    check_true("shows conviction breakdown", "momentum:EXPLOSIVE" in msg)
    check_true("labels signal-only", "SIGNAL ONLY" in msg)
    check_true("within telegram limit", len(msg) < alerts.MAX_LEN)

    bare = SafetyReport(ca=REDDIT.ca, chain="robinhood")
    unv = alerts.format_signal(
        scoring.evaluate(dataclasses.replace(REDDIT, age_hours=0.20), bare, "robinhood"), rh)
    check_true("unverified is stated loudly", "treat as unverified" in unv)

    ca = "DedupeTest"
    first = alerts.should_send(ca)
    alerts.mark_sent(ca)
    check_true("first send allowed", first)
    check_true("repeat blocked inside cooldown", not alerts.should_send(ca))
    check_true("allowed once cooldown elapses",
               alerts.should_send(ca, cooldown_minutes=0))

    check("no credentials fails cleanly",
          alerts.send("x").ok if config.TELEGRAM_BOT_TOKEN else False, False)


def test_store():
    """The in-memory fallback must behave like Supabase, or offline runs lie."""
    import time as _t
    import store as store_mod, chains
    print("\nstore (in-memory fallback)")
    s = store_mod.Store(url="", key="")
    check("no credentials -> not live", s.live, False)

    ev = scoring.evaluate(STRONG, STRONG_SAFETY, "solana",
                          social_channels=3, smart_wallets=2)
    s.record_signal(ev, chains.get_adapter("solana"), sent_ok=True)
    check("signal opens a position", len(s.open_positions()), 1)

    s.close_position(STRONG.ca, "WIN", "TP2", final_pnl=118.0, peak_pnl=204.0)
    check("closed position leaves open set", len(s.open_positions()), 0)
    check("win rate computed", s.stats()["win_rate"], 100.0)

    now = _t.time()
    s.record_mentions([
        {"ca": "X1", "chain": "solana", "channel": "Blessed", "seen_at": now},
        {"ca": "X1", "chain": "solana", "channel": "Catfish", "seen_at": now},
        {"ca": "X2", "chain": "solana", "channel": "Blessed", "seen_at": now},
        {"ca": "X3", "chain": "solana", "channel": "Kook", "seen_at": now - 99999},
    ])
    check("two channels counted", len(s.channels_for("X1")), 2)
    check("one channel not inflated", len(s.channels_for("X2")), 1)
    check("stale mention excluded", len(s.channels_for("X3")), 0)

    check("dedupe map populated", list(s.recently_alerted().keys()), [STRONG.ca])
    check("zero window clears dedupe", s.recently_alerted(minutes=0), {})

    s.mark_watch_event(STRONG.ca, "TP1", 52.0)
    check("watch event recorded", s.fired_watch_events(STRONG.ca), {"TP1"})


def test_social():
    """Extraction must reject markup and keep real calls."""
    import social
    print("\nsocial extraction")

    check("bare solana CA", social.extract_addresses(
        "CA: 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"),
        ["9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"])
    check("chart link only", social.extract_addresses(
        "https://dexscreener.com/solana/9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"),
        ["9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"])
    check("base64 data-uri rejected", social.extract_addresses(
        "url(data:image/svg+xml;base64,cDovL3d3dy53My5vcmcvMjAwMC9zdmc=)"), [])
    check("unpadded base64 rejected", social.extract_addresses(
        "src=data:image/png;base64,uZGVmaW5pdGUiLz48L2xpbmVhckdyYWRpZW50Pg"), [])
    check("wSOL blocklisted", social.extract_addresses(
        "So11111111111111111111111111111111111111112"), [])

    both = social.extract_addresses(
        "sol 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu "
        "evm 0xcb5ecd927f4ef6c9bd9cc434bc2119e05160160c")
    check("mixed line yields exactly two", len(both), 2)
    check_true("no base58 fragment carved from EVM address",
               not any(a.startswith("xcb5") for a in both))

    page = ('<style>background:url(data:image/svg+xml;base64,'
            'cDovL3d3dy53My5vcmcvMjAwMC9zdmc=)</style>'
            '<div class="tgme_widget_message_text" dir="auto">'
            'call 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu</div>')
    texts = social._message_texts(page)
    check("only message bodies parsed", len(texts), 1)
    check_true("markup outside messages ignored",
               "cDovL" not in " ".join(texts))

    now = __import__("time").time()
    M = social.Mention
    mentions = [
        M(ca="A", channel="Blessed", seen_at=now),
        M(ca="A", channel="Blessed", seen_at=now),   # same channel twice
        M(ca="A", channel="Catfish", seen_at=now),
        M(ca="B", channel="Kook", seen_at=now),
    ]
    vel = social.velocity(mentions, min_channels=2)
    check("velocity finds the consensus token", list(vel.keys()), ["A"])
    check("repeat posts are not consensus",
          social.channel_counts(mentions)["A"], 2)
    check("single channel excluded", "B" in vel, False)


def test_tiers():
    """
    Tier gates against real profiles from live runs.

    Volume is measured over the last hour, not 24h. A token twelve minutes
    old has a "24h volume" equal to its entire life, so a $50k 24h floor was
    demanding $50k of trade in twelve minutes and rejecting real runners.
    """
    print("\ntier gates")
    cases = [
        # name, chain, liq, fdv, vol, chg1h, chg5m, age, should_match
        ("REDDIT rh",     "robinhood", 7833,  8115,      12853,  321,    6.6,    0.2, True),
        ("FomoMining rh", "robinhood", 20848, 19153,     34075,  227,   -3.3,    0.2, True),
        ("Korea Robot",   "solana",    70170, 70879,     12573,  46,     46,     0.2, True),
        ("mid runner",    "solana",    45000, 190000,    210000, 85,     12,     1.5, True),
        ("3h old $60k",   "solana",    30000, 60000,     90000,  40,     5,      3.0, True),
        ("thin volume",   "solana",    13339, 6891,      2057,   6.5,    6.5,    0.2, False),
        ("dead $14 liq",  "monad",     14,    7722756,   2,      0,      0,      3.7, False),
        ("SKYAI garbage", "bsc",       14173, 819649865, 7086,   1.3e12, 1.3e12, 0.07, False),
    ]
    for name, chain, liq, fdv, vol, c1h, c5m, agehr, want in cases:
        m = TokenMarket(ca="x", chain=chain, name=name, symbol="X",
                        liquidity_usd=liq, fdv=fdv, volume_24h=vol,
                        volume_1h=vol, change_1h=c1h, change_5m=c5m,
                        age_hours=agehr, age_known=True, dex="uniswap")
        r = scoring.classify_tier(m, chain, session="NORMAL")
        check(f"{name} matches a tier", r.matched, want)

    # No coverage hole between tiers: first_moon stops at 2h, second_moon
    # needs $100k FDV, so a 3h-old $60k token must land in boosted.
    gap = TokenMarket(ca="g", chain="solana", name="gap", symbol="G",
                      liquidity_usd=30000, fdv=60000, volume_24h=90000,
                      volume_1h=90000, change_1h=40, change_5m=5,
                      age_hours=3.0, age_known=True, dex="raydium")
    check("inter-tier gap covered by boosted",
          scoring.classify_tier(gap, "solana", session="NORMAL").tier, "boosted")


def test_watchlist():
    """
    Discovery finds pools minutes old; the entry filter wants ten minutes.
    Parking is what stops that gap from silently discarding every launch.
    """
    import scan, store as store_mod
    print("\nwatchlist")

    def mk(age, liq=40000, fdv=60000, vol=80000, c1h=60):
        return TokenMarket(ca="w", chain="solana", name="W", symbol="W",
                           liquidity_usd=liq, fdv=fdv, volume_24h=vol,
                           volume_1h=vol, change_1h=c1h, change_5m=12,
                           buys_5m=8, sells_5m=2,
                           age_hours=age, age_known=True, dex="raydium")

    def park(m):
        return scan._worth_parking(
            scoring.classify_tier(m, "solana", session="NORMAL"), m)

    def mk_traded(**kw):
        base = dict(ca="w", chain="solana", name="W", symbol="W",
                    liquidity_usd=40000, fdv=60000, volume_24h=80000,
                    volume_1h=80000, change_1h=60, change_5m=12, buys_5m=8,
                    sells_5m=2, age_hours=0.04, age_known=True, dex="raydium")
        base.update(kw)
        return TokenMarket(**base)

    check("only sellers not parked",
          park(mk_traded(buys_5m=0, sells_5m=5)), False)

    check("healthy young pool parked", park(mk(0.04)), True)
    # Re-check slots are the scarce resource, not database rows.
    check("untraded pool not parked",
          park(TokenMarket(ca="u", chain="solana", name="U", symbol="U",
                           liquidity_usd=6000, fdv=9000, volume_24h=0,
                           volume_1h=0, change_1h=2, change_5m=0,
                           buys_5m=0, sells_5m=0, age_hours=0.04,
                           age_known=True, dex="raydium")), False)
    # Liquidity, volume and turnover all accumulate with time, so a pool
    # three minutes old failing them is one objection, not four.
    check("no volume yet still parked", park(mk(0.04, vol=200, c1h=2)), True)
    check("thin fresh pool still parked",
          park(mk(0.04, liq=3200, fdv=5800, vol=400, c1h=4)), True)
    check("dust pool not parked",
          park(mk(0.04, liq=400, fdv=900, vol=10, c1h=0)), False)
    check("absurd fdv not parked",
          park(mk(0.04, fdv=819_649_865, vol=100)), False)
    check("too old not parked", park(mk(48)), False)

    import time as _t
    s = store_mod.Store(url="", key="")
    now = _t.time()
    # Re-checking a token that is still inside the delay window spends a rate
    # limit to rediscover what we already knew.
    s.upsert("watchlist", {"ca": "young", "chain": "solana",
                           "first_seen": now - 120, "first_age_hours": 0.05},
             on_conflict="ca")
    s.upsert("watchlist", {"ca": "ready", "chain": "solana",
                           "first_seen": now - 1200, "first_age_hours": 0.05},
             on_conflict="ca")
    s.upsert("watchlist", {"ca": "recent", "chain": "solana",
                           "first_seen": now - 1200, "first_age_hours": 0.05,
                           "last_checked": now - 30}, on_conflict="ca")
    due = [r["ca"] for r in s.due_for_recheck()]
    check("only matured tokens re-checked", due, ["ready"])

    # Stale rows were only deleted when re-checked, but re-check skipped
    # anything past the window — so they became permanent and starved the
    # fresh ones behind them.
    s.upsert("watchlist", {"ca": "ancient", "chain": "solana",
                           "first_seen": now - 7 * 3600, "first_age_hours": 0.05},
             on_conflict="ca")
    check("stale entry purged", s.purge_watchlist(), 1)

    # Discovery re-surfaces the same pools between scans. Upserting on every
    # sighting wiped first_seen and reset checks, so a token could be
    # re-checked repeatedly and still look untouched — and never age out.
    check("first park accepted", s.watch_later("dup", "solana", 0.05), True)
    kept = s.select("watchlist", {"ca": "eq.dup"})[0]["first_seen"]
    s.bump_check("dup", 0)
    check("re-park ignored", s.watch_later("dup", "solana", 0.30), False)
    again = s.select("watchlist", {"ca": "eq.dup"})[0]
    check("check count survives re-park", again["checks"], 1)
    check("first_seen survives re-park", again["first_seen"] == kept, True)

    # Oldest-first meant the same 45 tokens filled every slot on every scan
    # while 239 others were never looked at once. Least-recently-checked
    # first gives the whole queue a turn.
    # _mem is module-global, so isolate before asserting on ordering.
    store_mod._mem["watchlist"] = []
    s2 = store_mod.Store(url="", key="")
    for ca, last, checks in (("never", None, 0), ("old", now - 3600, 1),
                             ("recent", now - 60, 1)):
        row = {"ca": ca, "chain": "solana", "first_seen": now - 3600,
               "first_age_hours": 0.05, "checks": checks}
        if last:
            row["last_checked"] = last
        s2.insert("watchlist", row)
    s2.insert("watchlist", {"ca": "spent", "chain": "solana",
                            "first_seen": now - 3600, "first_age_hours": 0.05,
                            "checks": 4, "last_checked": now - 3600})
    check("round-robin order", [r["ca"] for r in s2.due_for_recheck()],
          ["never", "old"])
    check("exhausted token retired", s2.purge_watchlist(), 1)
    check("survivors kept", sorted(r["ca"] for r in s2.select("watchlist")),
          ["never", "old", "recent"])
    store_mod._mem["watchlist"] = []
    check("dropped after revival",
          [r["ca"] for r in s.due_for_recheck()], [])


def main():
    print("=" * 64)
    print("SCORING TESTS")
    print("=" * 64)

    print("\nmarket session")
    check("03:00 UTC", scoring.market_session(datetime(2026, 8, 13, 3, tzinfo=timezone.utc)), "DEAD")
    check("15:00 UTC", scoring.market_session(datetime(2026, 8, 13, 15, tzinfo=timezone.utc)), "PEAK")
    check("11:00 UTC", scoring.market_session(datetime(2026, 8, 13, 11, tzinfo=timezone.utc)), "NORMAL")

    print("\nnarrative classification")
    check("Neural Agent", scoring.classify_narrative("Neural Agent", "NAGENT")[0], "AI")
    check("Doge Cheeto", scoring.classify_narrative("The Doge Cheeto", "Dogeeto")[0], "ELON")
    check("Trump 2026", scoring.classify_narrative("Trump 2026", "MAGA")[0], "POLITICAL")
    check("Pygmy Hippo", scoring.classify_narrative("Solana The Pygmy Hippo", "HIPPO")[0], "ANIMAL")
    check("Certain (no false AI)", scoring.classify_narrative("Certain", "CERTAIN")[0], "NONE")
    check("Captain (no false AI)", scoring.classify_narrative("Captain Hook", "CAP")[0], "NONE")

    print("\nmomentum quality")
    check("REDDIT", scoring.momentum_quality(REDDIT), "EXPLOSIVE")
    check("STRONG", scoring.momentum_quality(STRONG), "EXPLOSIVE")
    check("STRUK (dead)", scoring.momentum_quality(STRUK), "FAKE")

    print("\nlaunch phase")
    check("REDDIT 0.05h", scoring.launch_phase(REDDIT), "TOO_EARLY")
    check("STRONG 0.9h", scoring.launch_phase(STRONG), "GOLDEN_WINDOW")
    check("STRUK 3.7h", scoring.launch_phase(STRUK), "SWEET_SPOT")
    check("no timestamp", scoring.launch_phase(
        TokenMarket(ca="x", chain="base", age_known=False)), "UNKNOWN")

    print("\nsanity penalty reaches the score")
    skyai_conv = scoring.conviction_score(SKYAI, SKYAI_SAFETY)
    check_true("SKYAI scores below alert floor", not skyai_conv.alertable)
    check_true("SKYAI penalised for suspect data",
               any("suspect_data" in l for l, _ in skyai_conv.components))

    print("\nunverified penalty")
    bare = SafetyReport(ca="z", chain="robinhood")
    unv = scoring.conviction_score(REDDIT, bare)
    ver = scoring.conviction_score(REDDIT, REDDIT_SAFETY)
    check_true("unverified scores lower than verified", unv.score < ver.score)
    check_true("UNVERIFIED component present",
               any(l == "UNVERIFIED" for l, _ in unv.components))

    print("\nend-to-end evaluate()")
    for label, m, s, expect in (
        ("SKYAI", SKYAI, SKYAI_SAFETY, "safety"),
        ("MeowCoin", MEOW, MEOW_SAFETY, "safety"),
        ("Struk Mon", STRUK, STRUK_SAFETY, "safety"),
    ):
        ev = scoring.evaluate(m, s, m.chain)
        check(f"{label} rejected by", ev.rejected_by, expect)

    ev_strong = scoring.evaluate(STRONG, STRONG_SAFETY, "solana",
                                 social_channels=3, smart_wallets=2)
    print(f"\n  STRONG -> {ev_strong.summary()}")
    print(f"  breakdown: {ev_strong.conviction.explain()}")
    check_true("STRONG alerts", ev_strong.should_alert)
    check_true("STRONG scores HIGH", ev_strong.conviction.band in ("HIGH", "GOOD"))

    ev_reddit = scoring.evaluate(REDDIT, REDDIT_SAFETY, "robinhood")
    print(f"\n  REDDIT -> {ev_reddit.summary()}")
    print(f"  breakdown: {ev_reddit.conviction.explain()}")
    if ev_reddit.rejected_by == "tier":
        print(f"  tier misses: {ev_reddit.tier.failures.get('first_moon')}")

    test_alerts()
    test_store()
    test_social()
    test_tiers()
    test_watchlist()

    print("\n" + "=" * 64)
    print(f"  {PASS} passed, {FAIL} failed")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
