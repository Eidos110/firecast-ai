#!/usr/bin/env python3
"""
FireCast Launcher
=================
Unified launcher for the **single-service** (FastAPI API + React SPA) app.

Usage:
    python launch_prototype.py                    # Serve API + built React SPA
    python launch_prototype.py --mode api         # Serve API only (no SPA mount)
    python launch_prototype.py --mode test        # Run the backend test suite

Options:
    --mode MODE         Mode to run (app, api, test) [default: app]
    --port PORT         Port to bind (default: 7860)
    --host HOST         Host to bind (default: 0.0.0.0)
    --debug             Enable debug logging

Post-React-SPA migration the old Streamlit frontend is retired. There is no
separate frontend process anymore: ``mode=app`` serves the React build from
``frontend_react/build`` (when present) through FastAPI, exactly like
``start_api.py``. To work on the frontend with hot-module-reload, run the Vite
dev server instead:

    cd frontend_react && npm run dev            # http://localhost:3000
"""

import argparse
import importlib.util
import logging
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


# Setup logging
def setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def check_environment():
    """Check if environment is properly configured."""
    issues = []

    # pyproject.toml already enforces requires-python = ">=3.10" at install
    # time, so no inline version block is needed here (ruff UP036).

    # Check for .env file
    if not (project_root / ".env").exists():
        issues.append(".env file not found. Copy .env.example to .env and configure it.")

    # Check for required directories
    required_dirs = ["data", "models", "src"]
    for dir_name in required_dirs:
        if not (project_root / dir_name).exists():
            issues.append(f"Required directory '{dir_name}' not found")

    # Check for model files — missing ones only break inference at request time.
    model_files = ["lgb_model.pkl", "xgb_model.pkl", "scaler_all.pkl"]
    models_dir = project_root / "add_new_model"
    if models_dir.exists():
        missing_models = [f for f in model_files if not (models_dir / f).exists()]
        if missing_models:
            print(f"! Warning: Missing V4.2 model files: {', '.join(missing_models)}")
            print("  /predict will return an error until the bundle is restored.")

    return issues


def run_app(host: str = "0.0.0.0", port: int = 7860):
    """Serve the FastAPI API together with the built React SPA.

    This proxies to ``start_api.py`` so demo-mode auto-detection, the SPA
    history-mode fallback, and the model-bundle checks stay in one place.
    """
    logger.info("Starting FireCast (FastAPI + React SPA) on http://%s:%s", host, port)
    env = os.environ.copy()
    env["API_HOST"] = host
    env["PORT"] = str(port)
    try:
        subprocess.run([sys.executable, str(project_root / "start_api.py")], env=env, check=True)
    except KeyboardInterrupt:
        logger.info("App stopped by user")
    except subprocess.CalledProcessError as e:
        logger.error("App error: %s", e)
        sys.exit(1)


def run_api(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server alone (no SPA mount)."""
    logger.info("Starting FireCast API (FastAPI) on http://%s:%s", host, port)

    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    try:
        uvicorn.run("src.geo_api:app", host=host, port=port, reload=False, log_level="info")
    except KeyboardInterrupt:
        logger.info("API stopped by user")


def run_tests():
    """Run the backend test suite."""
    logger.info("Running FireCast Tests...")

    if importlib.util.find_spec("pytest") is None:
        logger.error("pytest not installed. Run: pip install pytest pytest-cov")
        sys.exit(1)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--strict-markers"]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Tests failed: %s", e)
        sys.exit(1)


def print_banner():
    """Print startup banner."""
    banner = """
    +---------------------------------------------------------------+
    |                                                               |
    |   FireCast - Fire Risk Prediction System                      |
    |                                                               |
    |   Version: 4.0.0 (Single-service: FastAPI + React SPA)        |
    |                                                               |
    +---------------------------------------------------------------+
    """
    print(banner)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FireCast Launcher (FastAPI + React SPA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch_prototype.py                    # Serve API + built React SPA on :7860
  python launch_prototype.py --mode api         # Serve API only on :8000
  python launch_prototype.py --mode test        # Run the backend tests

Frontend dev (hot-module-reload):
  cd frontend_react && npm run dev              # http://localhost:3000
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["app", "api", "test"],
        default="app",
        help="Mode to run (default: app = API + React SPA)",
    )
    parser.add_argument(
        "--port", type=int, help="Port to bind (default: 7860 for app, 8000 for api)"
    )
    parser.add_argument("--host", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Setup logging
    global logger
    logger = setup_logging(args.debug)

    # Print banner
    print_banner()

    # Check environment
    logger.info("Checking environment...")
    issues = check_environment()

    if issues:
        print("\n! Environment Issues Found:")
        for issue in issues:
            print(f"   - {issue}")
        print()

        # Ask user if they want to continue
        if args.mode != "test":
            response = input("Continue anyway? [y/N]: ")
            if response.lower() != "y":
                sys.exit(1)

    # Run in selected mode
    host = args.host or "0.0.0.0"
    try:
        if args.mode == "app":
            port = args.port or 7860
            print(f"\n>> App URL: http://localhost:{port}")
            print(">> Press Ctrl+C to stop\n")
            run_app(host, port)

        elif args.mode == "api":
            port = args.port or 8000
            print(f"\n>> API URL: http://localhost:{port}")
            print(f">> API Docs: http://localhost:{port}/docs")
            print(">> Press Ctrl+C to stop\n")
            run_api(host, port)

        elif args.mode == "test":
            run_tests()

    except Exception as e:
        logger.error("Error: %s", e)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
