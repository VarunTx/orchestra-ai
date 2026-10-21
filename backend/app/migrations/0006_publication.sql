ALTER TABLE project_work ADD COLUMN publication_workflow_id text;
ALTER TABLE project_work ADD COLUMN publication_task_id text;
ALTER TABLE project_work ADD COLUMN publication_submission text NOT NULL DEFAULT 'draft';
ALTER TABLE project_work ADD COLUMN model_budget_seconds integer NOT NULL DEFAULT 600 CHECK(model_budget_seconds BETWEEN 30 AND 3600);
