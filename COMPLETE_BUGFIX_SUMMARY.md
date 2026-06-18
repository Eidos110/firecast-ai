# Complete Risk Factors Bug Fix - Summary

## Problem Identified
AOI (Area of Interest) prediction showed **percentage of points** exceeding thresholds in "Faktor Penyebab Risiko Tinggi", while single point prediction showed **impact contribution scores** (how much each factor pushes risk up). These are completely different metrics.

---

## Root Causes

### Cause 1: Wrong Metric
**AOI Old Behavior**: Counted points where temperature > 32°C → "100% of points have high temp"
**Single Point**: Calculates impact → "High Temperature contributes 10 points to risk score"

These metrics answer different questions:
- **Percentage of points**: "How common is this risk factor in the area?"
- **Impact score**: "How much does this factor increase fire risk?"

The display showed both as "Kontribusi (%)" which was misleading for AOI.

### Cause 2: Three Different Implementations
```
Single Point REAL (src/predict.py):   _calculate_risk_factors() → impact scores
Single Point DEMO (prediction_engine): inline calculation → impact scores (different thresholds)
AOI (aoi_analysis.py):                _rank_risk_factors() → % of points
```

---

## Solution Implemented

### Change 1: Align AOI with Real Model Calculation
**File**: `frontend/utils/aoi_analysis.py`

Added `_calculate_per_point_factors()` that replicates `_calculate_risk_factors()` from `src/predict.py`:

```python
if temp > 35:
    factors["High Temperature"] = min((temp - 35) / 10 * 100, 100)
if humidity < 40:
    factors["Low Humidity"] = (40 - humidity) / 40 * 100
if wind > 5:
    factors["Strong Wind"] = min((wind - 5) / 15 * 100, 100)
if rainfall < 1:
    if rainfall == 0:
        factors["No Recent Rainfall"] = 80
    else:
        factors["No Recent Rainfall"] = 80 - (rainfall / 0.9 * 70)
```

### Change 2: Aggregate Impact Across Points
Modified `_rank_risk_factors()` to:
1. Filter to High/Extreme risk points only
2. Compute per-point contributions for each point
3. Average the impact scores across all high-risk points
4. Return list of `{"factor": "High Temperature", "pct_high": 20.0}` (still using "pct_high" key but it's now impact, not percentage)

### Change 3: Update Label Mapping
**File**: `frontend/components/results_display.py`

Updated `label_map` to use descriptive factor names:

```python
label_map = {
    "High Temperature": "Suhu Tinggi",
    "Low Humidity": "Kelembaban Rendah",
    "Strong Wind": "Angin Kencang",
    "No Recent Rainfall": "Tidak Ada Hujan",
}
```

---

## Example Output Comparison

### Before Fix (AOI):
```
Faktor Penyebab Risiko Tinggi
  Suhu Tinggi: 85%       ← 85% of 100 points exceeded threshold
  Angin Kencang: 60%     ← 60% of 100 points exceeded threshold
  Kelembaban Rendah: 45%
```
**Problem**: These are NOT impact values. They don't show how much each factor contributes to risk.

### After Fix (AOI):
```
Faktor Penyebab Risiko Tinggi
  Tidak Ada Hujan: 77.4  ← average impact contribution across high-risk points
  Angin Kencang: 26.7   ← average impact contribution
  Suhu Tinggi: 20.0     ← average impact contribution
  Kelembaban Rendah: 19.2
```
**Fixed**: Now matches single point's format and meaning (impact scores 0-100).

### Single Point (for comparison):
```
Faktor Penyebab Risiko
  High Temperature: 10.0
  Low Humidity: 5.0
  Strong Wind: 20.0
  No Recent Rainfall: 64.4
```

AOI now shows the **same metric** (impact contribution) as single point!

---

## Files Modified

### 1. frontend/utils/aoi_analysis.py
- Added `_calculate_per_point_factors()` (lines 11-38)
- Rewrote `_rank_risk_factors()` (lines 40-85) to aggregate per-point impacts
- Updated `analyze_aoi_results()` to call new function

### 2. frontend/components/results_display.py
- Updated label mapping (lines 139-145) to use descriptive factor names
- Kept the existing logic that converts analysis["risk_factors"] to risk_factors dict

---

## Additional Fixes Applied (from earlier)

1. **Bug 1**: Spread direction uses actual calculation, not hardcoded values
2. **Bug 2**: Temporal forecast format standardized across AOI and single point
3. **Bug 3**: FutureWarning suppressed for plotly/pandas
4. **Threshold alignment**: All thresholds now match real model (temp>35, humidity<40, wind>5, rainfall<1)
5. **Rainfall bug fixed**: Changed threshold from 0.0 to 1.0 mm

---

## Validation

Tested with mixed batch data:
```
3 high-risk points: average contributions correctly computed
→ Rainfall: 77.4, Wind: 26.7, Temperature: 20.0, Humidity: 19.2
```

All files pass Python syntax validation.
