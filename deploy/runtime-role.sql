-- Apply as migration owner after Alembic. Grant this group to a dedicated
-- password-managed login separately; no credentials belong in this file.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bouquet_runtime') THEN
    CREATE ROLE bouquet_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS extensions;
GRANT USAGE ON SCHEMA public, extensions TO bouquet_runtime;
DO $$
DECLARE entry record;
BEGIN
  FOR entry IN SELECT tablename FROM pg_tables WHERE schemaname='public'
    AND tablename IN ('sellers','source_accounts','source_posts','source_post_versions',
      'media_assets','source_post_media','listings','listing_sources','listing_revisions',
      'extraction_runs','field_assertions','model_versions','price_observations',
      'availability_observations','text_embeddings','image_embeddings','listing_similarity',
      'cohort_runs','cohort_members','jobs','ingestion_cursors','review_actions',
      'takedown_requests','app_users','interaction_events','cost_entries','rate_buckets',
      'account_aliases','message_edges','conversation_captures','capture_members',
      'offer_occurrences','offer_associations','canonical_configurations','canonical_links',
      'offer_claims','taxonomy_terms','discovery_settings','graph_executions',
      'discovery_frontier','action_receipts','model_calls','execution_events',
      'browser_observations','profile_snapshots','offer_analyses','association_reviews')
  LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.%I TO bouquet_runtime',entry.tablename);
    EXECUTE format('DROP POLICY IF EXISTS runtime_service ON public.%I',entry.tablename);
    EXECUTE format('CREATE POLICY runtime_service ON public.%I TO bouquet_runtime USING (true) WITH CHECK (true)',entry.tablename);
  END LOOP;
END $$;
DO $$
DECLARE entry record;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='graph_checkpoints') THEN
    GRANT USAGE ON SCHEMA graph_checkpoints TO bouquet_runtime;
    FOR entry IN SELECT tablename FROM pg_tables WHERE schemaname='graph_checkpoints'
      AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes')
    LOOP
      EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE graph_checkpoints.%I TO bouquet_runtime',entry.tablename);
      EXECUTE format('DROP POLICY IF EXISTS runtime_service ON graph_checkpoints.%I',entry.tablename);
      EXECUTE format('CREATE POLICY runtime_service ON graph_checkpoints.%I TO bouquet_runtime USING (true) WITH CHECK (true)',entry.tablename);
    END LOOP;
  END IF;
END $$;
