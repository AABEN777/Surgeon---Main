-- Surgeon v2 schema
-- Paste this whole file into Supabase -> SQL Editor -> Run.
-- Safe to re-run; everything is IF NOT EXISTS.

-- ── signals ──────────────────────────────────────────────────────
-- One row per alert fired. Also serves as the open-position table
-- (outcome = 'pending') and the trade history once closed.
create table if not exists signals (
  id              bigserial primary key,
  ca              text        not null,
  chain           text        not null,
  name            text,
  symbol          text,
  tier            text,
  conviction      integer,
  band            text,
  momentum        text,
  launch_phase    text,
  narrative       text,
  session         text,
  entry_price     double precision,
  liquidity_usd   double precision,
  fdv             double precision,
  volume_24h      double precision,
  change_5m       double precision,
  change_1h       double precision,
  age_hours       double precision,
  dex             text,
  launchpad       text,
  social_channels integer default 0,
  smart_wallets   integer default 0,
  safety_verdict  text,
  top_holder_pct  double precision,
  lp_locked_pct   double precision,
  safety_sources  text,
  unavailable     text,
  breakdown       text,
  alerted_at      double precision not null,
  alert_sent      boolean default false,
  outcome         text default 'pending',
  exit_type       text,
  final_pnl       double precision,
  peak_pnl        double precision,
  peak_price      double precision,
  closed_at       double precision
);

create index if not exists signals_ca_idx        on signals (ca);
create index if not exists signals_alerted_idx   on signals (alerted_at desc);
create index if not exists signals_outcome_idx   on signals (outcome);
create index if not exists signals_chain_idx     on signals (chain);

-- ── mentions ─────────────────────────────────────────────────────
-- Every CA seen in a monitored Telegram channel. Cross-channel overlap
-- inside the velocity window is the social signal.
create table if not exists mentions (
  id         bigserial primary key,
  ca         text not null,
  chain      text,
  channel    text not null,
  seen_at    double precision not null
);

create index if not exists mentions_ca_idx   on mentions (ca);
create index if not exists mentions_seen_idx on mentions (seen_at desc);
create unique index if not exists mentions_unique_idx
  on mentions (ca, channel, seen_at);

-- ── watch_events ─────────────────────────────────────────────────
-- Which position alerts have already fired, so TP1 does not notify
-- on every scan for the rest of the position's life.
create table if not exists watch_events (
  id        bigserial primary key,
  ca        text not null,
  event     text not null,
  pnl       double precision,
  fired_at  double precision not null
);

create index if not exists watch_ca_idx on watch_events (ca);
create unique index if not exists watch_unique_idx on watch_events (ca, event);

-- ── smart money wallets ──────────────────────────────────────────
-- Editable without a redeploy. Add a wallet here and the next scan uses it.
create table if not exists smart_wallets (
  id        bigserial primary key,
  address   text not null,
  chain     text not null,
  label     text,
  active    boolean default true,
  added_at  double precision default extract(epoch from now())
);

create unique index if not exists smart_wallets_unique_idx
  on smart_wallets (address, chain);


-- ── watchlist ────────────────────────────────────────────────────
-- Tokens too young to judge when first seen. Discovery surfaces pools
-- minutes old, the entry filter wants ten minutes, and by the next scan they
-- have dropped out of the new-pool feed. Waiting is correct; forgetting is
-- not.
create table if not exists watchlist (
  ca              text primary key,
  chain           text not null,
  name            text,
  symbol          text,
  first_seen      double precision not null,
  first_age_hours double precision,
  checks          integer default 0,
  last_checked    double precision
);

create index if not exists watchlist_seen_idx    on watchlist (first_seen desc);
create index if not exists watchlist_checked_idx on watchlist (last_checked asc);

-- ── meta_terms ───────────────────────────────────────────────────
-- Words shared by tokens that are currently performing. The fixed narrative
-- list cannot contain a meta that did not exist yesterday.
create table if not exists meta_terms (
  id         bigserial primary key,
  term       text not null,
  chain      text,
  change_24h double precision,
  seen_at    double precision not null
);

create index if not exists meta_terms_seen_idx on meta_terms (seen_at desc);
create index if not exists meta_terms_term_idx on meta_terms (term);

-- ── bot_state ────────────────────────────────────────────────────
-- Small key/value store. Currently holds the Telegram getUpdates offset so
-- the analyzer does not answer the same message twice.
create table if not exists bot_state (
  key   text primary key,
  value text
);

-- ── token_buyers ─────────────────────────────────────────────────
-- Wallets that were early to a token, cached permanently. Transfer history
-- never changes, and explorers return 429 after a handful of calls — so this
-- is fetched once per token and reused forever.
create table if not exists token_buyers (
  ca         text not null,
  chain      text not null,
  wallets    text,
  fetched_at double precision,
  primary key (ca, chain)
);

-- ── columns added after the first release ────────────────────────
-- Safe to re-run; each is a no-op once present.
alter table signals add column if not exists from_watchlist    boolean default false;
alter table signals add column if not exists creator_holds_pct double precision;
alter table signals add column if not exists dev_held          boolean default false;

-- Consensus is weighted, so this holds fractions rather than a count.
alter table signals
  alter column social_channels type double precision
  using social_channels::double precision;

alter table watchlist    enable row level security;
alter table meta_terms   enable row level security;
alter table bot_state    enable row level security;
alter table token_buyers enable row level security;


-- ── columns added after the first release, part two ──────────────
-- How many consecutive checks have failed to see a token. Absence is only
-- evidence when it repeats: "DexScreener returned nothing" and "the pool is
-- empty" were treated identically, so every timeout wrote -100% into the
-- outcome data.
alter table signals   add column if not exists missed_checks integer default 0;

-- Why a token is parked. "too_young" ages into its gates; "unverified" is
-- waiting for a safety source to answer.
alter table watchlist add column if not exists park_reason text default 'too_young';

-- ── row level security ───────────────────────────────────────────
-- Surgeon connects with the service key, which bypasses RLS. These
-- policies exist so the anon key cannot read your signal history if
-- the URL ever leaks.
alter table signals       enable row level security;
alter table mentions      enable row level security;
alter table watch_events  enable row level security;
alter table smart_wallets enable row level security;

-- ── convenience views ────────────────────────────────────────────
create or replace view v_open_positions as
  select ca, chain, name, symbol, tier, conviction, band,
         entry_price, alerted_at,
         (extract(epoch from now()) - alerted_at) / 3600 as hours_open
  from signals
  where outcome = 'pending'
  order by alerted_at desc;

create or replace view v_performance as
  select
    chain,
    count(*)                                            as trades,
    count(*) filter (where outcome in
      ('WIN','BIG_WIN','MOON','WEAK_WIN'))              as wins,
    round(100.0 * count(*) filter (where outcome in
      ('WIN','BIG_WIN','MOON','WEAK_WIN')) / count(*), 1) as win_rate,
    round(avg(final_pnl)::numeric, 1)                   as avg_pnl,
    round(avg(conviction)::numeric, 1)                  as avg_conviction
  from signals
  where outcome <> 'pending'
  group by chain
  order by trades desc;

-- Which conviction bands actually win. This is what retunes the weights.
create or replace view v_conviction_calibration as
  select
    band,
    width_bucket(conviction, 0, 100, 10) * 10 as score_bucket,
    count(*)                                  as trades,
    round(100.0 * count(*) filter (where outcome in
      ('WIN','BIG_WIN','MOON','WEAK_WIN')) / count(*), 1) as win_rate,
    round(avg(final_pnl)::numeric, 1)         as avg_pnl
  from signals
  where outcome <> 'pending'
  group by band, score_bucket
  order by score_bucket desc;

create or replace view v_narrative_performance as
  select
    narrative,
    count(*) as trades,
    round(100.0 * count(*) filter (where outcome in
      ('WIN','BIG_WIN','MOON','WEAK_WIN')) / count(*), 1) as win_rate,
    round(avg(final_pnl)::numeric, 1) as avg_pnl
  from signals
  where outcome <> 'pending' and narrative is not null
  group by narrative
  order by trades desc;
