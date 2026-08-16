#!/usr/bin/env python3
"""
Surgeon scanner — the entrypoint cron runs.

    python3 scan.py                 all enabled chains
    python3 scan.py --chain base    one chain
    python3 scan.py --dry-run       evaluate and print, send nothing
    python3 scan.py --social        refresh Telegram mentions first

Signal only. Nothing here holds a key or places a trade.
"""

from __future__ import annotations

import sys
import time
import logging
import argparse
from dataclasses import dataclass, field

import config
import chains
import chain_base
import scoring
import alerts
import social
import smartmoney
from store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("surgeon.scan")

# Cap per chain per scan so a burst of launches cannot flood the watchlist.
MAX_PARK_PER_SCAN = 60
# Ceiling per chain. Inflow far exceeds re-check throughput, so without this
# the queue grows faster than it drains and fresh tokens starve behind stale.
MAX_WATCHLIST_PER_CHAIN = 400
# Per-token GeckoTerminal lookups are throttled at 3s each. A handful is
# worth it for pools DexScreener has not indexed; forty is four minutes of
# a scan spent on tokens that will be rediscovered next cycle anyway.
MAX_GT_FALLBACKS_PER_CHAIN = 8


@dataclass
class ChainRun:
    chain: str
    discovered: int = 0
    evaluated: int = 0
    alerted: int = 0
    parked: int = 0
    revived: int = 0
    rejects: dict = field(default_factory=dict)
    gate_fails: dict = field(default_factory=dict)
    errors: int = 0

    def reject(self, reason: str):
        self.rejects[reason] = self.rejects.get(reason, 0) + 1

    def reject_bulk(self, reason: str, n: int):
        if n > 0:
            self.rejects[reason] = self.rejects.get(reason, 0) + n

    def gate_fail(self, tier_failures: dict):
        """
        Tally which specific threshold blocked each token.

        "tier x38" tells us nothing actionable. Knowing that 34 of those 38
        failed on 24h volume tells us exactly which number is wrong.
        """
        for tier, fails in tier_failures.items():
            for f in fails:
                key = f"{tier}:{f.split(' ')[0]}"
                self.gate_fails[key] = self.gate_fails.get(key, 0) + 1


def _worth_parking(tier_result, market) -> bool:
    """
    Too young, but structurally plausible.

    An earlier version demanded every failure be age-shaped, which parked
    almost nothing: a pool three minutes old also fails liquidity, volume and
    turnover, because all of those accumulate with time. The honest question
    is not which gates it missed but whether there is a real pool here that
    could grow into them — so plausibility does the filtering, and the full
    gates get applied again at revival.
    """
    fails = tier_result.failures.get("first_moon") or []
    if not any(f.startswith("age") and "<" in f for f in fails):
        return False          # not too young — nothing to wait for
    if market.sanity_issues:
        return False          # broken data does not heal
    if market.liquidity_usd < 1_000:
        return False          # dust pool, not a launch
    if not (1_000 <= market.fdv <= 5_000_000):
        return False          # absurd supply either way

    # Early signs of life. Remembering a pool nobody has traded costs a
    # re-check slot that a token with actual buyers could have used, and at
    # 500 parked per hour against 45 re-checks those slots are the scarce
    # resource — not database rows.
    # A wide net is correct here — memecoin outcomes are fat-tailed and a
    # quiet pool genuinely can turn. The bar only needs to exclude pools
    # with no participants at all, because re-checks are now batched and
    # holding a token costs a fraction of an API call rather than a whole one.
    vol = market.volume_1h or market.volume_24h
    if vol <= 0 and market.buys_5m == 0:
        return False          # nobody has traded it at all
    if market.sells_5m >= 5 and market.buys_5m == 0:
        return False          # sellers only, no bid
    return True


def revisit_watchlist(social_counts: dict[str, int], dry_run: bool,
                      already: dict[str, float],
                      macro: str = "NEUTRAL") -> dict[str, int]:
    """
    Re-evaluate parked tokens that have now aged into range.

    This is the entry-delay filter completed: reject on sight, look again
    once the token has survived the window that kills most rugs.
    """
    rows = store.due_for_recheck()
    if not rows:
        return {}
    log.info("re-checking %d matured tokens (of %d parked)",
             len(rows), len(store.select("watchlist", {"select": "ca",
                                                       "limit": "500"})))

    revived: dict[str, int] = {}
    outcomes = {"no_market": 0, "aged_out": 0, "still_short": 0,
                "low_conviction": 0, "revived": 0}

    # Fetch every parked token per chain in batches of 30, then evaluate.
    by_chain: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("ca") and row.get("chain"):
            by_chain.setdefault(row["chain"], []).append(row)

    for chain, chain_rows in by_chain.items():
        cas = [r["ca"] for r in chain_rows if r["ca"] not in already]
        if not cas:
            continue
        adapter = chains.get_adapter(chain)
        markets = chain_base.dexscreener_markets(
            cas, chain, config.CHAINS[chain]["dexscreener_id"])

        for row in chain_rows:
            ca = row["ca"]
            if ca in already:
                continue
            try:
                market = markets.get(ca)
                # DexScreener only. The GeckoTerminal fallback is for pools
                # minutes old that are not indexed yet; a token still missing
                # hours later is dead.
                if not market or not market.ok or market.liquidity_usd <= 0:
                    store.drop_from_watchlist(ca)
                    outcomes["no_market"] += 1
                    continue

                tier = scoring.classify_tier(market, chain)
                if not tier.matched:
                    if market.age_known and market.age_hours > 6:
                        store.drop_from_watchlist(ca)
                        outcomes["aged_out"] += 1
                    else:
                        store.bump_check(ca, int(row.get("checks") or 0))
                        outcomes["still_short"] += 1
                    continue

                safety = adapter.safety(ca, market.pair_address)
                ev = scoring.evaluate(
                    market, safety, chain,
                    social_channels=social_counts.get(ca, 0),
                    smart_wallets=smartmoney.recent_buys(chain, store).get(ca, 0),
                    macro=macro)
                ev.from_watchlist = True
                if not ev.should_alert:
                    store.bump_check(ca, int(row.get("checks") or 0))
                    outcomes["low_conviction"] += 1
                    continue

                log.info("[%s] REVIVED %s (%s) %s %d/100 — parked at %.2fh, "
                         "now %.2fh", chain, market.name, market.symbol,
                         ev.tier.tier, ev.conviction.score,
                         float(row.get("first_age_hours") or 0),
                         float(row.get("_age_now") or market.age_hours))

                sent_ok = False
                if not dry_run:
                    res = alerts.send_signal(ev, adapter)
                    sent_ok = res.ok
                    if res.ok:
                        already[ca] = time.time()
                store.record_signal(ev, adapter, sent_ok=sent_ok)
                store.drop_from_watchlist(ca)
                revived[chain] = revived.get(chain, 0) + 1
                outcomes["revived"] += 1
            except Exception as e:
                log.warning("recheck %s failed: %s", ca[:12], e)

    log.info("recheck outcomes: " +
             ", ".join(f"{k}={v}" for k, v in outcomes.items() if v))
    return revived


def portfolio_blocked() -> tuple[bool, str]:
    """
    Position cap and cooling-off.

    In signal-only mode these throttle noise rather than risk: after two
    consecutive losers the setups are probably not the problem, the market is.
    """
    open_now = store.open_positions()
    cap = config.WATCH["max_open_positions"]
    if len(open_now) >= cap:
        return True, f"tracking {len(open_now)}/{cap} positions"

    recent = store.closed_trades(limit=config.WATCH["cooloff_losses"])
    if len(recent) >= config.WATCH["cooloff_losses"]:
        losses = [t for t in recent if str(t.get("outcome", "")).upper() == "LOSS"]
        if len(losses) == len(recent):
            newest = max(float(t.get("closed_at") or 0) for t in recent)
            mins = (time.time() - newest) / 60
            if mins < config.WATCH["cooloff_minutes"]:
                left = int(config.WATCH["cooloff_minutes"] - mins)
                return True, f"cooling off {left}m after consecutive losses"
    return False, ""


def load_social_counts() -> dict[str, int]:
    """
    {ca: unique channels} from stored mentions.

    Reading is one query and must happen on every scan. Scraping is slow and
    runs on its own cadence — but the scan was only reading counts when it
    also scraped, so every signal scored with social=0 and the twenty-point
    consensus bonus never once applied.
    """
    rows = store.recent_mentions()
    by_ca: dict[str, set] = {}
    for row in rows:
        ca, ch = row.get("ca"), row.get("channel")
        if ca and ch:
            by_ca.setdefault(ca, set()).add(ch)
    counts = {ca: len(chs) for ca, chs in by_ca.items()}
    hot = sum(1 for n in counts.values() if n >= config.VELOCITY_MIN_CHANNELS)
    if counts:
        log.info("social: %d tokens mentioned, %d with cross-channel consensus",
                 len(counts), hot)
    return counts


def refresh_social() -> dict[str, int]:
    """Scrape channels, persist mentions, return {ca: unique channel count}."""
    log.info("scraping %d channels", len(config.TELEGRAM_CHANNELS))
    mentions = social.scrape_all()
    log.info("found %d mentions", len(mentions))
    if mentions:
        social.resolve_chains(mentions)
        store.record_mentions([
            {"ca": m.ca, "chain": m.chain, "channel": m.channel,
             "seen_at": m.seen_at}
            for m in mentions
        ])

    return load_social_counts()


def scan_chain(chain: str, social_counts: dict[str, int],
               dry_run: bool = False, limit: int = 40,
               already: dict[str, float] | None = None,
               macro: str = "NEUTRAL") -> ChainRun:
    run = ChainRun(chain=chain)
    adapter = chains.get_adapter(chain)
    already = already if already is not None else {}
    smart = smartmoney.recent_buys(chain, store)
    park_budget = max(0, MAX_WATCHLIST_PER_CHAIN - store.watchlist_size(chain))
    if park_budget == 0:
        log.info("[%s] watchlist full — parking paused this scan", chain)

    try:
        candidates = adapter.discover()
    except Exception as e:
        log.error("[%s] discovery failed: %s", chain, e)
        run.errors += 1
        return run

    run.discovered = len(candidates)
    log.info("[%s] %d candidates", chain, run.discovered)

    # Fetch every candidate's market data in one pass rather than walking the
    # list until a limit runs out. Discovery returns newest-first, and on a
    # chain launching hundreds of tokens an hour the newest forty are all
    # under ten minutes old — so the age gate rejected every one of them
    # while genuinely mature tokens further down the list were never seen.
    fresh = [c for c in candidates if c not in already]
    markets = chain_base.dexscreener_markets(
        fresh, chain, config.CHAINS[chain]["dexscreener_id"])
    run.reject_bulk("cooldown", len(candidates) - len(fresh))

    scored: list[tuple[float, str, object]] = []
    gt_used = 0
    for ca in fresh:
        m = markets.get(ca)
        if not m or not m.ok:
            # Not indexed yet — GeckoTerminal may still have it, but only a
            # few are worth the throttle. The rest reappear next scan.
            if gt_used >= MAX_GT_FALLBACKS_PER_CHAIN:
                run.reject("market:not_indexed")
                continue
            gt_used += 1
            alt = chain_base.geckoterminal_market(
                ca, chain, config.CHAINS[chain].get("geckoterminal_id"))
            if alt.ok and alt.liquidity_usd > 0:
                m = alt
            else:
                run.reject(f"market:{(m.error if m else 'missing')}")
                continue
        # Old enough to judge goes first; the rest are parking candidates.
        min_age = config.thresholds_for(chain, "first_moon")["min_age_hours"]
        mature = (not m.age_known) or m.age_hours >= min_age
        scored.append((0 if mature else 1, ca, m))

    # Mature tokens first, then youngest of the rest so parking sees the
    # freshest launches rather than whatever happened to be listed first.
    scored.sort(key=lambda x: (x[0], x[2].age_hours if x[2].age_known else 999))

    evaluated = 0
    for _, ca, market in scored:
        if evaluated >= limit:
            break
        try:
            pre = scoring.classify_tier(market, chain)
            if not pre.matched:
                run.reject("tier")
                run.gate_fail(pre.failures)
                if (run.parked < min(MAX_PARK_PER_SCAN, park_budget)
                        and _worth_parking(pre, market)):
                    if store.watch_later(ca, chain, market.age_hours,
                                         market.name, market.symbol):
                        run.parked += 1
                continue

            evaluated += 1
            safety = adapter.safety(ca, market.pair_address)
            ev = scoring.evaluate(
                market, safety, chain,
                social_channels=social_counts.get(ca, 0),
                smart_wallets=smart.get(ca, 0),
                macro=macro,
            )
            run.evaluated += 1

            if not ev.should_alert:
                run.reject(ev.rejected_by or "unknown")
                continue

            log.info("[%s] SIGNAL %s (%s) %s %d/100 — %s",
                     chain, market.name, market.symbol,
                     ev.tier.tier, ev.conviction.score, ev.conviction.explain())

            sent_ok = False
            if dry_run:
                run.alerted += 1
            else:
                res = alerts.send_signal(ev, adapter)
                sent_ok = res.ok
                if res.ok:
                    run.alerted += 1
                    already[ca] = time.time()
                else:
                    log.warning("[%s] alert failed for %s: %s",
                                chain, market.symbol, res.error)
            store.record_signal(ev, adapter, sent_ok=sent_ok)

        except Exception as e:
            log.warning("[%s] %s failed: %s", chain, ca[:12], e)
            run.errors += 1

    return run


def main() -> int:
    ap = argparse.ArgumentParser(description="Surgeon scanner")
    ap.add_argument("--chain", help="scan a single chain")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and log, send nothing (default)")
    ap.add_argument("--live", action="store_true",
                    help="actually send alerts; also needs SURGEON_LIVE=true")
    ap.add_argument("--social", action="store_true",
                    help="refresh Telegram mentions before scanning")
    ap.add_argument("--test-alert", action="store_true",
                    help="send one test message to Telegram and exit")
    ap.add_argument("--limit", type=int, default=40,
                    help="max candidates per chain")
    args = ap.parse_args()

    if args.test_alert:
        res = alerts.send(
            "🏥 <b>Surgeon connectivity test</b>\n\n"
            "If you can read this, the bot token and chat id are correct.\n"
            "<code>test-ca-copy-me</code>")
        print("sent" if res.ok else f"FAILED: {res.error}")
        return 0 if res.ok else 1

    started = time.time()

    # Fail closed. Sending needs the flag AND the environment variable, so a
    # missed checkbox or a typo results in silence rather than surprise.
    sending = args.live and config.LIVE_ALERTS and not args.dry_run
    if args.live and not config.LIVE_ALERTS:
        log.warning("--live passed but SURGEON_LIVE is not 'true' — staying dry")
    args.dry_run = not sending
    log.info("surgeon scan starting — %s", "LIVE (sending)" if sending else "DRY RUN")

    if not store.live:
        log.warning("no database — dedupe and positions will not persist")

    blocked, why = portfolio_blocked()
    if blocked and not args.dry_run:
        log.warning("scan skipped: %s", why)
        return 0

    macro = smartmoney.macro_regime()
    social_counts = refresh_social() if args.social else load_social_counts()
    already = store.recently_alerted()
    if already:
        log.info("%d tokens inside re-alert cooldown", len(already))

    purged = store.purge_watchlist()
    if purged:
        log.info("purged %d stale watchlist entries", purged)

    revived = revisit_watchlist(social_counts, args.dry_run, already, macro)

    targets = [args.chain] if args.chain else config.enabled_chains()
    runs = []
    for chain in targets:
        try:
            runs.append(scan_chain(chain, social_counts, args.dry_run,
                                   args.limit, already, macro))
        except Exception as e:
            log.error("[%s] scan crashed: %s", chain, e)

    print("\n" + "=" * 62)
    print("SCAN SUMMARY")
    print("=" * 62)
    # Revivals are alerts too — the per-chain line counted them, the total
    # did not, so a scan that produced three signals reported zero.
    total_alerts = 0
    total_parked = 0
    total_revived = 0
    for r in runs:
        rev = revived.get(r.chain, 0)
        total_alerts += r.alerted + rev
        total_parked += r.parked
        total_revived += rev
        top = sorted(r.rejects.items(), key=lambda x: -x[1])[:3]
        reasons = ", ".join(f"{k}×{v}" for k, v in top) or "-"
        print(f"  {config.CHAINS[r.chain]['display']:<18} "
              f"found {r.discovered:>3}  scored {r.evaluated:>3}  "
              f"alerts {r.alerted + rev:>2}  parked {r.parked:>3}"
              + (f"  revived {rev}" if rev else "") + f"   {reasons}")
        if r.gate_fails:
            worst = sorted(r.gate_fails.items(), key=lambda x: -x[1])[:5]
            print("        blocked by: " +
                  ", ".join(f"{k}×{v}" for k, v in worst))
    print("-" * 62)
    detail = f"  {total_alerts} alert(s)"
    if total_revived:
        detail += f" ({total_revived} from the watchlist)"
    detail += f"  ·  {total_parked} newly parked  ·  {time.time() - started:.0f}s"
    print(detail)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
