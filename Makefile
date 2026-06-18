# FireCast Makefile
# Usage: make <target>
# Run `make help` for the full command list.

.PHONY: help setup dev api both build-frontend build-all clean \
        up up-frontend up-api up-dev down logs \
        test lint format check deploy-staging deploy-prod \
        react-build react-dev react-preview

# ── Help ────────────────────────────────────────────────────────────────
help:
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║  FireCast – Available Commands                                  ║"
	@echo "╠══════════════════════════════════════════════════════════════════╣"
	@echo "║  setup             Install all Python & Node dependencies       ║"
	@echo "║  dev               Run Streamlit frontend (dev mode)            ║"
	@echo "║  api               Run FastAPI backend (dev mode)               ║"
	@echo "║  both              Run frontend + API together                   ║"
	@echo "║  build-frontend    Build React map component (frontend_react)    ║"
	@echo "║  build-all         Build all Docker images                       ║"
	@echo "║  up                Start frontend + API (Docker Compose)        ║"
	@echo "║  up-frontend       Start frontend only (Docker Compose)         ║"
	@echo "║  up-api            Start API only (Docker Compose)              ║"
	@echo "║  up-dev            Start dev environment with live mounts       ║"
	@echo "║  up-prod           Start all incl. nginx (production profile)   ║"
	@echo "║  down              Stop all Docker Compose services              ║"
	@echo "║  logs              Tail logs for all services                    ║"
	@echo "║  test              Run the pytest test suite                    ║"
	@echo "║  lint              Run flake8 + mypy linters                     ║"
	@echo "║  format            Format code (black + isort)                  ║"
	@echo "║  check             Run lint + test (CI-style check)             ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"

# ── Setup ───────────────────────────────────────────────────────────────
setup:
	@echo ">>> Installing Python dependencies …"
	pip install --upgrade pip
	pip install -r requirements.txt -r requirements-frontend.txt -r requirements-api.txt -r requirements-dev.txt
	@echo ">>> Installing Node dependencies …"
	cd frontend_react && npm ci
	@echo ">>> Setup complete. Copy .env.example → .env and fill in your API keys."

# ── Local Dev Commands ──────────────────────────────────────────────────
dev:
	@echo ">>> Starting Streamlit frontend on http://localhost:8501 …"
	streamlit run frontend/app.py

api:
	@echo ">>> Starting FastAPI backend on http://localhost:8000 …"
	uvicorn src.geo_api:app --reload --host 0.0.0.0 --port 8000

both:
	@echo ">>> Starting frontend + API …"
	python launch_prototype.py --mode both

# ── React Build ─────────────────────────────────────────────────────────
react-build:
	@echo ">>> Building React map component …"
	cd frontend_react && npm run build
	@echo ">>> Build artifacts in frontend_react/build/"

react-dev:
	@echo ">>> Starting React dev server on http://localhost:3000 …"
	cd frontend_react && npm run dev

react-preview:
	@echo ">>> Previewing built React component …"
	cd frontend_react && npm run preview

# ── Docker Commands ─────────────────────────────────────────────────────
build-all:
	@echo ">>> Building all Docker images …"
	docker-compose build

build-frontend:
	@echo ">>> Building frontend Docker image …"
	docker build --target frontend -t firecast-frontend:latest .

build-api:
	@echo ">>> Building API Docker image …"
	docker build --target api -t firecast-api:latest .

up:
	@echo ">>> Starting frontend + API services …"
	docker-compose up -d

up-frontend:
	@echo ">>> Starting frontend only …"
	docker-compose up -d frontend

up-api:
	@echo ">>> Starting API only …"
	docker-compose up -d api

up-dev:
	@echo ">>> Starting dev environment …"
	docker-compose up -d dev

up-prod:
	@echo ">>> Starting production stack (with nginx) …"
	docker-compose --profile production up -d

down:
	@echo ">>> Stopping all services …"
	docker-compose down

logs:
	@echo ">>> Tailing logs (frontend + API) …"
	docker-compose logs -f --tail=200

logs-frontend:
	@echo ">>> Tailing frontend logs …"
	docker-compose logs -f frontend

logs-api:
	@echo ">>> Tailing API logs …"
	docker-compose logs -f api

clean:
	@echo ">>> Removing containers, networks, volumes …"
	docker-compose down -v --remove-orphans
	docker system prune -f

# ── Health Checks ───────────────────────────────────────────────────────
health:
	@echo ">>> Frontend  → $$(curl -sf http://localhost:8501/_stcore/health || echo FAIL)"
	@echo ">>> API       → $$(curl -sf http://localhost:8000/health        || echo FAIL)"

# ── Testing / Linting ───────────────────────────────────────────────────
test:
	@echo ">>> Running pytest …"
	pytest tests/ -v --tb=short

lint:
	@echo ">>> Running flake8 …"
	flake8 src/ frontend/ tests/ --max-line-length=120 --show-source --statistics
	@echo ">>> Running mypy …"
	mypy src/ --ignore-missing-imports --no-error-summary

format:
	@echo ">>> Formatting with black + isort …"
	black src/ frontend/ tests/
	isort src/ frontend/ tests/

check: lint test

# ── CI / CD ─────────────────────────────────────────────────────────────
deploy-staging:
	@echo ">>> Pushing to staging …"
	@echo ">>> Add your CI/CD SSH deployment script here."
	@echo ">>> See plan section 6.2 for GitHub Actions workflow."

deploy-prod:
	@echo ">>> Prod deployment – manual trigger required."
	@echo ">>> Run: gh workflow run deploy.yml -f environment=production"
