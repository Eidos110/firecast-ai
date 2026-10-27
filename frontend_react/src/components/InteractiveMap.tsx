/**
 * InteractiveMap — Engineer Console map pane for the FireCast React SPA.
 *
 * Replaces the legacy Streamlit-component (`streamlit-component-lib`) bridge
 * with a plain React component. State flows in and out via props:
 *   - `selectedCell`/`onCellSelect` → click-to-predict
 *   - `aoi`/`onAoiDrawn`/`onAoiUpdated`/`onAoiDeleted` → polygon AOI drawing
 *   - `overlay` → GeoJSON FeatureCollection batch-prediction overlay
 *   - `layers` → which map layers are visible (legend toggles handled here)
 *
 * Heavy Leaflet init runs once via useEffect([]). Cleanup is mandatory per
 * Leaflet's docs ("map.remove()") to keep React StrictMode double-mount safe.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import L from 'leaflet';
import 'leaflet-draw';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';

import { getRiskColor, getRiskLevel, type RiskTierLabel } from '../theme/risk';
import type { PredictionOverlay } from '../store/inferenceStore';
import { logWarn, logError } from '../utils/log';

/**
 * Tile sources tried in order. CARTO ``dark_all`` matches the V4 dark
 * mockup; Stadia ``alidade_smooth_dark`` is a high-availability fallback
 * with the same dark look so the map doesn't go blank when CARTO is
 * blocked (sandbox, HF Spaces egress rules, ISP block, rate limit). The
 * third is a plain Light OSM tile used only if both dark providers fail —
 * better visible-but-bright than invisible.
 *
 * ``subdomains`` mirrors each provider's documented subdomain set so the
 * browser opens more parallel connections (Leaflet default is ``abc``).
 */
const TILE_SOURCES = [
  {
    name: 'carto-dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd',
    maxZoom: 19,
    attribution: '© OpenStreetMap © CARTO',
  },
  {
    name: 'stadia-dark',
    url: 'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd',
    maxZoom: 20,
    attribution: '© OpenStreetMap © Stadia Maps',
  },
  {
    name: 'osm-standard',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    subdomains: 'abc',
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors',
  },
] as const;

/**
 * After this many failed tile loads on the current source, swap to the
 * next source in ``TILE_SOURCES``. Tuned so a handful of normal in-flight
 * 404s (zoom level edge cases) doesn't trigger a fallback, but a full
 * provider outage is detected within ~2 visible rows of tiles.
 */
const TILE_ERROR_THRESHOLD = 5;

/** Visible status badge shown over the map when tile loads are failing. */
type TileStatus = { level: 'ok' | 'warn' | 'err'; message: string; source: string };

export interface MapPoint {
  lat: number;
  lon: number;
}

export interface MapLayerConfig {
  id: string;
  label: string;
  active: boolean;
  opacity: number;
}

export interface InteractiveMapProps {
  /** Currently selected cell — places a marker on the map. */
  selectedCell?: MapPoint | null;
  /** Fires when the user clicks the map. */
  onCellSelect?: (point: MapPoint) => void;

  /** The active AOI polygon (GeoJSON Feature). */
  aoi?: GeoJSON.Feature | null;
  /** Fires when a new AOI is drawn. */
  onAoiDrawn?: (feature: GeoJSON.Feature) => void;
  /** Fires when an existing AOI is edited. */
  onAoiUpdated?: (feature: GeoJSON.Feature) => void;
  /** Fires when an AOI is deleted. */
  onAoiDeleted?: () => void;

  /** Risk-overlay circles/markers from /predict/aoi batch. */
  overlay?: PredictionOverlay | null;

  /** Layer toggles — used by the left sidebar; rendered here as Leaflet layers. */
  layers?: MapLayerConfig[];

  /** Default center (lat, lon) and zoom when nothing is selected. */
  initialCenter?: [number, number];
  initialZoom?: number;
  height?: number | string;

  className?: string;
}

// Fix default Leaflet marker icons. Use bundled local assets under
// ``/leaflet/*`` (served from ``public/leaflet/*`` and copied verbatim into
// the build root by Vite) instead of an unpkg CDN request so the map keeps
// working in air-gapped HF Spaces / strict CSP environments. try/catch so
// SSR / vitest doesn't crash attempting the delete.
try {
  delete (L.Icon.Default.prototype as any)._getIconUrl;
} catch {
  /* no-op in strict environments */
}
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'leaflet/marker-icon-2x.png',
  iconUrl: 'leaflet/marker-icon.png',
  shadowUrl: 'leaflet/marker-shadow.png',
});

export function InteractiveMap(props: InteractiveMapProps): JSX.Element {
  const {
    selectedCell,
    onCellSelect,
    aoi,
    onAoiDrawn,
    onAoiUpdated,
    onAoiDeleted,
    overlay,
    layers,
    initialCenter = [-1.8, 113.5],
    initialZoom = 7,
    height = '100%',
    className,
  } = props;

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const tileSourceIdxRef = useRef<number>(0);
  const tileErrorCountRef = useRef<number>(0);
  const drawnItems = useRef<L.FeatureGroup | null>(null);
  /** Measurement-ruler FeatureGroup (ROADMAP §3-W4) — separate from
   * ``drawnItems`` so measure polylines don't trigger the AOI flow. */
  const measureItems = useRef<L.FeatureGroup | null>(null);
  const overlayLayer = useRef<L.LayerGroup | null>(null);
  const clickMarkerRef = useRef<L.Marker | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tileStatus, setTileStatus] = useState<TileStatus | null>(null);
  const { t } = useTranslation();
  // Keep the latest ``t`` available to the once-mounted tile handlers so a
  // language switch at runtime surfaces the right message without needing
  // to remount Leaflet.
  const tRef = useRef(t);
  tRef.current = t;

  // === Mount: init the map once ===
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;
    try {
      mapInstance.current = L.map(mapRef.current).setView(initialCenter, initialZoom);

      // === Tile layer with multi-provider fail-over ===
      // CARTO dark is the primary; on repeated tileerror Leaflet silently
      // shows blank squares. We count failures and swap to the next
      // provider in TILE_SOURCES once the threshold is crossed, so an
      // outage on basemaps.cartocdn.com (sandbox/egress block, rate limit,
      // geo-blocking) doesn't leave the engineer staring at a #0a0e13
      // void. crossOrigin=true lets the canvas renderer work behind TLS
      // proxies (HF Spaces / nginx).
      const addTileLayer = (idx: number): L.TileLayer | null => {
        const map = mapInstance.current;
        if (!map) return null;
        const src = TILE_SOURCES[idx];
        if (!src) {
          setTileStatus({ level: 'err', message: tRef.current('spa.map.tile.all_failed'), source: 'none' });
          return null;
        }
        const layer = L.tileLayer(src.url, {
          subdomains: src.subdomains,
          maxZoom: src.maxZoom,
          minZoom: 3,
          attribution: src.attribution,
          crossOrigin: true,
        });
        layer.on('tileerror', (ev: L.TileEvent & { tile?: HTMLImageElement }) => {
          tileErrorCountRef.current += 1;
          const errCount = tileErrorCountRef.current;
          const srcName = TILE_SOURCES[tileSourceIdxRef.current]?.name ?? '?';
          logWarn(`[map] tileerror #${errCount} on ${srcName}`, ev?.tile?.src);
          setTileStatus({
            level: errCount >= TILE_ERROR_THRESHOLD ? 'err' : 'warn',
            message: `${tRef.current('spa.map.tile.failing')} (${errCount})`,
            source: srcName,
          });
          if (errCount >= TILE_ERROR_THRESHOLD) {
            const nextIdx = tileSourceIdxRef.current + 1;
            if (nextIdx < TILE_SOURCES.length) {
              logWarn(`[map] switching tile source ${srcName} -> ${TILE_SOURCES[nextIdx].name}`);
              setTileStatus({
                level: 'warn',
                message: tRef.current('spa.map.tile.fallback', { from: srcName, to: TILE_SOURCES[nextIdx].name }),
                source: TILE_SOURCES[nextIdx].name,
              });
              if (tileLayerRef.current) {
                tileLayerRef.current.remove();
              }
              tileSourceIdxRef.current = nextIdx;
              tileErrorCountRef.current = 0;
              tileLayerRef.current = addTileLayer(nextIdx);
            } else {
              setTileStatus({ level: 'err', message: tRef.current('spa.map.tile.all_failed'), source: srcName });
            }
          }
        });
        layer.on('load', () => {
          // All visible tiles loaded for the current view — clear transient
          // warnings.
          tileErrorCountRef.current = 0;
          setTileStatus((s) => {
            if (!s) return { level: 'ok', message: tRef.current('spa.map.tile.ready'), source: src.name };
            if (s.level === 'err') return s; // hard failure stays until page reload
            return { level: 'ok', message: tRef.current('spa.map.tile.ready'), source: src.name };
          });
        });
        layer.addTo(map);
        return layer;
      };

      tileLayerRef.current = addTileLayer(0);

      drawnItems.current = new L.FeatureGroup();
      mapInstance.current.addLayer(drawnItems.current);
      overlayLayer.current = new L.LayerGroup();
      mapInstance.current.addLayer(overlayLayer.current);

      // Measurement ruler (ROADMAP §3-W4) — a dedicated FeatureGroup so the
      // ruler is *not* part of ``drawnItems`` (which is wired to the AOI
      // workflow and pushes polygons into the global store). Ruler lines
      // stay local: they don't become AOI, they don't trigger predictions,
      // and they get cleared automatically by the draw-control when the
      // user deletes them.
      measureItems.current = new L.FeatureGroup();
      mapInstance.current.addLayer(measureItems.current);

      const drawControl = new L.Control.Draw({
        draw: {
          polygon: { allowIntersection: false, showArea: true },
          rectangle: false,
          circle: false,
          marker: false,
          polyline: {
            shapeOptions: { color: 'var(--color-info, #3b82f6)', weight: 3 },
            // Built-in leaflet-draw length metric — shows km underneath
            // the cursor while drawing. ``metric: true`` adds the standard
            // distance label; no need for a custom tooltip component.
            metric: true,
            feet: false,
            showLength: true,
          },
          circlemarker: false,
        } as unknown as L.Control.DrawOptions,
        edit: {
          featureGroup: drawnItems.current,
          remove: true,
        },
      });
      mapInstance.current.addControl(drawControl);

      mapInstance.current.on('click', (e: L.LeafletMouseEvent) => {
        onCellSelect?.({ lat: e.latlng.lat, lon: e.latlng.lng });
      });

      mapInstance.current.on(L.Draw.Event.CREATED, (e: L.LeafletEvent) => {
        const layer = (e as any).layer as L.Layer;
        // Polyline goes to the local ruler group — *not* the AOI store.
        if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
          measureItems.current?.addLayer(layer);
          // Surface the total distance via a simple tooltip so engineers
          // can read it after the fact (ROADMAP §3-W4).
          const latLngs = layer.getLatLngs() as L.LatLng[];
          let metres = 0;
          for (let i = 1; i < latLngs.length; i++) {
            metres += latLngs[i - 1].distanceTo(latLngs[i]);
          }
          const km = metres / 1000;
          const text = tRef.current('spa.map.measurement.total_km', {
            defaultValue: 'Distance: {{km}} km',
            km: km.toFixed(2),
          });
          layer.bindTooltip(text, { sticky: true }).openTooltip();
          return;
        }
        // AOI branches — polygon layers only (markers/circles are disabled).
        drawnItems.current?.addLayer(layer);
        const feature = layerToGeoJSON(layer);
        if (feature) onAoiDrawn?.(feature);
      });

      mapInstance.current.on(L.Draw.Event.EDITED, (e: L.LeafletEvent) => {
        const layers = (e as any).layers as L.LayerGroup;
        let updated: GeoJSON.Feature | null = null;
        layers.eachLayer((layer: L.Layer) => {
          if (layer instanceof L.Polygon) updated = layerToGeoJSON(layer);
        });
        if (updated) onAoiUpdated?.(updated);
      });

      mapInstance.current.on(L.Draw.Event.DELETED, () => {
        onAoiDeleted?.();
      });
    } catch (initError) {
      logError('Error initializing InteractiveMap:', initError);
      setError(initError instanceof Error ? initError.message : String(initError));
    }

    return () => {
      if (mapInstance.current) {
        mapInstance.current.off();
        mapInstance.current.remove();
        mapInstance.current = null;
      }
      tileLayerRef.current = null;
      tileSourceIdxRef.current = 0;
      tileErrorCountRef.current = 0;
      if (clickMarkerRef.current) {
        clickMarkerRef.current.remove();
        clickMarkerRef.current = null;
      }
      if (drawnItems.current) {
        drawnItems.current.clearLayers();
        drawnItems.current = null;
      }
      if (measureItems.current) {
        measureItems.current.clearLayers();
        measureItems.current = null;
      }
      if (overlayLayer.current) {
        overlayLayer.current.clearLayers();
        overlayLayer.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // === selectedCell -> place/move a single marker on the map ===
  useEffect(() => {
    if (!mapInstance.current) return;
    if (!selectedCell) {
      if (clickMarkerRef.current) {
        clickMarkerRef.current.remove();
        clickMarkerRef.current = null;
      }
      return;
    }
    const latlng: L.LatLngExpression = [selectedCell.lat, selectedCell.lon];
    if (clickMarkerRef.current) {
      clickMarkerRef.current.setLatLng(latlng);
    } else {
      clickMarkerRef.current = L.marker(latlng).addTo(mapInstance.current);
    }
  }, [selectedCell]);

  // === aoi -> render the polygon (if drawn externally and pushed in) ===
  useEffect(() => {
    if (!drawnItems.current || !mapInstance.current) return;
    if (!aoi) return;
    try {
      // Render the incoming AOI as a yellow dashed polygon (V4 mock pattern).
      const geo = L.geoJSON(aoi, {
        style: { color: '#ffeb3b', weight: 1, dashArray: '4 4', fillOpacity: 0.05 },
      });
      drawnItems.current.addLayer(geo);
    } catch (e) {
      logWarn('Failed to render AOI overlay:', e);
    }
  }, [aoi]);

  // === overlay -> render risk circles (V4 mock pattern, scaled by score) ===
  useEffect(() => {
    if (!overlayLayer.current) return;
    overlayLayer.current.clearLayers();
    if (!overlay || overlay.features.length === 0) return;
    for (const f of overlay.features) {
      const { prediction, risk_level } = f.properties;
      const label: RiskTierLabel = risk_level ?? getRiskLevel(prediction);
      const color = getRiskColor(label);
      const lat = f.properties.latitude ?? f.geometry.coordinates[1];
      const lon = f.properties.longitude ?? f.geometry.coordinates[0];
      const radius = 8 + prediction * 12;
      L.circleMarker([lat, lon], {
        radius,
        color: '#000',
        weight: 1,
        fillColor: color,
        fillOpacity: 0.7,
      })
        .bindPopup(
          `<div style="font-family:Inter,sans-serif;font-size:12px;line-height:1.5;min-width:140px">
            <strong style="display:block;margin-bottom:4px;color:${color}">${label}</strong>
            <div>P(fire): ${(prediction * 100).toFixed(1)}%</div>
            <div>Lat: ${lat.toFixed(3)} • Lon: ${lon.toFixed(3)}</div>
          </div>`
        )
        .addTo(overlayLayer.current);
    }
  }, [overlay]);

  // === layers config -> this is mostly a no-op for base tile, but used in
  // future for risk_heatmap/wind/etc overlays. Kept so the prop is required.
  useEffect(() => {
    // Placeholder for future layer pre-add (wind vector layer, VIIRS hotspots, etc.)
    void layers;
  }, [layers]);

  return (
    <div
      className={className ?? 'map-container'}
      ref={mapRef}
      style={{ height, width: '100%' }}
      role="application"
      aria-label={t('spa.map.aria_label_interactive')}
    >
      {error && (
        <div className="error-display" role="alert">
          <strong>{t('spa.map.error.heading')}</strong>
          <span>{error}</span>
          <button onClick={() => window.location.reload()}>{t('spa.map.error.reload_button')}</button>
        </div>
      )}

      {tileStatus && tileStatus.level !== 'ok' && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            zIndex: 1000,
            pointerEvents: 'none',
            background:
              tileStatus.level === 'err' ? 'rgba(127,29,29,0.92)' : 'rgba(15,20,25,0.85)',
            border: `1px solid ${tileStatus.level === 'err' ? '#ef4444' : '#f59e0b'}`,
            borderRadius: 6,
            padding: '6px 10px',
            fontSize: 11,
            fontFamily: 'var(--font-family-mono)',
            color: '#f1f5f9',
            backdropFilter: 'blur(6px)',
            maxWidth: 320,
            boxShadow: '0 4px 14px rgba(0,0,0,0.45)',
          }}
          title={tileStatus.source}
        >
          {tileStatus.level === 'err' ? '⚠ ' : '• '}
          {tileStatus.message}
          {tileStatus.level === 'err' && (
            <>
              {' '}
              <button
                type="button"
                onClick={() => window.location.reload()}
                style={{
                  background: 'transparent',
                  border: '1px solid #f1f5f9',
                  color: 'inherit',
                  borderRadius: 4,
                  padding: '1px 6px',
                  fontSize: 10,
                  cursor: 'pointer',
                  verticalAlign: 'middle',
                }}
              >
                {t('spa.map.tile.reload')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function layerToGeoJSON(layer: L.Layer): GeoJSON.Feature | null {
  const anyLayer = layer as any;
  if (typeof anyLayer.toGeoJSON === 'function') {
    return anyLayer.toGeoJSON() as GeoJSON.Feature;
  }
  return null;
}

export default InteractiveMap;
