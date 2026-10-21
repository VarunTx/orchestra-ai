-- Restore permission metadata only for definitions registered through the existing audited validator.
INSERT INTO registered_definitions(name,version)
 SELECT split_part(resource_id,'@',1),split_part(resource_id,'@',2)::integer
 FROM audit_log WHERE action='workflow.register' AND resource_id ~ '^[a-z][a-z0-9_]{2,60}@[0-9]{1,3}$'
 ON CONFLICT DO NOTHING;
