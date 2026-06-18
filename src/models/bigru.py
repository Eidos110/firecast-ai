"""
BiGRU model module for FireCast.
Provides functions to load and run Bidirectional GRU predictions with Attention.
"""

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


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
        super(BiGRUWithAttention, self).__init__()

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
        # x shape: (batch, seq_len, features)
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


# Alias for backward compatibility
BiGRUModel = BiGRUWithAttention


def load_bigru_model(
    input_dim: int,
    model_path: Union[str, Path],
    hidden1: int = 64,
    hidden2: int = 32,
    dropout_rate: float = 0.33,
    device: Optional[torch.device] = None,
) -> BiGRUWithAttention:
    """
    Load BiGRU model from .pth file.

    Args:
        input_dim: Number of input features
        model_path: Path to the .pth model file
        hidden1: First hidden layer size
        hidden2: Second hidden layer size
        dropout_rate: Dropout rate
        device: PyTorch device

    Returns:
        Loaded BiGRU model
    """
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"BiGRU model not found at: {model_path}")

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    try:
        model = BiGRUWithAttention(
            input_dim=input_dim,
            hidden1=hidden1,
            hidden2=hidden2,
            dropout_rate=dropout_rate,
        )
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.to(device)
        model.eval()
        logger.info(f"BiGRU model loaded from {model_path}")
        return model
    except Exception as e:
        raise ValueError(f"Failed to load BiGRU model: {e}")


def predict_bigru(
    model: BiGRUWithAttention,
    X: np.ndarray,
    device: Optional[torch.device] = None,
    seq_len: int = 7,
) -> np.ndarray:
    """
    Run prediction using BiGRU model.

    Args:
        model: Loaded BiGRU model
        X: Input features (n_samples, n_features) or (n_samples, seq_len, n_features)
        device: PyTorch device
        seq_len: Sequence length expected by model (default 7)

    Returns:
        Array of predictions (probabilities)
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()

    # Handle different input shapes
    if X.ndim == 2:
        # Input is (n_samples, n_features) - need to create sequences
        # PROBLEM: Simply repeating the same features seq_len times creates
        # a "fake" sequence where all timesteps are identical, which is unnatural
        # FIX: Add small variations to create more realistic temporal patterns
        n_samples = X.shape[0]
        # Create sequence with small temporal variations for better predictions
        X_seq = np.zeros((n_samples, seq_len, X.shape[1]))
        for i in range(seq_len):
            # Add small noise to simulate temporal variation (decreasing towards present)
            noise_scale = 0.02 * (seq_len - i)  # More variation at earlier timesteps
            noise = np.random.randn(n_samples, X.shape[1]) * noise_scale
            X_seq[:, i, :] = X + noise
        X = X_seq
        logger.debug(
            f"BiGRU input transformed from {X.shape[0], X.shape[1]} to {X.shape}"
        )
    elif X.ndim == 1:
        # Single sample as 1D array - create 2D then 3D
        X = np.tile(X, seq_len).reshape(1, seq_len, -1)

    try:
        with torch.no_grad():
            X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
            logits = model(X_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()

        # Log prediction values for debugging
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
