"""
Cluster detection.

What Bubblemaps shows visually: wallets that are not independent. Supply
spread across two hundred addresses looks like healthy distribution in every
per-wallet metric, and dumps as one position because it is one position.

Two signatures, from data already being fetched:

  Solana   RugCheck computes insider networks — wallets it has already linked
           by funding and timing. Surgeon read the percentage and threw away
           the structure.

  EVM      The token's own transfer history. One address sending supply to
           dozens of wallets before trading opens is a bundle, and it is
           visible in the first page of transfers.

Neither is as thorough as a full transaction graph. Both catch the shape that
matters: many wallets, one hand.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

import config
from chain_base import http_get, safe_float, BURN_ADDRESSES

log = logging.getLogger("surgeon.clusters")


class Cluster:
    """A set of wallets that appear to be acting together."""

    def __init__(self, size: int, supply_pct: float, source: str, how: str):
        self.size = size
        self.supply_pct = supply_pct
        self.source = source
        self.how = how

    def __repr__(self):
        return (f"Cluster({self.size} wallets, {self.supply_pct:.1f}%, "
                f"{self.how})")


# ── SOLANA ────────────────────────────────────────────────────────

def solana_clusters(report: dict) -> list[Cluster]:
    """
    Insider networks from a RugCheck report.

    RugCheck has already done the graph work — it links wallets by funding
    source and timing and reports them as networks. Surgeon summed their
    holdings into insider_pct and discarded everything else, including how
    many separate hands were involved.
    """
    out = []
    networks = report.get("insiderNetworks") or []
    for net in networks:
        if not isinstance(net, dict):
            continue
        size = int(safe_float(net.get("size") or net.get("wallets") or 0))
        pct = safe_float(net.get("tokenAmountPct") or net.get("percent") or 0)
        # RugCheck reports fractions in some fields and percentages in others.
        if 0 < pct <= 1:
            pct *= 100
        if size >= config.CLUSTERS["min_wallets"]:
            out.append(Cluster(size, pct,
                               str(net.get("id") or net.get("type") or "network"),
                               "funded together"))

    # Some reports carry only a count rather than the networks themselves.
    if not out:
        detected = int(safe_float(report.get("graphInsidersDetected") or 0))
        if detected >= config.CLUSTERS["min_wallets"]:
            out.append(Cluster(detected, 0.0, "graph", "linked by rugcheck"))
    return out


# ── EVM ───────────────────────────────────────────────────────────

def evm_clusters(chain: str, ca: str,
                 exclude: set | None = None) -> list[Cluster]:
    """
    Wallets seeded by a single address before trading opened.

    Reads the earliest transfers and counts how many distinct wallets each
    sender supplied. A deployer distributing to forty addresses shows up as
    one sender with forty recipients, at the very start of the history —
    which is the whole bundle, before a single trade.

    The pool has to be excluded or every buyer counts as its recipient: a
    token with thirty ordinary buys reads as one address seeding thirty
    wallets, which is what trading looks like, not what bundling looks like.
    """
    base = config.CHAINS[chain].get("blockscout")
    if not base:
        return []

    data = http_get(f"{base}/api", params={
        "module": "account", "action": "tokentx",
        "contractaddress": ca, "sort": "asc", "page": 1,
        "offset": config.CLUSTERS["transfers_examined"],
    })
    result = (data or {}).get("result")
    if not isinstance(result, list) or not result:
        return []

    skip = {a.lower() for a in (exclude or set()) if a}
    skip |= {a.lower() for a in BURN_ADDRESSES}
    skip.add(ca.lower())

    recipients: dict[str, set] = defaultdict(set)
    volume: dict[str, float] = defaultdict(float)
    for tx in result:
        src = str(tx.get("from") or "").lower()
        dst = str(tx.get("to") or "").lower()
        if not src or not dst or src in skip or dst in skip:
            continue
        recipients[src].add(dst)
        volume[src] += safe_float(tx.get("value"))

    total = sum(volume.values()) or 1.0
    out = []
    for src, dests in recipients.items():
        if len(dests) >= config.CLUSTERS["min_wallets"]:
            out.append(Cluster(len(dests), volume[src] / total * 100.0,
                               src, "seeded by one address"))
    out.sort(key=lambda c: -c.size)
    return out[:3]


# ── shared ────────────────────────────────────────────────────────

def worst(clusters: list[Cluster]) -> Cluster | None:
    return max(clusters, key=lambda c: c.size, default=None)


def describe(clusters: list[Cluster]) -> str:
    c = worst(clusters)
    if not c:
        return ""
    if c.supply_pct > 0:
        return (f"{c.size} wallets {c.how}, holding {c.supply_pct:.0f}% "
                f"between them")
    return f"{c.size} wallets {c.how}"
