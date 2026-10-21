-- Label known local verification records without deleting project or engine history.
ALTER TABLE execution_links ADD COLUMN record_kind text NOT NULL DEFAULT 'project';
UPDATE execution_links l SET record_kind=p.record_kind FROM projects p WHERE l.project_id=p.id;
CREATE OR REPLACE FUNCTION link_project_execution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.workflow_id IS NOT NULL THEN
 INSERT INTO execution_links(workflow_id,project_id,work_id,project_name,record_kind)
 SELECT NEW.workflow_id,NEW.project_id,NEW.id,p.name,p.record_kind FROM projects p WHERE p.id=NEW.project_id
 ON CONFLICT(workflow_id) DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
