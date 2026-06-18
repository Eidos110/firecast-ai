import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet-draw';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import { Streamlit, ComponentProps } from 'streamlit-component-lib';

// Helper to safely call Streamlit methods
const safeSetComponentReady = () => {
  try {
    if (typeof Streamlit !== 'undefined' && Streamlit && typeof Streamlit.setComponentReady === 'function') {
      Streamlit.setComponentReady();
    } else {
      console.warn('Streamlit.setComponentReady not available');
    }
  } catch (e) {
    console.error('Error calling Streamlit.setComponentReady:', e);
  }
};

const safeSetComponentValue = (value: any) => {
  try {
    if (typeof Streamlit !== 'undefined' && Streamlit && typeof Streamlit.setComponentValue === 'function') {
      Streamlit.setComponentValue(value);
    } else {
      console.warn('Streamlit.setComponentValue not available');
    }
  } catch (e) {
    console.error('Error calling Streamlit.setComponentValue:', e);
  }
};

// Fix ikon default Leaflet di React/Vite
try {
  delete (L.Icon.Default.prototype as any)._getIconUrl;
} catch (e) {
  // ignore if not deletable
}
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

export function InteractiveMap(props: ComponentProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const drawnItems = useRef<L.FeatureGroup | null>(null);
  const lastEventId = useRef<number>(Date.now());
  const clickMarkerRef = useRef<L.Marker | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    try {
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
      mapInstance.current.on('click', (e: L.LeafletMouseEvent) => {
        const eventId = Date.now();
        lastEventId.current = eventId;

        // Add or update marker at click location
        if (clickMarkerRef.current) {
          clickMarkerRef.current.setLatLng(e.latlng);
        } else {
          clickMarkerRef.current = L.marker(e.latlng).addTo(mapInstance.current!);
        }

        safeSetComponentValue({
          type: 'click',
          lat: e.latlng.lat,
          lng: e.latlng.lng,
          timestamp: eventId,
          event_id: eventId
        });
      });

      // Event: Draw Created
      mapInstance.current.on(L.Draw.Event.CREATED, (e: any) => {
        const layer = e.layer;
        drawnItems.current?.addLayer(layer);
        
        const eventId = Date.now();
        lastEventId.current = eventId;
        
        safeSetComponentValue({
          type: 'aoi',
          geometry: layer.toGeoJSON(),
          timestamp: eventId,
          event_id: eventId
        });
      });

      // Event: Draw Edited
      mapInstance.current.on(L.Draw.Event.EDITED, (e: any) => {
        const layers = e.layers;
        const updatedGeoJSONs: any[] = [];
        
        layers.eachLayer((layer: L.Layer) => {
          if (layer instanceof L.Polygon) {
            updatedGeoJSONs.push(layer.toGeoJSON());
          }
        });
        
        const eventId = Date.now();
        lastEventId.current = eventId;
        
        safeSetComponentValue({
          type: 'aoi_updated',
          geometries: updatedGeoJSONs,
          timestamp: eventId,
          event_id: eventId
        });
      });

      // Event: Draw Deleted
      mapInstance.current.on(L.Draw.Event.DELETED, (e: any) => {
        const layers = e.layers;
        const deletedGeoJSONs: any[] = [];
        
        layers.eachLayer((layer: L.Layer) => {
          if (layer instanceof L.Polygon) {
            deletedGeoJSONs.push(layer.toGeoJSON());
          }
        });
        
        const eventId = Date.now();
        lastEventId.current = eventId;
        
        safeSetComponentValue({
          type: 'aoi_deleted',
          geometries: deletedGeoJSONs,
          timestamp: eventId,
          event_id: eventId
        });
      });

    } catch (error) {
      console.error('Error initializing InteractiveMap:', error);
      setError(`Failed to initialize map: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      // Notify Streamlit that component is ready (always)
      try {
        safeSetComponentReady();
      } catch (readyErr) {
        console.error('Error marking component ready:', readyErr);
        if (!error) {
          setError(`Failed to initialize component: ${readyErr instanceof Error ? readyErr.message : String(readyErr)}`);
        }
      }
    }

    // Cleanup function
    return () => {
      if (mapInstance.current) {
        // Remove all event listeners before removing map
        mapInstance.current.off();
        mapInstance.current.remove();
        mapInstance.current = null;
      }
      if (clickMarkerRef.current) {
        clickMarkerRef.current.remove();
        clickMarkerRef.current = null;
      }
      if (drawnItems.current) {
        drawnItems.current.clearLayers();
        drawnItems.current = null;
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
              const properties = feature.properties || {};
              const risk = properties.prediction || 0;
              const riskLevel = getRiskLevel(risk);
              const markerType = properties.marker_type || 'batch';

              let marker: L.CircleMarker | L.Marker;

              if (markerType === 'single') {
                // Custom fire icon for single point
                const icon = L.divIcon({
                  className: 'single-point-marker',
                  html: `<div style="
                    font-family: sans-serif;
                    font-size: 28px;
                    color: ${getRiskColor(riskLevel)};
                    text-shadow: 0 0 4px #000, 0 0 8px #000;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    line-height: 1;
                  ">🔥</div>`,
                  iconSize: [28, 28],
                  iconAnchor: [14, 14],
                });
                marker = L.marker(latlng, { icon }) as L.Marker;
              } else {
                // Batch point – circle marker
                marker = L.circleMarker(latlng, {
                  radius: 8 + risk * 12,
                  fillColor: getRiskColor(riskLevel),
                  color: '#000',
                  weight: 1,
                  opacity: 1,
                  fillOpacity: 0.7
                }) as L.CircleMarker;
              }

               // Popup with info
               marker.bindPopup(`
                 <div style="
                   font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                   font-size: 13px;
                   line-height: 1.5;
                   min-width: 140px;
                 ">
                   <strong style="display: block; margin-bottom: 4px; font-weight: 600; color: ${getRiskColor(riskLevel)}">
                     Risk: ${riskLevel}
                   </strong>
                   <div style="color: #64748b; font-size: 12px;">
                     <div>Score: ${(risk * 100).toFixed(1)}%</div>
                     <div>Lat: ${latlng.lat.toFixed(4)}</div>
                     <div>Lon: ${latlng.lng.toFixed(4)}</div>
                   </div>
                 </div>
               `);

              // Click handler: send to Streamlit and prevent map click
              marker.on('click', (e: L.LeafletMouseEvent) => {
                const lat = e.latlng.lat;
                const lon = e.latlng.lng;
                // Stop event from bubbling to map click
                if (mapInstance.current) {
                  L.DomEvent.stopPropagation(e);
                }
                safeSetComponentValue({
                  type: 'marker_click',
                  lat,
                  lng,
                  risk: risk,
                  risk_level: riskLevel,
                  timestamp: Date.now(),
                  event_id: Date.now()
                });
              });

              return marker;
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
            
            layer.bindPopup(`
              <div style="
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 13px;
                line-height: 1.5;
                min-width: 120px;
              ">
                <strong style="
                  display: block;
                  margin-bottom: 4px;
                  font-weight: 600;
                  color: ${getRiskColor(riskLevel)}
                ">
                  Risk: ${riskLevel}
                </strong>
                <div style="color: #64748b; font-size: 12px;">
                  Score: ${(risk * 100).toFixed(1)}%
                </div>
              </div>
            `);
          }
        }).addTo(drawnItems.current);
        
        // Fit bounds to the new overlay
        mapInstance.current?.fitBounds(geoJSON.getBounds());
      } catch (error) {
        console.error('Error rendering prediction overlay:', error);
        setError(`Failed to render prediction: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }, [props.args.predictionOverlay]);

  return (
    <div className="map-container" ref={mapRef} style={{ height: props.height || 600 }}>
      {error && (
        <div className="error-display" role="alert">
          <strong>Map Error</strong>
          <span>{error}</span>
          <button onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )}
    </div>
  );
}

// Helper functions for risk visualization
function getRiskLevel(risk: number): string {
  if (risk >= 0.8) return 'Extreme';
  if (risk >= 0.6) return 'High';
  if (risk >= 0.3) return 'Medium';
  return 'Low';
}

function getRiskColor(riskLevel: string): string {
  const colors: Record<string, string> = {
    'Low': '#22c55e',
    'Medium': '#f59e0b',
    'High': '#ef4444',
    'Extreme': '#991b1b'
  };
  return colors[riskLevel] || '#f59e0b';
}

export default InteractiveMap;