# Research — what Surgeon is missing

Sources: a production dataset of 15.1 billion rows of Solana trading data
with published queries and outcomes; Bubblemaps' own holder-analysis
methodology; DEXTools and Smithii rug-check guidance; sniper-bot
implementation notes from the trenches; and Banana Gun's pre-migration
filtering.

Where a number appears below it comes from a stated sample, not an opinion.
Single-source findings are marked as such.

---

## Already covered, and validated

Worth stating first, because most of what Surgeon does turns out to match
what the data supports.

| signal | what the research shows | Surgeon |
|---|---|---|
| age under 6h | 37.3% moon vs 23.5% baseline, 2.33x moon:dump | GOLDEN_WINDOW +15 |
| liquidity floor | under $1k = 58.8% dump rate | $6k minimum |
| mint + freeze authority | revoked + low insider = 4.4% rug vs 22.9% | hard reject |
| creator holdings | 5-20% has the lowest dump rate at 7.98% | warn 5%, risky 10% |
| dev sold | death signal, "very high" reliability | DEV_SOLD |
| liquidity drain | death signal, "immediate" action | LIQUIDITY_DRAIN |
| trailing stop | 8.5x more profit than fixed TP over 25,912 trades | give back 35% of peak |
| bundling / insiders | insiders >30% = 26.4% dump | CLUSTER, EVEN_SPLIT |
| narrative rotation | narratives create category-wide demand shocks | meta.py |

The trailing-stop finding is worth noting: their backtest used **-30% from
peak**, which is almost exactly where we landed independently from King's own
outcome data. Two different routes to the same number.

---

## The gaps, ranked by expected impact

### 1. Liquidity depth is the strongest signal in the dataset, and we treat it as a floor

Their numbers, 30 days, tokens with 50+ traders:

| liquidity | moon rate | dump rate | ratio |
|---|---|---|---|
| $100k+ | 84.3% | **0.25%** | 308x |
| $50k-$100k | 59.2% | 0.19% | 369x |
| $10k-$50k | 36.9% | 5.4% | 7x |
| $1k-$10k | 2.3% | 11.7% | — |
| under $1k | 3.4% | 58.8% | — |

Surgeon awards **+10 above $20k and nothing more**. A token with $150k of
liquidity scores identically to one with $21k, and the data says the first
is in a category with a 1-in-400 chance of dumping.

Their explanation is sound: providing $100k of liquidity costs real money,
and nobody spends $100k to steal $10k.

**Fix:** graded liquidity scoring with real weight at $50k and $100k. This
is a config change using a field we already fetch.

---

### 2. Holder count has a sweet spot we do not reward

| holders | moon rate | dump rate |
|---|---|---|
| 1,000-5,000 | **65.9%** | 11.1% |
| 5,000+ | 58.6% | 22.0% |
| 200-1,000 | 27.5% | 25.1% |
| 50-200 | 23.6% | 23.5% |
| under 50 | 4.3% | 16.4% |

They call this the strongest single predictor they measured — stronger than
trader count, because a holder is someone who bought and *kept*.

Surgeon has `holder_count` and uses it **only to penalise below 50**. The
1,000-5,000 band gets nothing.

Note the ceiling: above 5,000 the dump rate doubles. Widely known is worse
than growing.

**Fix:** score the band, not just the floor. Field already fetched.

---

### 3. Launchpad is a binary safety check we do not make

| platform | dump rate |
|---|---|
| Meteora DBC | **91.7%** |
| pump.fun | 10.1% |
| Let's Bonk | 5.6% |
| Raydium LaunchLab | 7.3% |

Nine in ten Meteora DBC tokens fall more than 50% within 24 hours. The
mechanism is structural: pump.fun's bonding curve prevents selling until it
fills, Meteora DBC allows selling from block zero, so it attracts creators
whose intent is to dump.

DexScreener returns `dexId` on every pair. We read it and store it as a
label. We never act on it.

**Fix:** one check. Possibly a hard reject.

*Caveat: single source. Worth verifying against our own data before making
it a reject — we have `dex` stored on every signal, so this is a query we
can run today.*

---

### 4. Social presence, and a counterintuitive finding about Telegram

| | pump rate | dump rate |
|---|---|---|
| has Twitter or website | 29.9% | **13.3%** |
| no social | 25.0% | **40.6%** |

Three times the dump rate with no socials.

And the part I did not expect: **adding Telegram to Twitter+Website raises
the dump rate from 12.7% to 27.6%.** Their explanation is that a Telegram
group is pump-and-dump infrastructure — private, coordinated, disposable —
whereas a Twitter account and a domain are public and persistent.

Surgeon fetches DexScreener's `token-profiles` endpoint, which carries
socials, and reads none of them.

**Fix:** parse socials, reward Twitter/website, treat Telegram-only as
neutral or negative.

---

### 5. Volume acceleration — computable today, from data we already have

`(5m volume x 288) / 24h volume`. Above 3x means money is flowing in faster
than the token's own recent norm. Their framing: the volume moves before the
price does.

We have `volume_5m` and `volume_24h` on every market snapshot. This is
arithmetic on fields already in memory.

---

### 6. Wash-trading detection — also computable today

Volume per trader. Over $100k volume with under 50 traders means each
"trader" averages $2,000, which is a handful of wallets recycling.

We have volume and transaction counts. We use transaction count in momentum
scoring but never the ratio.

Their organic-vs-wash signature, for reference:

```
ORGANIC                        WASH
many unique wallets            few wallets recycling
varied trade sizes             repetitive amounts
random intervals               regular timing
high traders per $volume       low traders per $volume
```

The finding worth carrying: **organic tokens do not just moon more, they
dump less.**

---

### 7. Buy ratio has a step function at 97%

| 1h buy ratio | moon rate |
|---|---|
| 100% | 68.1% |
| 99% | 54.1% |
| 98% | 38.9% |
| **97%** | **21.4%** |
| 96% | 11.3% |
| 95% | 10.0% |

Below 97% it is noise. Above, it roughly doubles per point. Their reading is
that sellers have been exhausted and the sell side of the book is empty.

They also flag it as a **timing** signal rather than a conviction one — 100%
is unsustainable and the break is fast.

Surgeon uses buy/sell ratio inside momentum quality but has no threshold
anywhere near this.

---

### 8. Bundlers — this one contradicts what we built

| bundler count | moon rate | dump rate |
|---|---|---|
| 50+ | 26.9% | 18.7% |
| 11-50 | 14.6% | **14.1%** |
| 1-10 | 22.8% | 21.1% |
| **none** | 23.4% | **28.0%** |

Tokens with **zero** bundlers have the highest dump rate. Their argument:
bundlers are a proxy for attention, and if fifty automated systems all
looked at a token and none bought, that is information.

Surgeon treats bundling as unambiguously bad — `CLUSTER` costs up to -28 and
`EVEN_SPLIT` -18. That may be too blunt.

*I would not act on this without checking our own data. It cuts against
King's stated heuristics and against the CyberPump case, which was a real
loss. But it is worth knowing that the relationship is not monotonic.*

---

### 9. Creator funding commitment

| creator funded with | graduation rate |
|---|---|
| 10+ SOL | **30.3%** |
| 5-10 SOL | 2.7% |
| 1-5 SOL | 1.6% |
| under 1 SOL | 2.6% |

And separately: first-time creators pump at 19.9%, serial deployers with 20+
tokens at 4.2% — a 4.8x gap they call the strongest predictor in the set.

We check `creator_rug_history` from RugCheck but not token count or funding.

*Needs a data source we do not have. Filed rather than proposed.*

---

### 10. Market cap sweet spot vs our tier ceilings

| market cap | moon rate | dump rate |
|---|---|---|
| $100k-$1M | **78.3%** | 3.0% |
| $1M+ | 64.1% | 12.8% |
| $10k-$100k | 48.8% | 2.6% |
| $1k-$10k | 1.2% | 12.5% |
| under $1k | 3.4% | **91.5%** |

Our `first_moon` caps FDV at $150k, so most of the best band falls to
`second_moon`, which demands more volume and turnover. Worth checking
whether our tier boundaries are cutting across the grain of this.

---

## What I would build, in order

**Now, from data already in hand:**

1. Graded liquidity depth — biggest single signal, config change
2. Holder count sweet spot — second biggest, config change
3. Volume acceleration — arithmetic on existing fields
4. Volume per trader — arithmetic on existing fields
5. Buy ratio threshold at 97%

**After a query against our own data:**

6. Launchpad check — we store `dex` already, so we can test the Meteora
   claim before acting on it
7. Whether our cluster penalties are too harsh

**Needs new fetching:**

8. Social links from DexScreener token-profiles

**Filed, no source:**

9. Creator funding and deploy count

---

## What I am not confident about

The dataset is one source. It is unusually specific — published queries,
stated sample sizes, internally consistent numbers — and where it overlaps
with Bubblemaps, DEXTools and the sniper-bot notes it agrees with them. But
several findings are counterintuitive enough that I would test them against
our own outcomes before treating them as settled, particularly the bundler
paradox and the Meteora claim.

Our own data is now the better authority on anything we can measure
ourselves. We have `dex`, `liquidity_usd`, `fdv`, `volume_24h` and
`top_holder_pct` on every closed signal. Three of the ten items above can be
checked against our own trades this afternoon rather than taken on trust.
