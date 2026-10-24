UV ?= uv
NPM ?= npm

.PHONY: setup seed backend frontend dev test lint

setup:            ## install deps and seed the demo catalog
	cd backend && $(UV) sync
	cd frontend && $(NPM) install
	$(MAKE) seed

seed:             ## (re)build catalog, reference crops and CLIP vectors
	cd backend && $(UV) run python -m scripts.seed_catalog --shop demo

backend:          ## REST API on http://127.0.0.1:8000 (docs at /docs)
	cd backend && $(UV) run uvicorn app.main:app --reload --timeout-graceful-shutdown 3 --host 127.0.0.1 --port 8000

frontend:         ## PWA on http://localhost:5173 (proxies /api and /media to the backend)
	cd frontend && $(NPM) run dev

dev:              ## backend + frontend together
	$(MAKE) -j2 backend frontend

test:
	cd backend && $(UV) run pytest -q

lint:
	cd backend && $(UV) run ruff check app scripts tests
	cd frontend && $(NPM) run lint && npx tsc -b
