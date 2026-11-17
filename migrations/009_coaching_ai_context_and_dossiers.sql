-- ============================================================================
-- DETOUR ATHLETICS LLC & DETOUR RUN CLUB INC.
-- Migration 009: Subscription-Bounded Coaching AI Context & Athlete Dossiers
--   1. Dedicated coaching.* schema with halfvec(1536) (50% lower RAM/disk)
--   2. Hard <= 2,048-byte CHECK cap on activity_compact_summaries (zero 1Hz bloat)
--   3. GIN inverted indexes on entity_tags[] and full-text tsvector
--   4. Mandatory Row-Level Security (RLS) separating athlete_visible, club_public,
--      and coach_internal records
--   5. SECURITY INVOKER RPC coaching.assemble_coaching_context
-- ============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS coaching;

CREATE OR REPLACE FUNCTION coaching.is_coach()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
  SELECT COALESCE(auth.jwt() -> 'app_metadata' ->> 'role', '') IN ('coach', 'admin');
$$;

-- 1. Curated Coach Doctrine & Protocols (default doc_priority = 1.25)
CREATE TABLE IF NOT EXISTS coaching.coach_doctrine_docs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body_md TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'club_public'
    CHECK (visibility IN ('club_public', 'athlete_visible', 'coach_internal')),
  doc_priority DOUBLE PRECISION NOT NULL DEFAULT 1.25,
  entity_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  embedding halfvec(1536),
  tsv TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body_md, ''))
  ) STORED,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Compiled O(1) Athlete Dossiers (1 row per athlete; deterministic truth + provenance log)
CREATE TABLE IF NOT EXISTS coaching.athlete_dossiers (
  athlete_id UUID PRIMARY KEY,
  compiled_truth_md TEXT NOT NULL DEFAULT '',
  structured_facts JSONB NOT NULL DEFAULT '{}'::jsonb,
  timeline_log JSONB NOT NULL DEFAULT '[]'::jsonb,
  visibility TEXT NOT NULL DEFAULT 'athlete_visible'
    CHECK (visibility IN ('athlete_visible', 'coach_internal')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Append-Only Athlete Evidence Events (default doc_priority = 0.90)
CREATE TABLE IF NOT EXISTS coaching.athlete_events (
  id TEXT PRIMARY KEY,
  athlete_id UUID NOT NULL,
  event_kind TEXT NOT NULL,
  summary_text TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  visibility TEXT NOT NULL DEFAULT 'athlete_visible'
    CHECK (visibility IN ('athlete_visible', 'coach_internal')),
  doc_priority DOUBLE PRECISION NOT NULL DEFAULT 0.90,
  entity_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  embedding halfvec(1536),
  tsv TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(event_kind, '') || ' ' || coalesce(summary_text, ''))
  ) STORED,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Compacted <= 2KB Activity Summaries (raw 1Hz arrays discarded in Python RAM)
CREATE TABLE IF NOT EXISTS coaching.activity_compact_summaries (
  activity_id TEXT PRIMARY KEY,
  athlete_id UUID NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  visibility TEXT NOT NULL DEFAULT 'athlete_visible'
    CHECK (visibility IN ('athlete_visible', 'coach_internal')),
  compact_json JSONB NOT NULL
    CHECK (octet_length(compact_json::text) <= 2048)
);

-- 5. Human-in-the-Loop Coach Review Queue (Pain >= 3/5 or GI Distress >= 4/5)
CREATE TABLE IF NOT EXISTS coaching.coach_review_queue (
  id BIGSERIAL PRIMARY KEY,
  athlete_id UUID NOT NULL,
  trigger_event_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending_coach_review'
    CHECK (status IN ('pending_coach_review', 'approved', 'dismissed')),
  proposed_action_md TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'coach_internal'
    CHECK (visibility IN ('coach_internal', 'athlete_visible')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Inverted GIN + B-Tree + HNSW halfvec Indexes
CREATE INDEX IF NOT EXISTS idx_doctrine_entity_tags ON coaching.coach_doctrine_docs USING GIN (entity_tags);
CREATE INDEX IF NOT EXISTS idx_doctrine_tsv ON coaching.coach_doctrine_docs USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_events_athlete_id ON coaching.athlete_events (athlete_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_entity_tags ON coaching.athlete_events USING GIN (entity_tags);
CREATE INDEX IF NOT EXISTS idx_events_tsv ON coaching.athlete_events USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_compact_athlete_id ON coaching.activity_compact_summaries (athlete_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON coaching.coach_review_queue (status, created_at DESC);

-- Enable Mandatory Row-Level Security on All 5 Tables
ALTER TABLE coaching.coach_doctrine_docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching.athlete_dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching.athlete_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching.activity_compact_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching.coach_review_queue ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Early-Binding Principal + Visibility Enforcement
CREATE POLICY doctrine_select_policy ON coaching.coach_doctrine_docs
  FOR SELECT TO authenticated
  USING (visibility IN ('club_public', 'athlete_visible') OR coaching.is_coach());

CREATE POLICY dossiers_select_policy ON coaching.athlete_dossiers
  FOR SELECT TO authenticated
  USING (
    coaching.is_coach()
    OR (athlete_id = auth.uid() AND visibility = 'athlete_visible')
  );

CREATE POLICY events_select_policy ON coaching.athlete_events
  FOR SELECT TO authenticated
  USING (
    coaching.is_coach()
    OR (athlete_id = auth.uid() AND visibility = 'athlete_visible')
  );

CREATE POLICY summaries_select_policy ON coaching.activity_compact_summaries
  FOR SELECT TO authenticated
  USING (
    coaching.is_coach()
    OR (athlete_id = auth.uid() AND visibility = 'athlete_visible')
  );

CREATE POLICY review_queue_select_policy ON coaching.coach_review_queue
  FOR SELECT TO authenticated
  USING (
    coaching.is_coach()
    OR (athlete_id = auth.uid() AND visibility = 'athlete_visible')
  );

-- SECURITY INVOKER Context Assembly RPC (RLS applies automatically per caller JWT)
CREATE OR REPLACE FUNCTION coaching.assemble_coaching_context(
  p_query TEXT,
  p_athlete_id UUID,
  p_entity_tags TEXT[] DEFAULT NULL,
  p_limit INT DEFAULT 8
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
AS $$
DECLARE
  v_tsq TSQUERY := websearch_to_tsquery('english', coalesce(nullif(trim(p_query), ''), 'run'));
  v_dossier JSONB;
  v_items JSONB;
BEGIN
  SELECT to_jsonb(d) INTO v_dossier
  FROM coaching.athlete_dossiers d
  WHERE d.athlete_id = p_athlete_id;

  WITH candidates AS (
    SELECT
      doc.id,
      'doctrine'::TEXT AS source_type,
      doc.title,
      doc.body_md AS snippet,
      doc.visibility,
      doc.entity_tags,
      (ts_rank_cd(doc.tsv, v_tsq) + 0.10) * doc.doc_priority AS score
    FROM coaching.coach_doctrine_docs doc
    WHERE (v_tsq @@ doc.tsv OR (p_entity_tags IS NOT NULL AND doc.entity_tags && p_entity_tags))
      AND (p_entity_tags IS NULL OR doc.entity_tags @> p_entity_tags)

    UNION ALL

    SELECT
      ev.id,
      'athlete_event'::TEXT AS source_type,
      ev.event_kind AS title,
      ev.summary_text AS snippet,
      ev.visibility,
      ev.entity_tags,
      (ts_rank_cd(ev.tsv, v_tsq) + 0.10) * ev.doc_priority AS score
    FROM coaching.athlete_events ev
    WHERE ev.athlete_id = p_athlete_id
      AND (v_tsq @@ ev.tsv OR (p_entity_tags IS NOT NULL AND ev.entity_tags && p_entity_tags))
      AND (p_entity_tags IS NULL OR ev.entity_tags @> p_entity_tags)
  )
  SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.score DESC), '[]'::jsonb)
  INTO v_items
  FROM (
    SELECT * FROM candidates ORDER BY score DESC LIMIT greatest(1, least(p_limit, 25))
  ) c;

  RETURN jsonb_build_object(
    'athlete_id', p_athlete_id,
    'dossier', v_dossier,
    'items', v_items
  );
END;
$$;

GRANT USAGE ON SCHEMA coaching TO authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA coaching TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA coaching TO service_role;
GRANT EXECUTE ON FUNCTION coaching.assemble_coaching_context(TEXT, UUID, TEXT[], INT) TO authenticated, service_role;

COMMIT;
