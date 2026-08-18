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

def _top_holder(safety) -> RiskFlag | None:
    """
    A single wallet holding real size can exit into your bid.

    Scaled rather than binary: 4% on a fresh launch is ordinary, 25% is a
    countdown. Pools, lockers and burn addresses are already excluded
    upstream, so this is float genuinely held by someone.
    """
    pct = safety.top_holder_pct
    if pct is None or pct <= config.SCAM["top_holder_pct"]:
        return None
    if pct >= 20:
        return RiskFlag("TOP_HOLDER", f"{pct:.1f}% in one wallet", -22, "danger")
    if pct >= 10:
        return RiskFlag("TOP_HOLDER", f"{pct:.1f}% in one wallet", -14)
    return RiskFlag("TOP_HOLDER", f"{pct:.1f}% in one wallet", -6)


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


def _thin_holders(safety) -> RiskFlag | None:
    n = safety.holder_count
    if n is None or n >= config.SCAM["min_holders"]:
        return None
    return RiskFlag("FEW_HOLDERS", f"{n} holders", -12)


def _creator_heavy(safety) -> RiskFlag | None:
    pct = safety.creator_holds_pct
    if pct is None or pct <= config.SCAM["creator_holds_pct"]:
        return None
    return RiskFlag("CREATOR_HOLDS", f"deployer holds {pct:.1f}%", -16, "danger")


def _unverified_safety(safety) -> RiskFlag | None:
    """Being unable to check is itself a risk, and should read as one."""
    if safety.verified:
        return None
    return RiskFlag("UNCHECKED", "no safety source answered", -10, "danger")


CHECKS = (
    ("safety", _top_holder),
    ("market", _thin_volume),
    ("safety", _bundled),
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
        flag = check(market if kind == "market" else safety)
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
