"""
Causal GRU model module for FireCast.
Provides functions to load and run Causal (uni-directional) GRU predictions with Attention.
This model uses only past information (strictly causal) for real-time inference.
"""

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class TemporalAttention(nn.Module):
    """Temporal attention mechanism for Causal GRU."""

    def __init__(self, hidden_dim: int):
        super().__init__()
        self.W = nn.Linear(hidden_dim, hidden_dim)
        self.v = nn.Linear(hidden_dim, 1, bias=False)

    def forward(self, gru_output: torch.Tensor) -> torch.Tensor:
        """
        Args:
            gru_output: (batch, seq_len, hidden_dim) GRU output sequence
        Returns:
            context vector: (batch, hidden_dim)
        """
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
        """
        Args:
            inputs: logits (batch_size,)
            targets: labels (batch_size,)
        """
        inputs = inputs.squeeze(-1) if inputs.ndim > 1 else inputs
        bce_loss = torch.nn.functional.binary_cross_entropy_with_logits(
            inputs, targets, reduction='none'
        )
        pt = torch.exp(-bce_loss)
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        return (alpha_t * (1 - pt) ** self.gamma * bce_loss).mean()


class CausalGRUWithAttention(nn.Module):
    """
    Causal (uni-directional) GRU with Attention for fire risk prediction.

    Architecture:
        - 2-layer uni-directional GRU (strict causal flow, no future information)
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
        # Uni-directional GRU: strict causal flow (bidirectional=False)
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
        """
        Forward pass.

        Args:
            x: Input tensor (batch, seq_len, features)
            return_embedding: If True, return dense embeddings instead of logits

        Returns:
            logits or embeddings
        """
        gru_out, _ = self.gru(x)  # (batch, seq_len, hidden1)
        context = self.attention(gru_out)  # (batch, hidden1)
        last_timestep_out = gru_out[:, -1, :]  # Focus on most recent day
        combined = torch.cat((context, last_timestep_out), dim=1)  # (batch, hidden1*2)
        dense_out = self.dense(combined)
        logits = self.output(dense_out).squeeze(1)
        return dense_out if return_embedding else logits


def load_causal_gru_model(
    input_dim: int,
    model_path: Union[str, Path],
    hidden1: int = 64,
    dropout_rate: float = 0.3,
    device: Optional[torch.device] = None,
) -> CausalGRUWithAttention:
    """
    Load Causal GRU model from .pth file.

    Args:
        input_dim: Number of input features (should match raw_features count, typically 19)
        model_path: Path to the .pth model file
        hidden1: GRU hidden layer size (default 64)
        dropout_rate: Dropout rate (default 0.3)
        device: PyTorch device

    Returns:
        Loaded CausalGRUWithAttention model in eval mode
    """
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"Causal GRU model not found at: {model_path}")

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    try:
        model = CausalGRUWithAttention(
            input_dim=input_dim,
            hidden1=hidden1,
            dropout_rate=dropout_rate,
        )
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.to(device)
        model.eval()
        logger.info(f"Causal GRU model loaded from {model_path}")
        return model
    except Exception as e:
        raise ValueError(f"Failed to load Causal GRU model: {e}")


def predict_causal_gru(
    model: CausalGRUWithAttention,
    X: np.ndarray,
    scaler_raw,
    raw_feature_indices: list,
    device: Optional[torch.device] = None,
    seq_len: int = 7,
) -> np.ndarray:
    """
    Run prediction using Causal GRU model.

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
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()

    # Extract only raw features and scale them
    X_raw = X[:, raw_feature_indices]  # (n_samples, n_raw_features)
    X_raw_scaled = scaler_raw.transform(X_raw)  # (n_samples, n_raw_features)

    # Create sequences (sliding window)
    n_samples = X_raw_scaled.shape[0]

    if n_samples < seq_len:
        # For single-sample or few-sample inputs (e.g., AOI predictions),
        # synthesize a sequence by repeating the last sample seq_len times.
        # This represents "no change" over the past days, which is a reasonable
        # assumption when historical data is unavailable.
        logger.info(
            f"Input has {n_samples} sample(s) < seq_len={seq_len}. "
            f"Synthesizing sequence by repeating last sample."
        )
        last_sample = X_raw_scaled[-1:]  # (1, n_raw_features)
        X_raw_scaled = np.repeat(last_sample, seq_len, axis=0)  # (seq_len, n_raw_features)
        n_samples = seq_len

    X_seq = np.zeros((n_samples - seq_len + 1, seq_len, X_raw_scaled.shape[1]))
    for i in range(n_samples - seq_len + 1):
        X_seq[i] = X_raw_scaled[i : i + seq_len]

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

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = load_causal_gru_model(input_dim, model_path, device=device)
        logger.info(f"Model loaded: {type(model)}")
        logger.info(f"Device: {device}")
        logger.info(f"Input dimension: {input_dim}")

        if len(sys.argv) > 3:
            import json

            X_test = np.array([json.loads(sys.argv[3])])
            dummy_scaler = None  # Add proper scaler for testing
            prob = predict_causal_gru(model, X_test, dummy_scaler, list(range(input_dim)))
            logger.info(f"Prediction shape: {prob.shape}")
            logger.info(f"Prediction: {prob[:5]}")
