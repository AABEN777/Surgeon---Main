"""
Social velocity.

Scrapes the public preview of each monitored Telegram channel, extracts
contract addresses, and treats the same CA appearing across several channels
inside a short window as conviction.

The extraction is deliberately paranoid. v1 regexed raw page HTML and stored
base64 fragments from inline SVG data-URIs as contract addresses — strings
like 'cDovL3d3dy53My5vcmcv' are valid base58 and sailed straight through a
naive check. Only message text is parsed here, never markup.
"""

from __future__ import annotations

import re
import html
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import config
from chain_base import http_get
import chains

log = logging.getLogger("surgeon.social")

TG_PREVIEW = "https://t.me/s/{channel}"

# Message bodies only — attributes, scripts and data-URIs are never scanned.
_MSG_BLOCK = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

_SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])"
                     r"([1-9A-HJ-NP-Za-km-z]{32,44})"
                     r"(?![1-9A-HJ-NP-Za-km-z])")
_EVM_RE = re.compile(r"(?<![0-9a-fA-Fx])(0x[a-fA-F0-9]{40})(?![0-9a-fA-F])")

# Addresses that are never a tradeable memecoin.
BLOCKLIST = {
    "So11111111111111111111111111111111111111112",   # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL token program
    "11111111111111111111111111111111",              # system program
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


@dataclass
class Mention:
    ca: str
    channel: str
    chain: Optional[str] = None
    seen_at: float = field(default_factory=time.time)


def _message_texts(page_html: str) -> list[str]:
    """Plain text of each message. Markup never reaches the extractor."""
    out = []
    for block in _MSG_BLOCK.findall(page_html or ""):
        text = _BR.sub("\n", block)
        text = _TAG.sub(" ", text)
        out.append(html.unescape(text))
    return out


def extract_addresses(text: str) -> list[str]:
    """
    Contract addresses from one message body.

    Base58 runs are only accepted when bounded by non-base58 characters, so
    a long token inside a URL path or an encoded blob does not fragment into
    something that merely looks like an address.
    """
    text = text or ""
    found, seen = [], set()

    def accept(match: str, haystack: str) -> bool:
        if match in seen or match in BLOCKLIST:
            return False
        idx = haystack.find(match)
        before = haystack[idx - 1] if idx > 0 else " "
        after = haystack[idx + len(match)] if idx + len(match) < len(haystack) else " "

        # base64 markers — '=' padding or '+' from an encoded payload
        if before in "=+" or after in "=+":
            return False
        # explicit data-URI context
        if "base64" in haystack[max(0, idx - 24):idx].lower():
            return False
        # A leading '/' is fine: channels often post nothing but a chart link,
        # and rejecting those would drop genuine calls.
        return True

    # EVM first, then blank those spans out. '0' and 'x' are not base58
    # characters, so an unmasked EVM address looks to the base58 scanner like
    # a clean 32-char token sitting between two valid boundaries.
    masked = text
    for m in _EVM_RE.findall(text):
        if accept(m, text):
            seen.add(m)
            found.append(m)
        masked = masked.replace(m, " " * len(m))

    for m in _SOL_RE.findall(masked):
        if accept(m, masked):
            seen.add(m)
            found.append(m)

    return found


def scrape_channel(channel: str, label: str = "") -> list[Mention]:
    page = http_get(TG_PREVIEW.format(channel=channel), timeout=15)
    if page is None:
        # http_get returns parsed JSON; Telegram serves HTML, so fetch raw.
        page = _raw_get(TG_PREVIEW.format(channel=channel))
    if not page:
        log.warning("no response from @%s", channel)
        return []

    mentions, now = [], time.time()
    for text in _message_texts(page):
        for ca in extract_addresses(text):
            mentions.append(Mention(ca=ca, channel=label or channel, seen_at=now))
    return mentions


def _raw_get(url: str) -> str:
    import requests
    try:
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": config.USER_AGENT})
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        log.warning("fetch %s failed: %s", url, e)
        return ""


def scrape_all(channels=None, limit: Optional[int] = None) -> list[Mention]:
    """Every monitored channel. Returns deduped mentions."""
    channels = channels or config.TELEGRAM_CHANNELS
    if limit:
        channels = channels[:limit]

    all_mentions, seen = [], set()
    for handle, label in channels:
        try:
            for mn in scrape_channel(handle, label):
                key = (mn.ca, mn.channel)
                if key not in seen:
                    seen.add(key)
                    all_mentions.append(mn)
        except Exception as e:
            log.warning("channel @%s failed: %s", handle, e)
    return all_mentions


def resolve_chains(mentions: list[Mention], max_lookups: int = 25) -> list[Mention]:
    """
    Attach a chain to each mention.

    Solana addresses are unambiguous. EVM addresses could be any of four
    chains, so those are resolved by asking which chain actually has a pool —
    capped, because it costs a request each.
    """
    lookups = 0
    cache: dict[str, Optional[str]] = {}
    for mn in mentions:
        if mn.ca in cache:
            mn.chain = cache[mn.ca]
            continue
        candidates = chains.detect_chains(mn.ca)
        if len(candidates) == 1:
            mn.chain = candidates[0]
        elif candidates and lookups < max_lookups:
            lookups += 1
            key, _ = chains.resolve_chain(mn.ca)
            mn.chain = key
        cache[mn.ca] = mn.chain
    return mentions


def velocity(mentions: list[Mention],
             min_channels: Optional[int] = None) -> dict[str, list[str]]:
    """
    {ca: [channels]} for tokens called by enough distinct channels.

    Counts unique channels, not messages — one channel posting a CA six times
    is one channel with an opinion, not consensus.
    """
    threshold = min_channels or config.VELOCITY_MIN_CHANNELS
    by_ca: dict[str, set[str]] = {}
    for mn in mentions:
        by_ca.setdefault(mn.ca, set()).add(mn.channel)
    return {ca: sorted(chs) for ca, chs in by_ca.items()
            if len(chs) >= threshold}


def channel_counts(mentions: list[Mention]) -> dict[str, int]:
    """{ca: unique channel count} — feeds the conviction score."""
    by_ca: dict[str, set[str]] = {}
    for mn in mentions:
        by_ca.setdefault(mn.ca, set()).add(mn.channel)
    return {ca: len(chs) for ca, chs in by_ca.items()}
