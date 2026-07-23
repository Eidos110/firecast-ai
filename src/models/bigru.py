"""
BiGRU model module for FireCast.
Provides functions to load and run Bidirectional GRU predictions with Attention.

Lazy-torch policy: this module does NOT import torch at top level so that on
Railway/HF Spaces (where torch's native deps may be blocked by exec-stack
policy) importing ``src.models.bigru`` cannot crash the host process. torch
is bound lazily via :mod:`src.utils.lazy` on first use.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.lazy import get_torch, require_torch

logger = logging.getLogger(__name__)


# ── Module-level torch binding cache ────────────────────────────────────
_Torch = None
_NN = None
_Attention = None
_BiGRUWithAttention = None


def _build_classes(torch, nn):
    """Build the torch-backed classes inside a factory so importing this
    module does not require torch. Returns a 2-tuple ``(Attention, BiGRU)``.
    Subclassing ``nn.Module`` requires torch at definition time.
    """

    class Attention(nn.Module):
        """Attention mechanism for BiGRU."""

        def __init__(self, hidden_dim: int):
            super().__init__()
            self.attention = nn.Linear(hidden_dim * 2, 1)

        def forward(self, gru_output: torch.Tensor) -> torch.Tensor:
            attn_weights = torch.softmax(self.attention(gru_output), dim=1)
            return torch.sum(attn_weights * gru_output, dim=1)

    class BiGRUWithAttention(nn.Module):
        """Bidirectional GRU model with Attention for fire risk prediction."""

        def __init__(
            self,
            input_dim: int,
            hidden1: int = 64,
            hidden2: int = 32,
            dropout_rate: float = 0.33,
        ):
            super().__init__()

            # First BiGRU layer
            self.gru1 = nn.GRU(
                input_size=input_dim,
                hidden_size=hidden1,
                num_layers=1,
                batch_first=True,
                bidirectional=True,
            )
            self.dropout1 = nn.Dropout(dropout_rate)

            # Second BiGRU layer
            self.gru2 = nn.GRU(
                input_size=hidden1 * 2,
                hidden_size=hidden2,
                num_layers=1,
                batch_first=True,
                bidirectional=True,
            )
            self.dropout2 = nn.Dropout(dropout_rate)

            # Attention mechanism
            self.attention = Attention(hidden2)

            # Dense layers (matching the saved model architecture)
            self.dense = nn.Sequential(
                nn.Linear(hidden2 * 2, 64),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.Dropout(dropout_rate),
                nn.Linear(64, 32),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.Dropout(dropout_rate),
            )

            # Output layer
            self.output = nn.Linear(32, 1)

        def forward(self, x: torch.Tensor, return_embedding: bool = False) -> torch.Tensor:
            """Forward pass.

            Args:
                x: Input tensor of shape (batch, seq_len, features)
                return_embedding: If True, return dense embeddings instead of logits

            Returns:
                logits or embeddings depending on return_embedding
            """
            out1, _ = self.gru1(x)
            out1 = self.dropout1(out1)

            out2, _ = self.gru2(out1)
            out2 = self.dropout2(out2)

            # Apply attention
            attn_out = self.attention(out2)

            # Dense layers
            dense_out = self.dense(attn_out)

            # Output
            logits = self.output(dense_out).squeeze(1)

            return dense_out if return_embedding else logits

    return Attention, BiGRUWithAttention


def _ensure_classes():
    """Lazily bind torch + build the torch-backed classes once. Safe to call
    repeatedly; uses the cached ``_Torch`` / ``_NN`` / class objects.
    """
    global _Torch, _NN, _Attention, _BiGRUWithAttention
    if _BiGRUWithAttention is not None:
        return _Torch, _NN, _Attention, _BiGRUWithAttention
    torch, nn = require_torch()
    _Torch, _NN = torch, nn
    _Attention, _BiGRUWithAttention = _build_classes(torch, nn)
    return _Torch, _NN, _Attention, _BiGRUWithAttention


def get_torch_and_nn():
    """Backward-compat accessor: returns ``(torch, nn)`` tuple."""
    return get_torch()


# Alias for backward compatibility. Resolved lazily via __getattr__ below
# because defining it at import time would require torch.
def __getattr__(name):  # PEP 562
    if name == "BiGRUWithAttention":
        _, _, _, cls = _ensure_classes()
        return cls
    if name == "BiGRUModel":
        _, _, _, cls = _ensure_classes()
        return cls
    if name == "Attention":
        _, _, att, _ = _ensure_classes()
        return att
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_bigru_model(
    input_dim: int,
    model_path: str | Path,
    hidden1: int = 64,
    hidden2: int = 32,
    dropout_rate: float = 0.33,
    device: Optional["object"] = None,
):
    """Load BiGRU model from .pth file.

    Args:
        input_dim: Number of input features
        model_path: Path to the .pth model file
        hidden1: First hidden layer size
        hidden2: Second hidden layer size
        dropout_rate: Dropout rate
        device: PyTorch device (optional; defaults to CPU/CUDA auto-detect)

    Returns:
        Loaded BiGRU model (BiGRUWithAttention instance)

    Raises:
        RuntimeError: if torch is unavailable on this worker.
        FileNotFoundError: if the model file does not exist.
        ValueError: if the state_dict cannot be loaded.
    """
    torch, nn, _, BiGRU = _ensure_classes()
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"BiGRU model not found at: {model_path}")

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    try:
        model = BiGRU(
            input_dim=input_dim,
            hidden1=hidden1,
            hidden2=hidden2,
            dropout_rate=dropout_rate,
        )
        # weights_only=True first (defence against malicious checkpoints), fall
        # back to False for legacy serialisations the strict loader rejects.
        try:
            state_dict = torch.load(model_path, map_location=device, weights_only=True)
        except Exception:
            state_dict = torch.load(model_path, map_location=device, weights_only=False)
        model.load_state_dict(state_dict)
        model.to(device)
        model.eval()
        logger.info(f"BiGRU model loaded from {model_path}")
        return model
    except Exception as e:
        raise ValueError(f"Failed to load BiGRU model: {e}")


def predict_bigru(
    model,
    X: np.ndarray,
    device: Optional["object"] = None,
    seq_len: int = 7,
) -> np.ndarray:
    """Run prediction using BiGRU model.

    Args:
        model: Loaded BiGRU model
        X: Input features (n_samples, n_features) or (n_samples, seq_len, n_features)
        device: PyTorch device
        seq_len: Sequence length expected by model (default 7)

    Returns:
        Array of predictions (probabilities), shape (n_samples,)

    Note:
        Previously this function injected ``np.random.randn`` noise to fake
        temporal variation when a 2-D input was repeated to a 3-D sequence.
        That made predictions stochastic per call (non-reproducible) and could
        bias fire-risk scoring. We now deterministically broadcast the input
        to ``(n_samples, seq_len, n_features)``. The trained GRU handles the
        repeated context just as it would any other sequence.
    """
    torch, _, _, _ = _ensure_classes()

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()

    # Handle different input shapes — DETERMINISTIC, no noise injection.
    if X.ndim == 2:
        n_samples, n_features = X.shape
        # Broadcast 2-D -> (n_samples, seq_len, n_features) by repeating the
        # current snapshot across the time axis. This matches the inference
        # contract when no historical lags are available and is reproducible.
        X_seq = np.broadcast_to(X[:, np.newaxis, :], (n_samples, seq_len, n_features)).copy()
        X = X_seq
        logger.debug(
            f"BiGRU input expanded from (n={n_samples}, f={n_features}) "
            f"to {X.shape} (deterministic broadcast)"
        )
    elif X.ndim == 1:
        # Single sample as 1D array - create 3D via broadcast
        X = np.broadcast_to(X[np.newaxis, np.newaxis, :], (1, seq_len, X.shape[0])).copy()

    try:
        with torch.no_grad():
            X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
            logits = model(X_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()

        logger.debug(f"BiGRU raw logits: {logits}, probs: {probs}")

        return probs.flatten()

    except Exception as e:
        logger.warning(f"BiGRU prediction error: {e}")
        raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        model_path = sys.argv[1]
        input_dim = int(sys.argv[2]) if len(sys.argv) > 2 else 79

        model = load_bigru_model(input_dim, model_path)
        logger.info(f"Model loaded: {type(model)}")

        if len(sys.argv) > 3:
            import json

            X_test = np.array([json.loads(sys.argv[3])])
            prob = predict_bigru(model, X_test)
            logger.info(f"Prediction: {prob}")
