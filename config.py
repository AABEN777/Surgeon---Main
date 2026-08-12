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
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")

# ── HTTP ──────────────────────────────────────────────────────────
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
        "enabled":         True,
        "explorer":        "https://solscan.io/token/{ca}",
        "chart":           "https://dexscreener.com/solana/{ca}",
        "native":          "SOL",
        "addr_regex":      r"^[1-9A-HJ-NP-Za-km-z]{32,44}$",
    },
    "robinhood": {
        "display":         "Robinhood Chain",
        "kind":            "evm",
        "dexscreener_id":  "robinhood",     # VERIFY
        "goplus_chain_id": None,            # VERIFY — GoPlus added support 2026-07-15
        "blockscout":      None,            # VERIFY — fallback for holder distribution
        "enabled":         True,
        "explorer":        "https://explorer.robinhood.com/token/{ca}",  # VERIFY
        "chart":           "https://dexscreener.com/robinhood/{ca}",
        "native":          "ETH",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "base": {
        "display":         "Base",
        "kind":            "evm",
        "dexscreener_id":  "base",
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
        "goplus_chain_id": "56",
        "blockscout":      None,
        "enabled":         True,
        "explorer":        "https://bscscan.com/token/{ca}",
        "chart":           "https://dexscreener.com/bsc/{ca}",
        "native":          "BNB",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "monad": {
        "display":         "Monad",
        "kind":            "evm",
        "dexscreener_id":  "monad",         # VERIFY
        "goplus_chain_id": None,            # VERIFY — may not be supported yet
        "blockscout":      None,            # VERIFY
        "enabled":         True,
        "explorer":        "https://monadexplorer.com/token/{ca}",  # VERIFY
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
    "first_moon": {
        "min_liquidity":  10_000,
        "min_fdv":        20_000,
        "max_fdv":        100_000,
        "min_age_hours":  0.17,    # 10min — survived the instant-rug window
        "max_age_hours":  2.0,
        "min_change_1h":  20.0,
        "min_volume_24h": 50_000,
        "min_change_5m":  -10.0,   # buy pressure gate
    },
    "second_moon": {
        "min_liquidity":  25_000,
        "min_fdv":        150_000,
        "max_fdv":        3_000_000,
        "min_age_hours":  0.17,
        "max_age_hours":  12.0,
        "min_change_1h":  10.0,
        "min_volume_24h": 75_000,
        "min_change_5m":  -10.0,
    },
    "boosted": {
        "min_liquidity":  20_000,
        "min_fdv":        50_000,
        "max_fdv":        5_000_000,
        "min_age_hours":  0.17,
        "max_age_hours":  24.0,
        "min_change_1h":  0.0,
        "min_volume_24h": 30_000,
        "min_change_5m":  -15.0,
    },
}

# Newer / thinner chains need looser absolute dollar gates.
CHAIN_THRESHOLD_OVERRIDES = {
    "robinhood": {"first_moon": {"min_liquidity": 5_000, "min_volume_24h": 25_000}},
    "monad":     {"first_moon": {"min_liquidity": 5_000, "min_volume_24h": 20_000}},
}

def thresholds_for(chain: str, tier: str) -> dict:
    base = dict(THRESHOLDS[tier])
    base.update(CHAIN_THRESHOLD_OVERRIDES.get(chain, {}).get(tier, {}))
    return base


# ── SAFETY GATES ──────────────────────────────────────────────────
SAFETY = {
    "max_top_holder_pct":   20.0,   # reject above
    "max_top10_pct":        60.0,
    "min_lp_locked_pct":    80.0,   # graduated pools only
    "max_buy_tax_pct":      10.0,   # EVM
    "max_sell_tax_pct":     10.0,   # EVM
    "rugcheck_raw_block":   500,    # Solana: raw score above this = block
    "reject_on_honeypot":   True,
    "reject_on_mint_auth":  True,
    "reject_on_freeze":     True,
    "reject_creator_rug_history": True,
    # If safety data can't be fetched, do we still alert?
    # True = alert but clearly label the gap. Never silently show 0%.
    "alert_on_partial":     True,
}

# ── MARKET HOURS (UTC) ────────────────────────────────────────────
MARKET_HOURS = {
    "peak": (13, 21),   # US open + EU evening overlap
    "dead": (2, 8),
}
MARKET_HOURS_ADJUST = {
    "PEAK":   {"min_change_1h_mult": 0.75, "min_volume_mult": 0.6, "conviction": +5},
    "NORMAL": {"min_change_1h_mult": 1.00, "min_volume_mult": 1.0, "conviction":  0},
    "DEAD":   {"min_change_1h_mult": 2.00, "min_volume_mult": 2.0, "conviction": -10},
}

# ── CONVICTION SCORING ────────────────────────────────────────────
CONVICTION = {
    "momentum":   {"EXPLOSIVE": 15, "REAL": 10, "WEAK": 3, "FAKE": 0},
    "launch":     {"GOLDEN_WINDOW": 15, "SWEET_SPOT": 10, "TOO_EARLY": -10,
                   "LATE": -5, "OLD": -5},
    "change_1h":  [(100, 15), (50, 10), (20, 5)],       # (threshold, points)
    "change_5m":  [(10, 10), (0, 5), (-5, -10)],
    "age_sweet":  [((0.17, 0.5), 10), ((0.5, 1.0), 7)],
    "liquidity":  [(20_000, 10), (15_000, 5)],
    "social":     {3: 20, 2: 12, 1: 5},                  # unique channels
    "smart_money":{2: 20, 1: 12},                        # unique wallets
    "macro":      {"BULLISH": 5, "NEUTRAL": 0, "CAUTION": -10, "PAUSE": -10},
    "min_to_alert": 30,
    "bands": {"HIGH": 80, "GOOD": 60, "WATCH": 30},
}

# ── NARRATIVE WEIGHTS ─────────────────────────────────────────────
# Retuned automatically by learn.py from realised win rates.
NARRATIVES = {
    "AI":        {"points":  8, "patterns": ["ai", "gpt", "agent", "robot", "neural",
                                             "compute", "agi", "llm", "model"]},
    "ANIMAL":    {"points":  5, "patterns": ["dog", "cat", "pepe", "frog", "bear",
                                             "whale", "bird", "wolf", "ape", "bunny",
                                             "hamster", "penguin"]},
    "POLITICAL": {"points": -15, "patterns": ["trump", "maga", "biden", "political",
                                              "president", "congress", "democrat",
                                              "republican", "election"]},
    "ELON":      {"points": -8, "patterns": ["elon", "musk", "grok", "doge"]},
    "RWA":       {"points":  3, "patterns": ["stock", "gold", "oil", "bond", "equity"]},
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
}

# ── SOCIAL CHANNELS ───────────────────────────────────────────────
TELEGRAM_CHANNELS = [
    ("Blessedmemecalls",       "Blessed"),
    ("CatfishcallsbyPoe",      "Catfish by Poe"),
    ("CryptoLord100xCalls",    "CryptoLord"),
    ("BanksDegenPlays",        "Banks"),
    ("ghostfacecallerchannel", "Poizer"),
    ("spidersjournal",         "SpiderCrypto"),
    ("hellokook",              "Kook"),
    ("SHITTYCALLZBYPOE",       "Shitty Calls by Poe"),
    ("Gems1000XXCalls",        "Royal Gems"),
    ("moderncryptoanalyst",    "Modern"),
    ("nft_brewery",            "Brewery"),
    ("jsdao",                  "JSDAO"),
    ("HubzCabal",              "HubzCabal"),
    ("realsolanahome",         "Solana Home"),
    ("SaintDovydegen",         "Saint Dovy"),
    ("Alphadropcall",          "Alpha Drop"),
    ("crypticsden22",          "Cryptics Den"),
    ("shahlito",               "Shahlito"),
    ("ferbsfriendz",           "Ferbs Friendz"),
    ("solidtradesz",           "Solid Trades"),
    ("solpumpforce67",         "Sol Pump Force"),
    ("calledbymaxi",           "Called By Maxi"),
    ("SonicsAlphacalls",       "Sonics Alpha"),
    ("newsgraph",              "Newsgraph"),
]
SOCIAL_WINDOW_SECONDS   = 7200   # 2h velocity window
VELOCITY_MIN_CHANNELS   = 2      # unique channels to fire a velocity alert

# ── POSITION WATCH (signal-only, no execution) ────────────────────
WATCH = {
    "tp1_pct":             50,
    "tp2_pct":            100,
    "tp3_pct":            200,
    "stop_loss_pct":      -15,
    "trail_after_tp2_pct": -20,
    "time_stop_hours":      2,   # exit alert if still negative
    "time_exit_hours":      4,   # exit alert if still flat
    "max_hold_hours":       8,
    "volume_fade_ratio":  0.30,  # 5m vol < 30% of hourly average
    "volume_fade_min_pnl":  20,
    "whale_recheck_hours":   2,
    "whale_recheck_min_pnl": 30,
    "whale_top_holder_pct":  30,
    "graduation_bc_pct":     60,
    "max_open_positions":    25,  # tracking cap
    "cooloff_losses":         2,
    "cooloff_minutes":       60,
}

# ── DEDUPE ────────────────────────────────────────────────────────
# Re-alert the same CA only after this long. Alerts are NOT suppressed
# just because the token is already being tracked — that bug cost us
# every second-moon signal in v1.
REALERT_COOLDOWN_MINUTES = 180
