# Changes to judge

## Verdicts from the first full dataset (1,123 closed trades)

**Reverted — boosted widening.** 21.8% on 110 trades against first_moon's
25.3%, worst average close in the system at -45, and not one of the fifteen
biggest winners was boosted. The 32.1% that justified widening was 28 trades
of luck. Back to 24h / $20k FDV.

**Removed — DEAD session penalty.** Five of the fifteen biggest winners were
taxed ten points for launching overnight: Bullballs (+4,332%), Caesar
(+794%), Fatal Boner (+832%), Burpcoin, Onigiricoin. The gates still tighten
in dead hours; the score no longer charges a token for its launch time.

**Changed — top holder scaled by age.** Halved inside the first hour. Buying
Power took -14 and ran +3,128%; Caesar took -14 and ran +794%. Concentration
on a twenty-minute-old token is what an early runner looks like. Severe
concentration stays severe at any age.

**Changed — unverified muted rather than penalised twice.** Unflagged tokens
rug at 16.0%, flagged at 10.9%. Rugs come from what cannot be checked, so
unverifiable tokens no longer interrupt — but the penalty drops to -10 so
they stay above the tracking floor and keep feeding the outcome data.

**Kept — scam heuristics.** Flagged tokens win 25.7% against 21.1% and rug at
10.9% against 16.0%.

**Kept — meta detection.** Theme metas 32.6%, word metas 25.7% with an average
peak of 86, against a 22.0% baseline on 967 trades. My copycat worry was
wrong: word metas have the highest peaks in the system.

**Not raised — score floors.** Conviction is flat from 30 to 69 and the
fifteen biggest winners have a median score of 51. Raising the floor would
cut winners and losers in equal measure — fewer alerts at the same win rate,
which is a worse deal. Volume was tightened through safety instead.

Net effect on the fifteen biggest winners: 8 would have reached the phone
before, 13 now.

## Second pass — reviewing my own reasoning

Reread every change against the data. Two did not survive.

**Reversed — muting unverified.** Justified with "unflagged tokens rug at
16.0% against 10.9%", but that query split on *risk flags*, not verification
status. Different things, and I used data about one to change the other.
央视抽象吉祥物 was unverified and ran +410%; muting would have silenced it.
Back to flagging, penalty -18.

**Removed — the unproven rule.** Fired on 0 of 1,116 closed trades across
every tier. An inert rule that looks like protection is worse than none,
because it gets counted as one.

**Fixed — a double charge.** UNVERIFIED cost -18 in conviction and the
UNCHECKED risk flag cost another -10 for the same fact. That took the +410%
winner from 59 to 49 and silenced it. The flag now names the condition
without billing for it.

### Two reverts I proposed and then withdrew

I first argued for restoring boosted's 60 floor and reducing the top-holder
grace, on the grounds that boosted closes at -45 and flags correlate with
risk. Both were wrong, for the same reason:

**`avg_final` measures our exit rules, not signal quality.** King trades
manually and does not hold to our trailing stop — which gives back 130 points
on average. Condemning boosted for its average close was condemning it for
how our own exit logic handled it.

On whether a token ever gave King a chance, boosted goes green **41.8%** of
the time against first_moon's **38.4%**. Muting it would have removed the
tier offering more opportunities than the one producing most alerts.

And flagged tokens *win more and rug less* — 25.7% against 21.1%, rugging
10.9% against 16.0%. Reducing that penalty moves with the data, not against
it. (Confound worth naming: a flag mostly means we had enough data to form an
opinion, so it may measure visibility rather than risk.)

### What I got wrong twice, the same way

Both errors came from reading an average without asking what produced it —
the trailing-versus-volume-fade comparison, and the boosted verdict. In each
case the mean concealed the mechanism. Worth watching for.

## Cooloff removed

Silenced Titan at 67/100 — which peaked +1,890% — and RWArt at 62/100. Both
cleared every floor.

It was inherited from the autonomous version, where pausing after losses
protected capital that was being spent. Signal-only it only decides not to
speak, while King decides what to trade.

And it got worse as Surgeon got better: improving rug detection closed more
positions as losses, which tripped the rule more often, until it was muting
35 qualified signals a day against 7 when it was last reviewed. A safety
improvement made a separate rule hostile — worth watching for elsewhere.

The position cap stays. That one limits noise rather than reacting to losses.

## Research checked against our own data

Three claims from a published Solana dataset, tested against King's 3,275
closed trades before building anything.

**Did not replicate — graded liquidity depth.** The study reported $100k+
liquidity dumping 0.25% of the time, a 308x moon:dump ratio, and called it
the strongest signal it measured. Here $100k+ rugged **28.3%** across 191
trades — a hundred times worse — and the relationship is not monotonic:
$10k-20k beat $20k-50k on win rate. I had this queued as the top-priority
build and it would have done nothing.

What did replicate is the floor: under $10k rugs at 51.2%. first_moon's
minimum moved from $6k to $10k. No graded scoring above it.

**Replicated, and found our own version — venue.** The study named Meteora
DBC at a 91.7% dump rate. We have no Meteora exposure, but the same query
found **pons-v2: 58 trades, 5.2% win, 87.9% rug**, with a 95% interval of
77-94% rug and 1.8-14% win. Blocked outright. pancakeswap, pancakeswap_v2
and uniswap-v3-robinhood all rug at twice baseline and take -18.
uniswap-v4-base (49.7% win, n=322) and uniswap-v4-robinhood (39.6%, n=164)
earn +6. uniswap and pumpswap sit exactly on the baseline across 2,051
trades and are deliberately absent.

**Replicated against us — the bundler paradox.** The study found tokens with
*zero* bundlers had the highest dump rate. Our data agrees in direction:
EVEN_SPLIT wins **40.5%** against a 28.3% baseline, and CLUSTER wins 37.0%.
Both were being charged -18 and -28, which removed our best-performing
cohort from alerting.

EVEN_SPLIT also rugs more (32.4% vs 19.7%) and both intervals clear the
baseline, so it is genuinely higher variance rather than simply good.
Reduced to -6 and named loudly. CLUSTER at n=27 is not significant in either
direction; reduced to -3/-6/-12 until the sample says otherwise.

Every threshold above was set from a Wilson interval rather than a point
estimate, so an effect has to survive its own uncertainty before it changes
anything.

## The mute label was lying

On 29 August the record said `muted:cooloff` for MU at 69/100, which ran
**+5,072%**. The cooloff had been removed two days earlier.

The label was hardcoded in scan.py and threw away which condition actually
fired. The real cause was the position cap — 32 positions open against a cap
of 25 — which also silenced VAULT at 71/100 (+1,313%) and GG at 61/100
(+2,985%). All three cleared every floor, and the record sent us hunting a
rule that no longer existed.

Two fixes. The reason is now carried from the condition that raised it, so
`muted:position_cap:32/25` says what happened. And the cap moved from 25 to
90, because it was inherited from the autonomous version where 25 open
positions meant genuine capital exposure — signal-only it only decides not
to speak, and it is not protecting against load either: the watcher batches
thirty addresses per request, so 25 positions is one call and 90 is three.

Third time a rule written for the autonomous bot has silenced a runner in a
signal-only system. Worth auditing anything else inherited from that era.

## Two data-integrity bugs

**False rugs.** `not market` — DexScreener returning nothing — was treated
identically to an empty pool, and both wrote -100% into the outcome data.
Their API timed out dozens of times an hour during the outage, so an unknown
number of healthy tokens were recorded as rugs. Every conclusion drawn from
outcome data this week rests partly on those rows: win rates understated,
rug rates overstated, and the venue penalties in particular may be inflated.

Absence now has to repeat before it counts — three silent checks for no data,
two for a pool that genuinely reads empty, and a token that comes back resets
its counter.

**UNVERIFIED was a chain tax, not a risk signal.** It fires on 99.7% of BSC
signals, 84.9% of Robinhood, 11.9% of Base and 0% of Solana, because RugCheck
always answers and GoPlus usually does not on a fresh EVM launch.

And where it varies it does not predict badness. On Robinhood, unverified
tokens win 27.4-36.7% against checked at 20.8-25.6%, and rug 26.9-36.1%
against 14.6-18.9% — neither interval overlaps. They win more and rug more,
with an average peak of 75 against 44. That is a newer token, which
GOLDEN_WINDOW already pays +15 for; we were charging 18 for the same fact.

Reduced to -5. Analyst was seen twice at 2.29h and 2.87h, scored 32 and 42,
and ran +3,536%. At -5 it scores 45 and 55, and the second sighting alerts.

Unverified tokens that would clear their floor once checked are now also
parked for a re-read, since GoPlus needs a few minutes on a fresh launch.

## Audit — which decisions rested on the false rug data

King caught that the venue penalties were set from rug rate while rug rate
was known to be contaminated. Every decision made from that dataset was
re-tested using win rate alone, which the bug does not touch.

**Survived on win rate alone:**

| decision | evidence without rug rate |
|---|---|
| pons-v2 blocked | 5.2% win [1.8-14.1], n=58 |
| pancakeswap_v2 -18 | 15.2% win [10.0-22.5], n=125 |
| pancakeswap -18 | 21.5% win [17.7-25.9], n=390 |
| uniswap-v4-base +6 | 49.7% win [44.3-55.1], n=322 |
| uniswap-v4-robinhood +6 | 39.6% win [32.5-47.3], n=164 |
| liquidity floor $10k | under $10k wins 20.3% [14.2-28.3] |
| robinhood $5k-10k closed | 16.5% win [10.4-25.1], 1 runner in 97 |
| EVEN_SPLIT penalty cut | 40.5% win [30.1-51.9], above baseline |
| UNVERIFIED cut to -5 | 27.4-36.7% vs 20.8-25.6% checked, no overlap |

**Withdrawn:** uniswap-v3-robinhood's -18. It rested entirely on a 60.7% rug
rate across 28 trades; its win interval is 10.2-39.5, which spans the
baseline and proves nothing. Worth re-checking once the rug data is clean.

Worth noting the direction of the contamination for the UNVERIFIED decision:
false rugs come from DexScreener having no record of a token, which is more
likely for newer tokens, which are also more likely to be unverified. So the
unverified rug rate was inflated more than the checked one — which makes the
case for cutting that penalty stronger, not weaker.

## The circuit breaker was manufacturing the outage it existed to survive

King noticed alerts arriving UNVERIFIED far more often than before. It was
the breaker, added the previous day, counting any non-200 as a host failure.

GoPlus and Blockscout return 404 for tokens they have not indexed — the
normal answer for a fresh launch, and the scan log was full of them. Four in
a row tripped the breaker, and then no safety call went out for 180 seconds,
so every token evaluated in that window came back UNVERIFIED. A scan takes
two to five minutes per chain, so one trip could blank safety for most of it.

Now only 401, 403, 429 and 5xx count as host failures. A 404 is an answer
about one token, not a verdict on the host, and it resets the counter rather
than incrementing it.

**This partly contaminates the UNVERIFIED analysis.** The 84.9% Robinhood and
99.7% BSC figures span 48 hours, and the breaker was live for roughly half of
that. The chain pattern itself is structural — RugCheck answers for Solana,
GoPlus often does not for fresh EVM launches — so the direction holds. But
the magnitude is overstated, and the -5 penalty should be re-checked against
clean data in a few days.

Second time in two days a rule of mine has caused the problem it was written
to prevent.

## The rug fix broke every exit

The confirmation counter never persisted. `note_missed_check` called `_req`
with `json=` when it takes `body=`, which raised TypeError into a bare
except that logged a warning and carried on.

So every check read 0, incremented to 1, and saved nothing. No position could
ever reach the threshold, which meant **nothing closed at all** — not stale
positions, not real liquidity drains, not dev-sold. King spotted both halves:
a position open 10.1 hours, and genuine rugs no longer being marked.

Three fixes:

- the keyword is right, and a failure now logs at error level rather than
  warning, because a counter that silently fails to persist stops the
  watcher dead
- a position past its maximum hold closes on schedule even with no price
  data. Time does not stop because the feed did, and a token DexScreener has
  quietly dropped could otherwise live in the open set forever
- the Alive workflow no longer goes red when it finds a problem. That was
  ambiguous with the watchdog itself breaking, and King could not tell them
  apart from the Actions tab. The Telegram message is the alert; a red run
  now means the watchdog is broken

Checked the repo for the same class of bug — wrong keywords into `_req`
anywhere, and exception handlers broad enough to hide a persistent failure.
Neither found elsewhere.

Third time in three days a protective rule of mine has caused the problem it
was written to prevent: the circuit breaker manufacturing an outage, the
mute label hiding its own cause, and now rug confirmation stopping every
exit. The pattern is that each one failed silently — the code kept running
and reported something plausible. Worth preferring a loud failure to a
graceful one in anything on the critical path.

## Correcting myself on what the rug bug touched

I told King the false-rug bug did not affect win rate, and used that to
justify keeping decisions made from contaminated data. That was wrong.

A falsely rugged token is recorded as `LOSS` at -100%. It stays in the
denominator and counts against the group. So any cohort DexScreener indexed
poorly had **both** an inflated rug rate and a depressed win rate — and the
"re-tested on win rate alone" audit was not the clean check I presented it
as.

Two consequences.

**The alert floor moved 50 -> 40.** On the 48 hours since the fix, the 40-49
band wins 46.4% [39.6-53.4] across 196 trades, against the 46.4% currently
reaching the phone across 561. The real break is now below 40, where 30-39
wins 30.9% [25.6-36.8]. Contamination understates win rates, so 46.4% is a
floor on the truth rather than a ceiling — the direction of this change is
safe even if the magnitude shifts.

**pons-v2 is no longer blocked.** If every one of its 51 recorded rugs were
false and those tokens won at the population rate, it lands near 43% —
indistinguishable from uniswap. The block cannot be defended on that data.

And a block generates no data at all, so it could never be tested: a
decision that confirms itself. Downgraded to -30, which keeps almost
everything below the floor while the tokens are still tracked and graded.
In a week there will be clean numbers to judge it on.

The general lesson: prefer a penalty to a veto when the evidence is thin,
because a penalty keeps learning and a veto stops.

## Still unresolved

**Trailing stops are the largest leak.** 156 exits, average peak +122%,
average close -8% — giving back 130 points. Volume fade gives back 21 and
closes at +79. Not yet touched, because the two largest winners (+5,900% and
+4,332%) exited on MAX_HOLD after running the full eight hours, so trailing
harder would cut off exactly the tokens that pay for everything else.

---


Every adjustment made in the last two days, what it was meant to fix, and
what evidence would show it worked or should be removed.

Written before the outcomes are in, so the test cannot be moved afterwards.

Entries marked **MINE** rest on my judgement rather than King's data. Those
are the first candidates for removal if they cannot show their worth.

---

## Backed by outcome data

### Boosted widened, first_moon left alone
Boosted won 32.1% across 28 trades against first_moon's 17.9% across 184.
Boosted's ceiling went to 36h, FDV floor to $15k, volume floor to $3.5k.

*Right if:* boosted's share of signals rises and its win rate holds above 25%.
*Wrong if:* boosted's win rate falls toward first_moon's — the original edge
was small-sample luck and the wider gates diluted it.

### Base gates raised hard
46 trades, 13% win rate, average peak +4%. First_moon now needs 45% hourly
change, $10k volume, 0.35 turnover, $12k liquidity.

*Right if:* Base sends far fewer signals but its win rate approaches the
other chains'.
*Wrong if:* Base goes silent entirely — the bar became a wall, and it should
be lowered rather than left as a chain we pay to scan and never hear from.

### first_moon momentum gate reverted to 15%
I raised it to 25% inferring "tighten the weak tier" from data that only said
"older tokens do better". It blocked 83 of 96 Solana candidates. Entry
momentum showed no stable direction across 515 trades — down within boosted
and second_moon, up within first_moon.

*Right if:* Solana's tier rejections stop being dominated by `1h`.
*Wrong if:* first_moon's win rate falls below 15% — the looser gate is
letting through tokens that were being correctly excluded.

### Volume fade loosened to 0.45 ratio, +10% floor
Volume fade closed at +78% against a +101% peak. Trailing closed at -21%
against a +95% peak. Momentum dies before price does.

*Right if:* VOLUME_FADE's share of exits rises and its average close stays
well above other exit types.
*Wrong if:* its average close drops toward the others — firing earlier is
catching noise rather than genuine fade.

### Watcher every 5 minutes instead of 15
Trailing stops were closing at -21% on +95% peaks because a fifteen-minute
poll only saw the drawdown once the move was over.

*Right if:* TRAIL_STOP's average close moves up substantially.
*Wrong if:* it does not move — the problem was the trailing rule, not the
polling interval.

### Stop split into warn and grade
CATCOIN was signalled and stopped out inside five minutes at -26% with a peak
of exactly +0%. Warn at -15%, grade at -35% after 20 minutes.

*Right if:* some positions that trip STOP_WARN later close green — early dips
do recover, and grading them immediately was recording good calls as losses.
*Wrong if:* nothing that warns ever recovers. Then the split only delays the
inevitable and makes losses bigger; revert to grading at -15%.

### Per-tier alert floors
One floor at 60 muted boosted entirely: 82 signals, zero sent, because its
gates are loosest so its tokens score lower by construction. Now boosted 38,
second_moon 48, first_moon 52.

*Right if:* boosted starts sending and those alerts perform at least as well
as first_moon's.
*Wrong if:* boosted alerts underperform badly — the score was correctly
identifying them as weak and the low floor is letting noise through.

### Scam heuristics kept, not removed
King asked for removal after a run of rugs. The data said flagged tokens win
25.5% against 20.2%, peak 43 against 30, and every rug that reached him came
from the *unflagged* group.

*Right if:* the gap holds as the sample grows.
*Wrong if:* it closes — the flags are noise and the correlation was
incidental.

---

## MINE — judgement, not evidence

### Channel calls evaluated as candidates
Mentions were only used to top up scores of tokens Surgeon had already found,
so 76 of 78 were discarded. Each mention is now a candidate with its own tier
reaching $50m FDV and a week old, gated on consensus rather than score.

*Right if:* channel calls alert and win at a rate comparable to discovery.
*Wrong if:* they alert often and lose — the channels are noise and this is an
expensive way to import it. Watch specifically whether consensus (2+
channels) beats single mentions.

### Meta detection, 12 point cap
Learns the running meta from tokens performing above 80% in 24h. Early read:
meta-matched tokens won 47.4% against 21.4% on 19 trades.

*Right if:* the gap survives 60+ trades. Then the cap is probably too low.
*Wrong if:* it regresses to the mean. Also watch whether copycat clusters
(`67coin`, `z500`) drag — if word metas underperform theme metas, exclude
clone waves rather than cutting the layer.

### Unproven safety penalty, -12
Every rug that reached King came from tokens with nothing flagged — not clean,
just unexamined. A low RugCheck score on a token with under 300 holders now
costs 12 points.

*Right if:* the rugs that reach him drop, or unproven-flagged tokens
underperform clearly.
*Wrong if:* unproven tokens perform the same as checked ones — the penalty is
punishing youth rather than risk, and 300 holders is an arbitrary line.

### LP zero corroboration
Zero LP no longer rejects when the deployer holds nothing, insiders hold
nothing and there are 500+ holders. Recovered the Cancer Vaccine, which was
rejected while holding 17,900 holders and 0% insider supply.

*Right if:* tokens recovered this way do not rug more than average.
*Wrong if:* any of them rug — the corroboration is too weak and needs a
tighter condition.

### LP lock expiry penalties
-6 inside a day, -12 inside twelve hours, -20 inside two, -25 expired.

*Right if:* tokens with imminent unlocks underperform.
*Wrong if:* no difference — short rolling locks are normal and this is
penalising a convention rather than a risk.

### Dev sold, now functional
Was dead code reading a field that was never written. Now compares the
deployer's holding against what it held at signal time; fires on emptied or
50%+ shed.

*Right if:* it fires at all, and tokens it fires on drop afterwards.
*Wrong if:* it never fires — either deployers on our signals are clean, or
the comparison is still broken.

### Solana discovery depth 6 pages
Two pages is ~40 pools, and Solana produces more than that in fifteen
minutes. A graduation creates a new pool, which is how the Cancer Vaccine
went unseen.

*Right if:* Solana's candidate count roughly triples and new tokens appear
that were not surfacing before.
*Wrong if:* candidates rise but signals do not — the extra pools are junk and
the cost in throttle is wasted.

### Cooling off loosened to 5 losses / 20 min, alerts only
Was 2 losses / 60 min and halted the whole scan. Two losers at a 20% win rate
is an ordinary afternoon.

*Right if:* it rarely triggers.
*Wrong if:* it never triggers at all — then it is dead weight and should go.

### Channel weights levelled to 1.0
I discounted nine channels to 0.35 on a misreading, then removed it. The
mechanism stays for measured hit rates later.

*Right if:* channel accuracy scoring eventually fills it with real numbers.
*Wrong if:* overlap never reaches a level where channels can be measured —
then the whole weighting mechanism is scaffolding for something that will
never be built.

---

## Unresolved, and the honest reason

**Conviction barely predicts outcome.** 30-69 is a flat plateau: 19.2, 19.4,
22.4, 21.4 across 533 trades. Only 70+ separates, at 33.3% on 45 trades.
The score largely measures how much a token resembles a fresh launch, not how
likely it is to run. Every weight in it is either carried from the VPS or
mine. This is the thing most in need of rebuilding from outcomes, and the
thing I have least evidence for.

**The 50-150% band.** first_moon tokens entering up 50-150% won 11.7% across
94 trades — worst cell with a real sample, and a third of all signals. Both
extremes beat it. Needs 250+ before acting.

**Social overlap.** Two tokens have ever appeared in both mentions and
signals. Channel accuracy scoring is blocked until that reaches ~50.
