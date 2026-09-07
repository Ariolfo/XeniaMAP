import { useCallback, useRef, useState } from "react";
import api, { setAuthToken } from "../api";
import { bboxFromGeojson } from "../utils/geo";
import {
  fetchFireRasterMapPayload,
  fetchFireResultGeojson,
  fetchFirmsLive,
} from "../utils/fireLazyLoad";
import { applyLayerStyleToMap } from "../utils/layerPaintStyle";

function paintOptsFromFireMeta(meta, visible = true) {
  if (meta?.fireSymbol) {
    return {
      symbol: meta.fireSymbol,
      visible,
      iconSize: meta.fireIconSize ?? (meta.fireSymbol === "star" ? 0.9 : 0.7),
      iconOpacity: meta.uiOpacity ?? meta.fireIconOpacity ?? 1,
    };
  }
  const fillMode = meta?.uiFillMode === "outline" ? "outline" : "fill";
  const opacity = meta?.uiOpacity ?? meta?.fireFillOpacity ?? 0.35;
  return {
    fillColor: meta?.fireFillColor || "#2d6cdf",
    lineColor: meta?.uiLineColor || meta?.fireLineColor || "#1a3f8c",
    fillOpacity: fillMode === "outline" ? 0 : opacity,
    lineWidth: meta?.fireLineWidth ?? 2,
    visible,
  };
}

function revokePreviewBlob(url) {
  if (!url) return;
  try {
    URL.revokeObjectURL(url);
  } catch (_) {
    /* ignore */
  }
}

/**
 * Dominio Fire: carga lazy de capas, toggles dNBR, FIRMS live.
 */
export default function useFireMap({
  mapRef,
  token,
  mapLayersRef,
  addMapLayer,
  toggleLayerVisibility,
  setLayerVisibility,
  patchMapLayer,
  clearAllMapLayers,
  setPendingDeletes,
  setDirty,
  paintLayerOnMap,
  setProjectId,
  setMessage,
  setLoading,
}) {
  const [fireFocusOrderId, setFireFocusOrderId] = useState(null);
  const fireLoadInflightRef = useRef(new Map());

  const ensureFireLayerLoaded = useCallback(
    async (lid) => {
      const layer = mapLayersRef.current.find((l) => l.id === lid);
      if (!layer?.metadata?.fireLazy) return true;
      if (layer.metadata.fireLoaded) return true;
      if (fireLoadInflightRef.current.has(lid)) {
        try {
          await fireLoadInflightRef.current.get(lid);
          return true;
        } catch (_) {
          return false;
        }
      }

      const orderId = layer.metadata.fireOrderId;
      if (!orderId) return false;

      const run = (async () => {
        patchMapLayer(lid, { metadata: { fireLoading: true } });
        try {
          if (layer.kind === "vector") {
            let gj = null;
            if (layer.metadata.fireLiveFirms) {
              const live = await fetchFirmsLive(orderId, layer.metadata.fireLiveHours || 48);
              gj = live?.layers?.[layer.metadata.fireArtifact] || null;
              if (!gj) gj = { type: "FeatureCollection", features: [] };
            } else {
              gj = await fetchFireResultGeojson(orderId, layer.metadata.fireArtifact);
            }
            const bb = bboxFromGeojson(gj);
            patchMapLayer(lid, {
              geojsonData: gj,
              bbox: bb,
              metadata: { fireLoaded: true, fireLoading: false, fireLazy: false },
            });
            const cur = mapLayersRef.current.find((l) => l.id === lid);
            paintLayerOnMap(
              lid,
              gj,
              paintOptsFromFireMeta(cur?.metadata || layer.metadata, cur?.visible !== false)
            );
            applyLayerStyleToMap(
              mapRef.current,
              mapLayersRef.current.find((l) => l.id === lid) || cur || layer
            );
            if (layer.metadata.fireSymbol && cur?.visible !== false) {
              const map = mapRef.current;
              if (map?.getLayer(lid)) {
                map.setLayoutProperty(lid, "visibility", "visible");
              }
            }
            return true;
          }

          if (layer.kind === "raster" && layer.metadata.firePreview) {
            const { bounds, tileTemplate } = await fetchFireRasterMapPayload(
              orderId,
              layer.metadata.fireArtifact,
              layer.metadata.fireSeverityClass ?? null
            );
            const prevUrl = mapLayersRef.current.find((l) => l.id === lid)?.metadata
              ?.previewBlobUrl;
            revokePreviewBlob(prevUrl);
            const rbbox = [
              [bounds[0], bounds[1]],
              [bounds[2], bounds[3]],
            ];
            patchMapLayer(lid, {
              bbox: rbbox,
              metadata: {
                bounds,
                tileTemplate,
                previewBlobUrl: null,
                fireLoaded: true,
                fireLoading: false,
                fireLazy: false,
              },
            });
            return true;
          }
          patchMapLayer(lid, { metadata: { fireLoading: false } });
          return false;
        } catch (_) {
          patchMapLayer(lid, {
            metadata: { fireLoading: false, fireLoadError: true },
          });
          return false;
        }
      })();

      fireLoadInflightRef.current.set(lid, run);
      try {
        return await run;
      } finally {
        fireLoadInflightRef.current.delete(lid);
      }
    },
    [mapLayersRef, mapRef, paintLayerOnMap, patchMapLayer]
  );

  const toggleFireDnbrGroup = useCallback(
    async (rootId, childIds = []) => {
      const root = mapLayersRef.current.find((l) => l.id === rootId);
      const children = mapLayersRef.current.filter((l) => childIds.includes(l.id));
      const anyOn = !!root?.visible || children.some((c) => c.visible);
      const turnOn = !anyOn;
      if (turnOn) {
        await Promise.all(childIds.map((cid) => ensureFireLayerLoaded(cid)));
      }
      setLayerVisibility(rootId, false);
      childIds.forEach((cid) => setLayerVisibility(cid, turnOn));
    },
    [ensureFireLayerLoaded, mapLayersRef, setLayerVisibility]
  );

  const toggleFireLayerVisibility = useCallback(
    async (lid) => {
      const layer = mapLayersRef.current.find((l) => l.id === lid);
      if (layer?.metadata?.fireDnbrGroupRoot) {
        const kids = mapLayersRef.current
          .filter((l) => l.metadata?.fireDnbrGroupChild)
          .map((l) => l.id);
        await toggleFireDnbrGroup(lid, kids);
        return;
      }
      const willShow = !layer?.visible;
      if (willShow && layer?.metadata?.fireLazy && !layer?.metadata?.fireLoaded) {
        await ensureFireLayerLoaded(lid);
      }
      toggleLayerVisibility(lid);
    },
    [ensureFireLayerLoaded, mapLayersRef, toggleFireDnbrGroup, toggleLayerVisibility]
  );

  const clearFireMap = useCallback(() => {
    clearAllMapLayers();
    setProjectId(null);
    setFireFocusOrderId(null);
    setMessage("Fire: seleccione un municipio o proyecto.");
  }, [clearAllMapLayers, setMessage, setProjectId]);

  const loadFireOrderOnMap = useCallback(
    async (orderDetail, options = {}) => {
      if (!orderDetail || !token) return;
      const fit = options.fit !== false;
      for (const l of mapLayersRef.current) {
        revokePreviewBlob(l?.metadata?.previewBlobUrl);
      }
      fireLoadInflightRef.current.clear();
      clearAllMapLayers();
      setPendingDeletes([]);
      setDirty(false);
      setFireFocusOrderId(orderDetail.id ?? null);
      if (orderDetail.project_id) setProjectId(orderDetail.project_id);
      setMessage(`Fire · ${orderDetail.request_name}: cargando capas…`);
      setLoading(true);
      let firstBbox = null;
      const orderId = orderDetail.id;
      try {
        setAuthToken(token);
        if (orderDetail.geometry) {
          const lid = addMapLayer("Polígono municipio", "vector", orderDetail.geometry, null, {
            metadata: {
              fireLayer: true,
              fireRole: "aoi",
              fillOpacity: 0,
              lineColor: "#dc2626",
              lineWidth: 3,
            },
            displayName: `Polígono · ${orderDetail.request_name}`,
          });
          paintLayerOnMap(lid, orderDetail.geometry, {
            fillColor: "#dc2626",
            lineColor: "#dc2626",
            fillOpacity: 0,
            lineWidth: 3,
          });
          firstBbox = bboxFromGeojson(orderDetail.geometry);
        }

        const catalogRes = await api.get(`/fire-orders/${orderId}/results`);
        const layers = Array.isArray(catalogRes.data?.layers) ? catalogRes.data.layers : [];
        const eagerLoads = [];

        for (const item of layers) {
          if (!item.available) continue;
          if (item.kind === "vector") {
            const defaultOn = !!item.default_on;
            const isHotspot =
              item.map_symbol === "star" ||
              String(item.filename || "").includes("FIRMS_VIIRS_hotspots") ||
              String(item.filename || "").toLowerCase().includes("hotspot");
            const meta = {
              fireLayer: true,
              fireOrderId: orderId,
              fireArtifact: item.filename,
              fireLazy: true,
              fireLoaded: false,
              ...(isHotspot
                ? {
                    fireSymbol: "star",
                    fireRole: "hotspot",
                    fireClassColor: "#ff0000",
                    fireIconSize: 0.9,
                    fireIconOpacity: 1,
                  }
                : {}),
              ...(item.filename.includes("recommended")
                ? {
                    // Naranja pálido + opacidad baja para que los hotspots (estrella roja) resalten.
                    fireFillColor: "#ffd4a8",
                    fireLineColor: "#e8a87c",
                    fireFillOpacity: 0.4,
                    fireLineWidth: 2,
                    fireClassColor: "#ffd4a8",
                  }
                : item.filename.includes("validated")
                  ? {
                      fireFillColor: "#ea580c",
                      fireLineColor: "#9a3412",
                      fireFillOpacity: 0.35,
                    }
                  : {
                      fireFillColor: "#eab308",
                      fireLineColor: "#a16207",
                      fireFillOpacity: 0.3,
                    }),
            };
            const lid = addMapLayer(item.label, "vector", null, null, {
              append: true,
              visible: defaultOn,
              metadata: meta,
              displayName: item.label,
            });
            if (defaultOn) {
              eagerLoads.push(
                ensureFireLayerLoaded(lid).then(() => {
                  const cur = mapLayersRef.current.find((l) => l.id === lid);
                  const bb =
                    cur?.bbox || (cur?.geojsonData ? bboxFromGeojson(cur.geojsonData) : null);
                  if (bb && !firstBbox) firstBbox = bb;
                })
              );
            }
          } else if (item.kind === "raster") {
            const defaultOn = !!item.default_on;
            const isDnbrGroup = !!item.severity_class_group;
            const rootLid = addMapLayer(item.label, "raster", null, null, {
              append: true,
              visible: false,
              metadata: {
                fireLayer: true,
                fireOrderId: orderId,
                fireArtifact: item.filename,
                firePreview: true,
                fireDnbrGroupRoot: isDnbrGroup,
                fireLazy: true,
                fireLoaded: false,
              },
              displayName: item.label,
            });
            if (!isDnbrGroup && defaultOn) {
              eagerLoads.push(
                ensureFireLayerLoaded(rootLid).then(() => {
                  setLayerVisibility(rootLid, true);
                  const cur = mapLayersRef.current.find((l) => l.id === rootLid);
                  if (cur?.bbox && !firstBbox) firstBbox = cur.bbox;
                })
              );
            }

            if (isDnbrGroup && Array.isArray(item.severity_classes)) {
              for (const cls of item.severity_classes) {
                if (!cls?.available || cls.class_id == null) continue;
                addMapLayer(`Clase ${cls.class_id} · ${cls.label}`, "raster", null, null, {
                  append: true,
                  visible: false,
                  metadata: {
                    fireLayer: true,
                    fireOrderId: orderId,
                    fireArtifact: cls.source_filename || "Fire_burn_severity.tif",
                    firePreview: true,
                    fireDnbrGroupChild: true,
                    fireSeverityClass: cls.class_id,
                    fireClassColor: cls.color || null,
                    fireParentArtifact: item.filename,
                    fireLazy: true,
                    fireLoaded: false,
                  },
                  displayName: `${cls.class_id}. ${cls.label}`,
                });
              }
            }
          }
        }

        await Promise.all(eagerLoads);

        try {
          const liveSpecs = [
            {
              key: "hotspots_24h",
              label: "Hotspots FIRMS 24 h",
              symbol: "star-24h",
              color: "#2563eb",
            },
            {
              key: "hotspots_48h",
              label: "Hotspots FIRMS 48 h",
              symbol: "star-48h",
              color: "#7c3aed",
            },
          ];
          const liveLids = [];
          for (const spec of liveSpecs) {
            const lid = addMapLayer(spec.label, "vector", null, null, {
              append: true,
              visible: true,
              metadata: {
                fireLayer: true,
                fireOrderId: orderId,
                fireLiveFirms: true,
                fireLiveHours: 48,
                fireArtifact: spec.key,
                fireSymbol: spec.symbol,
                fireRole: spec.key,
                fireClassColor: spec.color,
                fireLazy: true,
                fireLoaded: false,
              },
              displayName: spec.label,
            });
            liveLids.push(lid);
          }
          const live = await fetchFirmsLive(orderId, 48);
          for (const lid of liveLids) {
            const cur = mapLayersRef.current.find((l) => l.id === lid);
            const key = cur?.metadata?.fireArtifact;
            const gj = live?.layers?.[key] || { type: "FeatureCollection", features: [] };
            patchMapLayer(lid, {
              geojsonData: gj,
              bbox: bboxFromGeojson(gj),
              metadata: {
                fireLoaded: true,
                fireLoading: false,
                fireLazy: false,
                firmsStale: !!live?.stale,
                firmsCached: !!live?.cached,
              },
            });
            paintLayerOnMap(lid, gj, {
              symbol: cur?.metadata?.fireSymbol,
              visible: true,
            });
            const bb = bboxFromGeojson(gj);
            if (bb && !firstBbox) firstBbox = bb;
          }
          if (live?.stale) {
            setMessage(
              `Fire · FIRMS en modo degradado (caché stale). Datos pueden no estar al minuto.`
            );
          }
        } catch (_) {
          /* FIRMS ausente: stubs lazy quedan off hasta reintento */
        }

        addMapLayer("Imagen satelital", "raster", null, null, {
          append: true,
          visible: true,
          metadata: {
            fireLayer: true,
            fireRole: "basemap-satellite",
            fireBasemapSatellite: true,
            fireClassColor: "#38bdf8",
          },
          displayName: "Imagen satelital",
        });

        const map = mapRef.current;
        if (map?.isStyleLoaded?.()) {
          for (const l of mapLayersRef.current) {
            if (l.metadata?.fireSymbol && map.getLayer(l.id)) {
              try {
                map.moveLayer(l.id);
              } catch (_) {
                /* ignore */
              }
            }
          }
        }

        if (fit && firstBbox && mapRef.current) {
          mapRef.current.fitBounds(firstBbox, { padding: 60, maxZoom: 14 });
        }
        const n = mapLayersRef.current.length;
        const loaded = mapLayersRef.current.filter(
          (l) =>
            l.metadata?.fireLoaded ||
            l.metadata?.fireRole === "aoi" ||
            l.metadata?.fireBasemapSatellite
        ).length;
        setMessage(
          `Fire · ${orderDetail.request_name}: ${n} capa(s) (${loaded} listas). Resto al activar en Capas Fire.`
        );
      } catch (error) {
        setMessage(
          `Fire: error al cargar capas — ${error?.response?.data?.detail || error.message || "desconocido"}`
        );
      } finally {
        setLoading(false);
      }
    },
    [
      addMapLayer,
      clearAllMapLayers,
      ensureFireLayerLoaded,
      mapLayersRef,
      mapRef,
      paintLayerOnMap,
      patchMapLayer,
      setDirty,
      setLayerVisibility,
      setLoading,
      setMessage,
      setPendingDeletes,
      setProjectId,
      token,
    ]
  );

  return {
    fireFocusOrderId,
    setFireFocusOrderId,
    ensureFireLayerLoaded,
    toggleFireDnbrGroup,
    toggleFireLayerVisibility,
    clearFireMap,
    loadFireOrderOnMap,
  };
}
