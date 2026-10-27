"""FireCast model implementations.

Active bundle (V4.2): ``lgbm`` + ``xgb`` base learners and a two-leg
``LogisticRegressionCV`` meta-learner. ``cnn`` and ``ensemble`` remain for the
legacy ``model_type="legacy"`` path.

Modules are imported lazily at their call sites because the CNN imports torch
(which may be blocked in some sandboxes). This package only re-exports the
torch-free registry.
"""

from . import registry

__all__ = ["registry"]
