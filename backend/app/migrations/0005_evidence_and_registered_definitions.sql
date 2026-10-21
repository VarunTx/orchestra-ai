CREATE OR REPLACE VIEW service_evidence AS SELECT s.*,
 CASE WHEN NOT monitoring_enabled THEN 'disabled'
 WHEN last_checked_at IS NULL OR last_checked_at < now()-make_interval(secs => check_interval_seconds*3)
 OR (SELECT o.status FROM observations o WHERE o.service_id=s.id ORDER BY observed_at DESC LIMIT 1)='unknown' THEN 'unknown'
 ELSE current_status END AS effective_status,
 CASE WHEN NOT monitoring_enabled THEN 'disabled' WHEN last_checked_at IS NULL THEN 'unknown'
 WHEN last_checked_at < now()-make_interval(secs => check_interval_seconds*3) THEN 'stale'
 WHEN (SELECT o.status FROM observations o WHERE o.service_id=s.id ORDER BY observed_at DESC LIMIT 1)='unknown' THEN 'unknown' ELSE 'fresh' END AS evidence_state
 FROM services s;
CREATE TABLE registered_definitions (name text NOT NULL,version integer NOT NULL,created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(name,version));
