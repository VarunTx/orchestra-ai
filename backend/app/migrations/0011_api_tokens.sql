-- Scoped API tokens for machine clients (MCP servers, agents, scripts).
-- The secret is stored only as a SHA-256 fingerprint; the plaintext is returned once.
CREATE TABLE IF NOT EXISTS api_tokens (
    id           uuid PRIMARY KEY,
    label        text NOT NULL CHECK (length(label) BETWEEN 1 AND 80),
    token_hash   bytea NOT NULL UNIQUE,
    scope        text NOT NULL CHECK (scope IN ('read', 'operate', 'admin')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);

CREATE INDEX IF NOT EXISTS api_tokens_active_idx ON api_tokens (token_hash) WHERE revoked_at IS NULL;
