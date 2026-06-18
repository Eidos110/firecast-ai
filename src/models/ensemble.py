import numpy as np
import joblib
import logging
from sklearn.metrics import roc_auc_score, classification_report
from src import config
from src.utils import find_threshold_for_recall

logger = logging.getLogger(__name__)

def evaluate_ensemble(y_test, cnn_probs, lgbm_probs, threshold=None):
    """
    Evaluasi ensemble dengan memuat threshold dari file (jika tidak diberikan).
    """
    ensemble_probs = (cnn_probs + lgbm_probs) / 2
    
    if threshold is None:
        # Muat threshold yang disimpan saat training
        threshold = joblib.load(config.THRESHOLD_PATH)
    
    ensemble_preds = (ensemble_probs > threshold).astype(int)
    
    logger.info("\n" + "="*60)
    logger.info("ENSEMBLE MODEL EVALUATION (CNN + LGBM)")
    logger.info("="*60)
    logger.info(f"AUC: {roc_auc_score(y_test, ensemble_probs):.4f}")
    logger.info(f"Using threshold: {threshold:.3f}")
    logger.info("\nClassification Report:")
    # classification_report prints to stdout; capture and log
    report = classification_report(y_test, ensemble_preds, target_names=['No Fire', 'Fire'])
    logger.info("\n" + report)
    
    return ensemble_probs, ensemble_preds