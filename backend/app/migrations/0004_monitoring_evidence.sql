CREATE VIEW service_evidence AS SELECT s.*,
 CASE WHEN NOT monitoring_enabled THEN 'disabled'
 WHEN last_checked_at IS NULL OR last_checked_at < now()-make_interval(secs => check_interval_seconds*3) OR last_error IS NOT NULL THEN 'unknown'
 ELSE current_status END AS effective_status,
 CASE WHEN NOT monitoring_enabled THEN 'disabled' WHEN last_checked_at IS NULL THEN 'unknown'
 WHEN last_checked_at < now()-make_interval(secs => check_interval_seconds*3) THEN 'stale'
 WHEN last_error IS NOT NULL THEN 'unknown' ELSE 'fresh' END AS evidence_state
 FROM services s;
