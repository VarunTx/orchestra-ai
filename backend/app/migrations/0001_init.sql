-- Orchestra AI application schema. Lives in its own database; never inside Conductor's schema.

CREATE TABLE IF NOT EXISTS app_settings (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clusters (
    id          uuid PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    kind        text NOT NULL DEFAULT 'logical' CHECK (kind IN ('logical', 'provider', 'local')),
    provider    text,
    description text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connectors (
    id                 uuid PRIMARY KEY,
    provider           text NOT NULL CHECK (provider IN ('railway', 'github', 'docker')),
    name               text NOT NULL,
    config             jsonb NOT NULL DEFAULT '{}'::jsonb,
    credentials        bytea NOT NULL,
    status             text NOT NULL DEFAULT 'unconfigured'
                       CHECK (status IN ('unconfigured', 'connected', 'error')),
    last_validated_at  timestamptz,
    last_sync_at       timestamptz,
    last_error         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
    id          uuid PRIMARY KEY,
    name        text NOT NULL,
    slug        text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    cluster_id  uuid REFERENCES clusters(id) ON DELETE SET NULL,
    repo_url    text,
    repo_branch text,
    status      text NOT NULL DEFAULT 'unknown'
                CHECK (status IN ('healthy', 'degraded', 'down', 'unknown', 'disabled')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS environments (
    id         uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       text NOT NULL,
    slug       text NOT NULL,
    kind       text NOT NULL DEFAULT 'custom'
               CHECK (kind IN ('development', 'staging', 'production', 'custom')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, slug)
);

CREATE TABLE IF NOT EXISTS services (
    id                     uuid PRIMARY KEY,
    project_id             uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id         uuid REFERENCES environments(id) ON DELETE SET NULL,
    connector_id           uuid REFERENCES connectors(id) ON DELETE SET NULL,
    name                   text NOT NULL,
    slug                   text NOT NULL,
    kind                   text NOT NULL DEFAULT 'web'
                           CHECK (kind IN ('web', 'api', 'database', 'worker', 'queue', 'cache', 'external')),
    provider               text NOT NULL DEFAULT 'http'
                           CHECK (provider IN ('http', 'railway', 'github', 'docker', 'manual')),
    external_ref           jsonb NOT NULL DEFAULT '{}'::jsonb,
    health_url             text,
    monitoring_enabled     boolean NOT NULL DEFAULT true,
    check_interval_seconds integer NOT NULL DEFAULT 60 CHECK (check_interval_seconds BETWEEN 15 AND 86400),
    timeout_seconds        integer NOT NULL DEFAULT 10 CHECK (timeout_seconds BETWEEN 1 AND 60),
    expected_status        integer NOT NULL DEFAULT 200 CHECK (expected_status BETWEEN 100 AND 599),
    failure_threshold      integer NOT NULL DEFAULT 2 CHECK (failure_threshold BETWEEN 1 AND 20),
    recovery_threshold     integer NOT NULL DEFAULT 1 CHECK (recovery_threshold BETWEEN 1 AND 20),
    current_status         text NOT NULL DEFAULT 'unknown'
                           CHECK (current_status IN ('healthy', 'degraded', 'down', 'unknown', 'disabled')),
    status_changed_at      timestamptz,
    last_checked_at        timestamptz,
    last_ok_at             timestamptz,
    consecutive_failures   integer NOT NULL DEFAULT 0,
    consecutive_successes  integer NOT NULL DEFAULT 0,
    last_error             text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, slug)
);

CREATE INDEX IF NOT EXISTS services_project_idx ON services (project_id);
CREATE INDEX IF NOT EXISTS services_due_idx ON services (last_checked_at NULLS FIRST)
    WHERE monitoring_enabled;

CREATE TABLE IF NOT EXISTS deployments (
    id             uuid PRIMARY KEY,
    project_id     uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id uuid REFERENCES environments(id) ON DELETE SET NULL,
    service_id     uuid REFERENCES services(id) ON DELETE SET NULL,
    provider       text NOT NULL DEFAULT 'manual',
    external_id    text,
    version        text,
    commit_sha     text NOT NULL DEFAULT '',
    status         text NOT NULL DEFAULT 'unknown',
    url            text,
    detail         jsonb NOT NULL DEFAULT '{}'::jsonb,
    deployed_at    timestamptz NOT NULL DEFAULT now(),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS deployments_project_idx ON deployments (project_id, deployed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS deployments_external_idx
    ON deployments (provider, external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS observations (
    id          bigserial PRIMARY KEY,
    service_id  uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    observed_at timestamptz NOT NULL DEFAULT now(),
    status      text NOT NULL CHECK (status IN ('healthy', 'degraded', 'down', 'unknown', 'disabled')),
    source      text NOT NULL CHECK (source IN ('http', 'provider', 'agent', 'manual')),
    latency_ms  integer,
    http_status integer,
    message     text NOT NULL DEFAULT '',
    evidence    jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS observations_service_idx ON observations (service_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS observations_time_idx ON observations (observed_at DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id               uuid PRIMARY KEY,
    project_id       uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    service_id       uuid NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    title            text NOT NULL,
    severity         text NOT NULL DEFAULT 'major' CHECK (severity IN ('critical', 'major', 'minor')),
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
    opened_at        timestamptz NOT NULL DEFAULT now(),
    acknowledged_at  timestamptz,
    resolved_at      timestamptz,
    detection        jsonb NOT NULL DEFAULT '{}'::jsonb,
    resolution_note  text,
    workflow_id      text,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS incidents_one_active_per_service
    ON incidents (service_id) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status, opened_at DESC);

CREATE TABLE IF NOT EXISTS incident_events (
    id          bigserial PRIMARY KEY,
    incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    at          timestamptz NOT NULL DEFAULT now(),
    kind        text NOT NULL,
    actor       text NOT NULL DEFAULT 'monitor',
    message     text NOT NULL DEFAULT '',
    data        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS incident_events_idx ON incident_events (incident_id, at);

CREATE TABLE IF NOT EXISTS alerts (
    id                uuid PRIMARY KEY,
    name              text NOT NULL,
    channel           text NOT NULL DEFAULT 'webhook' CHECK (channel IN ('webhook')),
    target            bytea NOT NULL,
    project_id        uuid REFERENCES projects(id) ON DELETE CASCADE,
    min_severity      text NOT NULL DEFAULT 'major' CHECK (min_severity IN ('critical', 'major', 'minor')),
    cooldown_seconds  integer NOT NULL DEFAULT 900 CHECK (cooldown_seconds BETWEEN 0 AND 86400),
    enabled           boolean NOT NULL DEFAULT true,
    last_notified_at  timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
    id          bigserial PRIMARY KEY,
    incident_id uuid REFERENCES incidents(id) ON DELETE SET NULL,
    alert_id    uuid REFERENCES alerts(id) ON DELETE SET NULL,
    channel     text NOT NULL,
    status      text NOT NULL CHECK (status IN ('sent', 'failed', 'suppressed')),
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            bigserial PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    actor         text NOT NULL,
    action        text NOT NULL,
    resource_type text NOT NULL,
    resource_id   text NOT NULL DEFAULT '',
    detail        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_log_time_idx ON audit_log (at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    id           uuid PRIMARY KEY,
    token_hash   bytea NOT NULL UNIQUE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    user_agent   text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions (expires_at);
