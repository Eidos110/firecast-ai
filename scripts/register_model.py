#!/usr/bin/env python
"""
FireCast Model Registration Script
Register new model versions with the registry.
"""

import argparse
import json
import sys
from pathlib import Path

from src.models import registry
from src.database import init_db, get_engine
from src.predict import load_ensemble_models


def main():
    parser = argparse.ArgumentParser(
        description="Register a new model version with the FireCast registry"
    )
    parser.add_argument(
        "--model", required=True, choices=["cnn", "lgbm"], help="Model name"
    )
    parser.add_argument(
        "--version", required=True, help="Version string (e.g., v1.0.0)"
    )
    parser.add_argument("--path", required=True, help="Path to model file")
    parser.add_argument(
        "--metrics",
        type=str,
        help="Path to performance metrics JSON file (optional)",
    )
    parser.add_argument(
        "--metadata",
        type=str,
        help="Path to metadata JSON file (optional)",
    )
    args = parser.parse_args()

    # Load metrics and metadata if provided
    metrics = None
    metadata = None
    if args.metrics:
        try:
            with open(args.metrics, "r") as f:
                metrics = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load metrics file: {e}")
    if args.metadata:
        try:
            with open(args.metadata, "r") as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load metadata file: {e}")

    # Register the model version
    success = registry.register_model_version(
        model_name=args.model,
        version=args.version,
        file_path=args.path,
        performance_metrics=metrics,
        metadata=metadata,
    )

    if success:
        print(f"✅ Successfully registered {args.model} version {args.version}")
        # Set as active version
        from src.models.registry import activate_model_version

        if activate_model_version(args.model, args.version):
            print(f"✅ Successfully activated {args.model} version {args.version}")
        else:
            print(f"⚠️ Warning: Could not activate {args.model} version {args.version}")
    else:
        print(f"❌ Failed to register {args.model} version {args.version}")
        sys.exit(1)


if __name__ == "__main__":
    main()
