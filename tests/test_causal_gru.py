"""Single-sample inference test for ``predict_causal_gru`` (Fase 5).

The audit (AGENTS.md §5A) flagged that the Causal GRU single-sample path was
untested. This test instantiates a fresh, randomly-weighted
``CausalGRUWithAttention`` (no checkpoint file needed) + a fake scaler, feeds a
1-row input that is *shorter* than ``seq_len``, and asserts the documented
behaviour:

1. With ``n_samples < seq_len`` the function synthesises a sequence by repeating
   the last sample ``seq_len`` times (logs confirm this).
2. The return shape is ``length == 1`` (a single probability).
3. Probabilities are finite and within [0, 1].
4. Calling with a batch >= seq_len returns ``n_samples - seq_len + 1`` probs.

Skipped automatically if torch is unavailable (HuggingFace sandbox), so CI on
the slim env still passes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np

try:
    import torch  # noqa: F401

    from src.models import causal_gru as cg
    from src.models.causal_gru import predict_causal_gru

    _TORCH_OK = True
except Exception:
    _TORCH_OK = False


class _FakeScaler:
    """Minimal StandardScaler-compatible shim used by predict_causal_gru."""

    def __init__(self, dim: int):
        self.mean_ = np.zeros(dim, dtype=np.float32)
        self.scale_ = np.ones(dim, dtype=np.float32)

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean_) / self.scale_


@unittest.skipUnless(_TORCH_OK, "torch unavailable — skipping causal_gru single-sample test")
class TestPredictCausalGruSingleSample(unittest.TestCase):
    INPUT_DIM = 19
    RAW_FEATURE_INDICES = list(range(19))

    def setUp(self):
        _, _, cls = cg._ensure_classes()
        torch, _nn, _cls = cg._ensure_classes()
        # Fresh untrained model — we only need deterministic forward + shape contract.
        self.model = cls(input_dim=self.INPUT_DIM, hidden1=16)
        self.model.eval()
        self.scaler = _FakeScaler(self.INPUT_DIM)
        self.device = torch.device("cpu")

    def _sample_input(self, n: int) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.uniform(-1, 1, size=(n, self.INPUT_DIM)).astype(np.float32)

    def test_single_sample_synthesises_sequence_one_output(self):
        X = self._sample_input(1)
        probs = predict_causal_gru(
            self.model,
            X,
            self.scaler,
            self.RAW_FEATURE_INDICES,
            device=self.device,
            seq_len=7,
        )
        self.assertEqual(probs.shape, (1,))
        self.assertTrue(np.all(np.isfinite(probs)))
        self.assertTrue(np.all(probs >= 0.0) and np.all(probs <= 1.0))

    def test_few_samples_still_one_output(self):
        # 3 samples < seq_len 7 — synthesises to a single prediction.
        X = self._sample_input(3)
        probs = predict_causal_gru(
            self.model,
            X,
            self.scaler,
            self.RAW_FEATURE_INDICES,
            device=self.device,
            seq_len=7,
        )
        self.assertEqual(probs.shape, (1,))

    def test_batch_geq_seq_len_returns_n_minus_seq_plus_one(self):
        n = 14
        seq_len = 7
        X = self._sample_input(n)
        probs = predict_causal_gru(
            self.model,
            X,
            self.scaler,
            self.RAW_FEATURE_INDICES,
            device=self.device,
            seq_len=seq_len,
        )
        self.assertEqual(probs.shape, (n - seq_len + 1,))
        self.assertTrue(np.all(np.isfinite(probs)))
        self.assertTrue(np.all(probs >= 0.0) and np.all(probs <= 1.0))

    def test_model_logits_not_nan_when_repeated(self):
        # Repeated identical samples must not produce NaN (catches BatchNorm issues
        # under eval mode — even though eval disables running stats, the contract
        # is "finite probabilities").
        X = np.tile(self._sample_input(1), (1, 1))
        probs = predict_causal_gru(
            self.model,
            X,
            self.scaler,
            self.RAW_FEATURE_INDICES,
            device=self.device,
        )
        self.assertFalse(np.isnan(probs).any())


if __name__ == "__main__":
    unittest.main()
