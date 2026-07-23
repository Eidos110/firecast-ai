"""
Probability calibration helpers (audit Fase 3a).

Extracted from ``src/predict.py`` so the CNN/LGBM "aggressive-mean-shift"
calibration lives in one place, is unit-testable, and can be tuned centrally.
The historical heuristics below were tuned empirically against the CNN
best.pth + LightGBM best.pkl shipped under ``models/`` — DO NOT change the
constants without re-evaluating against the validation set.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def calibrate_cnn_probs(cnn_probs: np.ndarray, mean: float | None = None) -> np.ndarray:
    """Apply the CNN mean-shift calibration used by the FireCast ensemble.

    The trained CNN best.pth on this dataset outputs very low slope values;
    predictions concentrate near `[0, 0.1]`. To restore usable spread:

    - If ``mean < 0.10``  -> ``p' = clip(p * 5.0 + 0.10, 0, 1)``  (maps 0..0.1 -> 0.1..0.6)
    - If ``mean < 0.25``  -> ``p' = clip(p * 2.0 + 0.10, 0, 1)``  (maps 0..0.25 -> 0.1..0.6)
    - Else                -> no shift (already well-calibrated).

    Args:
        cnn_probs: 1-D array of raw CNN probabilities in ``[0, 1]``.
        mean:      Optional precomputed mean; if ``None`` it is computed here.

    Returns:
        New 1-D ndarray, calibrated & clipped to ``[0, 1]``.
    """
    if mean is None:
        mean = float(np.mean(cnn_probs)) if len(cnn_probs) else 0.0
    logger.debug(f"calibrate_cnn_probs: input mean={mean:.6f}, n={len(cnn_probs)}")

    if mean < 0.10:
        calibrated = np.clip(cnn_probs * 5.0 + 0.10, 0.0, 1.0)
        logger.info(
            f"CNN AGGRESSIVE CALIBRATED (mean<0.10): input={cnn_probs[:5]}, "
            f"output={calibrated[:5]}"
        )
        return calibrated
    if mean < 0.25:
        calibrated = np.clip(cnn_probs * 2.0 + 0.10, 0.0, 1.0)
        logger.info(f"CNN CALIBRATED (mean<0.25): input={cnn_probs[:5]}, output={calibrated[:5]}")
        return calibrated
    return cnn_probs


def calibrate_lgbm_probs(lgbm_probs: np.ndarray, mean: float | None = None) -> np.ndarray:
    """Apply the LightGBM mean-shift calibration used by the FireCast ensemble.

    Mirrors the historical branch in ``predict_batch``:

    - If ``mean > 0.75`` -> pull extreme-high tail toward 0.5 favoring
      ``0.5 + (p - 0.5) * 0.7`` for ``p > 0.5`` and ``p * 0.85`` otherwise.
    - If ``mean < 0.10`` -> ``p' = clip(p * 5.0 + 0.10, 0, 1)`` (same aggressive
      expansion as CNN — keeps the two base learners on comparable scales).

    Otherwise returns the input unmodified.
    """
    if mean is None:
        mean = float(np.mean(lgbm_probs)) if len(lgbm_probs) else 0.0
    logger.debug(f"calibrate_lgbm_probs: input mean={mean:.6f}, n={len(lgbm_probs)}")

    if mean > 0.75:
        calibrated = np.where(lgbm_probs > 0.5, 0.5 + (lgbm_probs - 0.5) * 0.7, lgbm_probs * 0.85)
        calibrated = np.clip(calibrated, 0.0, 1.0)
        logger.info(f"LGBM CALIBRATED (high mean>0.75): output={calibrated[:5]}")
        return calibrated
    if mean < 0.10:
        calibrated = np.clip(lgbm_probs * 5.0 + 0.10, 0.0, 1.0)
        logger.info(f"LGBM CALIBRATED (low mean<0.10): output={calibrated[:5]}")
        return calibrated
    return lgbm_probs


def temperature_scale(probs: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Apply temperature scaling ``p -> sigmoid(logit(p) / T)``.

    For ``T > 1`` predictions soften toward 0.5 (less overconfident);
    for ``T < 1`` they sharpen. ``T == 1`` is identity.

    Args:
        probs:    1-D array in (0, 1) (endpoints are clamped inside for logit
                  stability; pure 0/1 inputs are mapped ~ to themselves).
        temperature: must be > 0.
    """
    if temperature <= 0:
        raise ValueError(f"temperature must be > 0 (got {temperature})")
    if temperature == 1.0:
        return probs
    eps = 1e-7
    p = np.clip(probs, eps, 1 - eps)
    logit = np.log(p / (1 - p))
    scaled = 1.0 / (1.0 + np.exp(-logit / temperature))
    return scaled
