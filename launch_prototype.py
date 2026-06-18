#!/usr/bin/env python3
"""
FireCast Prototype Launcher
===========================
Unified launcher script for running FireCast in different modes.

Usage:
    python launch_prototype.py --mode frontend    # Run Streamlit frontend
    python launch_prototype.py --mode api         # Run FastAPI server
    python launch_prototype.py --mode both        # Run both frontend and API
    python launch_prototype.py --mode test        # Run tests

Options:
    --mode MODE         Mode to run (frontend, api, both, test) [default: frontend]
    --port PORT         Port to use (overrides config)
    --host HOST         Host to bind to (overrides config)
    --demo              Force demo mode
    --debug             Enable debug logging
"""

import argparse
import logging
import os
import sys
import subprocess
import threading
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup logging
def setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def check_environment():
    """Check if environment is properly configured."""
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        issues.append("Python 3.8 or higher is required")
    
    # Check for .env file
    if not (project_root / '.env').exists():
        issues.append(".env file not found. Copy .env.example to .env and configure it.")
    
    # Check for required directories
    required_dirs = ['data', 'models', 'src', 'frontend']
    for dir_name in required_dirs:
        if not (project_root / dir_name).exists():
            issues.append(f"Required directory '{dir_name}' not found")
    
    # Check for model files
    model_files = ['cnn_best.pth', 'lgbm_best.pkl', 'scaler.pkl']
    models_dir = project_root / 'models'
    if models_dir.exists():
        missing_models = [f for f in model_files if not (models_dir / f).exists()]
        if missing_models:
            print(f"⚠️  Warning: Missing model files: {', '.join(missing_models)}")
            print("   The application will run in DEMO mode.")
    
    return issues


def install_dependencies():
    """Install required dependencies."""
    logger.info("Checking dependencies...")
    
    requirements_files = [
        'requirements.txt',
        'requirements-frontend.txt',
        'requirements-api.txt'
    ]
    
    for req_file in requirements_files:
        req_path = project_root / req_file
        if req_path.exists():
            logger.info(f"Installing from {req_file}...")
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', '-q', '-r', str(req_path)
            ])


def run_frontend(port: int = None, host: str = None, demo: bool = False):
    """Run Streamlit frontend."""
    logger.info("🚀 Starting FireCast Frontend (Streamlit)...")
    
    cmd = [
        sys.executable, '-m', 'streamlit', 'run',
        str(project_root / 'frontend' / 'app.py'),
        '--server.headless=true'
    ]
    
    if port:
        cmd.extend(['--server.port', str(port)])
    if host:
        cmd.extend(['--server.address', host])
    
    env = os.environ.copy()
    if demo:
        env['ENABLE_DEMO_MODE'] = 'true'
    
    try:
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        logger.info("\n👋 Frontend stopped by user")
    except subprocess.CalledProcessError as e:
        logger.error(f"Frontend error: {e}")
        sys.exit(1)


def run_api(port: int = None, host: str = None, demo: bool = False):
    """Run FastAPI server."""
    logger.info("🚀 Starting FireCast API (FastAPI)...")
    
    # Import here to avoid loading if not needed
    try:
        import uvicorn
    except ImportError:
        logger.error("❌ uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)
    
    host = host or '0.0.0.0'
    port = port or 8000
    
    if demo:
        os.environ['ENABLE_DEMO_MODE'] = 'true'
    
    try:
        uvicorn.run(
            'src.geo_api:app',
            host=host,
            port=port,
            reload=False,
            log_level='info'
        )
    except KeyboardInterrupt:
        logger.info("\n👋 API stopped by user")


def run_both(frontend_port: int = None, api_port: int = None, demo: bool = False):
    """Run both frontend and API."""
    logger.info("🚀 Starting FireCast (Frontend + API)...")
    
    if demo:
        os.environ['ENABLE_DEMO_MODE'] = 'true'
    
    # Start API in a separate thread
    api_thread = threading.Thread(
        target=run_api,
        args=(api_port or 8000, '0.0.0.0', demo),
        daemon=True
    )
    api_thread.start()
    
    # Wait for API to start
    time.sleep(3)
    
    logger.info(f"📚 API Documentation: http://localhost:{api_port or 8000}/docs")
    
    # Start frontend (blocking)
    run_frontend(frontend_port or 8501, '0.0.0.0', demo)


def run_tests():
    """Run test suite."""
    logger.info("🧪 Running FireCast Tests...")
    
    try:
        import pytest
    except ImportError:
        logger.error("❌ pytest not installed. Run: pip install pytest pytest-cov")
        sys.exit(1)
    
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/',
        '-v',
        '--tb=short',
        '--strict-markers'
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Tests failed: {e}")
        sys.exit(1)


def print_banner():
    """Print startup banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🔥 FireCast - Fire Risk Prediction System                   ║
    ║                                                               ║
    ║   Version: 1.0.0 (Prototype)                                  ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='FireCast Prototype Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch_prototype.py                    # Run frontend only
  python launch_prototype.py --mode api         # Run API only
  python launch_prototype.py --mode both        # Run both services
  python launch_prototype.py --mode test        # Run tests
  python launch_prototype.py --demo             # Force demo mode
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['frontend', 'api', 'both', 'test'],
        default='frontend',
        help='Mode to run (default: frontend)'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='Port to use (overrides config)'
    )
    parser.add_argument(
        '--host',
        help='Host to bind to (overrides config)'
    )
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Force demo mode'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--install-deps',
        action='store_true',
        help='Install dependencies before running'
    )
    
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
        print("\n⚠️  Environment Issues Found:")
        for issue in issues:
            print(f"   - {issue}")
        print()
        
        # Ask user if they want to continue
        if args.mode != 'test':
            response = input("Continue anyway? [y/N]: ")
            if response.lower() != 'y':
                sys.exit(1)
    
    # Install dependencies if requested
    if args.install_deps:
        install_dependencies()
    
    # Run in selected mode
    try:
        if args.mode == 'frontend':
            print(f"\n🌐 Frontend URL: http://{args.host or 'localhost'}:{args.port or 8501}")
            print("⚠️  Press Ctrl+C to stop\n")
            run_frontend(args.port, args.host, args.demo)
            
        elif args.mode == 'api':
            print(f"\n🌐 API URL: http://{args.host or 'localhost'}:{args.port or 8000}")
            print(f"📚 API Docs: http://{args.host or 'localhost'}:{args.port or 8000}/docs")
            print("⚠️  Press Ctrl+C to stop\n")
            run_api(args.port, args.host, args.demo)
            
        elif args.mode == 'both':
            print(f"\n🌐 Frontend URL: http://{args.host or 'localhost'}:{args.port or 8501}")
            print(f"🌐 API URL: http://{args.host or 'localhost'}:{(args.port or 8000) + 1}")
            print(f"📚 API Docs: http://{args.host or 'localhost'}:{(args.port or 8000) + 1}/docs")
            print("⚠️  Press Ctrl+C to stop\n")
            run_both(args.port, (args.port or 8000) + 1 if args.port else 8000, args.demo)
            
        elif args.mode == 'test':
            run_tests()
            
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
