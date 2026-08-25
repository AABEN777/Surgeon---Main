"""
Scam heuristics.

These come from King's own trading experience rather than from anything the
APIs advertise, and the thresholds are far tighter than Surgeon's entry
gates — top holder at 3.5% against a 20% reject, for instance. Enforced as
rejects they would silence the scanner almost entirely.

So they are warnings that cost conviction. The signal still fires; it arrives
carrying its rap sheet, and a token collecting several of these ends up below
the alert floor on arithmetic rather than by decree.
"""

from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass
class RiskFlag:
    code: str
    detail: str
    penalty: int
    severity: str = "warn"      # warn | danger

    def __str__(self) -> str:
        return f"{self.code} ({self.detail})"


# ── individual checks ─────────────────────────────────────────────

def _top_holder(safety, market=None) -> RiskFlag | None:
    """
    The single largest wallet — the number King treats as mattering most.

    Ideal under 8%, risky above 12%. The previous line was 3.5%, which is
    tighter than the trenches use and tighter than the outcomes justify:
    TOP_HOLDER-6 and -14 had the two highest average peaks of any component
    in the table, at 68 and 67. Concentration was being charged against the
    best-performing cohort.
    """
    pct = safety.top_holder_pct
    if pct is None or pct <= config.SCAM["top_holder_pct"]:
        return None

    if pct >= 30:
        points, severity = -25, "danger"
    elif pct >= config.SCAM["top_holder_max"]:
        points, severity = -14, "danger"
    else:
        points, severity = -6, "warn"

    age = getattr(market, "age_hours", None) if market else None
    known = getattr(market, "age_known", False) if market else False
    if (known and age is not None
            and age < config.SCAM["top_holder_grace_hours"]
            and severity == "warn"):
        # A holder base takes hours to spread; charging full price for that
        # in the first hour penalises what every winner looked like.
        return RiskFlag("TOP_HOLDER",
                        f"{pct:.1f}% in one wallet, {age * 60:.0f}m old",
                        points // 2, severity)
    return RiskFlag("TOP_HOLDER", f"{pct:.1f}% in one wallet", points, severity)


def _top10(safety, market=None) -> RiskFlag | None:
    """
    What the ten largest hold between them.

    Ideal under 25%, with up to 35% tolerated while a token is very early —
    distribution genuinely takes time, and every one of the fifteen biggest
    winners was under two hours old when it signalled.
    """
    pct = safety.top10_pct
    if pct is None:
        return None

    age = getattr(market, "age_hours", None) if market else None
    known = getattr(market, "age_known", False) if market else False
    very_early = (known and age is not None
                  and age < config.SCAM["top10_early_hours"])
    line = (config.SCAM["top10_early_pct"] if very_early
            else config.SCAM["top10_pct"])
    if pct <= line:
        return None

    if pct >= 60:
        return RiskFlag("TOP10", f"top 10 hold {pct:.0f}%", -28, "danger")
    if pct >= 50:
        return RiskFlag("TOP10", f"top 10 hold {pct:.0f}%", -22, "danger")
    if pct >= 40:
        return RiskFlag("TOP10", f"top 10 hold {pct:.0f}%", -14, "danger")
    return RiskFlag("TOP10", f"top 10 hold {pct:.0f}%", -8)


def _bundled_distribution(safety, market=None) -> RiskFlag | None:
    """
    A distribution too flat to have happened on its own.

    Bundling produces a *low* top holder, not a high one: split the supply
    across two hundred wallets at half a percent each and the top ten hold
    five percent between them. CyberPump read 0.5% top holder at 1.2 hours
    old, was scored CLEAN, and was dumped into its own locked pool.

    Organic early distribution is a power law — someone always bought more
    than everyone else. When the largest holder of a young token holds almost
    nothing, and the next nine hold the same almost-nothing, the supply was
    placed rather than bought.
    """
    top1, top10 = safety.top_holder_pct, safety.top10_pct
    if top1 is None or top1 <= 0:
        return None

    age = getattr(market, "age_hours", None) if market else None
    known = getattr(market, "age_known", False) if market else False
    if not known or age is None or age > config.SCAM["bundle_max_age_hours"]:
        return None          # older tokens genuinely do flatten out

    if top1 > config.SCAM["bundle_max_top1"]:
        return None          # someone holds a real position, as expected

    detail = f"largest holder just {top1:.2f}% at {age * 60:.0f}m old"
    if top10 is not None and top10 > 0:
        # 1.0 means all ten hold exactly the same amount.
        uniformity = top10 / (top1 * 10)
        if uniformity < config.SCAM["bundle_uniformity"]:
            return None      # still a power law, just a small one
        detail += f", top 10 all near {top1:.2f}%"

    return RiskFlag("EVEN_SPLIT", detail, -18, "danger")


def _wallet_cluster(safety) -> RiskFlag | None:
    """
    Many wallets, one hand.

    Every per-wallet metric reads clean when supply is split across enough
    addresses — that is the point of splitting it. This counts the addresses
    that are not independent, which no amount of splitting reduces.
    """
    n = safety.cluster_wallets
    if not n or n < config.CLUSTERS["min_wallets"]:
        return None
    pct = safety.cluster_supply_pct or 0.0
    detail = f"{n} wallets {safety.cluster_how or 'acting together'}"
    if pct > 0:
        detail += f", {pct:.0f}% of supply"

    severe = (n >= config.CLUSTERS["danger_wallets"]
              or pct >= config.CLUSTERS["danger_supply_pct"])
    if severe:
        return RiskFlag("CLUSTER", detail, -28, "danger")
    if n >= config.CLUSTERS["min_wallets"] * 2:
        return RiskFlag("CLUSTER", detail, -18, "danger")
    return RiskFlag("CLUSTER", detail, -10)


def _thin_volume(market) -> RiskFlag | None:
    """
    Volume well below market cap means the valuation is not being tested.

    A real market turns over; a painted one shows a large cap on trades that
    never happened. Uses market cap where reported, FDV otherwise.
    """
    cap = market.market_cap or market.fdv
    if cap <= 0 or market.volume_24h <= 0:
        return None
    ratio = market.volume_24h / cap
    if ratio >= config.SCAM["min_volume_to_mcap"]:
        return None
    if ratio < 0.15:
        return RiskFlag("THIN_VOLUME",
                        f"24h volume {ratio:.0%} of cap", -18, "danger")
    return RiskFlag("THIN_VOLUME", f"24h volume {ratio:.0%} of cap", -10)


def _bundled(safety) -> RiskFlag | None:
    """
    Supply held by wallets funded together and bought at launch.

    RugCheck tags these as insiders; Surgeon previously filtered them out of
    the concentration figure and then discarded the fact, which quietly
    removed the strongest scam tell in the response.
    """
    pct = safety.insider_pct
    if pct is None or pct <= config.SCAM["bundled_pct"]:
        return None
    if pct >= 30:
        return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -30, "danger")
    if pct >= 20:
        return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -22, "danger")
    return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -14)


def _lock_expiring(safety) -> RiskFlag | None:
    """
    Liquidity locked until this afternoon is not locked in any useful sense.

    Scaled by how soon: a lock with an hour left is a countdown, one with a
    day left is a schedule. Burned LP and locks with no expiry return nothing.
    """
    h = safety.lp_unlock_hours
    if h is None:
        return None
    if h <= 0:
        return RiskFlag("LP_EXPIRED", "lock already expired", -25, "danger")
    if h <= 2:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h * 60:.0f}m", -20, "danger")
    if h <= 12:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h:.0f}h", -12)
    if h <= config.SAFETY["lp_min_lock_hours"]:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h:.0f}h", -6)
    return None


def _lp_pullable(safety) -> RiskFlag | None:
    """
    A single wallet able to drain the pool.

    Token concentration and LP concentration are different risks and we only
    measured the first. A Robinhood token with a 2.1% top holder — genuinely
    well distributed — had its liquidity removed in one transaction, because
    pulling a pool requires holding LP tokens, not the token itself.
    """
    pct = safety.lp_top_unlocked_pct
    if pct is None or pct <= config.SCAM["lp_pullable_pct"]:
        return None
    if pct >= 80:
        return RiskFlag("LP_PULLABLE", f"one wallet holds {pct:.0f}% of the pool",
                        -25, "danger")
    if pct >= 50:
        return RiskFlag("LP_PULLABLE", f"one wallet holds {pct:.0f}% of the pool",
                        -16, "danger")
    return RiskFlag("LP_PULLABLE", f"one wallet holds {pct:.0f}% of the pool", -8)


def _thin_holders(safety) -> RiskFlag | None:
    n = safety.holder_count
    if n is None or n >= config.SCAM["min_holders"]:
        return None
    return RiskFlag("FEW_HOLDERS", f"{n} holders", -12)


def _creator_heavy(safety) -> RiskFlag | None:
    """Deployer holdings. Ideal under 5%, risky above 10%."""
    pct = safety.creator_holds_pct
    if pct is None or pct <= config.SCAM["creator_holds_pct"]:
        return None
    if pct >= 20:
        return RiskFlag("CREATOR_HOLDS", f"deployer holds {pct:.1f}%",
                        -25, "danger")
    if pct >= config.SCAM["creator_holds_max"]:
        return RiskFlag("CREATOR_HOLDS", f"deployer holds {pct:.1f}%",
                        -16, "danger")
    return RiskFlag("CREATOR_HOLDS", f"deployer holds {pct:.1f}%", -8)


def _unverified_safety(safety) -> RiskFlag | None:
    """
    Being unable to check is itself a risk — but conviction already charges
    UNVERIFIED for exactly this, and two mechanisms billing the same fact
    took the +410% winner from 59 to 49 and silenced it. The flag remains so
    it appears in the alert and counts toward a stacked-danger block; the
    points sit in conviction alone.
    """
    if safety.verified:
        return None
    return RiskFlag("UNCHECKED", "no safety source answered", 0, "danger")


CHECKS = (
    ("safety_market", _top_holder),
    ("safety_market", _top10),
    ("safety_market", _bundled_distribution),
    ("safety", _wallet_cluster),
    ("market", _thin_volume),
    ("safety", _bundled),
    ("safety", _lock_expiring),
    ("safety", _lp_pullable),
    ("safety", _thin_holders),
    ("safety", _creator_heavy),
    ("safety", _unverified_safety),
)


def assess(market, safety) -> list[RiskFlag]:
    """Every warning this token earns, worst first."""
    if not config.SCAM.get("enabled", True):
        return []
    flags: list[RiskFlag] = []
    for kind, check in CHECKS:
        if kind == "market":
            flag = check(market)
        elif kind == "safety_market":
            flag = check(safety, market)
        else:
            flag = check(safety)
        if flag:
            flags.append(flag)
    flags.sort(key=lambda f: f.penalty)
    return flags


def total_penalty(flags: list[RiskFlag]) -> int:
    return sum(f.penalty for f in flags)


def danger_count(flags: list[RiskFlag]) -> int:
    return sum(1 for f in flags if f.severity == "danger")


def summarise(flags: list[RiskFlag]) -> str:
    if not flags:
        return "no scam flags"
    return " · ".join(str(f) for f in flags)
