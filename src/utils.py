import numpy as np
from sklearn.metrics import precision_recall_curve

def find_threshold_for_recall(y_true, y_prob, target_recall=0.80):
    """Mencari threshold yang memberikan recall minimal target_recall."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    idx = np.where(recall >= target_recall)[0]
    if len(idx) == 0:
        return 0.5
    best_idx = idx[np.argmax(precision[idx])]
    return thresholds[best_idx]