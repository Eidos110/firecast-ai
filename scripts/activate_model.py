#!/usr/bin/env python
"""
FireCast Model Activation Script
Activate a specific model version.
"""

import argparse
from src.models import registry


def main():
    parser = argparse.ArgumentParser(description="Activate a model version")
    parser.add_argument(
        "--model", required=True, choices=["cnn", "lgbm"], help="Model name"
    )
    parser.add_argument("--version", required=True, help="Version string to activate")

    args = parser.parse_args()

    if registry.activate_model_version(args.model, args.version):
        print(f"✅ Successfully activated {args.model} version {args.version}")
    else:
        print(f"❌ Failed to activate {args.model} version {args.version}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
