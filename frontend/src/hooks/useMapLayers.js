import { useRef, useState } from "react";
import { bboxFromGeojson } from "../utils/geo";

export default function useMapLayers(mapRef) {
  const [mapLayers, setMapLayers] = useState([]);
  const mapLayersRef = useRef([]);
  const layerIdCounter = useRef(1);
  const [pendingDeletes, setPendingDeletes] = useState([]);
  const [dirty, setDirty] = useState(false);

  function addMapLayer(name, kind, geojsonData, serverId, options = {}) {
    const lid = `layer_${layerIdCounter.current++}`;
    const bbox =
      options.bbox != null
        ? options.bbox
        : geojsonData
          ? bboxFromGeojson(geojsonData)
          : null;
    const entry = {
      id: lid,
      name,
      kind,
      visible: options.visible !== false,
      geojsonData,
      bbox,
      serverId: serverId || null,
      metadata: options.metadata ?? null,
      displayName: options.displayName ?? name,
    };
    setMapLayers((prev) => {
      const next = options.append ? [...prev, entry] : [entry, ...prev];
      mapLayersRef.current = next;
      return next;
    });
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
    setMapLayers((prev) => {
      const next = prev.filter((l) => l.id !== lid);
      mapLayersRef.current = next;
      return next;
    });
  }

  function toggleLayerVisibility(lid) {
    setMapLayers((prev) => {
      const next = prev.map((l) => {
        if (l.id !== lid) return l;
        const vis = !l.visible;
        const map = mapRef.current;
        if (map) {
          if (map.getLayer(lid)) {
            map.setLayoutProperty(lid, "visibility", vis ? "visible" : "none");
          }
          if (map.getLayer(`${lid}_outline`)) {
            map.setLayoutProperty(`${lid}_outline`, "visibility", vis ? "visible" : "none");
          }
        }
        return { ...l, visible: vis };
      });
      mapLayersRef.current = next;
      return next;
    });
  }

  /** Solo estado visible + lienzo; no borra la capa del proyecto ni del servidor. */
  function setLayerVisibility(lid, visible) {
    setMapLayers((prev) => {
      const next = prev.map((l) => {
        if (l.id !== lid) return l;
        const map = mapRef.current;
        if (map) {
          if (map.getLayer(lid)) {
            map.setLayoutProperty(lid, "visibility", visible ? "visible" : "none");
          }
          if (map.getLayer(`${lid}_outline`)) {
            map.setLayoutProperty(`${lid}_outline`, "visibility", visible ? "visible" : "none");
          }
        }
        return { ...l, visible };
      });
      mapLayersRef.current = next;
      return next;
    });
  }

  function clearAllMapLayers() {
    const map = mapRef.current;
    mapLayersRef.current.forEach((l) => {
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
    setMapLayers([]);
    mapLayersRef.current = [];
    layerIdCounter.current = 1;
  }

  return {
    mapLayers,
    mapLayersRef,
    pendingDeletes,
    setPendingDeletes,
    dirty,
    setDirty,
    addMapLayer,
    removeMapLayer,
    toggleLayerVisibility,
    setLayerVisibility,
    clearAllMapLayers,
  };
}
