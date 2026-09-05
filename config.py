"""
Surgeon v2 — central configuration.

Everything tunable lives here. Chain adapters read from CHAINS,
the scoring core reads from THRESHOLDS / NARRATIVES / SMART_MONEY.

Values marked VERIFY are resolved by running discover_chain_ids.py once.
"""

import os

# ── SECRETS (set as GitHub Actions secrets / env vars) ────────────
HELIUS_API_KEY      = os.getenv("HELIUS_API_KEY", "")
GOPLUS_APP_KEY      = os.getenv("GOPLUS_APP_KEY", "")      # optional, raises rate limit
GOPLUS_APP_SECRET   = os.getenv("GOPLUS_APP_SECRET", "")   # optional
# Sending is opt-in. A missing or mistyped flag must fail closed, not open.
LIVE_ALERTS         = os.getenv("SURGEON_LIVE", "").lower() == "true"
# Seconds between messages. Telegram allows about twenty a minute to one
# chat, and a scan finding nine signals can breach that in seconds.
TELEGRAM_MIN_GAP    = 3.5
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")

# ── HTTP ──────────────────────────────────────────────────────────
# After this many consecutive failures a host is skipped for a while. An
# outage should cost one round of learning, not the whole scan.
HTTP_CIRCUIT_FAILS    = 4
HTTP_CIRCUIT_COOLDOWN = 180
HTTP_TIMEOUT   = 12
HTTP_RETRIES   = 2
HTTP_BACKOFF   = 1.5
USER_AGENT     = "surgeon/2.0"

# ── CHAIN REGISTRY ────────────────────────────────────────────────
# enabled=False chains are registered but skipped by scanners.
# Turn one on and Surgeon starts covering it. No other code changes.
CHAINS = {
    "solana": {
        "display":         "Solana",
        "kind":            "svm",
        "dexscreener_id":  "solana",
        "geckoterminal_id": "solana",
        "discovery_pages":  6,
        "enabled":         True,
        "explorer":        "https://solscan.io/token/{ca}",
        "chart":           "https://dexscreener.com/solana/{ca}",
        "native":          "SOL",
        "addr_regex":      r"^[1-9A-HJ-NP-Za-km-z]{32,44}$",
    },
    "robinhood": {
        "display":         "Robinhood Chain",
        "kind":            "evm",
        "dexscreener_id":  "robinhood",     # resolved
        "geckoterminal_id": "robinhood",    # resolved
        "discovery_pages":  3,
        "goplus_chain_id": "4663",          # resolved
        "blockscout":      "https://robinhoodchain.blockscout.com",  # official explorer
        "enabled":         True,
        "explorer":        "https://explorer.robinhood.com/token/{ca}",
        "chart":           "https://dexscreener.com/robinhood/{ca}",
        "native":          "ETH",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "base": {
        "display":         "Base",
        "kind":            "evm",
        "dexscreener_id":  "base",
        "geckoterminal_id": "base",
        "discovery_pages":  2,
        "goplus_chain_id": "8453",
        "blockscout":      "https://base.blockscout.com",
        "enabled":         True,
        "explorer":        "https://basescan.org/token/{ca}",
        "chart":           "https://dexscreener.com/base/{ca}",
        "native":          "ETH",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "bsc": {
        "display":         "BNB Chain",
        "kind":            "evm",
        "dexscreener_id":  "bsc",
        "geckoterminal_id": "bsc",
        "discovery_pages":  2,
        "goplus_chain_id": "56",
        "blockscout":      None,
        "enabled":         True,
        "explorer":        "https://bscscan.com/token/{ca}",
        "chart":           "https://dexscreener.com/bsc/{ca}",
        "native":          "BNB",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    # Arc — Circle's L1, public mainnet 16 September 2026. Disabled until the
    # data providers index it: DexScreener and GeckoTerminal both need to
    # know the chain before Surgeon can read anything, and neither publishes
    # an identifier until launch. `python3 arc_ready.py` probes for them and
    # prints this block filled in.
    #
    # Worth knowing what Arc is before expecting much: built for
    # stablecoin-native applications and tokenized real-world assets, with
    # BlackRock, Visa and DTCC as validators. Not obviously a memecoin chain.
    # Being ready on day one costs little; expecting volume on day one might.
    "arc": {
        "display":          "Arc",
        "kind":             "evm",
        "enabled":          False,      # arc_ready.py resolves and flips this
        "native":           "USDC",     # gas is paid in USDC
        "dexscreener_id":   None,       # resolved at launch
        "geckoterminal_id": None,       # resolved at launch
        "goplus_chain_id":  None,
        "blockscout":       None,
        "explorer":         "https://explorer.arc.network",
        "discovery_pages":  3,
        "addr_regex":       r"^0x[a-fA-F0-9]{40}$",
    },
    "monad": {
        "display":         "Monad",
        "kind":            "evm",
        "dexscreener_id":  "monad",         # resolved via geckoterminal
        "geckoterminal_id": "monad",        # resolved
        "discovery_pages":  2,
        "goplus_chain_id": "143",           # resolved
        "blockscout":      None,
        "enabled":         True,
        "explorer":        "https://monadexplorer.com/token/{ca}",
        "chart":           "https://dexscreener.com/monad/{ca}",
        "native":          "MON",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
}

def enabled_chains():
    return [k for k, v in CHAINS.items() if v.get("enabled")]


# ── ENTRY THRESHOLDS ──────────────────────────────────────────────
# Per-tier gates. Chain overrides go in CHAIN_THRESHOLD_OVERRIDES.
THRESHOLDS = {
    # Volume is gated on the last hour plus turnover, never on 24h totals.
    # For a token minutes old, "24h volume" is lifetime volume — a $50k floor
    # demanded $50k of trade in twelve minutes and rejected genuine runners.
    # 184 first_moon trades won 17.9%; 28 boosted trades won 32.1%. That is
    # evidence older tokens outperform younger ones, which justifies widening
    # boosted — it says nothing about how much momentum to demand from a young
    # one, and raising this gate to 25% blocked 83 of 96 Solana candidates.
    #
    # It is also the wrong lever mechanically: for a twenty-minute-old token,
    # "1h change" spans its whole life, so a high floor rejects anything that
    # launched, dipped and is only now turning. Turnover stays raised, since
    # it measures real activity rather than a price path.
    "first_moon": {
        # Under $10k rugs at 51.2% across 123 closed trades — the one part of
        # the published liquidity research that replicated on our own data.
        # The graded tiers above it did not: $100k+ rugged at 28.3% here
        # against the 0.25% claimed, so depth is a floor and nothing more.
        "min_liquidity":  10_000,
        "min_fdv":         5_000,
        "max_fdv":       150_000,
        "min_age_hours":     0.17,   # 10min — past the instant-rug window
        "max_age_hours":     2.0,
        "min_change_1h":    15.0,
        "min_volume_1h":   4_000,
        "min_turnover_1h":   0.22,
        "min_change_5m":   -10.0,
    },
    "second_moon": {
        "min_liquidity":  20_000,
        "min_fdv":       100_000,
        "max_fdv":     3_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":    12.0,
        "min_change_1h":    10.0,
        "min_volume_1h":  15_000,
        "min_turnover_1h":   0.10,
        "min_change_5m":   -10.0,
    },
    # Catch-all so a token cannot fall between tiers: first_moon stops at 2h
    # and second_moon needs $100k FDV, which left a 3h-old $60k token matching
    # nothing at all.
    # Widened on a 28-trade sample showing 32.1%. On 110 trades it came in at
    # 21.8% with the worst average close in the system (-45), below
    # first_moon's 25.3%, and not one of the fifteen biggest winners was
    # boosted. The original edge was small-sample luck; reverted.
    "boosted": {
        "min_liquidity":  10_000,
        "min_fdv":        20_000,
        "max_fdv":     5_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":    24.0,
        "min_change_1h":     0.0,
        "min_volume_1h":   5_000,
        "min_turnover_1h":   0.05,
        "min_change_5m":   -15.0,
    },
    # Tokens the channels are calling. A different question entirely: not
    # "is this early enough to be worth a look" but "several people who watch
    # this full-time think it is running". A runner heading for $10m is far
    # outside every tier above — boosted stops at $5m — so a token three
    # channels are shouting about would find no tier and vanish silently.
    "social_call": {
        "min_liquidity":  15_000,
        "min_fdv":        20_000,
        "max_fdv":    50_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":   168.0,     # a week
        "min_change_1h":   -20.0,     # consensus matters more than momentum
        "min_volume_1h":  10_000,
        "min_turnover_1h":   0.05,
        "min_change_5m":   -30.0,
    },
}

# Newer chains trade at a fraction of Solana's dollar sizes. REDDIT on
# Robinhood was a real 321%-in-an-hour move on $7.8k liquidity and an $8k
# FDV — invisible to Solana-calibrated floors.
CHAIN_THRESHOLD_OVERRIDES = {
    "robinhood": {
        # Was $3k and $5k, on the reasoning that Robinhood's pools are
        # thinner. King's own trades disagree: the $5k-10k band rugged 56.7%
        # across 97 trades with a 16.5% win rate and produced one runner,
        # against 13.9% rug and 41 runners above $20k. Under $5k is only 13
        # trades — too few to defend a floor on, so it moves too.
        "first_moon": {"min_liquidity": 10_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 10_000, "min_volume_1h": 2_000},
    },
    # Arc's gates are Robinhood's until it has produced trades of its own. A
    # new chain has no outcome data, and inventing thresholds for one is how
    # first_moon ended up at a 25% momentum gate that blocked 83 of 96 Solana
    # candidates.
    "arc": {
        "first_moon": {"min_liquidity": 10_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 10_000, "min_volume_1h": 2_000},
    },
    "monad": {
        # Monad has produced no closed trades at all, so its floors were
        # never tested. Matched to Robinhood rather than left at an
        # unexamined $3k.
        "first_moon": {"min_liquidity": 10_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 10_000, "min_volume_1h": 2_000},
    },
    # 46 trades, 13% win rate, average peak +4% — Base signals barely go
    # green at all. Raised rather than disabled: the chain is not dead, our
    # bar for it was too low.
    "base": {
        "first_moon": {"min_change_1h": 45.0, "min_volume_1h": 10_000,
                       "min_turnover_1h": 0.35, "min_liquidity": 12_000},
        "boosted":    {"min_change_1h": 15.0, "min_volume_1h": 8_000,
                       "min_turnover_1h": 0.12},
    },
}

def thresholds_for(chain: str, tier: str) -> dict:
    base = dict(THRESHOLDS[tier])
    base.update(CHAIN_THRESHOLD_OVERRIDES.get(chain, {}).get(tier, {}))
    return base


# ── SAFETY GATES ──────────────────────────────────────────────────
SAFETY = {
    # Concentration no longer hard-rejects. It is scored on the scale in
    # SCAM below, because a threshold that blocks outright cannot express
    # "acceptable if the token is very new and the volume is real" — which
    # is the actual judgement.
    "min_lp_locked_pct":    80.0,   # graduated pools only
    # An LP reading of exactly zero is treated as unreadable rather than
    # unlocked when every other holder signal contradicts it.
    "lp_zero_creator_max":   0.5,
    "lp_zero_insider_max":   2.0,
    "lp_zero_holder_min":  500,
    "max_buy_tax_pct":      10.0,   # EVM
    "max_sell_tax_pct":     10.0,   # EVM
    # RugCheck serves two scores and changed which one `score` carries. The
    # legacy scale runs into the thousands; score_normalised is 0-100.
    # Reading only `score` meant every token came back as 1 once they
    # switched, and a block at 500 could never fire — the check was silently
    # dead. Both scales are handled now, and the threshold is chosen from
    # whichever the number is actually on.
    "rugcheck_raw_block":   500,    # legacy scale
    # 40 on the 0-100 scale, deliberately conservative until we can see what
    # real tokens score. King's alerts will show the scale and the threshold,
    # so this can be set from evidence rather than guessed at twice.
    "rugcheck_normalised_block": 40,
    # A low score on a token with no holder base means the checks had nothing
    # to examine, not that the token is safe.
    "rug_score_min_holders": 300,
    # A lock expiring within this window is not protection. Flagged rather
    # than rejected — plenty of real projects run short rolling locks.
    "lp_min_lock_hours":    24.0,
    "reject_on_honeypot":   True,
    "reject_on_mint_auth":  True,
    "reject_on_freeze":     True,
    "reject_creator_rug_history": True,
    # SKYAI on BSC passed with 1 holder and the creator holding 100% of supply,
    # because top_holder_pct was unavailable and nothing else was checked.
    # Hard rejects, restored after being lost in a rewrite. 20% for a single
    # wallet is the figure that was in place. The top-ten line is set at 50%,
    # matching where the trenches say serious traders stop looking — it sits
    # far above King's caution range so the graded warnings do the work.
    "max_top_holder_pct":   20.0,
    "max_top10_pct":        50.0,
    "max_creator_holds_pct": 20.0,
    "min_holder_count":      10,
    "reject_unverified_contract_if_thin": True,   # unverified + <50 holders
    # If safety data can't be fetched, do we still alert?
    # True = alert but clearly label the gap. Never silently show 0%.
    "alert_on_partial":     True,
    # A token no safety source could answer for is UNVERIFIED, not PASS.
    # "flag"  = still alert, label it loudly, heavy conviction penalty
    # "block" = never alert
    # Back to "flag". The muting was justified with a query that split on
    # risk flags, not on verification status — different things, and I used
    # data about one to change the other. 央视抽象吉祥物 carried UNVERIFIED-25
    # and ran +410%; muting would have silenced it. The penalty ranks it, the
    # alert says so plainly, and King decides.
    "unverified_policy":    "flag",
}

# ── VENUE ─────────────────────────────────────────────────────────
# Where a token trades, measured against King's own 3,174 closed trades
# rather than borrowed from a study. Baseline is 28.3% win / 19.7% rug.
#
# Only effects whose 95% confidence interval clears the baseline appear
# here — pons-v2 rugs between 77% and 94% of the time and wins between 1.8%
# and 14%, so 58 trades is enough. uniswap and pumpswap sit on the baseline
# on 1,459 and 592 trades and are deliberately absent.
VENUES = {
    # Was blocked outright on 5.2% win / 87.9% rug across 58 trades. Both
    # numbers came from data the false-rug bug had corrupted, and I was wrong
    # to tell King win rate was unaffected: a falsely rugged token is
    # recorded as a loss at -100%, so a venue DexScreener indexed poorly
    # would show a depressed win rate as well as an inflated rug rate.
    #
    # If every one of those 51 rugs were false and those tokens won at the
    # population rate, pons-v2 lands near 43% — indistinguishable from
    # uniswap. The block cannot be defended on that data.
    #
    # Worse, a block generates no data at all, so it could never be tested.
    # Downgraded to a heavy penalty: almost everything stays below the floor,
    # but tokens are tracked and graded, and in a week there will be clean
    # numbers to judge it on.
    "pons-v2":              {"conviction": -30},

    # Win rates whose upper bound sits below the baseline. These were first
    # set from rug rate, but rug rate was contaminated: "DexScreener returned
    # nothing" was being recorded as a rug at -100%. Re-tested on win rate
    # alone, which that bug does not touch, and both survive.
    "pancakeswap_v2":       {"conviction": -18},   # 15.2% win [10.0-22.5], n=125
    "pancakeswap":          {"conviction": -18},   # 21.5% win [17.7-25.9], n=390

    # uniswap-v3-robinhood removed. Its -18 rested entirely on a 60.7% rug
    # rate across 28 trades, and on win rate alone the interval is 10.2-39.5
    # — it spans the baseline and proves nothing. Worth re-checking once the
    # rug data is clean.

    # win rates whose lower bound sits above the baseline
    "uniswap-v4-base":      {"conviction":  +6},   # 49.7% win, n=322
    "uniswap-v4-robinhood": {"conviction":  +6},   # 39.6% win, n=164
}

# ── WALLET CLUSTERS ───────────────────────────────────────────────
# What Bubblemaps shows visually: wallets that are not independent. Supply
# across two hundred addresses looks like distribution in every per-wallet
# metric and dumps as one position, because it is one position.
CLUSTERS = {
    "min_wallets":            8,    # addresses acting together
    "transfers_examined":   200,    # earliest transfers read, EVM
    "danger_wallets":        25,
    "danger_supply_pct":     20.0,
}

# ── SCAM HEURISTICS ───────────────────────────────────────────────
# Trader-supplied tells, far tighter than the entry gates. Applied as
# conviction penalties rather than rejects — as rejects they would silence
# the scanner, and a token collecting several of them falls below the alert
# floor on arithmetic anyway.
SCAM = {
    # Flip to False to score exactly as before these were added.
    "enabled":            True,

    # Concentration, set from what the trenches actually treat as safe rather
    # than from my guesses. The previous lines were far tighter — top holder
    # at 3.5%, creator at 2% — and the outcome data says they were wrong:
    # risk:TOP_HOLDER-6 and -14 had average peaks of 68 and 67, the two
    # highest of any component in the table. We were penalising the
    # best-performing cohort.
    "top_holder_pct":        8.0,    # ideal under 8%
    "top_holder_max":       12.0,    # risky above 12%
    "creator_holds_pct":     5.0,    # ideal under 5%
    "creator_holds_max":    10.0,    # risky above 10%
    "top10_pct":            25.0,    # ideal under 25%
    "top10_early_pct":      35.0,    # up to 35% tolerated while very early
    "top10_early_hours":     1.0,
    "bundled_pct":          15.0,    # insider supply under 15%

    "min_volume_to_mcap":    0.80,
    "min_holders":          50,
    "lp_pullable_pct":      35.0,
    "top_holder_grace_hours": 1.0,

    # Bundling shows up as a *low* top holder: supply split across two
    # hundred wallets leaves nobody holding anything.
    "bundle_max_top1":       1.5,
    "bundle_max_age_hours":  6.0,
    "bundle_uniformity":     0.75,

    # One warning is survivable. Three severe ones together is a pattern.
    "max_danger_flags":      3,
}

# ── MARKET DATA SANITY ────────────────────────────────────────────
# Fresh pairs routinely report garbage: infinite-looking price changes,
# billion-dollar FDV sitting on $16k of liquidity. Treat these as bad data,
# not as signals.
SANITY = {
    "max_fdv_liq_ratio":  500,      # FDV more than 500x liquidity = fake supply
    "max_abs_change_pct": 50_000,   # anything beyond this is a data artefact
    "min_liquidity_usd":  1_000,    # below this nothing is tradeable
    "unknown_age_hours":  999.0,    # sentinel used when pairCreatedAt is absent
}

# ── MARKET HOURS (UTC) ────────────────────────────────────────────
MARKET_HOURS = {
    "peak": (13, 21),   # US open + EU evening overlap
    "dead": (2, 8),
}
MARKET_HOURS_ADJUST = {
    "PEAK":   {"min_change_1h_mult": 0.75, "min_volume_mult": 0.6, "conviction": +5},
    "NORMAL": {"min_change_1h_mult": 1.00, "min_volume_mult": 1.0, "conviction":  0},
    # Penalty removed. Five of the fifteen biggest winners took DEAD-10 —
    # Bullballs (+4,332%), Caesar (+794%), Fatal Boner (+832%), Burpcoin,
    # Onigiricoin. Ten points each, on tokens that launched overnight and ran
    # anyway. The gates still tighten in dead hours; the score no longer
    # taxes a token for the clock it launched on.
    "DEAD":   {"min_change_1h_mult": 2.00, "min_volume_mult": 2.0, "conviction": 0},
}

# ── CONVICTION SCORING ────────────────────────────────────────────
CONVICTION = {
    # WEAK appeared on 401 closed trades and won 13.2% against a 22%
    # baseline, average peak 6 — the worst component in the system, and it
    # was being paid +3. None of the fifteen biggest winners had weak
    # momentum: eleven EXPLOSIVE, four REAL, none weak.
    "momentum":   {"EXPLOSIVE": 15, "REAL": 10, "WEAK": -12, "FAKE": -15},
    "launch":     {"GOLDEN_WINDOW": 15, "SWEET_SPOT": 10, "TOO_EARLY": -10,
                   "LATE": -5, "OLD": -5},
    "change_1h":  [(100, 15), (50, 10), (20, 5)],       # (threshold, points)
    "change_5m":  [(10, 10), (0, 5), (-5, -10)],
    "age_sweet":  [((0.17, 0.5), 10), ((0.5, 1.0), 7)],
    "liquidity":  [(20_000, 10), (15_000, 5)],
    "social":     {3: 20, 2: 12, 1: 5},                  # unique channels
    "smart_money":{2: 20, 1: 12},                        # unique wallets
    # Reduced from -18 after measuring what it actually tracks.
    #
    # It fires on 99.7% of BSC signals, 84.9% of Robinhood, 11.9% of Base and
    # 0% of Solana — RugCheck always answers, GoPlus usually does not on a
    # fresh EVM launch. So it was less a risk signal than a tax on two
    # chains.
    #
    # And where it varies, it does not predict badness. On Robinhood
    # unverified tokens win 27.4-36.7% against checked at 20.8-25.6%, and rug
    # 26.9-36.1% against 14.6-18.9% — neither interval overlaps. They win
    # more AND rug more, with an average peak of 75 against 44. That is the
    # signature of a newer token, which GOLDEN_WINDOW already pays +15 for.
    # We were charging 18 for the same fact.
    #
    # Kept negative because not knowing is genuinely worse than knowing, but
    # small enough that it ranks rather than decides. Analyst scored 32 and
    # 42 with the old penalty and went on to run +3,536%; at -5 it scores 45
    # and 55, and the second alerts.
    "unverified": -5,
    "partial_safety": -8,
    # Removed. Fired on 0 of 1,116 closed trades across every tier — either
    # holder_count is not populating or the 300 line is cleared by everyone.
    # An inert rule that looks like protection is worse than no rule.
    "unproven_safety": 0,
    # A bleeding tape is not a small deduction. The same setup that is worth
    # taking with SOL up 8% is usually worth skipping with SOL down 12%.
    "macro":      {"BULLISH": 6, "NEUTRAL": 0, "CAUTION": -12, "PAUSE": -25},
    # Two different questions. Tracking is cheap and the data is how every
    # weight gets tuned, so track generously. Interrupting is expensive —
    # eleven signals a scan is several hundred a day and the channel gets
    # muted by evening.
    "min_to_track": 30,     # recorded, watched, feeds the outcome data
    "min_to_alert": 48,     # default bar for reaching Telegram

    # One floor across every tier silently muted the best-performing one.
    # Boosted produced 82 signals and sent zero: its gates are the loosest,
    # so its tokens score lower by construction — average 43, best 67 —
    # while winning 32.1% against first_moon's 17.9%.
    #
    # The score measures how much a token resembles a fresh launch, not how
    # likely it is to run. Boosted tokens score badly because they are older
    # and calmer, which is exactly what makes them win.
    # 525 closed trades at 12.6% against a 22% baseline, average peak 8 —
    # the worst cohort in the system by a wide margin, and 99 of them still
    # reached the phone. The -12 penalty was not enough to clear the floors.
    # Still tracked, so the outcome data keeps building.
    "block_weak_momentum": True,

    # The step moved once the data was clean.
    #
    # It sat at 50 when 40-49 won 31.4%. On the 48 hours after the false-rug
    # fix that band wins 46.4% [39.6-53.4] across 196 trades — the same as
    # the 46.4% currently reaching the phone across 561. The real break is
    # now below 40: the 30-39 band wins 30.9% [25.6-36.8] and does not
    # overlap it.
    #
    # The earlier reading was not wrong, it was measured through a bug. A
    # falsely rugged token is recorded as a loss at -100%, so every group
    # carrying false rugs had its win rate understated — which also means
    # 46.4% is a floor on the truth here, not a ceiling.
    "min_to_alert_by_tier": {
        "boosted":     40,
        "first_moon":  40,
        "second_moon": 40,
    },
    # Channel calls are not gated on this score at all. Conviction is
    # calibrated for fresh launches — it docks a 28h-old token for being old
    # and gives it no age bonus, which is right when the claim is "this is
    # early" and wrong when the claim is "four channels are on this". Setting
    # a separate number here was guesswork: the first genuine case landed at
    # 35 against a bar of 38, which says more about the bar than the token.
    #
    # What gates a channel call instead: real consensus, a matched tier, and
    # the same safety and scam checks as everything else. The score is still
    # computed and shown — it just does not decide.
    "bands": {"HIGH": 80, "GOOD": 60, "WATCH": 30},
}

# ── NARRATIVE WEIGHTS ─────────────────────────────────────────────
# Retuned automatically by learn.py from realised win rates.
NARRATIVES = {
    "AI":        {"points":  8, "patterns": ["ai", "gpt", "agent", "robot", "neural",
                                             "compute", "agi", "llm", "model"]},
    "ANIMAL":    {"points":  5, "patterns": [
        # Deliberately long. A dog meta runs as corgi, puppy and terrier, not
        # as the word "dog" — a short list makes category metas invisible.
        "dog", "doggo", "puppy", "pup", "shiba", "inu", "corgi", "husky",
        "terrier", "retriever", "poodle", "pug", "beagle", "dachshund",
        "labrador", "chihuahua", "mutt", "hound", "collie", "spaniel",
        "cat", "kitty", "kitten", "meow", "feline", "tabby", "persian",
        "lion", "tiger", "leopard", "cheetah", "panther", "lynx",
        "pepe", "frog", "toad", "bear", "bull", "whale", "shark", "dolphin",
        "bird", "duck", "goose", "owl", "eagle", "hawk", "penguin", "parrot",
        "wolf", "fox", "ape", "monkey", "gorilla", "chimp", "orangutan",
        "bunny", "rabbit", "hamster", "mouse", "rat", "squirrel", "otter",
        "goat", "sheep", "cow", "pig", "hippo", "rhino", "panda", "sloth",
        "koala", "camel", "llama", "alpaca", "crab", "snail", "turtle",
        "snake", "lizard", "gecko", "axolotl", "capybara", "raccoon",
    ]},
    "POLITICAL": {"points": -15, "patterns": ["trump", "maga", "biden", "political",
                                              "president", "congress", "democrat",
                                              "republican", "election"]},
    "ELON":      {"points": -8, "patterns": ["elon", "musk", "grok", "doge"]},
    "RWA":       {"points":  3, "patterns": ["stock", "gold", "oil", "bond", "equity"]},
}

# Checked in this order — a token matching both ELON and ANIMAL ("Doge") is
# an ELON play, and ELON's 25% historical win rate must win the tie.
NARRATIVE_PRIORITY = ["POLITICAL", "ELON", "AI", "RWA", "ANIMAL"]

# ── META DETECTION ────────────────────────────────────────────────
# The narrative list above is fixed and cannot contain a meta that did not
# exist yesterday. This learns one from whatever is actually performing.
META = {
    "min_change_24h":   80.0,    # a token must be running to vote
    "min_liquidity":  8_000,     # a 900% move on $300 is not a meta
    "window_hours":     24.0,
    "min_tokens":         3,     # distinct tokens carrying a word
    "min_tokens_category": 6,    # categories aggregate, so need more
    "saturate_at":       8,      # strength 1.0 at this many
    "max_points":        12,     # tops up a signal, never carries it
}

# ── WATCHDOG ──────────────────────────────────────────────────────
# Silence reads the same whether Surgeon is working or dead. Two outages
# went unnoticed for hours because no alerts looks exactly like a quiet
# market, and the daily brief runs on the same scheduler — so when that
# fails, the thing that would have told you also fails.
WATCHDOG = {
    "quiet_minutes":       75,   # no signal recorded for this long
    "no_scan_minutes":     45,   # no scan has run at all
    "stale_positions":     90,   # open positions not checked in this long
}

# ── DERIVED SMART MONEY ───────────────────────────────────────────
# Wallets found by looking at who held Surgeon's own winners early, rather
# than trusting a hand-researched list or a third-party leaderboard.
SMART_MONEY_DERIVED = {
    # Distinct winning tokens a wallet must appear in. Two is coincidence on
    # a chain with a few thousand active wallets; three is a pattern.
    "min_winners":         3,
    # Of the tokens a candidate held, this share must be winners. A wallet in
    # nine winners and two hundred losers is buying everything, not choosing.
    "min_precision":     0.25,
    "max_promote":        15,
    # One request per token — the v1 endpoint returns oldest-first, so there
    # is nothing to paginate through.
    "transfer_pages":      1,
    # New tokens fetched per run. Explorers return 429 after a handful of
    # calls, and transfer history never changes, so results are cached
    # permanently and the sample grows a little each day.
    "max_fetches_per_run": 25,
    # A newly added wallet gets this long before being judged, so it is not
    # retired for missing winners that closed before it was tracked.
    "review_after_hours": 72,
}

# ── SMART MONEY WALLETS ───────────────────────────────────────────
# chain -> [{address, label}]
SMART_MONEY = {
    "solana": [
        {"address": "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa",  "label": "SM1"},
        {"address": "BQm74qyqiUMRBkyxgLV5TRSaerTJqPxKB3Spa4tscPTN", "label": "SM2"},
        {"address": "8Hm2QtQnWLtZy4qMQWN9FM965Pan96kHVQeNbAmZxXpt", "label": "SM3"},
        {"address": "BtDaZUqHr2mKH5EYQCztuerHBuBEfQNYdquTDtEZp2Ym", "label": "SM4"},
        {"address": "5emPNcmwvh5CH3Vg5dqEuLrvo5jfQSEtKnDDLm3oSeK3", "label": "SM5"},
        {"address": "EeXvxkcGqMDZeTaVeawzxm9mbzZwqDUMmfG3bF7uzumH", "label": "SM6"},
    ],
    "robinhood": [],
    "base":      [],
    "bsc":       [],
    "monad":     [],
    "arc":       [],
}

# ── SOCIAL CHANNELS ───────────────────────────────────────────────
# (handle, label, weight). Weight is how much a mention counts toward
# consensus.
#
# Every channel counts equally for now. An earlier version discounted nine of
# them to 0.35 on the belief they were paid-promotion outlets — they are not,
# they are ordinary alpha channels whose owners are sometimes paid to post,
# which is true of most of this list. That weight was invented, not measured,
# and an invented penalty is worse than none.
#
# The mechanism stays because roadmap item 4 fills it with each channel's
# measured hit rate against outcomes. Until then, one channel, one vote.
ORGANIC = PROMO = 1.0

TELEGRAM_CHANNELS = [
    ("Blessedmemecalls",       "Blessed",             ORGANIC),
    ("CatfishcallsbyPoe",      "Catfish by Poe",      ORGANIC),
    ("CryptoLord100xCalls",    "CryptoLord",          ORGANIC),
    ("BanksDegenPlays",        "Banks",               ORGANIC),
    ("ghostfacecallerchannel", "Poizer",              ORGANIC),
    ("spidersjournal",         "SpiderCrypto",        ORGANIC),
    ("hellokook",              "Kook",                ORGANIC),
    ("SHITTYCALLZBYPOE",       "Shitty Calls by Poe", ORGANIC),
    ("Gems1000XXCalls",        "Royal Gems",          ORGANIC),
    ("moderncryptoanalyst",    "Modern",              ORGANIC),
    ("nft_brewery",            "Brewery",             ORGANIC),
    ("jsdao",                  "JSDAO",               ORGANIC),
    ("HubzCabal",              "HubzCabal",           ORGANIC),
    ("realsolanahome",         "Solana Home",         ORGANIC),
    ("SaintDovydegen",         "Saint Dovy",          ORGANIC),
    ("Alphadropcall",          "Alpha Drop",          ORGANIC),
    ("crypticsden22",          "Cryptics Den",        ORGANIC),
    ("shahlito",               "Shahlito",            ORGANIC),
    ("ferbsfriendz",           "Ferbs Friendz",       ORGANIC),
    ("solidtradesz",           "Solid Trades",        ORGANIC),
    ("solpumpforce67",         "Sol Pump Force",      ORGANIC),
    ("calledbymaxi",           "Called By Maxi",      ORGANIC),
    ("SonicsAlphacalls",       "Sonics Alpha",        ORGANIC),
    ("newsgraph",              "Newsgraph",           ORGANIC),

    # Added later; same standing as every channel above.
    ("EthansCrypto",           "Ethans Crypto",       PROMO),
    ("DegenPlayhouse",         "Degen Playhouse",     PROMO),
    ("SlavicCalls",            "Slavic Calls",        PROMO),
    ("houseofdegeneracy",      "House of Degeneracy", PROMO),
    ("bullybattalion",         "Bully Battalion",     PROMO),
    ("Diorscabal",             "Diors Cabal",         PROMO),
    ("eezzyjournal",           "Eezzy Journal",       PROMO),
    ("dogendojo",              "Dogen Dojo",          PROMO),
    ("unipcsjournal",          "Unipcs Journal",      PROMO),
]

CHANNEL_WEIGHTS = {label: weight for _, label, weight in TELEGRAM_CHANNELS}
PROMO_CHANNELS = {label for _, label, w in TELEGRAM_CHANNELS if w < ORGANIC}

SOCIAL_WINDOW_SECONDS   = 7200   # 2h velocity window
VELOCITY_MIN_CHANNELS   = 2      # weighted channels for consensus
# Each evaluated call costs a safety lookup, so this is a time budget rather
# than a philosophical limit. Consensus tokens are sorted first, so the cap
# trims the least-supported calls.
SOCIAL_CALL_LIMIT       = 20

# ── POSITION WATCH (signal-only, no execution) ────────────────────
WATCH = {
    "tp1_pct":             50,
    "tp2_pct":            100,
    "tp3_pct":            200,
    # Warning and grading are separate jobs. On the VPS they had to be the
    # same moment because the bot was exiting; signal-only means we can warn
    # early while the trade is still actionable, then grade once the outcome
    # is actually settled — and learn whether early dips recover.
    "stop_warn_pct":      -15,   # notify, keep watching
    "stop_loss_pct":      -35,   # grade it, stop watching
    "stop_grace_minutes":  20,   # no grading inside this window, warning only

    # Trailing arms on any meaningful gain, not just after TP2. wDELLx ran
    # +45%, never reached TP1 at +50%, and gave back everything with nothing
    # firing on the way down.
    # Measured as the fraction of the gain surrendered, not drawdown from
    # peak price. 40% off a +45% peak is break-even; 40% off a +500% peak is
    # still a large win. The same number cannot mean both.
    # 219 exits: average peak 149%, average close 11%. The rule says exit at
    # 65% of peak and it exits at 7% — price gaps straight past the threshold
    # between five-minute polls, so the ratio was never the problem. It
    # cannot be enforced at this granularity.
    #
    # Volume fade keeps 84% of peak across 253 exits because it fires on
    # momentum dying, which happens before price collapses. So trailing arms
    # earlier and gives back far less, and volume fade is loosened to
    # intercept more positions before they ever reach it.
    "trail_arm_pct":         15,   # peak gain needed to arm
    "give_back_ratio":      0.35,  # surrender this much of the gain -> exit
    "give_back_after_tp2":  0.25,  # tighter once TP2 is banked
    "time_stop_hours":      2,   # exit alert if still negative
    "time_exit_hours":      4,   # exit alert if still flat
    "max_hold_hours":       8,
    # Volume fade closed at +78% against a +101% peak; trailing closed at
    # -21% against a +95% peak, on the same average high. Momentum dies
    # before price does, so lean on the leading indicator.
    "volume_fade_ratio":  0.60,
    "volume_fade_min_pnl":   5,
    # Pool shrunk to this share of its size at signal. Fires before the pool
    # is empty, which is the only warning a sudden pull ever gives.
    "liquidity_drain_ratio": 0.55,
    "dev_sold_fraction":   0.5,   # deployer shedding this much of its bag
    # Base and BSC return no holder distribution for tokens under roughly
    # fifteen minutes old — GoPlus has not scanned them and Blockscout 404s.
    # Every early EVM signal therefore scores with safety_partial and an
    # unchecked top holder. Re-reading it once the indexers catch up turns a
    # guess into a fact, and can still stop a position that looked clean.
    "safety_recheck_minutes": [15, 60],
    "whale_recheck_hours":   2,
    "whale_recheck_min_pnl": 30,
    "whale_top_holder_pct":  30,
    "graduation_bc_pct":     60,
    # Inherited from the autonomous version, where 25 open positions meant
    # 25 real trades and genuine capital exposure. Signal-only it only
    # decides not to speak — and on 29 August it silenced MU at 69/100 which
    # ran +5,072%, VAULT at 71/100 which ran +1,313%, and GG at 61/100 which
    # ran +2,985%. All three cleared every floor.
    #
    # It is not protecting against load either: the watcher batches thirty
    # addresses per request, so 25 positions is one call and 90 is three.
    # Raised to a number that bounds the watcher's runtime rather than one
    # that stands in for a wallet.
    # Absence has to be confirmed before it counts as a rug. "DexScreener
    # returned nothing" and "the pool is empty" were treated identically, so
    # every timeout wrote -100% into the outcome data — and during their
    # outage there were dozens an hour.
    "rug_confirmations_no_data":  3,   # 15 minutes of silence
    "rug_confirmations_empty":    2,   # 10 minutes of a genuinely empty pool
    "max_open_positions":    90,  # tracking cap
    # Removed. Inherited from the autonomous version, where pausing after
    # losses protected capital that was actually being spent. Signal-only it
    # only decides not to speak, and it silenced Titan at 67/100 — which went
    # on to peak +1,890% — along with RWArt at 62/100.
    #
    # It also got worse as Surgeon got better: improving rug detection closed
    # more positions as losses, which tripped the rule more often, until it
    # was muting 35 qualified signals a day against 7 when it was last
    # reviewed. Set either value to 0 to disable; both are 0 here.
    "cooloff_losses":         0,
    "cooloff_minutes":        0,
    # A parked token that has failed the gates this many times is not going
    # to turn. Holding it costs a re-check slot a fresher token could use.
    "max_watchlist_checks":   12,
    # Tiers a parked token may revive into. Revived first_moon closes at +4;
    # revived second_moon at -36 and revived boosted at -39, on 182 alerts
    # at a 16.2% win rate against first_moon's 27.3%.
    "revive_tiers":        ("first_moon",),
    # A position cannot lose more than everything, and a reading above this
    # is a broken entry price rather than a moonshot. Seven such rows put
    # the average final PnL at 124 million percent.
    "pnl_floor_pct":       -100.0,
    "pnl_ceiling_pct":   10_000.0,
}

# ── DEDUPE ────────────────────────────────────────────────────────
# Re-alert the same CA only after this long. Alerts are NOT suppressed
# just because the token is already being tracked — that bug cost us
# every second-moon signal in v1.
REALERT_COOLDOWN_MINUTES = 180
