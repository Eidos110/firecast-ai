/**
 * MapArea — center pane wraps InteractiveMap with floating overlays
 * (coord readout, EPSG/zoom pill, compass widget — V1 + V4 mockups).
 *
 * The overlays are delegated to the dedicated <MapOverlays> component
 * (PLAN §4 TAHAP D #7) so that the overlay look-and-feel can be tested
 * in isolation without mounting Leaflet.
 *
 * Default view: Indonesia (-1.8, 113.5) zoom 7 (Kalimantan Tengah).
 * Updates the global inference store `selectedCell` on map click and
 * mirrors the same lat/lon into a local readout state so MapOverlays
 * can render a live coordinate bridge.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InteractiveMap } from './InteractiveMap';
import { MapOverlays } from './MapOverlays';
import { useInferenceStore } from '../store/inferenceStore';
import { toast } from '../store/toastStore';

const INITIAL_CENTER: [number, number] = [-1.8, 113.5];
const INITIAL_ZOOM = 7;

export function MapArea(): JSX.Element {
  const { t } = useTranslation();
  const [coordReadout, setCoordReadout] = useState<{ lat: number; lon: number; zoom: number } | null>(null);
  const setSelectedCell = useInferenceStore((s) => s.setSelectedCell);
  const layers = useInferenceStore((s) => s.layers);
  const selectedAoi = useInferenceStore((s) => s.selectedAoi);
  const aoiOverlay = useInferenceStore((s) => s.aoiOverlay);
  const setSelectedAoi = useInferenceStore((s) => s.setSelectedAoi);
  const setAoiOverlay = useInferenceStore((s) => s.setAoiOverlay);
  const pushApiLog = useInferenceStore((s) => s.pushApiLog);

  return (
    <main
      aria-label={t('spa.map.aria_label')}
      style={{ position: 'relative', flex: 1, background: '#0a0e13', overflow: 'hidden' }}
    >
      <InteractiveMap
        initialCenter={INITIAL_CENTER}
        initialZoom={INITIAL_ZOOM}
        height="100%"
        onCellSelect={(p) => {
          setSelectedCell(p);
          setCoordReadout({ lat: p.lat, lon: p.lon, zoom: INITIAL_ZOOM });
        }}
        aoi={selectedAoi}
        onAoiDrawn={(feature) => {
          setSelectedAoi(feature);
          pushApiLog('ok', t('spa.map.aoi.log_drawn'));
          const n = feature?.geometry?.type === 'Polygon' ? feature.geometry.coordinates[0]?.length - 1 : 0;
          toast.success(t('spa.map.toast.aoi_drawn', { n: Math.max(n, 0) }));
        }}
        onAoiUpdated={(feature) => {
          setSelectedAoi(feature);
          pushApiLog('ok', t('spa.map.aoi.log_updated'));
          toast.info(t('spa.map.toast.aoi_updated'));
        }}
        onAoiDeleted={() => {
          setSelectedAoi(null);
          setAoiOverlay(null);
          pushApiLog('warn', t('spa.map.aoi.log_deleted'));
          toast.info(t('spa.map.toast.aoi_deleted'));
        }}
        overlay={aoiOverlay}
        layers={layers.map((l) => ({ id: l.id, label: l.label, active: l.active, opacity: l.opacity }))}
      />

      <MapOverlays coordReadout={coordReadout} />
    </main>
  );
}

export default MapArea;
