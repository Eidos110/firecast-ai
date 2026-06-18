# Implementation Guide: Click-to-Predict & AOI Drawing

## Overview

This implementation adds interactive map features to FireCast:
- **Click-to-Predict**: Click anywhere on the map to select a location for prediction
- **AOI Drawing**: Draw polygons to define Areas of Interest for batch predictions
- **Interactive React Component**: Modern map interface with Leaflet.js
- **Real-time Event Handling**: Bidirectional communication between JS and Python

## Architecture

```
Layer                   Technology                           Function
Frontend        React + Vite (Streamlit Template)   UI Map, event listener, rendering
Map Engine      Leaflet + Leaflet-Draw              Rendering peta, klik, gambar polygon
Geospatial      toGeoJSON() (JS) ↔ geopandas (Python)   Format data spasial standar
Backend         Streamlit st.components.v1              Bridge JS ↔ Python
State/Perf      st.session_state + @st.fragment         Isolasi rerun, cache model
Communication   Streamlit.setComponentValue()           Kirim event/data JS → Python
```

## Data Flow (Bidirectional)

```
[JS: Click/Draw] → Streamlit.setComponentValue({type, payload}) 
       ↓
[Python: st.components] → return dict ke variabel Python
       ↓
[Python: st.session_state] → trigger prediction (isolated via @st.fragment)
       ↓
[Python: Model + Geopandas] → hasil prediksi
       ↓
[Python → JS] → props.args / Streamlit.renderData() → render overlay di peta
```

## File Structure

### New Files Created:

1. **Frontend React (Interactive Map)**
   - `frontend_react/` - React application with Vite
     - `package.json` - Dependencies (React, Leaflet, Streamlit component lib)
     - `vite.config.ts` - Build configuration
     - `src/components/InteractiveMap.tsx` - Main map component with click/draw handlers
     - `src/App.tsx` - Development wrapper

2. **Python Backend Integration**
   - `frontend/components/interactive_map.py` - Streamlit component wrapper
   - `frontend/utils/aoi_prediction.py` - AOI batch prediction logic
   - `demo_interactive_map.py` - Demo application

3. **Documentation**
   - `IMPLEMENTATION_GUIDE.md` - This file
   - Updated `cured` file with detailed planning

### Modified Files:
- None (all new functionality is additive)

## Setup Instructions

### 1. Install Frontend Dependencies

```bash
cd frontend_react
npm install
```

### 2. Build React Component

For development:
```bash
npm run dev
```

For production (to use with Streamlit):
```bash
npm run build
```

### 3. Run Demo Application

```bash
streamlit run demo_interactive_map.py
```

### 4. Integrate with Main App

To use in the main FireCast application:

```python
# Import the interactive map component
from frontend.components.interactive_map import (
    render_interactive_map,
    handle_map_events,
    get_aoi_coordinates,
    generate_grid_points
)

from frontend.utils.aoi_prediction import (
    predict_aoi_grid,
    get_aoi_risk_summary,
    export_aoi_results
)

# In your Streamlit app:
map_output = render_interactive_map(height=600)

# Handle map events
if map_output and handle_map_events(map_output):
    st.rerun()

# Run AOI prediction
if st.button("Predict AOI"):
    aoi_coords = get_aoi_coordinates()
    results = predict_aoi_grid(aoi_coords, grid_size=10)
    
    # Display results
    summary = get_aoi_risk_summary(results["batch_results"])
    st.write(f"Average Risk: {summary['average_risk']*100:.1f}%")
    st.write(f"High Risk Points: {summary['high_risk_count']}")
```

## Event Types

The interactive map component sends these event types:

### 1. Click Events
```json
{
  "type": "click",
  "lat": -6.1750,
  "lng": 106.8270,
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

### 2. AOI Creation
```json
{
  "type": "aoi",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon1, lat1], [lon2, lat2], ...]]
  },
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

### 3. AOI Updates
```json
{
  "type": "aoi_updated",
  "geometries": [geoJSON1, geoJSON2],
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

### 4. AOI Deletion
```json
{
  "type": "aoi_deleted",
  "geometries": [geoJSON1, geoJSON2],
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

## Best Practices

### 1. Event Handling
- Use `event_id` to prevent duplicate processing
- Store events in session state history
- Limit history size to prevent memory issues

### 2. Performance
- Use `@st.fragment` to isolate prediction reruns
- Cache model loading with `@st.cache_resource`
- Limit grid size for large AOIs (max 20×20 = 400 points)

### 3. Error Handling
- Validate AOI coordinates before processing
- Handle prediction errors gracefully
- Provide user feedback for all actions

### 4. User Experience
- Show loading states during predictions
- Provide visual feedback on map interactions
- Include undo/clear functionality
- Export results in multiple formats (JSON, CSV, GeoJSON)

## Testing

### 1. Component Testing
```bash
# Test React component
cd frontend_react
npm run dev

# Open browser at http://localhost:3000
```

### 2. Integration Testing
```bash
# Run demo app
streamlit run demo_interactive_map.py

# Test features:
# 1. Click on map → check console output
# 2. Draw polygon → check AOI history
# 3. Edit polygon → check update events
# 4. Delete polygon → check delete events
# 5. Run predictions → check results
```

### 3. Manual Tests
- [ ] Map loads correctly
- [ ] Click events are captured
- [ ] Polygon drawing works
- [ ] Edit/Delete functions work
- [ ] Events trigger Python handlers
- [ ] Predictions run successfully
- [ ] Results display on map
- [ ] Export functions work
- [ ] Error handling works

## Troubleshooting

### Common Issues:

1. **Map not loading**
   - Check Leaflet CSS/JS imports
   - Verify CDN URLs are accessible
   - Check browser console for errors

2. **Events not triggering**
   - Verify Streamlit component communication
   - Check event_id uniqueness
   - Look for duplicate event filtering

3. **Performance issues**
   - Reduce grid size for large AOIs
   - Implement progress indicators
   - Use caching for repeated predictions

4. **GeoJSON errors**
   - Validate coordinate format ([lon, lat] for GeoJSON)
   - Check polygon closure (first == last point)
   - Verify coordinate ranges (lat: -90 to 90, lon: -180 to 180)

## Future Enhancements

1. **Advanced Features**
   - Heatmap visualization
   - Risk contour lines
   - Time-series predictions
   - Multiple AOI comparison

2. **Performance**
   - Web Workers for batch predictions
   - Progressive loading for large grids
   - Client-side prediction caching

3. **UX Improvements**
   - Custom map styles
   - Layer controls
   - Measurement tools
   - Import/Export shapefiles

## Dependencies

### Frontend (React)
- React 18.2.0
- Leaflet 1.9.4 + Leaflet-Draw 1.0.4
- Streamlit Component Library 1.3.0
- Vite 5.0.8 + TypeScript 5.2.2

### Backend (Python)
- Streamlit 1.28.0+
- Geopandas 0.14.0+
- Shapely 2.0.0+
- NumPy 1.24.0+

## Security Considerations

1. **Input Validation**
   - Validate all coordinates
   - Sanitize GeoJSON input
   - Limit grid size to prevent DoS

2. **Data Privacy**
   - Don't log sensitive location data
   - Clear session state appropriately
   - Secure export file handling

3. **Performance Limits**
   - Maximum grid points: 400 (20×20)
   - Maximum history items: 50 clicks, 10 AOIs
   - Timeout for long-running predictions

## Support

For issues or questions:
1. Check browser console for JavaScript errors
2. Check Streamlit logs for Python errors
3. Review event data in debug panel
4. Test with demo application first

## Credits

Implementation based on planning document: `cured`
Architecture: React + Leaflet + Streamlit bidirectional communication
Event handling: Streamlit component library with unique event IDs