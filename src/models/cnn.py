"""
Tuned CNN 1D – ensemble component of FireCast.
No `import torch` at module level; defers until inst=new() or forward.
"""

import logging
from src import config

logger = logging.getLogger(__name__)

# ── Lazy torch loader ──────────────────────────────────────────────────
_torch_mod = None
_nn_mod = None

def _get_torch():
    """Import torch on first call. Returns None if blocked (Railway execstack)."""
    global _torch_mod, _nn_mod
    if _torch_mod is None:
        try:
            import torch as _t
            import torch.nn as _nn
            _torch_mod, _nn_mod = _t, _nn
        except ImportError:
            pass
    return _torch_mod, _nn_mod

def _require_torch():
    """Return (torch, nn) tuple; raise if unavailable."""
    result = _get_torch()
    if result[0] is None:
        raise RuntimeError(
            "PyTorch unavailable on this Railway worker. "
            "ML inference is disabled; run in demo mode."
        )
    return result


# ── CNN architecture ────────────────────────────────────────────────────

class TunedCNN1D:
    """1-D CNN classifier with lazy torch binding.
    
    __init__ stores hyper-parameters only.  Sub-modules are created on the
    first forward() call so the module can be instantiated even when torch
    is unavailable (startup sequence safety).
    """

    def __init__(self, input_dim: int, dropout_rate: float = 0.33):
        self.input_dim = input_dim
        self.dropout_rate = dropout_rate
        self._built = False
        self.conv_block1 = None
        self.conv_block2 = None
        self.conv_block3 = None
        self.dense = None
        self.output = None
        self.flattened_size = None

    # ------------------------------------------------------------------
    def _build(self):
        """Allocate all torch.nn layers.  Raises RuntimeError if torch missing."""
        torch_mod, nn_mod = _require_torch()
        d = self.dropout_rate

        self.conv_block1 = nn_mod.Sequential(
            nn_mod.Conv1d(1, 32, 3, padding=1), nn_mod.BatchNorm1d(32),
            nn_mod.ReLU(),
            nn_mod.Conv1d(32, 32, 3, padding=1), nn_mod.BatchNorm1d(32),
            nn_mod.ReLU(), nn_mod.MaxPool1d(2), nn_mod.Dropout(d),
        )
        self.conv_block2 = nn_mod.Sequential(
            nn_mod.Conv1d(32, 64, 3, padding=1), nn_mod.BatchNorm1d(64),
            nn_mod.ReLU(),
            nn_mod.Conv1d(64, 64, 3, padding=1), nn_mod.BatchNorm1d(64),
            nn_mod.ReLU(), nn_mod.MaxPool1d(2), nn_mod.Dropout(d),
        )
        self.conv_block3 = nn_mod.Sequential(
            nn_mod.Conv1d(64, 128, 3, padding=1), nn_mod.BatchNorm1d(128),
            nn_mod.ReLU(), nn_mod.AdaptiveAvgPool1d(4), nn_mod.Dropout(d),
        )
        # Infer flattened size
        with torch_mod.no_grad():
            dummy = torch_mod.zeros(1, 1, self.input_dim)
            out = self.conv_block3(
                self.conv_block2(self.conv_block1(dummy))
            )
            self.flattened_size = out.view(1, -1).size(1)
        self.dense = nn_mod.Sequential(
            nn_mod.Linear(self.flattened_size, 256), nn_mod.BatchNorm1d(256),
            nn_mod.ReLU(), nn_mod.Dropout(d),
            nn_mod.Linear(256, 128), nn_mod.BatchNorm1d(128),
            nn_mod.ReLU(), nn_mod.Dropout(d),
        )
        self.output = nn_mod.Linear(128, 1)
        self._built = True

    # ------------------------------------------------------------------
    def _set_nested(self, obj, path_parts, tensor):
        """Traverse ``obj.part[0].part[1]...`` and assign ``tensor`` at the leaf.

        Path parts may be attribute names (for ``nn.Module`` / plain attrs) or
        integer indices (for ``nn.Sequential`` style container layers).  The
        leaf value is always wrapped in ``nn.Parameter`` so that ``nn.Module``
        ``__setattr__`` (which enforces ``Parameter`` type) does not reject the
        assignment.
        """
        torch_mod, _ = _require_torch()
        nn_mod = torch_mod.nn
        cur = obj
        for part in path_parts[:-1]:
            if isinstance(cur, (list, tuple)):
                cur = cur[int(part)]
            else:
                cur = getattr(cur, part)
        leaf = path_parts[-1]
        leaf_dtype = getattr(tensor, 'dtype', None)
        # nn.Parameter requires float/complex dtypes; int/bool buffers (e.g.
        # BatchNorm.num_batches_tracked) must be assigned as plain tensors.
        if leaf_dtype is not None and not (leaf_dtype.is_floating_point or leaf_dtype.is_complex):
            if isinstance(cur, (list, tuple)):
                cur[int(leaf)] = tensor
            else:
                setattr(cur, leaf, tensor)
        else:
            param = nn_mod.Parameter(tensor.detach().clone())
            if isinstance(cur, (list, tuple)):
                cur[int(leaf)] = param
            else:
                setattr(cur, leaf, param)

    def load_state_dict(self, state_dict):
        """Load layer weights from a state-dict (plain or nested checkpoint).

        Handles keys using PEP-8 attribute paths (e.g. ``conv_block1.0.weight``)
        as well as full ``nn.state_dict()``-style output.

        Args:
            state_dict: Mapping of ``<layer_name>.<param_name>`` → ``Tensor``,
                or an object whose ``.state_dict()`` returns such a mapping.
        """
        if hasattr(state_dict, "state_dict") and callable(state_dict.state_dict):
            try:
                state_dict = state_dict.state_dict()
            except Exception:
                pass
        if not isinstance(state_dict, dict):
            raise TypeError(
                f"Expected a dict state-dict or an object with state_dict(), "
                f"got {type(state_dict).__name__}"
            )
        for key, tensor in state_dict.items():
            parts = key.split(".")
            # Validate that the top-level attribute exists (or build if not yet)
            top = getattr(self, parts[0], None)
            if top is None and not self._built:
                self._build()
                top = getattr(self, parts[0], None)
            if top is None:
                raise AttributeError(
                    f"No layer/top-level attribute {parts[0]!r} on TunedCNN1D "
                    f"(searched key {key!r})"
                )
            self._set_nested(self, parts, tensor)
        # After loading all weights, freeze all parameters (inference-only model)
        _, nn_mod = _require_torch()
        for attr_name, attr_val in self.__dict__.items():
            if isinstance(attr_val, nn_mod.Parameter):
                attr_val.requires_grad = False
            elif isinstance(attr_val, nn_mod.Module):
                for cp in attr_val.parameters():
                    cp.requires_grad = False

    def eval(self):
        """Set model to evaluation mode (no-op for this lightweight wrapper)."""
        self._eval = True

    def __call__(self, x):
        # Makes cnn_model(x) behave like an nn.Module call → delegates to forward()
        return self.forward(x)

    # ------------------------------------------------------------------
    def forward(self, x):
        if not self._built:
            self._build()
        # x: (B, features) → (B, 1, features) for Conv1d
        x = x.unsqueeze(1)
        x = self.conv_block1(x)
        x = self.conv_block2(x)
        x = self.conv_block3(x)
        x = x.view(x.size(0), -1)
        x = self.dense(x)
        return self.output(x).squeeze(1)


# ── Model loader ────────────────────────────────────────────────────────

def load_cnn_model(input_dim: int, model_path=None):
    """Load CNN weights from a state-dict file.

    The saved file may be either:
    - A plain state-dict string ``"<layer>.<param>" → Tensor`` mapping.
    - A checkpoint dict ``{state_dict: ..., epoch: ..., loss: ...}``.

    Args:
        input_dim: Number of features per sample.
        model_path: Override path; defaults to config.CNN_MODEL_PATH.

    Returns:
        Loaded TunedCNN1D instance.

    Raises:
        RuntimeError: If PyTorch is unavailable.
        FileNotFoundError: If model file missing.
    """
    torch_mod, nn_mod = _require_torch()
    if model_path is None:
        model_path = config.CNN_MODEL_PATH
    model = TunedCNN1D(input_dim, dropout_rate=config.CNN_DROPOUT)
    checkpoint = torch_mod.load(model_path, map_location=config.DEVICE)
    # Unwrap common checkpoint wrapper with epoch/loss metadata
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state = checkpoint["state_dict"]
    else:
        state = checkpoint
    model.load_state_dict(state)
    model.eval()
    return model
