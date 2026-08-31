#!/usr/bin/env python3
"""
Watchdog.

Silence reads the same whether Surgeon is working or dead. Two outages went
unnoticed for hours because no alerts looks exactly like a quiet market — and
the daily brief runs on the same scheduler, so when that fails the thing that
would have told you fails with it.

This runs on its own schedule and only speaks when something is wrong.

    python3 alive.py            report to stdout
    python3 alive.py --send     and message Telegram if unhealthy
    python3 alive.py --force    send even when everything is fine

Exit code is 0 when healthy and 1 when not, so an external scheduler can
alert on the failure too.
"""

from __future__ import annotations

import sys
import time
import logging
import argparse

import config
import alerts
from chain_base import safe_float
from store import store

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("surgeon.alive")


def _minutes_since(ts: float) -> float | None:
    ts = safe_float(ts)
    return (time.time() - ts) / 60 if ts > 0 else None


def check() -> tuple[list[str], dict]:
    """
    (problems, facts). An empty problem list means Surgeon is alive.

    Each check answers a different failure. A scan can run and find nothing,
    which is normal; a scan that has not run at all is not. Positions can sit
    open for hours legitimately, but not unchecked.
    """
    W = config.WATCHDOG
    problems, facts = [], {}

    # -- has anything been recorded? -------------------------------
    rows = store.select("signals", {
        "select": "alerted_at,alert_sent",
        "order": "alerted_at.desc", "limit": "1"})
    last_signal = _minutes_since(rows[0]["alerted_at"]) if rows else None
    facts["last_signal_min"] = last_signal

    if last_signal is None:
        problems.append("no signals have ever been recorded")
    elif last_signal > W["quiet_minutes"]:
        problems.append(
            f"nothing recorded for {last_signal:.0f} minutes — the scanner "
            f"is not running, or is running and storing nothing")

    # -- is the watcher keeping up? --------------------------------
    # An open position that has not been re-read is the clearest sign the
    # watcher has stopped, and it is the failure that costs money: exits stop
    # firing while positions stay open.
    open_rows = store.open_positions()
    facts["open_positions"] = len(open_rows)
    if open_rows:
        oldest = min((safe_float(r.get("alerted_at")) for r in open_rows),
                     default=0)
        age = _minutes_since(oldest)
        facts["oldest_position_min"] = age
        if age and age > W["stale_positions"] + 60 * 8:
            # Past max_hold, so the watcher should have closed it long ago.
            problems.append(
                f"a position has been open {age / 60:.1f} hours — past the "
                f"maximum hold, so the watcher is not closing anything")

    # -- is anything reaching the phone? ---------------------------
    recent = store.select("signals", {
        "select": "alert_sent,alerted_at",
        "alerted_at": f"gte.{time.time() - 6 * 3600}",
        "limit": "500"})
    sent = sum(1 for r in recent if r.get("alert_sent"))
    facts["signals_6h"] = len(recent)
    facts["sent_6h"] = sent
    if recent and sent == 0:
        problems.append(
            f"{len(recent)} signals in six hours and none sent — delivery or "
            f"the alert floors are wrong")

    # -- is the database writable? ---------------------------------
    facts["store_live"] = getattr(store, "live", False)
    if not facts["store_live"]:
        problems.append("no database connection — nothing is being stored")

    return problems, facts


def compose(problems: list[str], facts: dict) -> str:
    if not problems:
        last = facts.get("last_signal_min")
        return ("💚 <b>Surgeon is alive</b>\n\n"
                f"Last signal {last:.0f}m ago · "
                f"{facts.get('open_positions', 0)} open · "
                f"{facts.get('sent_6h', 0)}/{facts.get('signals_6h', 0)} "
                f"sent in 6h")

    lines = ["🚨 <b>Surgeon may be down</b>", ""]
    lines += [f"• {alerts.esc(p)}" for p in problems]
    lines += ["", "<i>Checks worth running:</i>",
              "• Actions tab — are runs appearing?",
              "• cron-job.org — are triggers returning 204?",
              "• githubstatus.com — is Actions degraded?"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Surgeon watchdog")
    ap.add_argument("--send", action="store_true",
                    help="message Telegram when unhealthy")
    ap.add_argument("--force", action="store_true",
                    help="send even when everything is fine")
    args = ap.parse_args()

    problems, facts = check()
    text = compose(problems, facts)

    import re
    print(re.sub(r"<[^>]+>", "", text))

    if args.send and (problems or args.force):
        res = alerts.send(text)
        print("\nsent" if res.ok else f"\nsend failed: {res.error}")

    # Non-zero for a command line or an external scheduler that wants to
    # act on it. The GitHub workflow deliberately tolerates this, so a red
    # run there means the watchdog broke rather than that Surgeon is
    # unhealthy — the Telegram message carries that.
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
