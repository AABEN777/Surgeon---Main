# Surgeon v2 — build plan

Signal only. No keys, no execution. Everything below is about producing
better signals and knowing which ones were right.

---

## Built

- Five chain adapters — Solana, Robinhood, Base, BNB Chain, Monad
- Discovery: GeckoTerminal new pools + DexScreener promoted, merged
- Market data: DexScreener with GeckoTerminal fallback, batched 30/request
- Safety: RugCheck (Solana), GoPlus + Blockscout (EVM), never invents a value
- Scoring: tiers, momentum, launch phase, narrative, conviction 0–100
- Watchlist: park too-young tokens, re-check as they mature, retire the spent
- Social velocity: 25 Telegram channels, cross-channel consensus
- Smart money: Solana wallets via Helius
- Macro regime: SOL 24h move → BULLISH / NEUTRAL / CAUTION / PAUSE
- Alerts: Telegram HTML, escaped, copy-on-tap CA, visible score breakdown
- Persistence: Supabase, in-memory fallback for offline runs
- 95 offline tests

---

## 1. Position watcher — *next*

Everything downstream depends on knowing how signals turned out.

Track every alerted token and notify on: TP1 +50%, TP2 +100%, TP3 +200%,
stop −15%, trailing −20% after TP2, volume fade, dev wallet sold, whale
concentration appearing, bonding curve graduation, time stops.

Writes outcomes back to `signals`, which is what turns the whole system from
a scanner into something that learns.

**Blocks:** items 2, 4, 5 and the go-live decision.

---

## 2. Derived smart money

The wallets currently tracked were hand-researched on a machine that no
longer exists, and nothing has verified they are still any good. Third-party
leaderboards are not a fix — fomo has exactly the right data but no public
API, and no certainty it exposes addresses rather than usernames.

Better source: **Surgeon's own winners.**

1. When a signal closes as a winner, pull its early holders
2. Wallets appearing across several unrelated winners become candidates
3. Promote into `smart_wallets`, tagged with the evidence
4. Measure existing entries the same way — retire ones that stop earning

Self-tuning, tied to this signal universe rather than someone else's, and
dependent on nothing external. Works on every chain where holder data is
available.

**Needs:** outcome tracking (item 1).

---

## 3. CA analyzer command

Paste a contract address to the bot, get the full readout: market, safety
including top-holder percentage, conviction with breakdown, chain
auto-detected from address format. The chain resolution already exists in
`chains.resolve_chain()`.

Independent of everything else — buildable at any point.

---

## 4. Channel accuracy scoring

Twenty-five channels are weighted equally. Some are consistently early,
some consistently late, some noise. Track each channel's calls against
outcomes over a rolling window and weight the social bonus by hit rate.

v1 never had enough overlap to do this — only two tokens appeared in both
mentions and trades. Needs a few hundred outcomes.

**Needs:** outcome tracking (item 1).

---

## 5. Narrative auto-retune

`NARRATIVES` weights are fixed guesses carried over from v1's trade history
(AI +8, ANIMAL +5, POLITICAL −15, ELON −8). `v_narrative_performance` already
computes real win rates per narrative; feed those back so the weights follow
evidence rather than memory.

**Needs:** outcome tracking (item 1).

---

## 6. EVM holder data gap

On Base and BNB Chain, tokens under roughly fifteen minutes old have no
holder distribution at all — GoPlus has not scanned them, Blockscout 404s.
Every early EVM signal therefore scores with `safety_partial −8` and an
unchecked top-holder field.

Robinhood is fine; its Blockscout instance indexes from block one.

Options: re-check safety at +15/+60min via the position watcher and alert if
concentration turns out ugly; find a faster indexer; or compute distribution
directly from an RPC.

---

## 7. Going live

Alerting is deliberately fail-closed. Sending requires **both** `--live` on
the command and `SURGEON_LIVE=true` in the environment; either alone stays
dry. Confirm delivery first with `python3 scan.py --test-alert`.

---

## Deferred

- **EVM smart money** — Helius is Solana-only, no per-chain wallet indexer found
- **PumpFun WebSocket watcher** — cannot survive on scheduled Actions runs
- **fomo integration** — revisit if a public API appears
