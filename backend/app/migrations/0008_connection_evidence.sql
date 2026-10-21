ALTER TABLE project_connections ADD COLUMN evidence jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE project_connections ADD COLUMN checked_at timestamptz;
