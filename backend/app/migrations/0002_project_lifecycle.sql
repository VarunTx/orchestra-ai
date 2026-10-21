ALTER TABLE projects ADD COLUMN IF NOT EXISTS management jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE deployments ADD COLUMN IF NOT EXISTS evidence_kind text NOT NULL DEFAULT 'deployment';
UPDATE deployments SET evidence_kind = 'ci' WHERE provider = 'github' AND external_id LIKE 'github-run-%';
CREATE TABLE project_runners (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 name text NOT NULL, token_hash text NOT NULL UNIQUE, last_seen_at timestamptz,
 revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE project_work (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 runner_id uuid NOT NULL REFERENCES project_runners(id), title text NOT NULL,
 request text NOT NULL, acceptance text NOT NULL, model_approved boolean NOT NULL DEFAULT false,
 workflow_id text UNIQUE, submission text NOT NULL DEFAULT 'draft', active boolean NOT NULL DEFAULT false,
 task_id text, artifacts jsonb NOT NULL DEFAULT '{}'::jsonb,
 approved_sha text, approved_at timestamptz, publish_approved boolean NOT NULL DEFAULT false,
 publication jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX project_one_active_work ON project_work(project_id) WHERE active;
CREATE TABLE project_releases (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 expected_sha text NOT NULL, evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), checked_at timestamptz
);
