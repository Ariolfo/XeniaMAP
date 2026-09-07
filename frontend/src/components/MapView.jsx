import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { buildBaseStyle, applyBasemap, isBasemapLayerId } from "../utils/geo";

function rectangleFeatureCollection(c1, c2) {
  const w = Math.min(c1[0], c2[0]);
  const e = Math.max(c1[0], c2[0]);
  const s = Math.min(c1[1], c2[1]);
  const n = Math.max(c1[1], c2[1]);
  const ring = [
    [w, s],
    [e, s],
    [e, n],
    [w, n],
    [w, s],
  ];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring] },
      },
    ],
  };
}

function polygonFromRing(pts) {
  if (pts.length < 3) return null;
  const ring = [...pts, pts[0]];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring] },
      },
    ],
  };
}

const TMP_SRC = "_study_draw_tmp_src";
const TMP_LINE = "_study_draw_tmp_line";
const SAT_SRC = "_fire_basemap_satellite_src";
const ESRI_SAT_TILES =
  "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export default function MapView({
  mapRef,
  mapLayers,
  mapLayersRef,
  projectId: _projectId,
  token: _token,
  baseStyle,
  studyDraw = null,
}) {
  const containerRef = useRef(null);
  const [mapInitError, setMapInitError] = useState(null);
  const rasterBlobUrlsRef = useRef(new Map());
  const polygonPtsRef = useRef([]);
  const rectCornerRef = useRef(null);
  const drawCompleteRef = useRef(null);
  const drawTooFewRef = useRef(null);

  useEffect(() => {
    drawCompleteRef.current = studyDraw?.onComplete;
    drawTooFewRef.current = studyDraw?.onPolygonTooFew;
  }, [studyDraw?.onComplete, studyDraw?.onPolygonTooFew]);

  function removeStudyTemp(map) {
    try {
      if (map.getLayer(TMP_LINE)) map.removeLayer(TMP_LINE);
    } catch (_) {}
    try {
      if (map.getSource(TMP_SRC)) map.removeSource(TMP_SRC);
    } catch (_) {}
  }

  function paintTempLine(map, pts) {
    removeStudyTemp(map);
    if (pts.length < 2) return;
    const geo = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: pts },
    };
    if (!map.isStyleLoaded()) return;
    map.addSource(TMP_SRC, { type: "geojson", data: geo });
    map.addLayer({
      id: TMP_LINE,
      type: "line",
      source: TMP_SRC,
      paint: { "line-color": "#e11d48", "line-width": 2 },
    });
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    try {
      mapRef.current = new maplibregl.Map({
        container: containerRef.current,
        style: buildBaseStyle("vectorial"),
        center: [-74.2973, 4.5709],
        zoom: 5.5,
        transformRequest: (url, resourceType) => {
          if (
            (resourceType === "Tile" || resourceType === "Image") &&
            typeof url === "string" &&
            ((url.includes("/fire-orders/") && url.includes("/results/tiles/")) ||
              (url.includes("/layers/") && url.includes("/tiles/") && url.includes(".mvt")))
          ) {
            const access = sessionStorage.getItem("xeniamap_access");
            if (access) {
              return {
                url,
                headers: { Authorization: `Bearer ${access}` },
              };
            }
          }
          return { url };
        },
      });
      mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");
      setMapInitError(null);
    } catch (err) {
      mapRef.current = null;
      const msg =
        err?.message ||
        (typeof err === "string" ? err : null) ||
        "No se pudo inicializar el mapa (WebGL).";
      setMapInitError(String(msg));
      console.error("MapView: fallo al crear MapLibre", err);
    }
    return () => {
      try {
        mapRef.current?.remove?.();
      } catch (_) {}
      mapRef.current = null;
    };
  }, [mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const swap = () => {
      if (!map.isStyleLoaded()) return;
      applyBasemap(map, baseStyle);
    };
    if (map.isStyleLoaded()) swap();
    else map.once("style.load", swap);
  }, [baseStyle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const paintFireRasters = () => {
      if (!map.isStyleLoaded()) return;
      const fireRasters = (mapLayersRef.current || []).filter(
        (l) =>
          l.kind === "raster" &&
          l.metadata?.firePreview &&
          Array.isArray(l.metadata?.bounds) &&
          (l.metadata?.tileTemplate || l.metadata?.previewBlobUrl || l.metadata?.pngBase64)
      );
      const keep = new Set(fireRasters.map((l) => l.id));

      for (const [id, url] of [...rasterBlobUrlsRef.current.entries()]) {
        if (keep.has(id)) continue;
        URL.revokeObjectURL(url);
        rasterBlobUrlsRef.current.delete(id);
        try {
          if (map.getLayer(id)) map.removeLayer(id);
          if (map.getSource(id)) map.removeSource(id);
        } catch (_) {}
      }

      for (const layer of fireRasters) {
        const [w, s, e, n] = layer.metadata.bounds;
        const tileTemplate = layer.metadata.tileTemplate || null;

        try {
          if (map.getLayer(layer.id)) map.removeLayer(layer.id);
          if (map.getSource(layer.id)) map.removeSource(layer.id);
        } catch (_) {}

        if (tileTemplate) {
          try {
            map.addSource(layer.id, {
              type: "raster",
              tiles: [tileTemplate],
              tileSize: 256,
              bounds: [w, s, e, n],
              minzoom: 0,
              maxzoom: 22,
            });
            map.addLayer({
              id: layer.id,
              type: "raster",
              source: layer.id,
              paint: { "raster-opacity": 0.85 },
              layout: { visibility: layer.visible ? "visible" : "none" },
            });
          } catch (_) {
            /* style busy */
          }
          continue;
        }

        const coordinates = [
          [w, n],
          [e, n],
          [e, s],
          [w, s],
        ];
        const metaUrl = layer.metadata.previewBlobUrl || null;
        let url = rasterBlobUrlsRef.current.get(layer.id);
        if (metaUrl && url !== metaUrl) {
          url = metaUrl;
          rasterBlobUrlsRef.current.set(layer.id, url);
        }
        if (!url && layer.metadata.pngBase64) {
          try {
            const bin = atob(layer.metadata.pngBase64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
            url = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
            rasterBlobUrlsRef.current.set(layer.id, url);
          } catch (_) {
            continue;
          }
        }
        if (!url) continue;
        try {
          map.addSource(layer.id, { type: "image", url, coordinates });
          map.addLayer({
            id: layer.id,
            type: "raster",
            source: layer.id,
            paint: { "raster-opacity": 0.85 },
            layout: { visibility: layer.visible ? "visible" : "none" },
          });
        } catch (_) {
          /* style busy */
        }
      }

      // Estrellas FIRMS por encima de dNBR/RGB (si no, quedan tapadas).
      for (const l of mapLayersRef.current || []) {
        if (!l?.metadata?.fireSymbol) continue;
        if (!map.getLayer(l.id)) continue;
        try {
          map.moveLayer(l.id);
        } catch (_) {
          /* ignore */
        }
      }
    };

    if (map.isStyleLoaded()) paintFireRasters();
    else map.once("style.load", paintFireRasters);
  }, [mapLayers]);

  // Imagen satelital (Esri) como capa conmutable bajo las capas Fire.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const syncSatellite = () => {
      if (!map.isStyleLoaded()) return;
      const satLayer = (mapLayersRef.current || []).find(
        (l) => l.metadata?.fireBasemapSatellite
      );

      const removeSatOverlay = () => {
        const styleLayers = [...(map.getStyle()?.layers || [])];
        for (const l of styleLayers) {
          if (l.source === SAT_SRC) {
            try {
              map.removeLayer(l.id);
            } catch (_) {}
          }
        }
        try {
          if (map.getSource(SAT_SRC)) map.removeSource(SAT_SRC);
        } catch (_) {}
      };

      if (!satLayer) {
        removeSatOverlay();
        return;
      }

      const layerId = satLayer.id;
      const visible = !!satLayer.visible;

      if (!map.getSource(SAT_SRC)) {
        map.addSource(SAT_SRC, {
          type: "raster",
          tiles: [ESRI_SAT_TILES],
          tileSize: 256,
          attribution: "Esri World Imagery",
        });
      }

      if (!map.getLayer(layerId)) {
        // Quitar overlays huérfanos con el mismo source.
        for (const l of map.getStyle()?.layers || []) {
          if (l.source === SAT_SRC && l.id !== layerId) {
            try {
              map.removeLayer(l.id);
            } catch (_) {}
          }
        }
        const styleLayers = map.getStyle()?.layers || [];
        const firstOverlay = styleLayers.find((l) => !isBasemapLayerId(l.id));
        const beforeId = firstOverlay?.id;
        const layerDef = {
          id: layerId,
          type: "raster",
          source: SAT_SRC,
          paint: { "raster-opacity": 1 },
          layout: { visibility: visible ? "visible" : "none" },
        };
        try {
          if (beforeId) map.addLayer(layerDef, beforeId);
          else map.addLayer(layerDef);
        } catch (_) {
          try {
            map.addLayer(layerDef);
          } catch (__) {
            /* ignore */
          }
        }
      } else {
        try {
          map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
        } catch (_) {}
        try {
          const styleLayers = map.getStyle()?.layers || [];
          const firstOverlay = styleLayers.find(
            (l) => !isBasemapLayerId(l.id) && l.id !== layerId && l.source !== SAT_SRC
          );
          if (firstOverlay?.id) map.moveLayer(layerId, firstOverlay.id);
        } catch (_) {}
      }

      for (const l of mapLayersRef.current || []) {
        if (!l?.metadata?.fireSymbol) continue;
        if (!map.getLayer(l.id)) continue;
        try {
          map.moveLayer(l.id);
        } catch (_) {}
      }
    };

    if (map.isStyleLoaded()) syncSatellite();
    else map.once("style.load", syncSatellite);
  }, [mapLayers, baseStyle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !studyDraw?.active) {
      polygonPtsRef.current = [];
      rectCornerRef.current = null;
      if (map && map.isStyleLoaded()) removeStudyTemp(map);
      if (map) {
        try {
          map.doubleClickZoom.enable();
        } catch (_) {}
      }
      return undefined;
    }

    polygonPtsRef.current = [];
    rectCornerRef.current = null;
    const onStyle = () => {
      try {
        map.doubleClickZoom.disable();
      } catch (_) {}
    };
    if (map.isStyleLoaded()) onStyle();
    else map.once("load", onStyle);

    const onClick = (e) => {
      const lng = e.lngLat.lng;
      const lat = e.lngLat.lat;
      if (studyDraw.mode === "polygon") {
        polygonPtsRef.current = [...polygonPtsRef.current, [lng, lat]];
        paintTempLine(map, polygonPtsRef.current);
      } else if (studyDraw.mode === "rectangle") {
        if (!rectCornerRef.current) {
          rectCornerRef.current = [lng, lat];
        } else {
          const gj = rectangleFeatureCollection(rectCornerRef.current, [lng, lat]);
          removeStudyTemp(map);
          rectCornerRef.current = null;
          polygonPtsRef.current = [];
          try {
            map.doubleClickZoom.enable();
          } catch (_) {}
          drawCompleteRef.current?.(gj);
        }
      }
    };

    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
      removeStudyTemp(map);
      polygonPtsRef.current = [];
      rectCornerRef.current = null;
      try {
        map.doubleClickZoom.enable();
      } catch (_) {}
    };
  }, [studyDraw?.active, studyDraw?.mode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !studyDraw?.active || studyDraw.mode !== "polygon") return;
    const key = studyDraw.finalizePolygonKey ?? 0;
    if (key <= 0) return;
    const pts = polygonPtsRef.current;
    if (pts.length < 3) {
      drawTooFewRef.current?.();
      return;
    }
    const gj = polygonFromRing(pts);
    if (!gj) return;
    removeStudyTemp(map);
    polygonPtsRef.current = [];
    try {
      map.doubleClickZoom.enable();
    } catch (_) {}
    drawCompleteRef.current?.(gj);
  }, [studyDraw?.finalizePolygonKey, studyDraw?.active, studyDraw?.mode]);

  return (
    <main className="map-container">
      {mapInitError ? (
        <div className="map-webgl-fallback" role="alert">
          <h2>No se pudo cargar el mapa</h2>
          <p>
            El navegador no pudo crear un contexto WebGL (necesario para MapLibre). Activa la
            aceleración por hardware o prueba otro navegador / perfil.
          </p>
          <p className="map-webgl-fallback-detail">{mapInitError}</p>
        </div>
      ) : null}
      <div className="map" ref={containerRef} style={mapInitError ? { display: "none" } : undefined} />
    </main>
  );
}
