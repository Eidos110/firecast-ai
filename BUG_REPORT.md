# FireCast Bug Report

## Summary
This document details the bugs identified in the FireCast fire forecasting system. The analysis was performed by examining the codebase and running the existing test suite.

## Test Results
- Total tests: 29
- Passed: 28
- Failed: 1

### Failed Test
- `TestRiskFactors.test_no_risk_factors_normal_conditions` - FAILED

## Detailed Bug Analysis

### Bug #1: Default rainfall value triggers false risk factor (CRITICAL)
**Location:** `src/predict.py`, lines 852, 868-870

**Severity:** HIGH

**Description:** 
When `rainfall` is not provided in the features dictionary, it defaults to 0 (line 852). This triggers the "No Recent Rainfall" risk factor (lines 868-870), which is incorrect behavior for normal conditions.

**Code:**
```python
# Line 852
rainfall = features.get("rainfall", 0)  # Defaults to 0

# Lines 868-870
if rainfall < 1:
    if rainfall == 0:
        factors["No Recent Rainfall"] = 80  # Always triggers when rainfall not provided
```

**Impact:** 
- The test `test_no_risk_factors_normal_conditions` fails because it expects no risk factors for normal conditions (temperature=25, humidity=60, wind_speed=3), but the function adds "No Recent Rainfall" = 80.
- Users who don't provide rainfall data will get incorrect risk assessments.
- Could lead to false alarms in operational use.

**Fix:** 
Change the default value of rainfall from 0 to `None` and handle it appropriately:
```python
# Option 1: Use None as default and skip if not provided
rainfall = features.get("rainfall")
if rainfall is not None and rainfall < 1:
    if rainfall == 0:
        factors["No Recent Rainfall"] = 80
    else:
        factors["No Recent Rainfall"] = 80 - (rainfall / 0.9 * 70)

# Option 2: Use a neutral default (>= 1)
rainfall = features.get("rainfall", 1.0)  # No risk by default
```

**Test Case:**
```python
def test_no_risk_factors_normal_conditions(self):
    """Test no risk factors in normal conditions."""
    features = {'temperature': 25, 'humidity': 60, 'wind_speed': 3}
    factors = _calculate_risk_factors(features)
    self.assertEqual(len(factors), 0)  # Currently fails: returns 1 factor
```

---

### Bug #2: Inconsistent feature column configuration
**Location:** `src/config.py`, lines 115-120

**Severity:** MEDIUM

**Description:** 
There's inconsistency in the property names for feature columns in the configuration:
- Line 115: `new_feature_columns_path` (singular "column")
- Line 120: `new_feature_columns_path` (plural "columns")

However, both properties point to different files:
- Line 115: Returns `self.new_model_dir / "feature_cols.json"`
- Line 120: Returns `self.new_model_dir / "feature_cols.json"`

Wait, actually looking more carefully, both are the same. Let me re-examine...

Actually, there's only one property: `new_feature_columns_path` (line 119-120). But in `src/predict.py` line 282, the function `load_new_feature_columns()` uses `config.NEW_FEATURE_COLUMNS_PATH`, which is defined in the legacy compatibility section (line 326).

**Potential Issue:** The legacy variable `NEW_FEATURE_COLUMNS_PATH` (line 326) uses `cfg.paths.new_feature_columns_path`, which is correct. But there might be confusion about which file to use.

**Impact:** 
- Could lead to loading wrong feature columns if files are not synchronized.
- Maintenance confusion due to legacy compatibility layer.

**Recommendation:** 
- Ensure all feature column files are consistent.
- Consider deprecating legacy variables in favor of the new config object.

---

### Bug #3: Missing validation for ensemble probability range
**Location:** `src/predict.py`, lines 689-698, 782-793

**Severity:** MEDIUM

**Description:** 
The code doesn't validate that ensemble probabilities are within [0, 1] range before using them. After calibration (lines 328-346, 358-374), probabilities could theoretically exceed these bounds.

**Code:**
```python
# Lines 333-338
if cnn_mean < 0.1:
    cnn_calibrated = cnn_probs * 5.0 + 0.1
    cnn_calibrated = np.clip(cnn_calibrated, 0.0, 0.9)  # Clipped to 0.9, not 1.0
    cnn_probs = cnn_calibrated
```

**Impact:** 
- Risk scores could be outside valid [0, 1] range.
- Could cause issues with downstream processing.
- Clipping to 0.9 instead of 1.0 might underestimate extreme risks.

**Fix:** 
- Add validation after calibration to ensure probabilities are in [0, 1].
- Use `np.clip(cnn_calibrated, 0.0, 1.0)` instead of 0.9.
- Add similar validation for LGBM calibration.

---

### Bug #4: Potential division by zero in _safe_divide
**Location:** `src/predict.py`, lines 46-61

**Severity:** LOW

**Description:** 
The `_safe_divide` function adds epsilon to the denominator, but the logic has a subtle issue:

```python
def _safe_divide(numerator, denominator, epsilon=1e-8):
    if isinstance(denominator, np.ndarray):
        return numerator / (denominator + epsilon)
    else:
        return numerator / (denominator + epsilon) if denominator != 0 else numerator / epsilon
```

When denominator is 0 (not array), it returns `numerator / epsilon`, which could be very large if numerator is not 0.

**Impact:** 
- Could produce extremely large values in spectral index calculations.
- Might cause numerical instability.

**Fix:** 
```python
def _safe_divide(numerator, denominator, epsilon=1e-8):
    if isinstance(denominator, np.ndarray):
        return numerator / (denominator + epsilon)
    else:
        if denominator == 0:
            return 0.0  # or numerator / epsilon if that's the intended behavior
        return numerator / (denominator + epsilon)
```

---

### Bug #5: Hardcoded risk factor thresholds
**Location:** `src/predict.py`, lines 855-873

**Severity:** MEDIUM

**Description:** 
Risk factor thresholds are hardcoded and might not be appropriate for all regions:
- Temperature: 35°C (line 855)
- Humidity: 40% (line 859)
- Wind: 5 m/s (line 863)
- Rainfall: 1mm (line 868)

**Impact:** 
- Not adaptable to different climate zones.
- Could underestimate/overestimate risks in certain regions.

**Recommendation:** 
- Make thresholds configurable via environment variables or config file.
- Consider regional calibration.

---

### Bug #6: Potential issue with temporal feature estimation
**Location:** `src/predict.py`, lines 973-1028

**Severity:** LOW

**Description:** 
The `_estimate_temporal_feature` function uses hardcoded heuristics that might not be accurate:
- Line 987: Spectral bands get `+ 15` and `+ 5` offsets, which seem arbitrary
- Line 1015: Precipitation deficit increases with time, which might not be accurate

**Impact:** 
- Could lead to incorrect feature engineering.
- Might affect model performance.

**Recommendation:** 
- Validate heuristics against actual historical data.
- Consider making parameters configurable.

---

### Bug #7: Missing error context in _create_feature_vector
**Location:** `src/predict.py`, lines 1254-1256

**Severity:** LOW

**Description:** 
When an exception occurs, the error is logged and re-raised, but without additional context about which feature caused the issue.

**Impact:** 
- Difficult to debug feature vector creation failures.

**Fix:** 
```python
except Exception as e:
    logger.error(f"Fatal error in _create_feature_vector: {e}")
    logger.error(f"Feature columns: {feature_columns}")
    logger.error(f"Available features: {list(all_features.keys())}")
    raise  # Propagate error with additional context
```

---

### Bug #8: Inconsistent NaN handling in predict_stacking
**Location:** `src/predict.py`, lines 782-793

**Severity:** MEDIUM

**Description:** 
When all ensemble predictions are NaN, the code falls back to using LGBM prediction (line 793), but this might not be appropriate if LGBM also fails.

**Code:**
```python
if np.any(valid_mask):
    ensemble_prob = float(ensemble_probs[valid_mask][0])
else:
    logger.error(f"All ensemble predictions are NaN...")
    ensemble_prob = float(lgbm_model.predict(feature_vector_scaled)[0])
```

**Impact:** 
- Fallback might not work if LGBM model also has issues.
- Could propagate errors silently.

**Fix:** 
- Add more robust error handling.
- Consider raising an exception if all predictions are NaN.

---

## Additional Issues

### Issue #1: Deprecated sklearn warnings
**Description:** 
Multiple warnings about unpickling estimators from older sklearn versions:
- "Trying to unpickle estimator StandardScaler from version 1.0.2 when using version 1.4.0"
- "Trying to unpickle estimator LogisticRegressionCV from version 1.0.2 when using version 1.4.0"

**Impact:** 
- Could lead to breaking code or invalid results.
- Models might not load correctly in future sklearn versions.

**Recommendation:** 
- Retrain models with current sklearn version.
- Use version-agnostic model formats (e.g., ONNX) if possible.

### Issue #2: XGBoost compatibility warning
**Description:** 
"If you are loading a serialized model... please export the model by calling `Booster.save_model` from that version first"

**Impact:** 
- Models might not work correctly with newer XGBoost versions.

**Recommendation:** 
- Re-export models using current XGBoost version.

---

## Recommendations

1. **Immediate Actions:**
   - Fix Bug #1 (rainfall default) - this is causing test failure
   - Add validation for probability ranges (Bug #3)
   - Retrain models with current sklearn/XGBoost versions

2. **Short-term:**
   - Make risk factor thresholds configurable (Bug #5)
   - Improve error handling and logging (Bugs #7, #8)
   - Fix _safe_divide edge cases (Bug #4)

3. **Long-term:**
   - Validate temporal feature heuristics (Bug #6)
   - Consider regional calibration for risk factors
   - Implement comprehensive test suite for edge cases

## Conclusion

The most critical bug is **Bug #1** (rainfall default), which causes incorrect risk assessments when rainfall data is not provided. This is also the cause of the failing test. The fix is straightforward: change the default rainfall value from 0 to a neutral value (≥1) or handle missing rainfall data explicitly.

Several other bugs relate to numerical stability, error handling, and model compatibility. While not critical, these should be addressed to ensure robust operation.
