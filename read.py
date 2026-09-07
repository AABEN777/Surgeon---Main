"""
The read.

Surgeon sends a few hundred alerts a day across four chains. The score tells
King how much a token resembles a fresh launch; it does not tell him what
this particular one looks like. This does.

Every number below is measured from King's own closed trades, with the sample
size stated. Nothing here is an opinion about what ought to matter — if a
factor is not in the outcome data, it is not in this file.

The headline finding: two or more strong signals together wins 58.8% across
170 trades against 35.9% across 1,433. That spread is the point of the whole
module.
"""

from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass
class Factor:
    """One measured thing, with the evidence behind it."""
    label: str
    win_rate: float
    sample: int
    positive: bool = True
    rug_rate: float | None = None      # where it is the point of the factor

    @property
    def confidence(self) -> str:
        """How much weight the sample can carry."""
        if self.sample >= 100:
            return "solid"
        if self.sample >= 40:
            return "fair"
        return "thin"


# ── what the data actually says ───────────────────────────────────
# Baseline for comparison: 38.4% across everything closed.
# Update these from real queries, never from expectation.
BASELINE = 38.4

STRONG = {
    "buy_ratio":   Factor("buying pressure 85-97%", 69.8, 43),
    "holders_5k":  Factor("5,000+ holders",         72.0, 25),
    "holders_1k":  Factor("1,000-5,000 holders",    45.9, 74),
    "venue":       Factor("on a venue that wins",   60.0, 110),
    "cluster":     Factor("wallet cluster present", 59.1, 22),
    "tier":        Factor("second_moon or boosted", 46.6, 311),

    # Age, and it is the only thing that separates a clean token that rugs
    # from a clean token that survives. Restricted to tokens that passed
    # safety, the two groups are identical on every field we check — top ten
    # 13.7% against 12.2%, insider 0.0% against 0.0%, LP 100% locked in both.
    # The one difference is how long they had been alive: 0.76h against
    # 3.29h.
    "age_30_60":   Factor("30-60 minutes old",      54.3,  46, rug_rate=10.9),
    "age_1h_plus": Factor("over an hour old",       57.1,  42, rug_rate=4.8),
}

WEAK = {
    "no_activity": Factor("no trades in 5 minutes",  3.0, 164, positive=False),
    "top10_heavy": Factor("top 10 hold 25%+",       34.4,  32, positive=False),
    "first_moon":  Factor("first_moon tier",        33.4, 629, positive=False),
    "holders_few": Factor("under 1,000 holders",    33.9,  59, positive=False),

    # Three times the rug rate of anything older, on 88 trades. No safety
    # check we have distinguishes these — only the clock does.
    "age_under_30": Factor("under 30 minutes old",  39.8,  88,
                           positive=False, rug_rate=30.7),
}

# Measured directly: how the count of strong signals maps to outcome.
BY_COUNT = {
    0: Factor("no strong signals",       35.9, 1433),
    1: Factor("one strong signal",       35.9, 1433),   # same cohort
    2: Factor("two or more",             58.8,  170),
}


def _venue_wins(dex: str | None) -> bool:
    rule = config.VENUES.get((dex or "").lower())
    return bool(rule and rule.get("conviction", 0) > 0)


def assess(market, safety, tier: str) -> tuple[list[Factor], list[Factor]]:
    """(strong signals present, weak signals present)."""
    strong, weak = [], []

    # -- buying pressure -------------------------------------------
    buys = market.buys_5m if market.buys_5m is not None else None
    sells = market.sells_5m if market.sells_5m is not None else None
    if buys is not None and sells is not None:
        total = buys + sells
        if total == 0:
            weak.append(WEAK["no_activity"])
        else:
            ratio = buys / total
            # The measured band. Above 97% is a different cohort — 43.8% on
            # 16 trades, too thin to claim, and unsustainable by nature.
            if 0.85 <= ratio <= 0.97:
                strong.append(STRONG["buy_ratio"])

    # -- holders ---------------------------------------------------
    holders = safety.holder_count
    if holders is not None:
        if holders >= 5000:
            strong.append(STRONG["holders_5k"])
        elif holders >= 1000:
            strong.append(STRONG["holders_1k"])
        elif holders >= 200:
            weak.append(WEAK["holders_few"])

    # -- venue -----------------------------------------------------
    if _venue_wins(market.dex):
        strong.append(STRONG["venue"])

    # -- wallet clusters -------------------------------------------
    # Counterintuitive and thin, but it is what the data says: clustered
    # tokens win 59.1% and rug 4.5%. Shown with its sample size so King can
    # weigh it himself.
    if (safety.cluster_wallets or 0) >= config.CLUSTERS["min_wallets"]:
        strong.append(STRONG["cluster"])

    # -- tier ------------------------------------------------------
    if tier in ("second_moon", "boosted"):
        strong.append(STRONG["tier"])
    elif tier == "first_moon":
        weak.append(WEAK["first_moon"])

    # -- age -------------------------------------------------------
    # The only factor that separates a clean token that rugs from a clean one
    # that survives, so it belongs in the read whatever the score does with
    # it.
    if getattr(market, "age_known", False) and market.age_hours is not None:
        age = market.age_hours
        if age < 0.5:
            weak.append(WEAK["age_under_30"])
        elif age < 1.0:
            strong.append(STRONG["age_30_60"])
        else:
            strong.append(STRONG["age_1h_plus"])

    # -- concentration ---------------------------------------------
    if (safety.top10_pct or 0) >= config.SCAM["top10_pct"]:
        weak.append(WEAK["top10_heavy"])

    return strong, weak


def expected(strong_count: int) -> Factor:
    """What this many strong signals has been worth historically."""
    return BY_COUNT[2] if strong_count >= 2 else BY_COUNT[0]


def render(market, safety, tier: str) -> str:
    """
    The read, as Telegram HTML. Empty when there is nothing measured to say.

    Sample sizes are shown because a 72% win rate on 25 trades and one on 629
    are not the same claim, and King should be able to tell them apart at a
    glance rather than taking the number at face value.
    """
    import alerts

    strong, weak = assess(market, safety, tier)
    if not strong and not weak:
        return ""

    band = expected(len(strong))
    if len(strong) >= 2:
        icon, verdict = "🟢", f"{len(strong)} strong signals"
    elif len(strong) == 1:
        icon, verdict = "🟡", "one strong signal"
    else:
        icon, verdict = "⚪", "no strong signals"

    lines = [f"{icon} <b>READ</b> — {verdict} · "
             f"this shape wins {band.win_rate:.0f}% "
             f"<i>(n={band.sample})</i>"]

    def detail(f):
        # Rug rate is shown where it is the point of the factor — for age it
        # is the whole reason the factor exists.
        if f.rug_rate is not None:
            return (f"<i>{f.win_rate:.0f}% win, {f.rug_rate:.0f}% rug, "
                    f"n={f.sample}</i>")
        return f"<i>{f.win_rate:.0f}%, n={f.sample}</i>"

    for f in strong:
        lines.append(f"   ✓ {alerts.esc(f.label)} {detail(f)}")
    for f in weak:
        lines.append(f"   ✗ {alerts.esc(f.label)} {detail(f)}")

    thin = [f for f in strong + weak if f.confidence == "thin"]
    if thin:
        lines.append("   <i>· thin samples marked by n; treat with care</i>")

    return "\n".join(lines)
