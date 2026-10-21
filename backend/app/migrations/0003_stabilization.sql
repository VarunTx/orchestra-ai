-- Associations are evidence metadata, not a second workflow state store.
CREATE TABLE execution_links (
 workflow_id text PRIMARY KEY,
 project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
 work_id uuid,
 project_name text NOT NULL,
 purpose text NOT NULL DEFAULT 'coding',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION link_project_execution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.workflow_id IS NOT NULL THEN
 INSERT INTO execution_links(workflow_id,project_id,work_id,project_name)
 SELECT NEW.workflow_id,NEW.project_id,NEW.id,p.name FROM projects p WHERE p.id=NEW.project_id
 ON CONFLICT(workflow_id) DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER project_execution_link AFTER INSERT OR UPDATE OF workflow_id ON project_work
 FOR EACH ROW EXECUTE FUNCTION link_project_execution();
INSERT INTO execution_links(workflow_id,project_id,work_id,project_name)
 SELECT w.workflow_id,w.project_id,w.id,p.name FROM project_work w JOIN projects p ON p.id=w.project_id WHERE w.workflow_id IS NOT NULL
 ON CONFLICT DO NOTHING;
ALTER TABLE project_work ALTER COLUMN runner_id DROP NOT NULL;
ALTER TABLE projects ADD COLUMN record_kind text NOT NULL DEFAULT 'project';
ALTER TABLE project_runners ADD COLUMN diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE project_connections (
 project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 connector_id uuid NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
 PRIMARY KEY(project_id,connector_id)
);
