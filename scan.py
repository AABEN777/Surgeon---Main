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
import scoring
import alerts
import social
from store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("surgeon.scan")

# Cap per chain per scan so a burst of launches cannot flood the watchlist.
MAX_PARK_PER_SCAN = 25


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
    return True


def revisit_watchlist(social_counts: dict[str, int], dry_run: bool,
                      already: dict[str, float]) -> dict[str, int]:
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
    for row in rows:
        ca, chain = row.get("ca"), row.get("chain")
        if not ca or not chain or ca in already:
            continue
        try:
            adapter = chains.get_adapter(chain)
            market = adapter.market(ca)
            if not market.ok:
                store.drop_from_watchlist(ca)
                continue

            tier = scoring.classify_tier(market, chain)
            if not tier.matched:
                # Aged past the window entirely — stop carrying it.
                if market.age_known and market.age_hours > 6:
                    store.drop_from_watchlist(ca)
                else:
                    store.bump_check(ca, int(row.get("checks") or 0))
                continue

            safety = adapter.safety(ca, market.pair_address)
            ev = scoring.evaluate(market, safety, chain,
                                  social_channels=social_counts.get(ca, 0))
            if not ev.should_alert:
                store.bump_check(ca, int(row.get("checks") or 0))
                continue

            log.info("[%s] REVIVED %s (%s) %s %d/100 — parked at %.2fh, "
                     "now %.2fh", chain, market.name, market.symbol,
                     ev.tier.tier, ev.conviction.score,
                     float(row.get("first_age_hours") or 0),
                     float(row.get("_age_now") or market.age_hours))

            if not dry_run:
                res = alerts.send_signal(ev, adapter)
                store.record_signal(ev, adapter, sent_ok=res.ok)
                if res.ok:
                    already[ca] = time.time()
            store.drop_from_watchlist(ca)
            revived[chain] = revived.get(chain, 0) + 1
        except Exception as e:
            log.warning("recheck %s failed: %s", ca[:12], e)
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

    stored = store.recent_mentions()
    by_ca: dict[str, set] = {}
    for row in stored:
        ca = row.get("ca")
        ch = row.get("channel")
        if ca and ch:
            by_ca.setdefault(ca, set()).add(ch)

    counts = {ca: len(chs) for ca, chs in by_ca.items()}
    hot = {ca: n for ca, n in counts.items()
           if n >= config.VELOCITY_MIN_CHANNELS}
    if hot:
        log.info("cross-channel consensus on %d tokens", len(hot))
    return counts


def scan_chain(chain: str, social_counts: dict[str, int],
               dry_run: bool = False, limit: int = 40,
               already: dict[str, float] | None = None) -> ChainRun:
    run = ChainRun(chain=chain)
    adapter = chains.get_adapter(chain)
    already = already if already is not None else {}

    try:
        candidates = adapter.discover()
    except Exception as e:
        log.error("[%s] discovery failed: %s", chain, e)
        run.errors += 1
        return run

    run.discovered = len(candidates)
    log.info("[%s] %d candidates", chain, run.discovered)

    for ca in candidates[:limit]:
        if ca in already:
            run.reject("cooldown")
            continue

        try:
            market = adapter.market(ca)
            if not market.ok:
                run.reject(f"market:{market.error}")
                continue

            # Cheap structural gate before spending a safety request.
            pre = scoring.classify_tier(market, chain)
            if not pre.matched:
                run.reject("tier")
                run.gate_fail(pre.failures)
                # Too young is a "not yet", not a "no". Park it.
                if run.parked < MAX_PARK_PER_SCAN and _worth_parking(pre, market):
                    store.watch_later(ca, chain, market.age_hours,
                                      market.name, market.symbol)
                    run.parked += 1
                continue

            safety = adapter.safety(ca, market.pair_address)
            ev = scoring.evaluate(
                market, safety, chain,
                social_channels=social_counts.get(ca, 0),
                smart_wallets=0,
            )
            run.evaluated += 1

            if not ev.should_alert:
                run.reject(ev.rejected_by or "unknown")
                continue

            log.info("[%s] SIGNAL %s (%s) %s %d/100 — %s",
                     chain, market.name, market.symbol,
                     ev.tier.tier, ev.conviction.score, ev.conviction.explain())

            if dry_run:
                run.alerted += 1
                continue

            res = alerts.send_signal(ev, adapter)
            if res.ok:
                run.alerted += 1
                already[ca] = time.time()
            else:
                log.warning("[%s] alert failed for %s: %s",
                            chain, market.symbol, res.error)
            store.record_signal(ev, adapter, sent_ok=res.ok)

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

    social_counts = refresh_social() if args.social else {}
    already = store.recently_alerted()
    if already:
        log.info("%d tokens inside re-alert cooldown", len(already))

    revived = revisit_watchlist(social_counts, args.dry_run, already)

    targets = [args.chain] if args.chain else config.enabled_chains()
    runs = []
    for chain in targets:
        try:
            runs.append(scan_chain(chain, social_counts, args.dry_run,
                                   args.limit, already))
        except Exception as e:
            log.error("[%s] scan crashed: %s", chain, e)

    print("\n" + "=" * 62)
    print("SCAN SUMMARY")
    print("=" * 62)
    total_alerts = 0
    for r in runs:
        total_alerts += r.alerted
        top = sorted(r.rejects.items(), key=lambda x: -x[1])[:3]
        reasons = ", ".join(f"{k}×{v}" for k, v in top) or "-"
        rev = revived.get(r.chain, 0)
        print(f"  {config.CHAINS[r.chain]['display']:<18} "
              f"found {r.discovered:>3}  scored {r.evaluated:>3}  "
              f"alerts {r.alerted + rev:>2}  parked {r.parked:>3}"
              + (f"  revived {rev}" if rev else "") + f"   {reasons}")
        if r.gate_fails:
            worst = sorted(r.gate_fails.items(), key=lambda x: -x[1])[:5]
            print("        blocked by: " +
                  ", ".join(f"{k}×{v}" for k, v in worst))
    print("-" * 62)
    print(f"  {total_alerts} alert(s) in {time.time() - started:.0f}s")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
