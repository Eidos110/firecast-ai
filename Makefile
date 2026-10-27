# FireCast Makefile — FastAPI + React SPA
# Run `make help` for the command list.

.PHONY: help setup app api dev test lint format check \
        react-install react-build react-dev react-test react-typecheck react-lint \
        docker-build docker-up docker-down docker-logs clean

help:
	@echo "FireCast commands"
	@echo "  setup            Install Python (dev) + Node dependencies"
	@echo "  app              Serve API + built SPA on :7860 (start_api.py)"
	@echo "  api              Serve API only on :8000 with reload"
	@echo "  dev              Vite dev server on :3000 (proxies API to :8000)"
	@echo "  test             Run the backend pytest suite"
	@echo "  lint             ruff check"
	@echo "  format           black + ruff --fix"
	@echo "  check            lint + backend tests + frontend typecheck/tests"
	@echo "  react-build      Production SPA build"
	@echo "  react-test       Vitest suite"
	@echo "  react-typecheck  tsc --noEmit"
	@echo "  react-lint       ESLint (zero warnings)"
	@echo "  docker-build     Build the single-service image"
	@echo "  docker-up        Start the compose service"
	@echo "  docker-down      Stop the compose service"
	@echo "  docker-logs      Tail compose logs"

setup:
	pip install -r requirements-dev.txt
	cd frontend_react && npm ci

app:
	python start_api.py

api:
	uvicorn src.geo_api:app --reload --host 0.0.0.0 --port 8000

dev:
	cd frontend_react && npm run dev

test:
	python -m pytest tests/ -q

lint:
	ruff check .
	black --check --diff src tests start_api.py launch_prototype.py scripts

format:
	black src tests start_api.py launch_prototype.py scripts
	ruff check --fix .

check: lint test react-typecheck react-test

# ── React SPA ───────────────────────────────────────────────────────────
react-install:
	cd frontend_react && npm ci

react-build:
	cd frontend_react && npm run build

react-dev:
	cd frontend_react && npm run dev

react-test:
	cd frontend_react && npm test

react-typecheck:
	cd frontend_react && npm run typecheck

react-lint:
	cd frontend_react && npm run lint

# ── Docker ──────────────────────────────────────────────────────────────
docker-build:
	docker build -t firecast:local .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=200

clean:
	docker compose down -v --remove-orphans
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage frontend_react/.lighthouseci
