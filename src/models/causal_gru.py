"""
Causal GRU model module for FireCast.
Provides functions to load and run Causal (uni-directional) GRU predictions with Attention.
This model uses only past information (strictly causal) for real-time inference.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.lazy import require_torch

logger = logging.getLogger(__name__)


# ── Module-level torch binding cache ────────────────────────────────────
_Torch = None
_NN = None
_TemporalAttention = None
_FocalLoss = None
_CausalGRUWithAttention = None


def _build_classes(torch, nn):
    """Construct the torch-backed classes INSIDE a factory so that ``import`` of
    this module does not require torch. Returns a 4-tuple of classes.

    Each class subclasses ``nn.Module`` directly (torch is required to define
    any ``nn.Module`` subclass), so the classes themselves are lazily built on
    the first call that needs them (load / predict).
    """

    class TemporalAttention(nn.Module):
        """Temporal attention mechanism for Causal GRU."""

        def __init__(self, hidden_dim: int):
            super().__init__()
            self.W = nn.Linear(hidden_dim, hidden_dim)
            self.v = nn.Linear(hidden_dim, 1, bias=False)

        def forward(self, gru_output: torch.Tensor) -> torch.Tensor:
            energy = torch.tanh(self.W(gru_output))
            attention_scores = self.v(energy).squeeze(-1)  # (batch, seq_len)
            attn_weights = torch.softmax(attention_scores, dim=1)
            context = torch.bmm(attn_weights.unsqueeze(1), gru_output).squeeze(1)
            return context

    class FocalLoss(nn.Module):
        """Focal Loss for addressing class imbalance."""

        def __init__(self, alpha: float = 0.25, gamma: float = 2.0):
            super().__init__()
            self.alpha = alpha
            self.gamma = gamma

        def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
            inputs = inputs.squeeze(-1) if inputs.ndim > 1 else inputs
            bce_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                inputs, targets, reduction="none"
            )
            pt = torch.exp(-bce_loss)
            alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
            return (alpha_t * (1 - pt) ** self.gamma * bce_loss).mean()

    class CausalGRUWithAttention(nn.Module):
        """Causal (uni-directional) GRU with Attention for fire risk prediction.

        Architecture:
            - 2-layer uni-directional GRU (strict causal flow, no future info)
            - Temporal attention over sequence
            - Dense layers with BatchNorm and Dropout
            - Single logit output for binary classification
        """

        def __init__(
            self,
            input_dim: int,
            hidden1: int = 64,
            dropout_rate: float = 0.3,
        ):
            super().__init__()
            self.gru = nn.GRU(
                input_dim,
                hidden1,
                num_layers=2,
                batch_first=True,
                dropout=dropout_rate,
                bidirectional=False,
            )
            self.attention = TemporalAttention(hidden1)
            self.dense = nn.Sequential(
                nn.Linear(hidden1 * 2, 64),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.Dropout(dropout_rate),
                nn.Linear(64, 32),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.Dropout(dropout_rate),
            )
            self.output = nn.Linear(32, 1)

        def forward(self, x: torch.Tensor, return_embedding: bool = False) -> torch.Tensor:
            gru_out, _ = self.gru(x)
            context = self.attention(gru_out)
            last_timestep_out = gru_out[:, -1, :]
            combined = torch.cat((context, last_timestep_out), dim=1)
            dense_out = self.dense(combined)
            logits = self.output(dense_out).squeeze(1)
            return dense_out if return_embedding else logits

    return TemporalAttention, FocalLoss, CausalGRUWithAttention


def _ensure_classes():
    """Build (and cache) the torch-backed classes on first use.

    Returns ``(torch, nn, CausalGRUWithAttention)``. Raises RuntimeError if
    torch is unavailable — callers must propagate that as a model-load error
    (never a silent 0.5 fallback, per AGENTS §3).
    """
    global _Torch, _NN, _TemporalAttention, _FocalLoss, _CausalGRUWithAttention
    if _CausalGRUWithAttention is not None:
        return _Torch, _NN, _CausalGRUWithAttention
    _Torch, _NN = require_torch()
    _TemporalAttention, _FocalLoss, _CausalGRUWithAttention = _build_classes(_Torch, _NN)
    return _Torch, _NN, _CausalGRUWithAttention


def __getattr__(name):
    # Expose the top-level class names for callers that do
    # ``from src.models.causal_gru import CausalGRUWithAttention``. These are
    # resolved lazily on first attribute access (after torch has been loaded)
    # so importing this module never triggers the torch import.
    if name in ("CausalGRUWithAttention", "TemporalAttention", "FocalLoss"):
        _, _, _ = _ensure_classes()
        if name == "CausalGRUWithAttention":
            return _CausalGRUWithAttention
        if name == "TemporalAttention":
            return _TemporalAttention
        return _FocalLoss
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_causal_gru_model(
    input_dim: int,
    model_path: str | Path,
    hidden1: int = 64,
    dropout_rate: float = 0.3,
    device: Optional["object"] = None,
) -> "CausalGRUWithAttention":
    """Load Causal GRU model from .pth file.

    Args:
        input_dim: Number of input features (should match raw_features count, typically 19)
        model_path: Path to the .pth model file
        hidden1: GRU hidden layer size (default 64)
        dropout_rate: Dropout rate (default 0.3)
        device: PyTorch device

    Returns:
        Loaded CausalGRUWithAttention model in eval mode

    Raises:
        RuntimeError: If PyTorch is unavailable.
        FileNotFoundError: If model file missing.
    """
    torch, nn, cls = _ensure_classes()
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"Causal GRU model not found at: {model_path}")

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    try:
        model = cls(
            input_dim=input_dim,
            hidden1=hidden1,
            dropout_rate=dropout_rate,
        )
        # weights_only=True: reject arbitrary pickle (defence against malicious
        # checkpoints). Legacy state_dicts are pure Tensor leaves, so the
        # restricted loader accepts them; we fall back to weights_only=False
        # only if the strict loader rejects the file (older format quirk).
        try:
            state_dict = torch.load(model_path, map_location=device, weights_only=True)
        except Exception:
            state_dict = torch.load(model_path, map_location=device, weights_only=False)
        model.load_state_dict(state_dict)
        model.to(device)
        model.eval()
        logger.info(f"Causal GRU model loaded from {model_path}")
        return model
    except Exception as e:
        raise ValueError(f"Failed to load Causal GRU model: {e}")


def predict_causal_gru(
    model: "CausalGRUWithAttention",
    X: np.ndarray,
    scaler_raw,
    raw_feature_indices: list,
    device: Optional["object"] = None,
    seq_len: int = 7,
) -> np.ndarray:
    """Run prediction using Causal GRU model.

    IMPORTANT: The Causal GRU requires raw (unengineered) features only and
    internally creates temporal sequences. This function handles:
    1. Selecting only raw features from the full feature set
    2. Scaling raw features using the provided scaler_raw
    3. Creating sequences of length seq_len (causal: using only past)
    4. Returning probabilities for each input row

    For single-sample inputs (n_samples < seq_len), a synthetic sequence is created
    by repeating the sample seq_len times. This represents "no change" over the
    past days and allows GRU prediction even without historical data.

    Args:
        model: Loaded CausalGRUWithAttention model
        X: Input features (n_samples, n_total_features) - ALL engineered features
        scaler_raw: Fitted StandardScaler for raw features only
        raw_feature_indices: List of column indices in X that correspond to raw features
        device: PyTorch device
        seq_len: Sequence length for GRU (default 7)

    Returns:
        Array of probabilities:
        - If n_samples >= seq_len: length = n_samples - seq_len + 1
        - If n_samples < seq_len (synthesized): length = 1
    """
    torch, _, _ = _ensure_classes()
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()

    # Extract only raw features and scale them
    X_raw = X[:, raw_feature_indices]
    X_raw_scaled = scaler_raw.transform(X_raw)

    n_samples = X_raw_scaled.shape[0]

    if n_samples < seq_len:
        logger.info(
            f"Input has {n_samples} sample(s) < seq_len={seq_len}. "
            f"Synthesizing sequence by repeating last sample."
        )
        last_sample = X_raw_scaled[-1:]
        X_raw_scaled = np.repeat(last_sample, seq_len, axis=0)
        n_samples = seq_len

    # Vectorised sliding-window construction (ROADMAP §2-G).
    #
    # The naive loop ``for i in range(...): X_seq[i] = X_raw[i:i+seq_len]``
    # costs O(n_windows * seq_len * n_features) Python-level slice-and-copy
    # calls — ~100 ms for a 500-cell AOI on CPU. ``sliding_window_view``
    # creates a strided *view* of the underlying contiguous buffer instead
    # of materialising ``n_windows`` separate slices, yielding a bitwise-
    # identical tensor at a fraction of the cost.
    #
    # ``sliding_window_view(X, (seq_len, n_features))`` on a
    # ``(n_samples, n_features)`` input returns a view of shape
    # ``(n_samples - seq_len + 1, 1, seq_len, n_features)``; we drop the
    # singleton feature-axis to obtain the (n_windows, seq_len, n_features)
    # layout the GRU expects.
    from numpy.lib.stride_tricks import sliding_window_view

    n_features = X_raw_scaled.shape[1]
    X_seq = sliding_window_view(X_raw_scaled, (seq_len, n_features))
    # Shape: (n_windows, 1, seq_len, n_features) -> squeeze axis 1.
    X_seq = np.ascontiguousarray(X_seq[:, 0], dtype=np.float32)
    n_windows = n_samples - seq_len + 1
    # Sanity: sliding-window count must match the old Python-loop count.
    assert X_seq.shape[0] == n_windows, (
        f"sliding_window_view produced {X_seq.shape[0]} windows, "
        f"expected {n_windows} (n_samples={n_samples}, seq_len={seq_len})"
    )

    X_tensor = torch.tensor(X_seq, dtype=torch.float32).to(device)

    try:
        with torch.no_grad():
            logits = model(X_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()

        logger.debug(
            f"Causal GRU: input {X.shape} -> raw {X_raw.shape} -> seq {X_seq.shape} -> output {probs.shape}"
        )
        return probs.flatten()

    except Exception as e:
        logger.error(f"Causal GRU prediction error: {e}")
        raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        model_path = sys.argv[1]
        input_dim = int(sys.argv[2]) if len(sys.argv) > 2 else 19

        device = _ensure_classes()[0].device(
            "cuda" if _ensure_classes()[0].cuda.is_available() else "cpu"
        )
        model = load_causal_gru_model(input_dim, model_path, device=device)
        logger.info(f"Model loaded: {type(model)}")
        logger.info(f"Device: {device}")
        logger.info(f"Input dimension: {input_dim}")

        if len(sys.argv) > 3:
            import json

            X_test = np.array([json.loads(sys.argv[3])], dtype=float)
            # Identity scaler (mean=0, std=1) — bug #4 historically was passing
            # None here which caused AttributeError on scaler.transform().
            from sklearn.preprocessing import StandardScaler

            dummy_scaler = StandardScaler()
            dummy_scaler.mean_ = np.zeros(input_dim)
            dummy_scaler.scale_ = np.ones(input_dim)
            dummy_scaler.var_ = np.ones(input_dim)
            dummy_scaler.n_features_in_ = input_dim
            prob = predict_causal_gru(model, X_test, dummy_scaler, list(range(input_dim)))
            logger.info(f"Prediction shape: {prob.shape}")
            logger.info(f"Prediction: {prob[:5]}")
