import { useRef, useState } from "react";
import { bboxFromGeojson } from "../utils/geo";
import { createLayerDescriptor, createLayerStore } from "../map/LayerStore";

/**
 * Hook React sobre LayerStore único (F6).
 * Mantiene mapLayers / mapLayersRef sincronizados con el store.
 */
export default function useMapLayers(mapRef) {
  const storeRef = useRef(null);
  if (!storeRef.current) {
    storeRef.current = createLayerStore();
  }
  const store = storeRef.current;

  const [mapLayers, setMapLayers] = useState([]);
  const mapLayersRef = useRef([]);
  const [pendingDeletes, setPendingDeletes] = useState([]);
  const [dirty, setDirty] = useState(false);

  function sync(next) {
    mapLayersRef.current = next;
    store.replaceAll(next);
    setMapLayers(next);
  }

  function addMapLayer(name, kind, geojsonData, serverId, options = {}) {
    const lid = store.nextLayerId();
    const bbox =
      options.bbox != null
        ? options.bbox
        : geojsonData
          ? bboxFromGeojson(geojsonData)
          : null;
    const entry = createLayerDescriptor({
      id: lid,
      name,
      kind,
      geojsonData,
      serverId,
      options,
      bbox,
    });
    const next = options.append
      ? [...mapLayersRef.current, entry]
      : [entry, ...mapLayersRef.current];
    sync(next);
    return lid;
  }

  function removeMapLayer(lid, options = {}) {
    const skipPending = options.skipPending === true;
    const map = mapRef.current;
    if (map) {
      if (map.getLayer(lid)) map.removeLayer(lid);
      if (map.getLayer(lid + "_outline")) map.removeLayer(lid + "_outline");
      if (map.getSource(lid)) map.removeSource(lid);
    }
    const removed = mapLayersRef.current.find((l) => l.id === lid);
    if (removed && removed.serverId && !skipPending) {
      setPendingDeletes((prev) => [
        ...prev,
        { kind: removed.kind, serverId: removed.serverId },
      ]);
      setDirty(true);
    }
    sync(mapLayersRef.current.filter((l) => l.id !== lid));
  }

  function toggleLayerVisibility(lid) {
    const cur = mapLayersRef.current.find((l) => l.id === lid);
    if (!cur) return;
    const vis = !cur.visible;
    const map = mapRef.current;
    if (map) {
      if (map.getLayer(lid)) {
        map.setLayoutProperty(lid, "visibility", vis ? "visible" : "none");
      }
      if (map.getLayer(`${lid}_outline`)) {
        map.setLayoutProperty(`${lid}_outline`, "visibility", vis ? "visible" : "none");
      }
    }
    sync(
      mapLayersRef.current.map((l) => (l.id === lid ? { ...l, visible: vis } : l))
    );
  }

  /** Solo estado visible + lienzo; no borra la capa del proyecto ni del servidor. */
  function setLayerVisibility(lid, visible) {
    const map = mapRef.current;
    if (map) {
      if (map.getLayer(lid)) {
        map.setLayoutProperty(lid, "visibility", visible ? "visible" : "none");
      }
      if (map.getLayer(`${lid}_outline`)) {
        map.setLayoutProperty(`${lid}_outline`, "visibility", visible ? "visible" : "none");
      }
    }
    sync(
      mapLayersRef.current.map((l) =>
        l.id === lid ? { ...l, visible: !!visible } : l
      )
    );
  }

  function patchMapLayer(lid, patch) {
    sync(
      mapLayersRef.current.map((l) => {
        if (l.id !== lid) return l;
        const meta =
          patch.metadata !== undefined
            ? { ...(l.metadata || {}), ...(patch.metadata || {}) }
            : l.metadata;
        return {
          ...l,
          ...patch,
          metadata: meta,
          id: l.id,
        };
      })
    );
  }

  function clearAllMapLayers() {
    const map = mapRef.current;
    mapLayersRef.current.forEach((l) => {
      const blob = l?.metadata?.previewBlobUrl;
      if (blob) {
        try {
          URL.revokeObjectURL(blob);
        } catch (_) {}
      }
      if (map) {
        if (map.getLayer(l.id)) map.removeLayer(l.id);
        if (map.getLayer(l.id + "_outline")) map.removeLayer(l.id + "_outline");
        if (map.getSource(l.id)) map.removeSource(l.id);
      }
    });
    if (map) {
      try {
        const satSrc = "_fire_basemap_satellite_src";
        for (const l of [...(map.getStyle()?.layers || [])]) {
          if (l.source === satSrc) {
            try {
              map.removeLayer(l.id);
            } catch (_) {}
          }
        }
        if (map.getSource(satSrc)) map.removeSource(satSrc);
      } catch (_) {}
    }
    store.clear();
    mapLayersRef.current = [];
    setMapLayers([]);
  }

  return {
    mapLayers,
    mapLayersRef,
    layerStore: store,
    pendingDeletes,
    setPendingDeletes,
    dirty,
    setDirty,
    addMapLayer,
    removeMapLayer,
    toggleLayerVisibility,
    setLayerVisibility,
    patchMapLayer,
    clearAllMapLayers,
  };
}
