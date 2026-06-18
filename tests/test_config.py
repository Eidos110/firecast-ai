"""
FireCast Configuration Tests
============================
Tests for configuration management.
"""

import unittest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import (
    FireCastConfig,
    PathsConfig,
    ModelConfig,
    DataConfig,
    get_config
)


class TestPathsConfig(unittest.TestCase):
    """Test path configuration."""
    
    def test_base_dir_exists(self):
        """Test base directory exists."""
        paths = PathsConfig()
        self.assertTrue(paths.base_dir.exists())
    
    def test_data_dir_path(self):
        """Test data directory path."""
        paths = PathsConfig()
        expected = paths.base_dir / "data"
        self.assertEqual(paths.data_dir, expected)
    
    def test_models_dir_path(self):
        """Test models directory path."""
        paths = PathsConfig()
        expected = paths.base_dir / "models"
        self.assertEqual(paths.models_dir, expected)


class TestModelConfig(unittest.TestCase):
    """Test model configuration."""
    
    def test_default_device(self):
        """Test default device configuration."""
        config = ModelConfig(device='auto')
        # Should be cpu or cuda
        self.assertIn(str(config.torch_device), ['cpu', 'cuda'])
    
    def test_cnn_dropout_range(self):
        """Test CNN dropout is in valid range."""
        config = ModelConfig(cnn_dropout=0.3)
        self.assertGreaterEqual(config.cnn_dropout, 0)
        self.assertLessEqual(config.cnn_dropout, 1)
    
    def test_target_recall_range(self):
        """Test target recall is in valid range."""
        config = ModelConfig(target_recall=0.8)
        self.assertGreaterEqual(config.target_recall, 0)
        self.assertLessEqual(config.target_recall, 1)


class TestDataConfig(unittest.TestCase):
    """Test data configuration."""
    
    def test_train_split_valid(self):
        """Test train split is valid."""
        config = DataConfig(train_split=0.9)
        self.assertGreater(config.train_split, 0)
        self.assertLess(config.train_split, 1)
    
    def test_lag_positive(self):
        """Test lag is positive."""
        config = DataConfig(lag=3)
        self.assertGreater(config.lag, 0)
    
    def test_roll_window_positive(self):
        """Test rolling window is positive."""
        config = DataConfig(roll_window=7)
        self.assertGreater(config.roll_window, 0)


class TestFireCastConfig(unittest.TestCase):
    """Test main configuration class."""
    
    def test_singleton_pattern(self):
        """Test that get_config returns same instance."""
        config1 = get_config()
        config2 = get_config()
        self.assertIs(config1, config2)
    
    def test_config_has_required_attributes(self):
        """Test config has all required attributes."""
        config = FireCastConfig()
        
        self.assertIsNotNone(config.paths)
        self.assertIsNotNone(config.model)
        self.assertIsNotNone(config.data)
        self.assertIsNotNone(config.api)
        self.assertIsNotNone(config.frontend)
        self.assertIsNotNone(config.weather)
    
    def test_to_dict(self):
        """Test config serialization to dict."""
        config = FireCastConfig()
        config_dict = config.to_dict()
        
        self.assertIsInstance(config_dict, dict)
        self.assertIn('paths', config_dict)
        self.assertIn('model', config_dict)
        self.assertIn('data', config_dict)


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation."""
    
    @patch.dict(os.environ, {'TRAIN_SPLIT': '1.5'})
    def test_invalid_train_split(self):
        """Test validation catches invalid train split."""
        with self.assertRaises(ValueError):
            FireCastConfig()
    
    @patch.dict(os.environ, {'TRAIN_SPLIT': '-0.1'})
    def test_negative_train_split(self):
        """Test validation catches negative train split."""
        with self.assertRaises(ValueError):
            FireCastConfig()


if __name__ == '__main__':
    unittest.main()
