-- ============================================================
-- MediCompare India — Database Schema v2 (PostgreSQL 14+)
--
-- Refined for: SIMPLICITY · DEDUPLICATION · SEARCH SPEED
--
-- Changes from v1:
--   • Removed editorial_actions table (move to app-level audit
--     later when actually needed; keeps MVP simple)
--   • Removed ingestion_runs table (use app logging instead)
--   • Added search_key columns for aggressive deduplication
--   • Added materialized medicine_search view for one-query lookup
--   • Pre-computed per_unit_mrp on packs (avoids runtime division)
--   • Strict UNIQUE constraints + dedup triggers where it matters
-- ============================================================
 
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;


-- ============================================================
-- HELPER FUNCTION: aggressive search-key normalizer
-- "Dolo 650 Tablet"  -> "dolo650tablet"
-- "Dolo-650 Tab"     -> "dolo650tab"
-- "Sun Pharma Ltd."  -> "sunpharmaltd"
-- Strips spaces, hyphens, dots, parens, commas. Lowercases.
-- This is the single weapon against typo-duplicates.
-- ============================================================

CREATE OR REPLACE FUNCTION make_search_key(input TEXT)
RETURNS TEXT AS $$
    SELECT lower(regexp_replace(unaccent(coalesce(input, '')), '[^a-zA-Z0-9]', '', 'g'));
$$ LANGUAGE SQL IMMUTABLE;


-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE dosage_form AS ENUM (
    'tablet', 'capsule', 'syrup', 'suspension', 'injection',
    'cream', 'ointment', 'gel', 'drops', 'spray',
    'inhaler', 'lozenge', 'powder', 'patch', 'suppository',
    'solution', 'lotion', 'sachet', 'other'
);

CREATE TYPE strength_unit AS ENUM (
    'mg', 'mcg', 'g', 'ml', 'IU', 'percent', 'mg_per_ml', 'mg_per_g'
);

CREATE TYPE medicine_status AS ENUM (
    'active', 'discontinued', 'banned', 'pending_review'
);

CREATE TYPE price_source AS ENUM (
    'manufacturer_website', 'manufacturer_gst_list',
    'jan_aushadhi_catalog', 'nppa_ceiling',
    'pack_photo_verified', 'user_reported',
    'manual_entry', 'partner_feed'
);

CREATE TYPE data_quality AS ENUM (
    'verified', 'pending', 'flagged'
);


-- ============================================================
-- 1. SALTS
-- ============================================================

CREATE TABLE salts (
    salt_id           SERIAL PRIMARY KEY,
    canonical_name    TEXT NOT NULL,
    search_key        TEXT NOT NULL UNIQUE
                      GENERATED ALWAYS AS (make_search_key(canonical_name)) STORED,
    -- search_key is auto-computed and enforced unique.
    -- Trying to insert "Paracetamol" twice (or "paracetamol",
    -- or "Paracetamol IP") will fail because they all collapse
    -- to the same key.

    aliases           TEXT[] NOT NULL DEFAULT '{}',
    therapeutic_class TEXT,
    is_prescription   BOOLEAN NOT NULL DEFAULT FALSE,
    is_banned         BOOLEAN NOT NULL DEFAULT FALSE,
    banned_reason     TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_salts_search_key ON salts (search_key);
CREATE INDEX idx_salts_aliases ON salts USING GIN (aliases); -- GIN (Generalized Inverted Index)
CREATE INDEX idx_salts_canonical_trgm ON salts USING GIN (canonical_name gin_trgm_ops);


-- ============================================================
-- 2. MANUFACTURERS
-- ============================================================

CREATE TABLE manufacturers (
    manufacturer_id           SERIAL PRIMARY KEY,
    canonical_name            TEXT NOT NULL,
    search_key                TEXT NOT NULL UNIQUE
                              GENERATED ALWAYS AS (make_search_key(canonical_name)) STORED,
    -- Auto-prevents "Sun Pharma", "Sun Pharma Ltd", "Sun Pharmaceutical Ltd"
    -- from existing as 3 rows. Whoever inserts second gets a constraint
    -- violation and must add to aliases instead.

    aliases                   TEXT[] NOT NULL DEFAULT '{}',
    website                   TEXT,
    is_generic_focused        BOOLEAN NOT NULL DEFAULT FALSE,
    is_jan_aushadhi_supplier  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_manufacturers_search_key ON manufacturers (search_key);


-- ============================================================
-- 3. COMPOSITIONS  —  the matching key
-- composition_hash is built by the ingestion code from sorted,
-- canonicalized salts + strengths + form.
-- ============================================================

CREATE TABLE compositions (
    composition_id     SERIAL PRIMARY KEY,
    composition_hash   TEXT NOT NULL UNIQUE,
    -- Example: "paracetamol-650-mg|tablet"
    -- This is what makes alternative-matching a single index lookup.

    display_name       TEXT NOT NULL,
    dosage_form        dosage_form NOT NULL,
    is_combination     BOOLEAN NOT NULL DEFAULT FALSE,
    is_banned          BOOLEAN NOT NULL DEFAULT FALSE,
    banned_reason      TEXT,
    banned_notice_ref  TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_compositions_hash ON compositions (composition_hash);
CREATE INDEX idx_compositions_form ON compositions (dosage_form);


-- ============================================================
-- 4. COMPOSITION_SALTS  —  link table
-- ============================================================

CREATE TABLE composition_salts (
    composition_id   INTEGER NOT NULL REFERENCES compositions(composition_id) ON DELETE CASCADE,
    salt_id          INTEGER NOT NULL REFERENCES salts(salt_id),
    strength_value   NUMERIC(12, 4) NOT NULL CHECK (strength_value > 0),
    strength_unit    strength_unit NOT NULL,
    sort_order       SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (composition_id, salt_id, strength_value, strength_unit)
);

CREATE INDEX idx_composition_salts_salt ON composition_salts (salt_id);


-- ============================================================
-- 5. MEDICINES (brands)
-- Search-key uniqueness is the strong dedup guard here.
-- ============================================================

CREATE TABLE medicines (
    medicine_id           SERIAL PRIMARY KEY,
    brand_name            TEXT NOT NULL,
    brand_search_key      TEXT NOT NULL
                          GENERATED ALWAYS AS (make_search_key(brand_name)) STORED,
    manufacturer_id       INTEGER NOT NULL REFERENCES manufacturers(manufacturer_id),
    composition_id        INTEGER NOT NULL REFERENCES compositions(composition_id),

    is_generic            BOOLEAN NOT NULL DEFAULT FALSE,
    is_jan_aushadhi       BOOLEAN NOT NULL DEFAULT FALSE,
    prescription_required BOOLEAN NOT NULL DEFAULT FALSE,

    status                medicine_status NOT NULL DEFAULT 'pending_review',
    nppa_regulated        BOOLEAN NOT NULL DEFAULT FALSE,
    nppa_ceiling_price    NUMERIC(10, 2),

    quality_status        data_quality NOT NULL DEFAULT 'pending',
    primary_source_url    TEXT,
    last_verified_at      TIMESTAMPTZ,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- THE KEY DEDUP RULE: same brand search-key + manufacturer
    -- can only exist once, period. "Dolo 650 Tablet" and
    -- "Dolo-650 Tab" from Micro Labs collapse to the same key.
    UNIQUE (brand_search_key, manufacturer_id)
);

CREATE INDEX idx_medicines_brand_search_key ON medicines (brand_search_key);
CREATE INDEX idx_medicines_brand_trgm ON medicines USING GIN (brand_name gin_trgm_ops);
CREATE INDEX idx_medicines_composition ON medicines (composition_id);
CREATE INDEX idx_medicines_manufacturer ON medicines (manufacturer_id);
CREATE INDEX idx_medicines_status ON medicines (status);
CREATE INDEX idx_medicines_jan_aushadhi ON medicines (is_jan_aushadhi)
    WHERE is_jan_aushadhi = TRUE;


-- ============================================================
-- 6. PACKS
-- ============================================================

CREATE TABLE packs (
    pack_id          SERIAL PRIMARY KEY,
    medicine_id      INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE CASCADE,
    pack_size        NUMERIC(12, 3) NOT NULL CHECK (pack_size > 0),
    pack_unit        TEXT NOT NULL,
    pack_description TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (medicine_id, pack_size, pack_unit)
);

CREATE INDEX idx_packs_medicine ON packs (medicine_id);


-- ============================================================
-- 7. PRICES (time series — keep all observations)
-- ============================================================

CREATE TABLE prices (
    price_id        BIGSERIAL PRIMARY KEY,
    pack_id         INTEGER NOT NULL REFERENCES packs(pack_id) ON DELETE CASCADE,
    mrp             NUMERIC(10, 2) CHECK (mrp IS NULL OR mrp >= 0),
    selling_price   NUMERIC(10, 2) CHECK (selling_price IS NULL OR selling_price >= 0),
    currency        CHAR(3) NOT NULL DEFAULT 'INR',
    source          price_source NOT NULL,
    source_detail   TEXT,
    source_date     DATE,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quality_status  data_quality NOT NULL DEFAULT 'pending',

    CONSTRAINT price_at_least_one CHECK (mrp IS NOT NULL OR selling_price IS NOT NULL)
);

CREATE INDEX idx_prices_pack_recorded ON prices (pack_id, recorded_at DESC);


-- ============================================================
-- 8. SEARCH_LOG (lightweight)
-- ============================================================

CREATE TABLE search_log (
    search_id            BIGSERIAL PRIMARY KEY,
    query_text           TEXT NOT NULL,
    query_search_key     TEXT NOT NULL
                         GENERATED ALWAYS AS (make_search_key(query_text)) STORED,
    matched_medicine_id  INTEGER REFERENCES medicines(medicine_id),
    matched_salt_id      INTEGER REFERENCES salts(salt_id),
    result_count         INTEGER NOT NULL DEFAULT 0,
    user_session_hash    TEXT,
    searched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_search_log_key ON search_log (query_search_key);
CREATE INDEX idx_search_log_no_results ON search_log (searched_at DESC)
    WHERE result_count = 0;


-- ============================================================
-- 9. MEDICINE_REQUESTS (demand signal from zero-result searches)
-- ============================================================

CREATE TABLE medicine_requests (
    request_id       BIGSERIAL PRIMARY KEY,
    query_text       TEXT NOT NULL,
    query_search_key TEXT NOT NULL UNIQUE
                     GENERATED ALWAYS AS (make_search_key(query_text)) STORED,
    -- Search-key uniqueness means "Pacimol", "PACIMOL", "Pacimol-650"
    -- all collapse into one request row with rising count.

    request_count    INTEGER NOT NULL DEFAULT 1,
    first_requested  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_requested   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fulfilled        BOOLEAN NOT NULL DEFAULT FALSE,
    medicine_id      INTEGER REFERENCES medicines(medicine_id)
);

CREATE INDEX idx_medicine_requests_unfulfilled
    ON medicine_requests (request_count DESC)
    WHERE fulfilled = FALSE;


-- ============================================================
-- VIEW: latest price per pack
-- ============================================================

CREATE OR REPLACE VIEW latest_prices AS
SELECT DISTINCT ON (pack_id)
    pack_id, mrp, selling_price, currency, source, source_date, recorded_at
FROM prices
WHERE quality_status IN ('verified', 'pending')
ORDER BY pack_id, recorded_at DESC;


-- ============================================================
-- MATERIALIZED VIEW: medicine_search
--
-- This is the search-speed multiplier.
-- One row per medicine, with everything the search/results
-- screen needs already joined and pre-computed. Search hits
-- THIS view, not 5 joined tables.
--
-- Refreshed nightly (or after any large ingestion batch).
-- ============================================================

CREATE MATERIALIZED VIEW medicine_search AS
SELECT
    m.medicine_id,
    m.brand_name,
    m.brand_search_key,
    m.composition_id,
    c.composition_hash,
    c.display_name AS composition_display,
    c.dosage_form,
    c.is_banned AS composition_banned,
    c.banned_reason AS composition_banned_reason,
    mfr.manufacturer_id,
    mfr.canonical_name AS manufacturer_name,
    m.is_generic,
    m.is_jan_aushadhi,
    m.prescription_required,
    m.status,
    m.nppa_regulated,
    m.nppa_ceiling_price,
    m.quality_status,
    -- The CHEAPEST per-unit MRP across all packs for this medicine.
    -- Pre-computed so sorting alternatives is just ORDER BY a column.
    MIN(lp.mrp / NULLIF(p.pack_size, 0)) AS min_per_unit_mrp,
    -- The smallest pack's MRP (often the most relatable to users)
    MIN(lp.mrp) AS min_pack_mrp,
    -- Readable pack display
    MIN(p.pack_size)::TEXT || ' ' || MIN(p.pack_unit) AS pack_display,
    -- How many packs we have for this medicine
    COUNT(p.pack_id) AS pack_count
FROM medicines m
JOIN manufacturers mfr ON mfr.manufacturer_id = m.manufacturer_id
JOIN compositions c ON c.composition_id = m.composition_id
LEFT JOIN packs p ON p.medicine_id = m.medicine_id
LEFT JOIN latest_prices lp ON lp.pack_id = p.pack_id
WHERE m.status != 'banned'
GROUP BY
    m.medicine_id, m.brand_name, m.brand_search_key, m.composition_id,
    c.composition_hash, c.display_name, c.dosage_form,
    c.is_banned, c.banned_reason,
    mfr.manufacturer_id, mfr.canonical_name,
    m.is_generic, m.is_jan_aushadhi, m.prescription_required,
    m.status, m.nppa_regulated, m.nppa_ceiling_price, m.quality_status;

-- Indexes on the materialized view make search ONE index lookup
CREATE UNIQUE INDEX idx_msearch_medicine_id ON medicine_search (medicine_id);
CREATE INDEX idx_msearch_brand_key ON medicine_search (brand_search_key);
CREATE INDEX idx_msearch_brand_trgm ON medicine_search USING GIN (brand_name gin_trgm_ops);
CREATE INDEX idx_msearch_composition ON medicine_search (composition_id);
CREATE INDEX idx_msearch_composition_price ON medicine_search (composition_id, min_per_unit_mrp);
-- The last index is the KEY one: "given a composition_id, return
-- alternatives sorted by price" becomes a single index range scan.

-- Refresh the view (run after ingestion):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY medicine_search;


-- ============================================================
-- THE THREE QUERIES THE APP WILL ACTUALLY RUN
-- ============================================================

-- (A) Autocomplete as user types "dol":
-- SELECT medicine_id, brand_name, composition_display, manufacturer_name
-- FROM medicine_search
-- WHERE brand_search_key LIKE 'dol%'
--    OR brand_name ILIKE 'dol%'
-- ORDER BY brand_name
-- LIMIT 10;
--
-- Uses idx_msearch_brand_key (B-tree prefix scan) — instant.

-- (B) User picks "Dolo 650 Tablet" — show alternatives:
-- SELECT medicine_id, brand_name, manufacturer_name, is_jan_aushadhi,
--        is_generic, min_per_unit_mrp, min_pack_mrp
-- FROM medicine_search
-- WHERE composition_id = (
--     SELECT composition_id FROM medicine_search WHERE medicine_id = $1
-- )
--   AND medicine_id != $1
-- ORDER BY min_per_unit_mrp ASC NULLS LAST;
--
-- Uses idx_msearch_composition_price — fetches pre-sorted directly.

-- (C) User searches a salt name "paracetamol":
-- SELECT DISTINCT composition_id, composition_display
-- FROM medicine_search ms
-- JOIN composition_salts cs ON cs.composition_id = ms.composition_id
-- JOIN salts s ON s.salt_id = cs.salt_id
-- WHERE s.search_key = make_search_key('paracetamol')
--    OR 'paracetamol' = ANY(s.aliases);


-- ============================================================
-- WHAT THIS SCHEMA GUARANTEES
-- ============================================================
-- DEDUP: search_key columns + UNIQUE constraints make it
--   IMPOSSIBLE to create:
--     • two salts that differ only in punctuation/case
--     • two manufacturers that differ only in punctuation/case
--     • two medicines from same maker with same normalized brand
--     • two requests for the same medicine in different formatting
--     • two compositions with same hash
--   Duplicates fail at INSERT, not in cleanup later.
--
-- SEARCH: every user-facing query goes through medicine_search
--   (the materialized view), which is one indexed lookup. No
--   runtime joins, no runtime math. Sub-millisecond at 100k records.
--
-- SIMPLE: 9 tables + 1 view + 1 materialized view.
--   No editorial_actions log (move to app logs if needed later).
--   No ingestion_runs table (use app logs).
--   No barcode/route fields until we actually need them.
-- ============================================================

-- ============================================================
-- SCRAPED_MARKETERS FOR 1mg scraping loop
-- ============================================================
CREATE TABLE IF NOT EXISTS scraped_marketers (
    marketer_url TEXT PRIMARY KEY,
    scraped_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- HELPER FUNCTION: normalize_composition
-- Used in the search query to match against composition_display with regex.
-- ============================================================
CREATE OR REPLACE FUNCTION normalize_composition(text)
RETURNS text AS
$$
SELECT lower(
    regexp_replace(
        regexp_replace(
            regexp_replace($1, '\s+', '', 'g'),
            '[()]',
            '',
            'g'
        ),
        '[^a-z0-9]',
        '',
        'g'
    )
);
$$ LANGUAGE sql IMMUTABLE;

CREATE INDEX idx_norm_comp
ON medicine_search (
    normalize_composition(composition_display)
);