#!/usr/bin/env python3
"""
Training script untuk FireCast
Script ini melakukan data preparation, feature engineering, dan training model
Jalankan notebook 03_ensemble_cnn+lgbm.ipynb untuk training lengkap
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("""
╔═══════════════════════════════════════════════════════╗
║        FireCast Training Pipeline                     ║
╚═══════════════════════════════════════════════════════╝

Untuk training model, silakan jalankan notebook:
  - 01_feature_engineering.ipynb      (Data preparation)
  - 02_cnn1d_baseline.ipynb           (CNN baseline)
  - 03_ensemble_cnn+lgbm.ipynb        (Ensemble training)
  - 04_hyperparameter_tuning.ipynb    (Hyperparameter tuning)

Atau jalankan secara berurutan dari Jupyter:
  jupyter notebook
""")
