"""
Simple Interactive Map Component for Streamlit
No React build required - uses inline HTML/JavaScript
"""

import streamlit as st
import streamlit.components.v1 as components
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def create_interactive_map_component():
    """
    Create interactive map component with inline HTML/JavaScript.
    No React build required.
    """

    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
            integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
            crossorigin=""/>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css"/>
        <style>
            #map { 
                height: 600px;
                width: 100%;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
            .leaflet-container {
                font-family: inherit;
            }
            .leaflet-draw-toolbar {
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div id="map"></div>
        
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js"></script>
        
        <script>
            // Initialize map
            const map = L.map('map').setView([-6.175, 106.827], 12);
            
            // Add OpenStreetMap tiles
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);
            
            // Feature group for drawn items
            const drawnItems = new L.FeatureGroup();
            map.addLayer(drawnItems);
            
            // Draw control (only polygon)
            const drawControl = new L.Control.Draw({
                draw: {
                    polygon: true,
                    rectangle: false,
                    circle: false,
                    marker: false,
                    polyline: false,
                    circlemarker: false
                },
                edit: {
                    featureGroup: drawnItems,
                    remove: true
                }
            });
            map.addControl(drawControl);
            
            // Event counter for unique IDs
            let eventCounter = 0;
            
            // Function to send data to Streamlit
            function sendToStreamlit(data) {
                const eventId = Date.now() + '_' + (eventCounter++);
                data.event_id = eventId;
                data.timestamp = Date.now();
                
                // Send to Streamlit
                if (window.parent) {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: data
                    }, '*');
                }
                
                console.log('Sent to Streamlit:', data);
            }
            
            // Click event
            map.on('click', function(e) {
                sendToStreamlit({
                    type: 'click',
                    lat: e.latlng.lat,
                    lng: e.latlng.lng
                });
            });
            
            // Draw created event
            map.on(L.Draw.Event.CREATED, function(e) {
                const layer = e.layer;
                drawnItems.addLayer(layer);
                
                sendToStreamlit({
                    type: 'aoi',
                    geometry: layer.toGeoJSON()
                });
            });
            
            // Draw edited event
            map.on(L.Draw.Event.EDITED, function(e) {
                const layers = e.layers;
                const geometries = [];
                
                layers.eachLayer(function(layer) {
                    if (layer instanceof L.Polygon) {
                        geometries.push(layer.toGeoJSON());
                    }
                });
                
                sendToStreamlit({
                    type: 'aoi_updated',
                    geometries: geometries
                });
            });
            
            // Draw deleted event
            map.on(L.Draw.Event.DELETED, function(e) {
                const layers = e.layers;
                const geometries = [];
                
                layers.eachLayer(function(layer) {
                    if (layer instanceof L.Polygon) {
                        geometries.push(layer.toGeoJSON());
                    }
                });
                
                sendToStreamlit({
                    type: 'aoi_deleted',
                    geometries: geometries
                });
            });
            
            // Function to render prediction overlay
            window.renderPredictionOverlay = function(geojsonData) {
                if (!geojsonData) return;
                
                // Clear existing overlays
                drawnItems.clearLayers();
                
                try {
                    const geoJsonLayer = L.geoJSON(geojsonData, {
                        pointToLayer: function(feature, latlng) {
                            const props = feature.properties || {};
                            const risk = props.prediction || 0;
                            const riskLevel = getRiskLevel(risk);
                            
                            return L.circleMarker(latlng, {
                                radius: 8 + risk * 12,
                                fillColor: getRiskColor(riskLevel),
                                color: '#000',
                                weight: 1,
                                opacity: 1,
                                fillOpacity: 0.7
                            }).bindPopup(
                                '<b>Risk: ' + riskLevel + '</b><br>' +
                                'Score: ' + (risk * 100).toFixed(1) + '%<br>' +
                                'Lat: ' + latlng.lat.toFixed(4) + '<br>' +
                                'Lon: ' + latlng.lng.toFixed(4)
                            );
                        },
                        style: function(feature) {
                            const props = feature.properties || {};
                            const risk = props.prediction || 0;
                            const riskLevel = getRiskLevel(risk);
                            
                            return {
                                fillColor: getRiskColor(riskLevel),
                                weight: 2,
                                opacity: 1,
                                color: '#000',
                                fillOpacity: 0.4
                            };
                        },
                        onEachFeature: function(feature, layer) {
                            const props = feature.properties || {};
                            const risk = props.prediction || 0;
                            const riskLevel = getRiskLevel(risk);
                            
                            layer.bindPopup(
                                '<b>Risk: ' + riskLevel + '</b><br>' +
                                'Score: ' + (risk * 100).toFixed(1) + '%'
                            );
                        }
                    }).addTo(drawnItems);
                    
                    // Fit bounds to overlay
                    map.fitBounds(geoJsonLayer.getBounds());
                    
                } catch (error) {
                    console.error('Error rendering prediction overlay:', error);
                }
            };
            
            // Helper functions
            function getRiskLevel(risk) {
                if (risk >= 0.8) return 'Extreme';
                if (risk >= 0.6) return 'High';
                if (risk >= 0.3) return 'Medium';
                return 'Low';
            }
            
            function getRiskColor(riskLevel) {
                const colors = {
                    'Low': '#22c55e',
                    'Medium': '#f59e0b',
                    'High': '#ef4444',
                    'Extreme': '#991b1b'
                };
                return colors[riskLevel] || '#f59e0b';
            }
            
            // Notify Streamlit that component is ready
            if (window.parent) {
                window.parent.postMessage({
                    type: 'streamlit:componentReady',
                    value: true
                }, '*');
            }
            
            console.log('Interactive map initialized');
        </script>
    </body>
    </html>
    """

    return components.html(html_code, height=650)


def create_simple_interactive_map(height=600, prediction_overlay=None):
    """
    Create a simple interactive map without React build.

    Args:
        height: Map height in pixels
        prediction_overlay: GeoJSON data for prediction visualization

    Returns:
        Streamlit component
    """

    # Create HTML with dynamic height
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
            integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
            crossorigin=""/>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css"/>
        <style>
            #map { 
                height: {{HEIGHT}}px;
                width: 100%;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
            .leaflet-container {
                font-family: inherit;
            }
        </style>
    </head>
    <body>
        <div id="map"></div>
        
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js"></script>
        
        <script>
            // Initialize map
            const map = L.map('map').setView([-6.175, 106.827], 12);
            
            // Add OpenStreetMap tiles
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);
            
            // Feature group for drawn items
            const drawnItems = new L.FeatureGroup();
            map.addLayer(drawnItems);
            
            // Draw control (only polygon)
            const drawControl = new L.Control.Draw({
                draw: {
                    polygon: true,
                    rectangle: false,
                    circle: false,
                    marker: false,
                    polyline: false
                },
                edit: {
                    featureGroup: drawnItems,
                    remove: true
                }
            });
            map.addControl(drawControl);
            
            // Event handling
            let lastEventId = 0;
            
            function sendEventToParent(type, data) {
                const eventId = Date.now();
                if (eventId === lastEventId) return;
                lastEventId = eventId;
                
                const eventData = {
                    type: type,
                    ...data,
                    timestamp: eventId,
                    event_id: eventId.toString()
                };
                
                // Send to Streamlit
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: eventData
                }, '*');
                
                console.log('Event sent:', eventData);
            }
            
            // Map events
            map.on('click', function(e) {
                sendEventToParent('click', {
                    lat: e.latlng.lat,
                    lng: e.latlng.lng
                });
            });
            
            map.on(L.Draw.Event.CREATED, function(e) {
                const layer = e.layer;
                drawnItems.addLayer(layer);
                
                sendEventToParent('aoi', {
                    geometry: layer.toGeoJSON()
                });
            });
            
            map.on(L.Draw.Event.EDITED, function(e) {
                const layers = e.layers;
                const geometries = [];
                
                layers.eachLayer(function(layer) {
                    geometries.push(layer.toGeoJSON());
                });
                
                sendEventToParent('aoi_updated', {
                    geometries: geometries
                });
            });
            
            map.on(L.Draw.Event.DELETED, function(e) {
                const layers = e.layers;
                const geometries = [];
                
                layers.eachLayer(function(layer) {
                    geometries.push(layer.toGeoJSON());
                });
                
                sendEventToParent('aoi_deleted', {
                    geometries: geometries
                });
            });
            
            // Render prediction overlay if provided
            {% if PREDICTION_OVERLAY %}
            try {
                const predictionData = {{PREDICTION_OVERLAY|safe}};
                renderPredictionOverlay(predictionData);
            } catch (error) {
                console.error('Error loading prediction overlay:', error);
            }
            {% endif %}
            
            // Function to render prediction overlay
            function renderPredictionOverlay(geojsonData) {
                if (!geojsonData) return;
                
                drawnItems.clearLayers();
                
                try {
                    const geoJsonLayer = L.geoJSON(geojsonData, {
                        pointToLayer: function(feature, latlng) {
                            const props = feature.properties || {};
                            const risk = props.prediction || 0;
                            const radius = 6 + risk * 10;
                            const color = getRiskColor(risk);
                            
                            return L.circleMarker(latlng, {
                                radius: radius,
                                fillColor: color,
                                color: '#000',
                                weight: 1,
                                opacity: 0.8,
                                fillOpacity: 0.6
                            }).bindPopup(
                                '<b>Risk: ' + (risk * 100).toFixed(1) + '%</b><br>' +
                                'Lat: ' + latlng.lat.toFixed(4) + '<br>' +
                                'Lon: ' + latlng.lng.toFixed(4)
                            );
                        }
                    }).addTo(drawnItems);
                    
                    if (geoJsonLayer.getBounds().isValid()) {
                        map.fitBounds(geoJsonLayer.getBounds());
                    }
                    
                } catch (error) {
                    console.error('Error rendering overlay:', error);
                }
            }
            
            // Helper function to get risk color
            function getRiskColor(risk) {
                if (risk >= 0.8) return '#dc2626';
                if (risk >= 0.6) return '#ef4444';
                if (risk >= 0.3) return '#f59e0b';
                return '#22c55e';
            }
            
            // Notify ready
            window.parent.postMessage({
                type: 'streamlit:componentReady',
                value: true
            }, '*');
            
        </script>
    </body>
    </html>
    """

    # Prepare prediction overlay JSON
    prediction_json = "null"
    if prediction_overlay:
        try:
            prediction_json = json.dumps(prediction_overlay)
        except (TypeError, ValueError):
            prediction_json = "null"

    # Replace template variables
    html = html_template.replace("{{HEIGHT}}", str(height))
    html = html.replace("{{PREDICTION_OVERLAY|safe}}", prediction_json)

    return components.html(html, height=height + 50)


# Simple event handler functions (same as before)
def initialize_session_state():
    """Initialize session state for interactive map."""
    defaults = {
        "map_output": None,
        "prediction_result": None,
        "aoi_geojson": None,
        "last_event_id": None,
        "click_history": [],
        "aoi_history": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def handle_map_event(event_data):
    """
    Handle map event from JavaScript component.

    Args:
        event_data: Event data from map

    Returns:
        True if event was processed
    """
    if not event_data:
        return False

    event_type = event_data.get("type")
    event_id = event_data.get("event_id")

    # Check for duplicate events
    if event_id and event_id == st.session_state.get("last_event_id"):
        logger.debug(f"Ignoring duplicate event: {event_id}")
        return False

    st.session_state.last_event_id = event_id
    st.session_state.map_output = event_data

    if event_type == "click":
        return handle_click_event(event_data)
    elif event_type == "aoi":
        return handle_aoi_event(event_data)
    elif event_type in ["aoi_updated", "aoi_deleted"]:
        return handle_aoi_update_event(event_data, event_type)

    return False


def handle_click_event(event_data):
    """Handle click event."""
    lat = event_data.get("lat")
    lng = event_data.get("lng")

    if lat is None or lng is None:
        return False

    # Store in history
    click_entry = {
        "lat": lat,
        "lng": lng,
        "timestamp": event_data.get("timestamp"),
        "datetime": datetime.fromtimestamp(
            event_data.get("timestamp", 0) / 1000
        ).isoformat()
        if event_data.get("timestamp")
        else None,
    }

    st.session_state.click_history.append(click_entry)
    if len(st.session_state.click_history) > 50:
        st.session_state.click_history = st.session_state.click_history[-50:]

    logger.info(f"Map click at: ({lat:.4f}, {lng:.4f})")

    # Update selected location
    st.session_state.selected_location = {
        "lat": lat,
        "lon": lng,
        "name": f"Click: {lat:.4f}, {lng:.4f}",
        "zoom": 12,
    }

    return True


def handle_aoi_event(event_data):
    """Handle AOI drawing event."""
    geometry = event_data.get("geometry")

    if not geometry:
        return False

    # Store in history
    aoi_entry = {
        "geometry": geometry,
        "timestamp": event_data.get("timestamp"),
        "datetime": datetime.fromtimestamp(
            event_data.get("timestamp", 0) / 1000
        ).isoformat()
        if event_data.get("timestamp")
        else None,
        "type": "created",
    }

    st.session_state.aoi_history.append(aoi_entry)
    st.session_state.aoi_geojson = geometry

    logger.info("AOI drawn")

    return True


def handle_aoi_update_event(event_data, event_type):
    """Handle AOI update/delete events."""
    geometries = event_data.get("geometries", [])

    if not geometries:
        return False

    # Store in history
    update_entry = {
        "geometries": geometries,
        "timestamp": event_data.get("timestamp"),
        "datetime": datetime.fromtimestamp(
            event_data.get("timestamp", 0) / 1000
        ).isoformat()
        if event_data.get("timestamp")
        else None,
        "type": event_type,
    }

    st.session_state.aoi_history.append(update_entry)

    if event_type == "aoi_updated" and geometries:
        st.session_state.aoi_geojson = geometries[0]
        logger.info(f"AOI updated: {len(geometries)} geometries")
    elif event_type == "aoi_deleted":
        st.session_state.aoi_geojson = None
        logger.info(f"AOI deleted: {len(geometries)} geometries")

    return True


def get_aoi_coordinates():
    """Extract coordinates from current AOI."""
    aoi_geojson = st.session_state.get("aoi_geojson")
    if not aoi_geojson:
        return []

    try:
        geometry = aoi_geojson.get("geometry", {})
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])

        if geom_type == "Polygon" and coordinates:
            # Polygon coordinates are nested: [[[lon, lat], ...]]
            ring = coordinates[0]  # First ring (exterior)
            return [[lat, lon] for lon, lat in ring]  # Convert to [lat, lon]
        elif geom_type == "Point" and coordinates:
            # Point coordinates: [lon, lat]
            lon, lat = coordinates
            return [[lat, lon]]
    except Exception as e:
        logger.error(f"Error extracting AOI coordinates: {e}")

    return []
