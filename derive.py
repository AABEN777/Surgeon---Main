"""
Derived smart money.

King's idea, and the right one: rather than trusting a hand-researched list
or a third-party leaderboard, find the wallets that were holding Surgeon's
own winners early, and promote the ones that keep showing up.

Self-tuning, tied to this signal universe rather than someone else's, and
dependent on nothing external.

I had this blocked for weeks on the wrong constraint — I assumed it needed
Helius, which is Solana-only, and Solana has too few quality winners to work
from. But 27 of the 46 MOONs came from Robinhood, whose Blockscout instance
serves holder data we already fetch every scan. The chain that produces the
winners can also tell us who held them.

Runs on its own cadence, not inside the scan:

    python3 derive.py              measure wallets against recent winners
    python3 derive.py --dry-run    report without promoting anything
"""

from __future__ import annotations

import sys
import time
import logging
import argparse
from collections import defaultdict

import config
import chains
from chain_base import http_get, safe_float, is_solana_infrastructure
from store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("surgeon.derive")

WINNING_OUTCOMES = ("MOON", "BIG_WIN", "WIN")


def winners(limit: int = 200, min_peak: float = 100.0) -> list[dict]:
    """
    Closed signals worth learning from.

    WEAK_WIN is excluded deliberately: a token that closed +4% tells us
    nothing about who was early to it, and there are enough of those to drown
    the real ones.
    """
    rows = store.select("signals", {
        "select": "ca,chain,name,symbol,peak_pnl,outcome,alerted_at",
        "outcome": f"in.({','.join(WINNING_OUTCOMES)})",
        "order": "peak_pnl.desc",
        "limit": str(limit * 2),
    })
    return [r for r in rows
            if safe_float(r.get("peak_pnl")) >= min_peak][:limit]


# ── holder lookups ────────────────────────────────────────────────

def _evm_holders(chain: str, ca: str, top: int = 50) -> list[str]:
    """Holder addresses from a chain's Blockscout instance."""
    base = config.CHAINS[chain].get("blockscout")
    if not base:
        return []
    data = http_get(f"{base}/api/v2/tokens/{ca}/holders")
    out = []
    from chain_base import BURN_ADDRESSES
    for item in (data or {}).get("items", [])[:top]:
        addr = ((item.get("address") or {}).get("hash") or "").lower()
        is_contract = (item.get("address") or {}).get("is_contract")
        # A contract holding tokens is a pool or a bridge, not a trader —
        # and Blockscout does not flag the zero address as a contract, which
        # is how it turned up holding seven winners at an average peak of
        # 2,320%.
        if not addr or is_contract or addr in BURN_ADDRESSES:
            continue
        if set(addr[2:]) <= {"0"} or addr.endswith("dead"):
            continue
        out.append(addr)
    return out


def _solana_holders(ca: str, top: int = 50) -> list[str]:
    data = http_get(f"https://api.rugcheck.xyz/v1/tokens/{ca}/report")
    if not data:
        return []
    from chain_base import solana_pool_accounts
    pools = solana_pool_accounts(data.get("markets"))
    out = []
    for h in (data.get("topHolders") or [])[:top]:
        if is_solana_infrastructure(h, pools):
            continue
        owner = h.get("owner") or h.get("address")
        if owner:
            out.append(str(owner))
    return out


def holders_of(chain: str, ca: str) -> list[str]:
    try:
        if config.CHAINS[chain]["kind"] == "svm":
            return _solana_holders(ca)
        return _evm_holders(chain, ca)
    except Exception as e:
        log.warning("holders for %s on %s failed: %s", ca[:12], chain, e)
        return []


# ── the derivation ────────────────────────────────────────────────

def measure(sample: list[dict]) -> dict[str, dict]:
    """
    {wallet: {chain, winners, tokens, total_peak}} across the sample.

    Counts distinct winning tokens, not appearances. A wallet holding one
    token that mooned is a lottery winner; a wallet holding four unrelated
    ones is doing something repeatable.
    """
    seen: dict[str, dict] = defaultdict(
        lambda: {"chain": None, "winners": 0, "tokens": [], "total_peak": 0.0})

    for row in sample:
        ca, chain = row.get("ca"), row.get("chain")
        if not ca or not chain:
            continue
        peak = safe_float(row.get("peak_pnl"))
        for wallet in holders_of(chain, ca):
            key = f"{chain}:{wallet}"
            rec = seen[key]
            rec["chain"] = chain
            rec["wallet"] = wallet
            if ca not in rec["tokens"]:
                rec["tokens"].append(ca)
                rec["winners"] += 1
                rec["total_peak"] += peak
    return dict(seen)


def losers(limit: int = 120, max_peak: float = 20.0,
           chain: str | None = None) -> list[dict]:
    """
    Closed signals that went nowhere — the control group, per chain.

    The chain filter is not a refinement, it is the whole point. A Robinhood
    wallet cannot appear in a Base token's holder list, so checking it
    against Base losers returns zero by construction and reports a wallet as
    perfectly selective when nothing was actually tested. Every candidate in
    the first run came back at 70-100% precision for exactly that reason.
    """
    params = {
        "select": "ca,chain,peak_pnl,outcome",
        "outcome": "in.(LOSS,WEAK_WIN)",
        "order": "alerted_at.desc",
        "limit": str(limit * 3),
    }
    if chain:
        params["chain"] = f"eq.{chain}"
    rows = store.select("signals", params)
    return [r for r in rows
            if safe_float(r.get("peak_pnl")) <= max_peak][:limit]


def count_appearances(sample: list[dict], wallets: set[str]) -> dict[str, int]:
    """How many of these tokens each wallet held."""
    counts: dict[str, int] = defaultdict(int)
    for row in sample:
        ca, chain = row.get("ca"), row.get("chain")
        if not ca or not chain:
            continue
        for wallet in holders_of(chain, ca):
            key = f"{chain}:{wallet}"
            if key in wallets:
                counts[key] += 1
    return dict(counts)


def promote(measured: dict[str, dict], dry_run: bool = False,
            loser_counts: dict[str, int] | None = None,
            tested: dict[str, int] | int | None = None) -> list[dict]:
    """
    Wallets appearing across enough unrelated winners become smart money.

    The bar is distinct tokens, because that is the thing that cannot happen
    by chance. Two is coincidence on a chain with a few thousand active
    wallets; the threshold sits above it.
    """
    cfg = config.SMART_MONEY_DERIVED
    need = cfg["min_winners"]
    loser_counts = loser_counts or {}
    picks = []

    for key, rec in measured.items():
        if rec["winners"] < need:
            continue

        # Selectivity, not popularity. A wallet in nine winners and two
        # hundred losers is buying everything; one in nine winners and a
        # dozen losers is choosing.
        lost = loser_counts.get(key, 0)
        seen = rec["winners"] + lost
        precision = rec["winners"] / seen if seen else 0.0

        # Only judge a wallet that was actually compared against something on
        # its own chain. Untested is not the same as perfect.
        was_tested = (tested.get(key, 0) if isinstance(tested, dict)
                      else (tested or 0))
        if not was_tested:
            continue
        if precision < cfg["min_precision"]:
            continue

        picks.append({
            "address": rec["wallet"],
            "chain": rec["chain"],
            "label": (f"derived: {rec['winners']}W/{lost}L "
                      f"({precision:.0%}), avg peak "
                      f"{rec['total_peak'] / rec['winners']:.0f}%"),
            "active": True,
            "added_at": time.time(),
            "_score": precision * rec["winners"],
        })

    picks.sort(key=lambda p: -p["_score"])
    for p in picks:
        p.pop("_score", None)
    picks = picks[:config.SMART_MONEY_DERIVED["max_promote"]]

    if picks and not dry_run:
        store.upsert("smart_wallets", picks, on_conflict="address,chain")
    return picks


def review_existing(measured: dict[str, dict], dry_run: bool = False) -> list[str]:
    """
    Retire tracked wallets that no longer appear in any winner.

    The six hand-picked wallets were researched on a machine that no longer
    exists, and nothing has ever checked whether they still earn their place.
    Only wallets added long enough ago to have had a fair chance are judged.
    """
    rows = store.select("smart_wallets",
                        {"select": "address,chain,label,added_at,active",
                         "active": "eq.true", "limit": "200"})
    if not rows:
        return []

    grace = config.SMART_MONEY_DERIVED["review_after_hours"] * 3600
    cutoff = time.time() - grace
    retired = []

    for row in rows:
        added = safe_float(row.get("added_at"))
        if added and added > cutoff:
            continue                      # too new to judge
        key = f"{row.get('chain')}:{row.get('address')}"
        if key in measured:
            continue                      # still turning up in winners
        retired.append(row["address"])
        if not dry_run:
            store.update("smart_wallets",
                         {"address": row["address"], "chain": row["chain"]},
                         {"active": False,
                          "label": f"retired {time.strftime('%Y-%m-%d')}"})
    return retired


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive smart money from winners")
    ap.add_argument("--dry-run", action="store_true",
                    help="report without promoting or retiring")
    ap.add_argument("--limit", type=int, default=60,
                    help="how many winners to examine")
    ap.add_argument("--min-peak", type=float, default=100.0,
                    help="minimum peak %% to count as a winner")
    ap.add_argument("--losers", type=int, default=80,
                    help="how many losing tokens to check candidates against")
    args = ap.parse_args()

    started = time.time()
    sample = winners(args.limit, args.min_peak)
    if not sample:
        log.info("no winners above +%.0f%% yet", args.min_peak)
        return 0

    by_chain: dict[str, int] = defaultdict(int)
    for r in sample:
        by_chain[r.get("chain")] += 1
    log.info("examining %d winners: %s", len(sample),
             ", ".join(f"{c} {n}" for c, n in sorted(by_chain.items(),
                                                     key=lambda x: -x[1])))

    measured = measure(sample)
    log.info("%d distinct wallets held them", len(measured))

    # The control group, matched by chain: what else did these wallets buy?
    need = config.SMART_MONEY_DERIVED["min_winners"]
    candidates = {k for k, v in measured.items() if v["winners"] >= need}

    by_chain: dict[str, set[str]] = defaultdict(set)
    for key in candidates:
        by_chain[key.split(":", 1)[0]].add(key)

    loser_counts: dict[str, int] = {}
    tested: dict[str, int] = {}
    for chain_key, keys in by_chain.items():
        sample_l = losers(args.losers, chain=chain_key)
        if not sample_l:
            log.warning("[%s] no losing tokens to compare against — "
                        "candidates here cannot be judged", chain_key)
            continue
        log.info("[%s] checking %d candidates against %d tokens that went "
                 "nowhere", chain_key, len(keys), len(sample_l))
        loser_counts.update(count_appearances(sample_l, keys))
        for k in keys:
            tested[k] = len(sample_l)

    picks = promote(measured, args.dry_run, loser_counts, tested)
    retired = review_existing(measured, args.dry_run)

    print("\n" + "=" * 62)
    print("DERIVED SMART MONEY" + ("  (dry run)" if args.dry_run else ""))
    print("=" * 62)
    if picks:
        for p in picks:
            print(f"  + {p['chain']:<11} {p['address'][:20]}…  {p['label']}")
    else:
        need = config.SMART_MONEY_DERIVED["min_winners"]
        best = max((r["winners"] for r in measured.values()), default=0)
        print(f"  no wallet reached {need} distinct winners (best was {best})")
    if retired:
        print(f"\n  retired {len(retired)} wallet(s) no longer appearing in winners")
    print("-" * 62)
    print(f"  {len(sample)} winners, {len(measured)} wallets, "
          f"{time.time() - started:.0f}s")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
