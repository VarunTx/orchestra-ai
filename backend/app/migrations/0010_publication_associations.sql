-- Persist publication provenance in the same transaction as scheduling reconciliation.
CREATE FUNCTION link_project_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.publication_workflow_id IS NOT NULL THEN
 INSERT INTO execution_links(workflow_id,project_id,work_id,project_name,purpose,record_kind)
 SELECT NEW.publication_workflow_id,NEW.project_id,NEW.id,p.name,'publication',p.record_kind
 FROM projects p WHERE p.id=NEW.project_id ON CONFLICT(workflow_id) DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER project_publication_link AFTER INSERT OR UPDATE OF publication_workflow_id ON project_work
 FOR EACH ROW EXECUTE FUNCTION link_project_publication();
INSERT INTO execution_links(workflow_id,project_id,work_id,project_name,purpose,record_kind)
 SELECT w.publication_workflow_id,w.project_id,w.id,p.name,'publication',p.record_kind
 FROM project_work w JOIN projects p ON p.id=w.project_id WHERE w.publication_workflow_id IS NOT NULL
 ON CONFLICT DO NOTHING;
