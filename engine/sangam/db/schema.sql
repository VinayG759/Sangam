-- Sangam schema.
--
-- Governing rule: no table or column may encode one country's administrative
-- vocabulary. No "district", no "panchayat", no scheme names. The moment one
-- appears, adding a second country becomes a migration instead of a folder.
--
-- Apply with:  psql "$DATABASE_URL" -f engine/sangam/db/schema.sql

create extension if not exists postgis;
create extension if not exists vector;
create extension if not exists pg_trgm;   -- fuzzy place-name matching

-- ---------------------------------------------------------------------------
-- The geographic spine. One self-referencing tree, so India's
-- country > state > district > block and Brazil's country > estado > municipio
-- are the same structure at different depths.
-- ---------------------------------------------------------------------------
create table if not exists admin_units (
    unit_id         text primary key,
    country_code    text not null,
    level           int  not null,          -- 0 country, 1 state, 2 district, 3 block
    name            text not null,
    name_variants   text[] not null default '{}',
    parent_unit_id  text references admin_units(unit_id),
    external_code   text,                   -- LGD (IN), IBGE (BR)
    population      bigint,
    geom            geometry(MultiPolygon, 4326),
    centroid        geometry(Point, 4326),
    source_name     text,
    source_url      text
);

create index if not exists admin_units_country_level_idx on admin_units (country_code, level);
create index if not exists admin_units_parent_idx        on admin_units (parent_unit_id);
create index if not exists admin_units_geom_idx          on admin_units using gist (geom);
-- trigram index over the name, for fuzzy matching spoken place names
create index if not exists admin_units_name_trgm_idx     on admin_units using gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- How well served a place already is. TALL, not wide: one row per
-- (place, statistic). A wide table would need an ALTER TABLE for every new
-- country's statistics; tall means a new country ships rows.
--
-- source_url is on every row. Provenance is a column, not a feature.
-- ---------------------------------------------------------------------------
create table if not exists indicators (
    id            bigserial primary key,
    unit_id       text not null references admin_units(unit_id) on delete cascade,
    indicator_key text not null,            -- e.g. water.piped_household_pct
    value         numeric not null,
    unit          text,                     -- percent | households | count
    period        text,                     -- '2026', '2019'
    source_name   text,
    source_url    text,
    unique (unit_id, indicator_key, period)
);

create index if not exists indicators_key_idx on indicators (indicator_key);

-- ---------------------------------------------------------------------------
-- Public money. Optional per country: India publishes no district-level
-- sanctioned amounts, so the India pack derives its delivery signal from
-- indicators instead. Kept because other countries do publish this.
-- ---------------------------------------------------------------------------
create table if not exists sanctioned_projects (
    project_id      text primary key,
    unit_id         text not null references admin_units(unit_id) on delete cascade,
    sector          text not null,          -- matches a need_taxonomy key
    title           text,
    amount          numeric,
    currency        text,
    status          text check (status in ('sanctioned','in_progress','completed','stalled')),
    sanctioned_date date,
    completion_date date,
    source_name     text,
    source_url      text
);

create index if not exists sanctioned_unit_sector_idx on sanctioned_projects (unit_id, sector);

-- ---------------------------------------------------------------------------
-- The raw citizen voice.
--
-- channel_user_hash is HMAC-SHA256 of the platform user id plus a server-side
-- pepper. The raw id is never stored, so we can count distinct reporters
-- without ever being able to name one.
--
-- raw_text is PII-redacted BEFORE the first write, not before display --
-- anything written to disk can leak later.
-- ---------------------------------------------------------------------------
create table if not exists citizen_requests (
    id                  uuid primary key default gen_random_uuid(),
    country_code        text not null,
    channel             text not null check (channel in ('telegram','whatsapp','web')),
    channel_user_hash   text not null,
    tracking_id         text not null unique,

    raw_text            text,
    raw_language        text,
    translated_text     text,
    media_url           text,
    media_type          text,
    media_expires_at    timestamptz,        -- retention, set from pack config

    need_type           text,
    urgency             int check (urgency between 1 and 5),
    affected_estimate   int default 0,
    is_actionable       boolean default true,

    location_text       text,               -- as the citizen said it
    location_text_latin text,               -- romanised; what the resolver matches on
    unit_id             text references admin_units(unit_id),
    location_confidence numeric,

    embedding           vector(768),

    status              text not null default 'received',
    model_version       text,
    created_at          timestamptz not null default now()
);

create index if not exists requests_unit_need_idx on citizen_requests (unit_id, need_type);
create index if not exists requests_created_idx   on citizen_requests (created_at desc);
create index if not exists requests_hash_idx      on citizen_requests (channel_user_hash);
-- Vector index. IVFFlat is enough at prototype scale; switch to HNSW when the
-- table passes a few million rows.
create index if not exists requests_embedding_idx on citizen_requests
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ---------------------------------------------------------------------------
-- The single follow-up question. Expires in an hour: one question, never two.
-- ---------------------------------------------------------------------------
create table if not exists pending_intake (
    channel_user_hash text primary key,
    channel           text not null,
    partial_request   jsonb not null,
    awaiting          text not null,        -- 'location'
    expires_at        timestamptz not null
);

-- ---------------------------------------------------------------------------
-- Analysis runs. Each run writes under a new id and is marked complete only at
-- the end; the dashboard reads the newest COMPLETE run. A job that crashes
-- halfway leaves no partial state visible -- yesterday's answer stays live.
-- ---------------------------------------------------------------------------
create table if not exists analysis_runs (
    run_id        uuid primary key default gen_random_uuid(),
    country_code  text not null,
    status        text not null default 'running' check (status in ('running','complete','failed')),
    started_at    timestamptz not null default now(),
    completed_at  timestamptz,
    note          text
);

create index if not exists runs_latest_idx on analysis_runs (country_code, status, completed_at desc);

-- ---------------------------------------------------------------------------
-- Demand grouped by place x need.
--
-- distinct_reporters, not request_count, is what scoring uses. Five hundred
-- messages from one identity contribute exactly one -- so flooding does not
-- get blocked, it simply stops working.
-- ---------------------------------------------------------------------------
create table if not exists demand_clusters (
    id                  uuid primary key default gen_random_uuid(),
    run_id              uuid not null references analysis_runs(run_id) on delete cascade,
    unit_id             text not null references admin_units(unit_id) on delete cascade,
    need_type           text not null,
    request_count       int  not null,
    distinct_reporters  int  not null,
    reporters_per_1000  numeric,
    baseline_ratio      numeric,            -- vs the pack-wide median for this need
    coordinated_flag    boolean default false,
    first_seen          timestamptz,
    last_seen           timestamptz,
    unique (run_id, unit_id, need_type)
);

create index if not exists clusters_run_idx on demand_clusters (run_id);

-- ---------------------------------------------------------------------------
-- The output.
--
-- Two lists, not one: "fund this" and "send an inspector" are different
-- actions and must not compete on a single ranking.
--
-- evidence holds every figure with its source. No number reaches a
-- policymaker's screen unless it appears here.
-- ---------------------------------------------------------------------------
create table if not exists recommendations (
    id                uuid primary key default gen_random_uuid(),
    run_id            uuid not null references analysis_runs(run_id) on delete cascade,
    cluster_id        uuid references demand_clusters(id) on delete cascade,
    unit_id           text not null references admin_units(unit_id) on delete cascade,
    need_type         text not null,

    list              text not null check (list in ('fund','audit','monitor')),
    rank              int  not null,
    verdict           text not null,        -- unserved_gap | left_behind | not_flowing | served | monitor
    priority_score    numeric not null,
    score_components  jsonb not null,       -- the arithmetic, exposed

    title             text not null,
    justification     text,
    justification_verified boolean default false,
    est_beneficiaries int,

    evidence          jsonb not null default '[]',
    partial_evidence  boolean default false,
    model_version     text,
    generated_at      timestamptz not null default now()
);

create index if not exists recs_run_list_rank_idx on recommendations (run_id, list, rank);
create index if not exists recs_unit_idx          on recommendations (unit_id);
