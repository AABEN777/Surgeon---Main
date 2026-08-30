#!/usr/bin/env python3
"""
Arc readiness check.

Arc's public mainnet launches on 16 September 2026. Surgeon is chain-agnostic
— the adapters already handle any EVM chain — so the only thing standing
between it and firing Arc alerts is four identifiers that do not exist until
the data providers index the network.

This finds them. Run it on launch day and every day after until it says
Surgeon is ready, then paste the block it prints into config.py.

    python3 arc_ready.py              probe every provider
    python3 arc_ready.py --verbose    show what each one returned

Providers add chains at their own pace. Base took about a week after launch
before DexScreener indexed it, so a few days of "not yet" is normal rather
than a sign anything is wrong.
"""

from __future__ import annotations

import sys
import json
import argparse

import config
from chain_base import http_get

# Names Arc might be listed under. Providers are inconsistent — Robinhood's
# chain appears as "robinhood" on DexScreener and "robinhood" on
# GeckoTerminal, but BNB is "bsc" on one and "bsc" on the other while GoPlus
# wants the numeric 56.
CANDIDATE_SLUGS = ["arc", "arc-network", "circle-arc", "arcnetwork", "arcchain"]

# Arc's EVM chain ID, needed for GoPlus. Published with the network; these are
# the values seen in Circle's testnet documentation and the likely mainnet
# range. The probe below confirms which, if any, GoPlus actually answers for.
CANDIDATE_CHAIN_IDS = ["9999", "10101", "42161919", "4200", "5151"]

# Explorer hosts worth trying. Blockscout instances follow a house pattern.
CANDIDATE_EXPLORERS = [
    "https://explorer.arc.network",
    "https://arc.blockscout.com",
    "https://explorer.arc.io",
    "https://arcscan.io",
]


def probe_dexscreener(verbose: bool) -> str | None:
    """
    DexScreener's chainId, found by asking for the newest pairs and reading
    back what it calls the chain.
    """
    for slug in CANDIDATE_SLUGS:
        data = http_get(f"https://api.dexscreener.com/latest/dex/search",
                        params={"q": slug})
        pairs = (data or {}).get("pairs") or []
        seen = {p.get("chainId") for p in pairs if isinstance(p, dict)}
        if verbose and seen:
            print(f"    dexscreener q={slug!r} -> chains {sorted(seen)}")
        for chain_id in seen:
            if chain_id and "arc" in str(chain_id).lower():
                return chain_id
    return None


def probe_geckoterminal(verbose: bool) -> str | None:
    """GeckoTerminal publishes its network list, so this one is exact."""
    for page in (1, 2, 3, 4):
        data = http_get("https://api.geckoterminal.com/api/v2/networks",
                        params={"page": page})
        rows = (data or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            ident = str(row.get("id") or "")
            name = str((row.get("attributes") or {}).get("name") or "")
            if "arc" in ident.lower() or name.lower().startswith("arc"):
                if verbose:
                    print(f"    geckoterminal -> {ident} ({name})")
                # "arbitrum" contains "arc"? No — but "arcana" might, so
                # confirm the name really is Arc rather than a coincidence.
                if ident.lower().startswith("arc") or name.lower() == "arc":
                    return ident
    return None


def probe_goplus(verbose: bool) -> str | None:
    """
    GoPlus wants a numeric chain ID. It answers 404 for chains it does not
    support, so a non-404 means the chain is known even if the token is not.
    """
    probe_token = "0x" + "0" * 39 + "1"
    for chain_id in CANDIDATE_CHAIN_IDS:
        data = http_get(
            f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}",
            params={"contract_addresses": probe_token})
        if data is None:
            continue
        code = data.get("code")
        message = str(data.get("message") or "")
        if verbose:
            print(f"    goplus chain_id={chain_id} -> code={code} {message[:40]}")
        # code 1 is success; an unsupported chain returns a specific error.
        if code == 1 and "not support" not in message.lower():
            return chain_id
    return None


def probe_explorer(verbose: bool) -> str | None:
    """A Blockscout instance, needed for holder data and cluster detection."""
    for base in CANDIDATE_EXPLORERS:
        data = http_get(f"{base}/api/v2/stats")
        if data and isinstance(data, dict) and (
                "total_blocks" in data or "total_transactions" in data):
            if verbose:
                print(f"    explorer {base} -> {list(data)[:4]}")
            return base
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether Arc is scannable")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("  ARC READINESS")
    print("=" * 66)
    print()

    found = {}
    for label, fn, needed_for in (
            ("dexscreener_id", probe_dexscreener, "market data — required"),
            ("geckoterminal_id", probe_geckoterminal, "discovery — required"),
            ("goplus_chain_id", probe_goplus, "safety checks"),
            ("blockscout", probe_explorer, "holders and clusters")):
        print(f"  checking {label} ...", end=" ", flush=True)
        try:
            value = fn(args.verbose)
        except Exception as e:
            value = None
            if args.verbose:
                print(f"\n    {type(e).__name__}: {e}")
        found[label] = value
        print(f"{value}" if value else f"not yet  ({needed_for})")

    print()
    required = ("dexscreener_id", "geckoterminal_id")
    missing = [k for k in required if not found.get(k)]

    if missing:
        print("-" * 66)
        print("  Not scannable yet. Still waiting on:", ", ".join(missing))
        print()
        print("  Both are required — DexScreener supplies price, liquidity and")
        print("  volume, GeckoTerminal supplies new-pool discovery. Without")
        print("  either, Surgeon has nothing to read.")
        print()
        print("  Providers add chains at their own pace; Base took about a")
        print("  week after launch. Run this again tomorrow.")
        print("=" * 66)
        return 1

    print("-" * 66)
    print("  Scannable. Paste this into config.CHAINS in config.py:")
    print("-" * 66)
    print(f'''
    "arc": {{
        "display":         "Arc",
        "kind":            "evm",
        "enabled":         True,
        "native":          "USDC",
        "dexscreener_id":  "{found['dexscreener_id']}",
        "geckoterminal_id": "{found['geckoterminal_id']}",
        "goplus_chain_id": {json.dumps(found.get('goplus_chain_id'))},
        "blockscout":      {json.dumps(found.get('blockscout'))},
        "explorer":        "{found.get('blockscout') or 'https://explorer.arc.network'}",
        "discovery_pages": 3,
    }},''')

    if not found.get("goplus_chain_id"):
        print("  GoPlus is not covering Arc yet, so every token will read")
        print("  UNVERIFIED until it does. That costs 5 points and no longer")
        print("  silences anything, so it is survivable — but there will be no")
        print("  honeypot, holder or LP-lock data until GoPlus catches up.")
        print()
    if not found.get("blockscout"):
        print("  No explorer found, so cluster detection and derived smart")
        print("  money will not work on Arc. Everything else will.")
        print()

    print("  Then run: python3 scan.py --chain arc --dry-run")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
