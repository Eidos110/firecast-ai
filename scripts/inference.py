#!/usr/bin/env python3
"""
Inference script untuk FireCast
Melakukan prediksi pada data baru menggunakan model ensemble
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.predict import main

if __name__ == "__main__":
    main()
