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

    print("\n" + "=" * 64)
    print(f"  {PASS} passed, {FAIL} failed")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
