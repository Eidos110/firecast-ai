# Simple Implementation Guide: Click-to-Predict & AOI Drawing

## Overview

**No React build required!** This implementation uses pure HTML/JavaScript with CDN libraries for the interactive map features:

- **Click-to-Predict**: Click anywhere on the map to select a location
- **AOI Drawing**: Draw polygons for area-based predictions  
- **Edit/Delete**: Modify drawn shapes
- **Real-time Events**: JavaScript to Python communication
- **Risk Visualization**: Color-coded overlays

## Architecture

```
Frontend:    HTML + JavaScript (Leaflet.js CDN)
Backend:     Streamlit Python
Communication: window.postMessage() API
Data Format:  GeoJSON standard
```

## File Structure

### Core Files:

1. **`frontend/components/interactive_map_simple.py`**
   - Streamlit component with inline HTML/JavaScript
   - Event handling functions
   - No external build required

2. **`demo_simple_interactive_map.py`**
   - Complete demo application
   - Shows all features in action

3. **`frontend/utils/aoi_prediction.py`** (from previous implementation)
   - AOI batch prediction logic
   - Risk analysis and export functions

### Dependencies:
- **Leaflet.js** (CDN): Map rendering
- **Leaflet.draw** (CDN): Drawing tools  
- **Streamlit**: Python framework
- **NumPy/Geopandas**: Geospatial processing

## Setup Instructions

### 1. Install Python Dependencies
```bash
pip install streamlit numpy pandas
# Optional: pip install geopandas shapely for advanced features
```

### 2. Run the Demo
```bash
streamlit run demo_simple_interactive_map.py
```

### 3. Test Features
- Open browser at `http://localhost:8501`
- Click on map → check console/output
- Draw polygon → check AOI creation
- Edit/delete shapes → check updates
- Run predictions → check results

## How It Works

### JavaScript → Python Communication
```javascript
// JavaScript sends events to Python
window.parent.postMessage({
    type: 'streamlit:setComponentValue',
    value: {
        type: 'click',
        lat: -6.175,
        lng: 106.827,
        timestamp: Date.now()
    }
}, '*');
```

### Python → JavaScript Communication
```python
# Python sends data to JavaScript via HTML template
prediction_overlay = {
    "type": "FeatureCollection",
    "features": [...]
}

# Rendered in HTML template
html = template.replace("{{PREDICTION_OVERLAY}}", json.dumps(prediction_overlay))
```

### Event Types

1. **Click Event**
```json
{
  "type": "click",
  "lat": -6.1750,
  "lng": 106.8270,
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

2. **AOI Drawing Event**
```json
{
  "type": "aoi",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon, lat], ...]]
  },
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

3. **AOI Edit/Delete Events**
```json
{
  "type": "aoi_updated",  // or "aoi_deleted"
  "geometries": [geoJSON1, geoJSON2],
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

## Integration with Main App

### Basic Integration:
```python
from frontend.components.interactive_map_simple import (
    create_simple_interactive_map,
    initialize_session_state,
    handle_map_event,
    get_aoi_coordinates
)

# Initialize
initialize_session_state()

# Render map
map_component = create_simple_interactive_map(height=600)

# Handle events (in callback or after render)
if st.session_state.get("map_output"):
    event_data = st.session_state.map_output
    handle_map_event(event_data)
    
    if event_data["type"] == "click":
        # Run single prediction
        location = st.session_state.selected_location
        # ... prediction logic
        
    elif event_data["type"] == "aoi":
        # Show AOI options
        aoi_coords = get_aoi_coordinates()
        # ... AOI batch prediction logic
```

### With AOI Predictions:
```python
from frontend.utils.aoi_prediction import predict_aoi_grid

if st.button("Predict AOI"):
    aoi_coords = get_aoi_coordinates()
    results = predict_aoi_grid(aoi_coords, grid_size=10)
    
    # Display results
    if results["status"] == "success":
        st.write(f"✅ {results['grid_count']} points predicted")
        
        # Create visualization overlay
        features = []
        for result in results["batch_results"]:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [result["longitude"], result["latitude"]]
                },
                "properties": {
                    "prediction": result["overall_risk"],
                    "risk_level": result["risk_level"]
                }
            })
        
        prediction_overlay = {
            "type": "FeatureCollection",
            "features": features
        }
        
        # Update map with overlay
        st.rerun()
```

## Features

### ✅ Implemented
- Interactive map with OpenStreetMap
- Click event handling
- Polygon drawing with Leaflet.draw
- Shape editing and deletion
- Event deduplication
- Session state management
- Prediction overlays
- Batch predictions for AOI
- Multiple export formats (JSON, CSV)

### 🎨 Styling
- Responsive design
- Custom map height
- Border radius and styling
- Color-coded risk visualization
- Toolbar integration

### 🔧 Configuration
- Adjustable map height
- Configurable grid size
- Risk tolerance settings
- Model selection options

## Performance

### Optimizations:
- **CDN loading**: No local build required
- **Event deduplication**: Prevents duplicate processing
- **Session state**: Efficient state management
- **Lazy loading**: Resources loaded on demand

### Limits:
- Max grid points: 400 (20×20 recommended)
- Max history items: 50 clicks, 10 AOI events
- Browser compatibility: Modern browsers only

## Troubleshooting

### Common Issues:

1. **Map not loading**
   - Check internet connection (CDN access)
   - Browser console for errors
   - Streamlit logs for Python errors

2. **Events not working**
   - Check iframe permissions
   - Verify event handler registration
   - Look for JavaScript errors

3. **Drawing tools missing**
   - Verify Leaflet.draw CDN loaded
   - Check toolbar initialization
   - Browser compatibility

4. **Performance issues**
   - Reduce grid size for large AOIs
   - Limit prediction overlay size
   - Use efficient data structures

### Debugging:
```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check session state
st.write(st.session_state)

# Check event data
if st.session_state.get("map_output"):
    st.json(st.session_state.map_output)
```

## Browser Compatibility

- Chrome 60+ ✅
- Firefox 55+ ✅  
- Safari 11+ ✅
- Edge 79+ ✅
- Internet Explorer: ❌ Not supported

## Security Considerations

1. **Input Validation**
   - Validate all coordinates
   - Sanitize GeoJSON input
   - Limit data size

2. **Cross-Origin Communication**
   - Uses `postMessage` with origin `'*'`
   - Event validation in Python
   - No sensitive data in events

3. **Resource Loading**
   - CDN resources over HTTPS
   - No local file access required
   - Fallback handling

## Extending the Implementation

### Add New Features:

1. **Custom Map Tiles**
```javascript
// In HTML template
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
    attribution: '© CartoDB'
}).addTo(map);
```

2. **Additional Drawing Tools**
```javascript
const drawControl = new L.Control.Draw({
    draw: {
        polygon: true,
        rectangle: true,  // Enable rectangles
        circle: true,     // Enable circles
        marker: true,     // Enable markers
        polyline: true    // Enable polylines
    }
});
```

3. **Custom Event Types**
```javascript
// Add custom event
map.on('moveend', function() {
    sendEventToParent('map_moved', {
        bounds: map.getBounds(),
        zoom: map.getZoom()
    });
});
```

## Comparison with React Version

| Feature | Simple (HTML/JS) | React Version |
|---------|-----------------|---------------|
| Setup | No build required | Requires npm build |
| Development | Edit HTML template | Edit TypeScript files |
| Performance | Faster initial load | Better for complex UIs |
| Maintenance | Simpler | More structured |
| Dependencies | CDN only | Local node_modules |
| Type Safety | Limited | Full TypeScript support |

## Recommendations

### Use Simple Version When:
- Quick setup needed
- No React experience
- Simple map features required
- Limited development time

### Use React Version When:
- Complex UI needed
- Type safety important
- Team has React experience
- Advanced features planned

## Support

For issues:
1. Check browser console (F12)
2. Check Streamlit logs
3. Verify CDN access
4. Test with demo application

## Credits

Implementation based on:
- Leaflet.js for mapping
- Leaflet.draw for drawing tools  
- Streamlit for Python integration
- OpenStreetMap for map tiles

## License

Part of FireCast project. See main project license.