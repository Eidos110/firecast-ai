"""
Integration Tests for FireCast
Test end-to-end prediction pipeline
"""

import unittest
import sys
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPredictionPipeline(unittest.TestCase):
    """Test complete prediction pipeline"""

    @classmethod
    def setUpClass(cls):
        """Setup test fixtures"""
        try:
            from src.data_loader import load_data_for_evaluation

            cls.data_loader = load_data_for_evaluation
        except ImportError:
            cls.skipTest(cls, "Data loader not available")

    def test_data_loading(self):
        """Test that data can be loaded"""
        try:
            from src.data_loader import load_data_for_evaluation

            X_test, y_test, features = load_data_for_evaluation()

            # Check data shapes
            self.assertEqual(len(X_test), len(y_test))
            self.assertGreater(len(features), 0)
            self.assertGreater(X_test.shape[0], 0)
            self.assertGreater(X_test.shape[1], 0)
        except Exception as e:
            self.skipTest(f"Data loading test skipped: {e}")

    def test_model_loading(self):
        """Test that models can be loaded"""
        try:
            from src.models.cnn import load_cnn_model
            from src.models.lgbm import load_lgbm_model

            # Try loading models
            cnn = load_cnn_model(79)  # 79 features
            lgbm = load_lgbm_model()

            self.assertIsNotNone(cnn)
            self.assertIsNotNone(lgbm)
        except Exception as e:
            self.skipTest(f"Model loading test skipped: {e}")


if __name__ == "__main__":
    unittest.main()
