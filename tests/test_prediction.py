"""
FireCast Prediction Tests
=========================
Unit and integration tests for prediction functionality.
"""

import unittest
import sys
from pathlib import Path
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.predict import (
    predict_fire_risk,
    _get_risk_level,
    _calculate_risk_factors,
    PredictionError
)


class TestRiskLevel(unittest.TestCase):
    """Test risk level classification."""
    
    def test_low_risk(self):
        """Test low risk classification."""
        self.assertEqual(_get_risk_level(0.0), 'Low')
        self.assertEqual(_get_risk_level(0.1), 'Low')
        self.assertEqual(_get_risk_level(0.29), 'Low')
    
    def test_medium_risk(self):
        """Test medium risk classification."""
        self.assertEqual(_get_risk_level(0.3), 'Medium')
        self.assertEqual(_get_risk_level(0.4), 'Medium')
        self.assertEqual(_get_risk_level(0.49), 'Medium')
    
    def test_high_risk(self):
        """Test high risk classification."""
        self.assertEqual(_get_risk_level(0.5), 'High')
        self.assertEqual(_get_risk_level(0.6), 'High')
        self.assertEqual(_get_risk_level(0.69), 'High')
    
    def test_extreme_risk(self):
        """Test extreme risk classification."""
        self.assertEqual(_get_risk_level(0.7), 'Extreme')
        self.assertEqual(_get_risk_level(0.8), 'Extreme')
        self.assertEqual(_get_risk_level(1.0), 'Extreme')


class TestRiskFactors(unittest.TestCase):
    """Test risk factor calculation."""
    
    def test_high_temperature_factor(self):
        """Test high temperature creates risk factor."""
        features = {'temperature': 40, 'humidity': 50, 'wind_speed': 5}
        factors = _calculate_risk_factors(features)
        self.assertIn('High Temperature', factors)
        self.assertGreater(factors['High Temperature'], 0)
    
    def test_low_humidity_factor(self):
        """Test low humidity creates risk factor."""
        features = {'temperature': 30, 'humidity': 20, 'wind_speed': 5}
        factors = _calculate_risk_factors(features)
        self.assertIn('Low Humidity', factors)
        self.assertGreater(factors['Low Humidity'], 0)
    
    def test_strong_wind_factor(self):
        """Test strong wind creates risk factor."""
        features = {'temperature': 30, 'humidity': 50, 'wind_speed': 10}
        factors = _calculate_risk_factors(features)
        self.assertIn('Strong Wind', factors)
        self.assertGreater(factors['Strong Wind'], 0)
    
    def test_no_risk_factors_normal_conditions(self):
        """Test no risk factors in normal conditions."""
        features = {'temperature': 25, 'humidity': 60, 'wind_speed': 3}
        factors = _calculate_risk_factors(features)
        self.assertEqual(len(factors), 0)


class TestPredictFireRisk(unittest.TestCase):
    """Test main prediction function."""
    
    def test_valid_input(self):
        """Test prediction with valid input."""
        features = {
            'temperature': 35,
            'humidity': 40,
            'wind_speed': 8,
            'latitude': -6.2,
            'longitude': 106.8
        }
        
        result = predict_fire_risk(features)
        
        # Check result structure
        self.assertIn('risk_score', result)
        self.assertIn('risk_level', result)
        self.assertIn('confidence', result)
        self.assertIn('status', result)
        
        # Check value ranges
        self.assertGreaterEqual(result['risk_score'], 0)
        self.assertLessEqual(result['risk_score'], 1)
        self.assertGreaterEqual(result['confidence'], 0)
        self.assertLessEqual(result['confidence'], 1)
    
    def test_missing_required_features(self):
        """Test prediction with missing required features."""
        features = {
            'temperature': 35,
            # Missing humidity, wind_speed, latitude, longitude
        }
        
        with self.assertRaises(PredictionError):
            predict_fire_risk(features)
    
    def test_empty_input(self):
        """Test prediction with empty input."""
        with self.assertRaises(PredictionError):
            predict_fire_risk({})
    
    def test_extreme_values(self):
        """Test prediction with extreme input values."""
        features = {
            'temperature': 50,  # Very high
            'humidity': 5,      # Very low
            'wind_speed': 30,   # Very high
            'rainfall': 0,      # No rain - dry conditions (explicit for extreme scenario)
            'latitude': -6.2,
            'longitude': 106.8
        }
        
        result = predict_fire_risk(features)
        
        # Should predict high risk
        self.assertGreater(result['risk_score'], 0.5)
        self.assertIn(result['risk_level'], ['High', 'Extreme'])


class TestPredictionIntegration(unittest.TestCase):
    """Integration tests for prediction pipeline."""
    
    def test_full_prediction_workflow(self):
        """Test complete prediction workflow."""
        # This test simulates the full workflow from user input to result
        input_data = {
            'temperature': 32,
            'humidity': 45,
            'wind_speed': 5,
            'wind_direction': 90,
            'rainfall': 0,
            'latitude': -1.1747,
            'longitude': 100.4012,
            'vegetation_type': 'Savana'
        }
        
        result = predict_fire_risk(input_data)
        
        # Verify result is complete
        self.assertIn('risk_score', result)
        self.assertIn('risk_level', result)
        self.assertIn('factors', result)
        self.assertIn('timestamp', result)
        
        # Verify risk level is consistent with score
        risk_score = result['risk_score']
        expected_level = _get_risk_level(risk_score)
        self.assertEqual(result['risk_level'], expected_level)


if __name__ == '__main__':
    unittest.main()
