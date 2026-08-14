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


@dataclass
class ChainRun:
    chain: str
    discovered: int = 0
    evaluated: int = 0
    alerted: int = 0
    rejects: dict = field(default_factory=dict)
    errors: int = 0

    def reject(self, reason: str):
        self.rejects[reason] = self.rejects.get(reason, 0) + 1


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
                    help="evaluate and log, send nothing")
    ap.add_argument("--social", action="store_true",
                    help="refresh Telegram mentions before scanning")
    ap.add_argument("--limit", type=int, default=40,
                    help="max candidates per chain")
    args = ap.parse_args()

    started = time.time()
    log.info("surgeon scan starting — %s mode",
             "DRY RUN" if args.dry_run else "LIVE")

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
        print(f"  {config.CHAINS[r.chain]['display']:<18} "
              f"found {r.discovered:>3}  scored {r.evaluated:>3}  "
              f"alerts {r.alerted:>2}   {reasons}")
    print("-" * 62)
    print(f"  {total_alerts} alert(s) in {time.time() - started:.0f}s")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
