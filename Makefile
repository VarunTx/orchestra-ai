.PHONY: setup up down test test-db typecheck build smoke browser recovery
setup:
	python3 scripts/setup_env.py
up: setup
	docker compose up -d --build --wait --wait-timeout 240
down:
	docker compose down
# Fast host-side suite. Database-backed tests report as skipped unless DATABASE_URL is set.
test:
	PYTHONPATH=backend .venv/bin/pytest backend/tests -q
	npm --prefix frontend run typecheck
# Complete suite, including persistence, monitoring and incident tests, inside the Compose network.
test-db:
	docker compose run --rm --no-deps -v "$$PWD/backend:/app" api python -m pytest tests -q
typecheck:
	npm --prefix frontend run typecheck
build:
	npm --prefix frontend run build
smoke:
	.venv/bin/python scripts/smoke.py
browser:
	npm --prefix frontend run test:e2e
recovery:
	.venv/bin/python scripts/recovery.py
