-- Initialize PostgreSQL extensions for VitaeX Agentic Platform
-- This script runs automatically when the TimescaleDB container starts

-- Enable TimescaleDB extension for time-series data
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable PGVector extension for embeddings and semantic search
CREATE EXTENSION IF NOT EXISTS vector CASCADE;

-- Enable additional useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create time-series hypertables for health data
-- This will be created by the TimeseriesClient but good to have as backup
DO $$
BEGIN
    -- Create measurements table if it doesn't exist
    IF NOT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'measurements') THEN
        CREATE TABLE measurements (
            user_id TEXT NOT NULL,
            metric TEXT NOT NULL,
            ts TIMESTAMPTZ NOT NULL,
            value DOUBLE PRECISION,
            meta JSONB DEFAULT '{}'::jsonb
        );
        
        -- Convert to hypertable (FIXED: Use PERFORM instead of SELECT)
        PERFORM create_hypertable('measurements', 'ts', if_not_exists => TRUE);
        
        -- Create indexes for efficient queries
        CREATE INDEX idx_measurements_user_metric ON measurements(user_id, metric, ts DESC);
        CREATE INDEX idx_measurements_meta ON measurements USING GIN(meta);
    END IF;
    
    -- Create embeddings table for vector storage
    IF NOT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'embeddings') THEN
        CREATE TABLE embeddings (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding VECTOR(1536) NOT NULL
        );
        
        -- Create indexes for vector similarity search
        CREATE INDEX idx_embeddings_namespace ON embeddings(namespace);
        CREATE INDEX idx_embeddings_metadata ON embeddings USING GIN(metadata);
        CREATE INDEX idx_embeddings_embedding ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    END IF;
    
    RAISE NOTICE 'VitaeX database extensions and tables initialized successfully';
END
$$;