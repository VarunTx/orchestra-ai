.PHONY: setup up down test smoke browser recovery
setup:
	python3 scripts/setup_env.py
up: setup
	docker compose up -d --build --wait --wait-timeout 180
down:
	docker compose down
test:
	PYTHONPATH=backend .venv/bin/pytest backend/tests -q
	npm --prefix frontend run typecheck
smoke:
	.venv/bin/python scripts/smoke.py
browser:
	npm --prefix frontend run test:e2e
recovery:
	.venv/bin/python scripts/recovery.py
