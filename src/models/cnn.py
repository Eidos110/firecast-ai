"""
Tuned CNN 1D – ensemble component of FireCast.

No ``import torch`` at module level: torch / torch.nn are loaded lazily on the
first call that actually needs them, so importing this module is safe even on
Railway/HF Spaces workers where PyTorch cannot be loaded (``libtorch_cpu.so``
execstack issue). The shared lazy loader lives in :mod:`src.utils.lazy`.
"""

import logging
from typing import Any

from src import config
from src.utils.lazy import require_torch

logger = logging.getLogger(__name__)


# ── CNN architecture ────────────────────────────────────────────────────


def _build_cnn_class(nn):
    """Build a real ``nn.Module`` subclass bound to the provided ``torch.nn``.

    Defining the class inside a factory keeps ``TunedCNN1D`` free of any
    top-level ``nn.*`` references, so the module imports cleanly even when
    torch is absent; the class is only constructed once torch is available.

    The returned class subclasses ``nn.Module`` natively so that:

    * ``model.eval()`` propagates recursively to BatchNorm / Dropout (fixes
      the audit #4 noop-eval bug that let BatchNorm stay in train mode and
      bias inference by ±0.1–0.3),
    * ``model.load_state_dict(sd)`` is the native PyTorch loader (fixes
      audit #3 ``_set_nested`` ``OrderedDict[int]`` IndexError on legacy
      ``.pth`` keys like ``conv_block1.0.weight``),
    * sub-modules register with ``nn.Module.__setattr__`` (real ``Parameter``
      tracking, proper ``.parameters()``, ``.to(device)``).
    """

    class TunedCNN1D(nn.Module):
        """1-D CNN classifier (Conv blocks → dense → single logit)."""

        def __init__(self, input_dim: int, dropout_rate: float = 0.33):
            super().__init__()
            self.input_dim = input_dim
            self.dropout_rate = dropout_rate
            d = dropout_rate

            self.conv_block1 = nn.Sequential(
                nn.Conv1d(1, 32, 3, padding=1),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.Conv1d(32, 32, 3, padding=1),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Dropout(d),
            )
            self.conv_block2 = nn.Sequential(
                nn.Conv1d(32, 64, 3, padding=1),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.Conv1d(64, 64, 3, padding=1),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Dropout(d),
            )
            self.conv_block3 = nn.Sequential(
                nn.Conv1d(64, 128, 3, padding=1),
                nn.BatchNorm1d(128),
                nn.ReLU(),
                nn.AdaptiveAvgPool1d(4),
                nn.Dropout(d),
            )
            # Infer flattened size with a dummy forward of the conv backbone.
            import torch as _t

            with _t.no_grad():
                dummy = _t.zeros(1, 1, input_dim)
                out = self.conv_block3(self.conv_block2(self.conv_block1(dummy)))
                flattened_size = out.view(1, -1).size(1)
            self.dense = nn.Sequential(
                nn.Linear(flattened_size, 256),
                nn.BatchNorm1d(256),
                nn.ReLU(),
                nn.Dropout(d),
                nn.Linear(256, 128),
                nn.BatchNorm1d(128),
                nn.ReLU(),
                nn.Dropout(d),
            )
            self.output = nn.Linear(128, 1)

        def forward(self, x):
            # x: (B, features) → (B, 1, features) for Conv1d
            x = x.unsqueeze(1)
            x = self.conv_block1(x)
            x = self.conv_block2(x)
            x = self.conv_block3(x)
            x = x.view(x.size(0), -1)
            x = self.dense(x)
            return self.output(x).squeeze(1)

    return TunedCNN1D


# ── Module-level placeholder ────────────────────────────────────────────
# Populated on first ``load_cnn_model`` call once torch is available. Keeps
# ``isinstance`` checks in callers (and downstream code that does ``from
# src.models.cnn import TunedCNN1D``) working without top-level torch import.
_TunedCNN1DClass = None


def _get_cnn_class():
    """Return the concrete ``nn.Module`` subclass for the CNN, building it once."""
    global _TunedCNN1DClass
    if _TunedCNN1DClass is None:
        _, nn = require_torch()
        _TunedCNN1DClass = _build_cnn_class(nn)
    return _TunedCNN1DClass


# Expose ``TunedCNN1D`` as a module attribute that lazily redirects to the
# real class. Code that does ``TunedCNN1D(input_dim=...)`` resolves through
# ``__getattr__`` (only fires when the attribute is missing from the module),
# so we keep the name exported but defer instantiation to after torch loads.
def __getattr__(name):
    if name == "TunedCNN1D":
        return _get_cnn_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Model loader ────────────────────────────────────────────────────────


def load_cnn_model(input_dim: int, model_path: Any = None):
    """Load CNN weights from a state-dict file.

    The saved file may be either:
    - A plain state-dict (mapping ``"<layer>.<param>" → Tensor``) — this is the
      format of ``models/cnn_best.pth`` (no ``model.*`` prefix; keys are
      ``conv_block1.0.weight`` style, directly loadable by the native
      ``nn.Module.load_state_dict``).
    - A checkpoint dict ``{state_dict: ..., epoch: ..., loss: ...}``.

    Args:
        input_dim: Number of features per sample.
        model_path: Override path; defaults to ``config.CNN_MODEL_PATH``.

    Returns:
        Loaded ``TunedCNN1D`` (``nn.Module``) instance in eval mode.

    Raises:
        RuntimeError: If PyTorch is unavailable.
        FileNotFoundError: If model file missing.
    """
    torch_mod, _nn = require_torch()
    if model_path is None:
        model_path = config.CNN_MODEL_PATH

    cnn_cls = _get_cnn_class()
    model = cnn_cls(input_dim, dropout_rate=config.CNN_DROPOUT)

    # Legacy ``.pth`` checkpoints were saved with ``torch.save(state_dict)``
    # (plain OrderedDict, no pickle of custom classes). Try the strict
    # ``weights_only=True`` loader first (defence against malicious files),
    # then fall back to the older ``weights_only=False`` for serialisations
    # the restricted loader rejects.
    try:
        checkpoint = torch_mod.load(model_path, map_location=config.DEVICE, weights_only=True)
    except Exception:
        checkpoint = torch_mod.load(model_path, map_location=config.DEVICE, weights_only=False)
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state = checkpoint["state_dict"]
    else:
        state = checkpoint

    # Native loader: strict=True would catch missing/extra keys. The legacy
    # checkpoint keys (``conv_block1.0.weight`` ...) match our nn.Module
    # exactly, so strict loading is fine and surfaces drift loudly.
    model.load_state_dict(state, strict=True)
    model.eval()
    return model
