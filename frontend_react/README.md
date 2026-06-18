# FireCast Interactive Map Frontend

React + Leaflet frontend for FireCast interactive map features.

## Features

- **Interactive Map**: Leaflet.js with OpenStreetMap tiles
- **Click-to-Predict**: Click anywhere to select locations
- **AOI Drawing**: Draw polygons for area-based predictions
- **Real-time Updates**: Bidirectional communication with Python
- **Risk Visualization**: Color-coded risk overlays

## Development

### Prerequisites
- Node.js 16+ and npm
- Python 3.8+ with Streamlit

### Setup
```bash
# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build
```

### Project Structure
```
frontend_react/
├── src/
│   ├── components/
│   │   └── InteractiveMap.tsx    # Main map component
│   ├── App.tsx                   # Development wrapper
│   ├── main.tsx                  # Entry point
│   └── index.css                # Global styles
├── public/                       # Static assets
├── package.json                  # Dependencies
├── vite.config.ts               # Build configuration
└── tsconfig.json                # TypeScript config
```

## Integration with Streamlit

### 1. Build the Component
```bash
npm run build
```

### 2. Python Integration
```python
import streamlit.components.v1 as components

# Declare component
InteractiveMap = components.declare_component(
    "interactive_map", 
    path="./frontend_react/build"
)

# Use in Streamlit app
map_output = InteractiveMap(height=600)
```

### 3. Event Handling
The component sends events to Python:
- `click`: Map click events with lat/lng
- `aoi`: Polygon drawing events
- `aoi_updated`: Polygon edit events
- `aoi_deleted`: Polygon delete events

## Component Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `height` | number | 600 | Map height in pixels |
| `predictionOverlay` | GeoJSON | null | Risk visualization data |
| `key` | string | - | Streamlit component key |

## Event Data Format

### Click Event
```json
{
  "type": "click",
  "lat": -6.1750,
  "lng": 106.8270,
  "timestamp": 1713628800000,
  "event_id": "unique_id"
}
```

### AOI Event
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

## Prediction Overlay Format

The component accepts GeoJSON FeatureCollection for risk visualization:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [lon, lat]
      },
      "properties": {
        "prediction": 0.75,
        "risk_level": "High",
        "latitude": lat,
        "longitude": lon
      }
    }
  ]
}
```

## Development Notes

### Leaflet Icons
Leaflet requires explicit icon URLs in React. The component includes a fix:
```typescript
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});
```

### Streamlit Integration
- Uses `Streamlit.setComponentValue()` to send events
- Uses `Streamlit.setComponentReady()` to notify readiness
- Receives data via `props.args`

### Styling
- CSS imported via `import 'leaflet/dist/leaflet.css'`
- Custom styles in `index.css`
- Responsive design with 100% width/height

## Testing

### Development Server
```bash
npm run dev
```
Open http://localhost:3000

### Build Test
```bash
npm run build
npm run preview
```

### Integration Test
1. Build the component
2. Run Streamlit demo app
3. Test click and draw functionality

## Troubleshooting

### Map Not Loading
1. Check Leaflet CSS/JS imports
2. Verify CDN URLs are accessible
3. Check browser console for errors

### Events Not Sending
1. Verify Streamlit component is mounted
2. Check `Streamlit.setComponentValue()` calls
3. Look for JavaScript errors

### Performance Issues
1. Limit prediction overlay size
2. Use efficient GeoJSON structures
3. Implement debouncing for rapid events

## Dependencies

- `react` & `react-dom`: UI framework
- `leaflet`: Map rendering
- `leaflet-draw`: Drawing tools
- `streamlit-component-lib`: Streamlit integration
- `@types/*`: TypeScript definitions
- `vite`: Build tool

## License

Part of FireCast project. See main project license.