import { useCallback } from "react";
import api, { formatApiErrorDetail, setAuthToken } from "../api";
import {
  bboxFromBoundsWgs84,
  bboxFromGeojson,
  formatRecorteDisplayName,
} from "../utils/geo";
import { LAYER_MVT_SOURCE_LAYER, layerMvtTilesTemplate } from "../utils/layerMvt";
import { isLegacyS2ZipBandRaster } from "../utils/userRole";

/**
 * Proyectos Agro: listado, selección en mapa, CRUD básico.
 * ``getToken`` evita acoplar el orden de hooks con useAuthSession.
 */
export default function useProjectWorkspace({
  mapRef,
  getToken,
  projects,
  setProjects,
  projectId,
  setProjectId,
  setTargetRasterId,
  mapLayersRef,
  addMapLayer,
  clearAllMapLayers,
  setPendingDeletes,
  setDirty,
  paintLayerOnMap,
  setMessage,
  setLoading,
  requireAdminAction,
}) {
  const fetchProjects = useCallback(
    async (accessToken, module = "agro") => {
      try {
        setAuthToken(accessToken);
        const res = await api.get("/projects", { params: { module } });
        const list = Array.isArray(res.data) ? res.data : [];
        if (module === "agro") setProjects(list);
        return list;
      } catch (_) {
        if (module === "agro") setProjects([]);
        return [];
      }
    },
    [setProjects]
  );

  const fetchLayerGeojson = useCallback(async (pid, layerId, accessToken) => {
    try {
      setAuthToken(accessToken);
      const res = await api.get(`/layers/${pid}/${layerId}/geojson`);
      return res.data;
    } catch (_) {
      return null;
    }
  }, []);

  const selectProject = useCallback(
    async (id, accessToken) => {
      const tk = accessToken || getToken();
      clearAllMapLayers();
      setPendingDeletes([]);
      setDirty(false);
      setProjectId(id);
      setTargetRasterId("");
      setMessage("Cargando capas del proyecto...");
      setLoading(true);
      try {
        setAuthToken(tk);
        const [layersRes, rastersRes] = await Promise.all([
          api.get(`/layers/${id}`),
          api.get(`/raster/${id}`),
        ]);
        let firstBbox = null;
        const mvtLayers = [];
        const geojsonLayers = [];
        for (const layer of layersRes.data) {
          if (layer.mvt_ready) mvtLayers.push(layer);
          else geojsonLayers.push(layer);
        }
        for (const layer of mvtLayers) {
          const rbbox = bboxFromBoundsWgs84(layer.bbox);
          const lid = addMapLayer(layer.name, "vector", null, layer.id, {
            ...(rbbox ? { bbox: rbbox } : {}),
          });
          paintLayerOnMap(lid, null, {
            tileTemplate: layerMvtTilesTemplate(id, layer.id),
            sourceLayer: layer.mvt_source_layer || LAYER_MVT_SOURCE_LAYER,
          });
          if (rbbox && !firstBbox) firstBbox = rbbox;
        }
        const geojsonResults = await Promise.all(
          geojsonLayers.map((layer) => fetchLayerGeojson(id, layer.id, tk))
        );
        geojsonLayers.forEach((layer, i) => {
          const geojson = geojsonResults[i];
          const lid = addMapLayer(layer.name, "vector", geojson, layer.id);
          if (geojson) {
            paintLayerOnMap(lid, geojson);
            if (!firstBbox) firstBbox = bboxFromGeojson(geojson);
          }
        });
        for (const raster of rastersRes.data) {
          const m = raster.metadata || {};
          if (
            (m.source === "sentinel-2" || m.source === "sentinel-1") &&
            m.type === "download"
          ) {
            continue;
          }
          if (isLegacyS2ZipBandRaster(m)) continue;
          const rb = m.bounds_wgs84;
          const rbbox = bboxFromBoundsWgs84(rb);
          const title =
            formatRecorteDisplayName(raster.metadata, raster.name) || raster.name;
          addMapLayer(raster.name, "raster", null, raster.id, {
            ...(rbbox ? { bbox: rbbox } : {}),
            metadata: raster.metadata,
            displayName: title,
            append: true,
          });
          if (raster.id) setTargetRasterId(String(raster.id));
          if (rbbox && !firstBbox) firstBbox = rbbox;
        }
        if (firstBbox && mapRef.current) {
          mapRef.current.fitBounds(firstBbox, { padding: 60, maxZoom: 17 });
        }
        const visibleRasters = rastersRes.data.filter((r) => {
          const m = r.metadata || {};
          if ((m.source === "sentinel-2" || m.source === "sentinel-1") && m.type === "download")
            return false;
          if (isLegacyS2ZipBandRaster(m)) return false;
          return true;
        });
        const totalLayers = layersRes.data.length + visibleRasters.length;
        const proj = projects.find((p) => p.id === id);
        const projName = proj ? proj.name : `ID ${id}`;
        setMessage(
          totalLayers > 0
            ? `Proyecto "${projName}" seleccionado. ${totalLayers} capa(s) cargada(s).`
            : `Proyecto "${projName}" seleccionado. Sin capas aun.`
        );
      } catch (error) {
        const detail = error?.response?.data?.detail || error.message || "Error al cargar capas";
        setMessage(`Proyecto seleccionado pero error al cargar capas: ${detail}`);
      } finally {
        setLoading(false);
      }
    },
    [
      addMapLayer,
      clearAllMapLayers,
      fetchLayerGeojson,
      getToken,
      mapRef,
      paintLayerOnMap,
      projects,
      setDirty,
      setLoading,
      setMessage,
      setPendingDeletes,
      setProjectId,
      setTargetRasterId,
    ]
  );

  const zoomToLayer = useCallback(
    (lid) => {
      const map = mapRef.current;
      if (!map) return;
      const layer = mapLayersRef.current.find((l) => l.id === lid);
      if (!layer) return;

      if (layer.bbox) {
        map.fitBounds(layer.bbox, { padding: 60, maxZoom: 17 });
        return;
      }
      if (layer.geojsonData) {
        const bbox = bboxFromGeojson(layer.geojsonData);
        if (bbox) {
          map.fitBounds(bbox, { padding: 60, maxZoom: 17 });
          return;
        }
      }
      try {
        const src = map.getSource(lid);
        if (src) {
          const data = src._data || src.serialize?.()?.data;
          if (data) {
            const bbox = bboxFromGeojson(data);
            if (bbox) {
              map.fitBounds(bbox, { padding: 60, maxZoom: 17 });
              return;
            }
          }
        }
      } catch (_) {}
      try {
        const features = map.querySourceFeatures(lid);
        if (features.length > 0) {
          const bbox = bboxFromGeojson({ type: "FeatureCollection", features });
          if (bbox) {
            map.fitBounds(bbox, { padding: 60, maxZoom: 17 });
            return;
          }
        }
      } catch (_) {}
      if (layer.kind === "raster") {
        setMessage(
          "Esta capa raster no tiene extensión geográfica (CRS). Si es Sentinel-2, sube un ZIP de la carpeta .SAFE completa (no un solo JPG). También puedes usar un GeoTIFF/JP2 con CRS o volver a cargar el proyecto tras el procesamiento."
        );
        return;
      }
      setMessage("No se pudo calcular la extension de esta capa.");
    },
    [mapLayersRef, mapRef, setMessage]
  );

  const updateProjectName = useCallback(
    async (id, name) => {
      if (!requireAdminAction()) return false;
      const trimmed = name.trim();
      if (!trimmed) {
        setMessage("Error: el nombre del proyecto no puede estar vacío.");
        return false;
      }
      const token = getToken();
      setLoading(true);
      setMessage("");
      try {
        setAuthToken(token);
        await api.patch(`/projects/${id}`, { name: trimmed });
        await fetchProjects(token);
        setMessage(`Proyecto renombrado a "${trimmed}".`);
        return true;
      } catch (error) {
        setMessage(`Error: ${formatApiErrorDetail(error)}`);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchProjects, getToken, requireAdminAction, setLoading, setMessage]
  );

  const deleteProject = useCallback(
    async (id) => {
      const token = getToken();
      if (!token) {
        setMessage("Debes iniciar sesion.");
        return;
      }
      const proj = projects.find((p) => p.id === id);
      const projName = proj ? proj.name : `ID ${id}`;
      if (!window.confirm(`Eliminar el proyecto "${projName}" y todas sus capas?`)) return;
      setLoading(true);
      setMessage("");
      try {
        setAuthToken(token);
        await api.delete(`/projects/${id}`);
        if (Number(projectId) === Number(id)) {
          setProjectId("");
          setTargetRasterId("");
          clearAllMapLayers();
        }
        await fetchProjects(token);
        setMessage(`Proyecto "${projName}" eliminado.`);
      } catch (error) {
        const detail =
          error?.response?.data?.detail || error.message || "Error al eliminar proyecto";
        setMessage(`Error: ${detail}`);
      } finally {
        setLoading(false);
      }
    },
    [
      clearAllMapLayers,
      fetchProjects,
      getToken,
      projectId,
      projects,
      setLoading,
      setMessage,
      setProjectId,
      setTargetRasterId,
    ]
  );

  return {
    fetchProjects,
    selectProject,
    zoomToLayer,
    updateProjectName,
    deleteProject,
  };
}
