import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet-draw';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import { Streamlit } from 'streamlit-component-lib';
// Fix ikon default Leaflet di React/Vite
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
    iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
    shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});
export function InteractiveMap(props) {
    const mapRef = useRef(null);
    const mapInstance = useRef(null);
    const drawnItems = useRef(null);
    const lastEventId = useRef(Date.now());
    useEffect(() => {
        if (!mapRef.current || mapInstance.current)
            return;
        // Inisialisasi peta
        mapInstance.current = L.map(mapRef.current).setView([-6.175, 106.827], 12);
        // Tambahkan tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(mapInstance.current);
        // Layer untuk AOI
        drawnItems.current = new L.FeatureGroup();
        mapInstance.current.addLayer(drawnItems.current);
        // Kontrol Draw (hanya Polygon)
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
                featureGroup: drawnItems.current,
                remove: true
            }
        });
        mapInstance.current.addControl(drawControl);
        // Event: Click
        mapInstance.current.on('click', (e) => {
            const eventId = Date.now();
            lastEventId.current = eventId;
            Streamlit.setComponentValue({
                type: 'click',
                lat: e.latlng.lat,
                lng: e.latlng.lng,
                timestamp: eventId,
                event_id: eventId
            });
        });
        // Event: Draw Created
        mapInstance.current.on(L.Draw.Event.CREATED, (e) => {
            const layer = e.layer;
            drawnItems.current?.addLayer(layer);
            const eventId = Date.now();
            lastEventId.current = eventId;
            Streamlit.setComponentValue({
                type: 'aoi',
                geometry: layer.toGeoJSON(),
                timestamp: eventId,
                event_id: eventId
            });
        });
        // Event: Draw Edited
        mapInstance.current.on(L.Draw.Event.EDITED, (e) => {
            const layers = e.layers;
            const updatedGeoJSONs = [];
            layers.eachLayer((layer) => {
                if (layer instanceof L.Polygon) {
                    updatedGeoJSONs.push(layer.toGeoJSON());
                }
            });
            const eventId = Date.now();
            lastEventId.current = eventId;
            Streamlit.setComponentValue({
                type: 'aoi_updated',
                geometries: updatedGeoJSONs,
                timestamp: eventId,
                event_id: eventId
            });
        });
        // Event: Draw Deleted
        mapInstance.current.on(L.Draw.Event.DELETED, (e) => {
            const layers = e.layers;
            const deletedGeoJSONs = [];
            layers.eachLayer((layer) => {
                if (layer instanceof L.Polygon) {
                    deletedGeoJSONs.push(layer.toGeoJSON());
                }
            });
            const eventId = Date.now();
            lastEventId.current = eventId;
            Streamlit.setComponentValue({
                type: 'aoi_deleted',
                geometries: deletedGeoJSONs,
                timestamp: eventId,
                event_id: eventId
            });
        });
        // Notify Streamlit that component is ready
        Streamlit.setComponentReady();
        // Cleanup function
        return () => {
            if (mapInstance.current) {
                mapInstance.current.remove();
                mapInstance.current = null;
            }
        };
    }, []);
    // Terima data dari Python (misal: hasil prediksi untuk di-render)
    useEffect(() => {
        if (props.args.predictionOverlay && mapInstance.current && drawnItems.current) {
            // Hapus overlay lama
            drawnItems.current.clearLayers();
            // Render GeoJSON baru
            try {
                const geoJSON = L.geoJSON(props.args.predictionOverlay, {
                    pointToLayer: (feature, latlng) => {
                        // Custom styling untuk points
                        const properties = feature.properties || {};
                        const risk = properties.prediction || 0;
                        const riskLevel = getRiskLevel(risk);
                        return L.circleMarker(latlng, {
                            radius: 8 + risk * 12,
                            fillColor: getRiskColor(riskLevel),
                            color: '#000',
                            weight: 1,
                            opacity: 1,
                            fillOpacity: 0.7
                        }).bindPopup(`<b>Risk: ${riskLevel}</b><br>Score: ${(risk * 100).toFixed(1)}%<br>` +
                            `Lat: ${latlng.lat.toFixed(4)}<br>Lon: ${latlng.lng.toFixed(4)}`);
                    },
                    style: (feature) => {
                        // Styling untuk polygons
                        const properties = feature.properties || {};
                        const risk = properties.prediction || 0;
                        const riskLevel = getRiskLevel(risk);
                        return {
                            fillColor: getRiskColor(riskLevel),
                            weight: 2,
                            opacity: 1,
                            color: '#000',
                            fillOpacity: 0.4
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        // Add popup for each feature
                        const properties = feature.properties || {};
                        const risk = properties.prediction || 0;
                        const riskLevel = getRiskLevel(risk);
                        layer.bindPopup(`<b>Risk: ${riskLevel}</b><br>Score: ${(risk * 100).toFixed(1)}%`);
                    }
                }).addTo(drawnItems.current);
                // Fit bounds to the new overlay
                mapInstance.current?.fitBounds(geoJSON.getBounds());
            }
            catch (error) {
                console.error('Error rendering prediction overlay:', error);
            }
        }
    }, [props.args.predictionOverlay]);
    return (_jsx("div", { ref: mapRef, style: {
            width: '100%',
            height: props.args.height || 600,
            borderRadius: '8px',
            overflow: 'hidden',
            border: '1px solid #e0e0e0'
        } }));
}
// Helper functions for risk visualization
function getRiskLevel(risk) {
    if (risk >= 0.8)
        return 'Extreme';
    if (risk >= 0.6)
        return 'High';
    if (risk >= 0.3)
        return 'Medium';
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
export default InteractiveMap;
