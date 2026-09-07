import { useCallback, useEffect, useRef, useState } from "react";
import api, { API_URL, formatApiErrorDetail, setAuthToken } from "../../api";
import { adaptInventories } from "../dataAdapter";
import { fetchPreviewDataUrl } from "../previewUtils";

const SOIL_KINDS = ["dem", "cv", "aspect", "slope", "cluster", "bars", "qchart"];

export default function useLandingProjectData(projectId, token) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [adapted, setAdapted] = useState(null);
  const [aoiGeojson, setAoiGeojson] = useState(null);
  const [clusterBySensor, setClusterBySensor] = useState({ s1: null, s2: null, ps: null });
  const [clustersLoading, setClustersLoading] = useState(false);
  const [clustersError, setClustersError] = useState("");
  const [psStClusters, setPsStClusters] = useState({
    1: { preview: "", busy: false, error: "" },
    2: { preview: "", busy: false, error: "" },
    3: { preview: "", busy: false, error: "" },
  });
  const [clientSoilSummary, setClientSoilSummary] = useState(null);
  const [clientSoilImgUrls, setClientSoilImgUrls] = useState({ fast: {}, matlab: {} });
  const [soilLoading, setSoilLoading] = useState(false);
  const [soilError, setSoilError] = useState("");
  const [seriesBySensor, setSeriesBySensor] = useState({ s1: null, s2: null, ps: null });
  const [climateBySensor, setClimateBySensor] = useState({ s1: [], s2: [], ps: [] });
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [seriesError, setSeriesError] = useState("");
  const previewCache = useRef(new Map());
  const seriesCache = useRef(new Map());
  const adaptedRef = useRef(null);

  const loadClusters = useCallback(async () => {
    if (!projectId || !token) return;
    setClustersLoading(true);
    setClustersError("");
    try {
      setAuthToken(token);
      const [c1, c2, c3] = await Promise.all([
        api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=s1`).catch(() => ({ data: { results: [] } })),
        api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=s2`).catch(() => ({ data: { results: [] } })),
        api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=ps`).catch(() => ({ data: { results: [] } })),
      ]);
      setClusterBySensor({
        s1: c1.data || { results: [] },
        s2: c2.data || { results: [] },
        ps: c3.data || { results: [] },
      });
    } catch (e) {
      setClustersError(formatApiErrorDetail(e));
    } finally {
      setClustersLoading(false);
    }
  }, [projectId, token]);

  const loadSmartClusters = useCallback(async () => {
    if (!projectId || !token) return;
    const base = API_URL.replace(/\/$/, "");
    const presets = [
      { slot: 1, preset: "smart1" },
      { slot: 2, preset: "smart2" },
      { slot: 3, preset: "smart3" },
    ];
    for (const { slot, preset } of presets) {
      setPsStClusters((prev) => ({
        ...prev,
        [slot]: { ...prev[slot], busy: true, error: "" },
      }));
      try {
        const preview = await fetchPreviewDataUrl(
          `${base}/preprocess/ps-spatiotemporal-cluster-preview/${projectId}?preset=${encodeURIComponent(preset)}`,
          token
        );
        setPsStClusters((prev) => ({
          ...prev,
          [slot]: { preview, busy: false, error: "" },
        }));
      } catch (e) {
        setPsStClusters((prev) => ({
          ...prev,
          [slot]: { preview: "", busy: false, error: formatApiErrorDetail(e) },
        }));
      }
    }
  }, [projectId, token]);

  const loadSoil = useCallback(async () => {
    if (!projectId || !token) return;
    setSoilLoading(true);
    setSoilError("");
    try {
      setAuthToken(token);
      const base = API_URL.replace(/\/$/, "");
      const { data } = await api.get(`/preprocess/soilplus-saved-summary/${projectId}`);
      const variants = data?.variants || {};
      setClientSoilSummary(variants);
      const nextBucket = { fast: {}, matlab: {} };
      for (const vk of Object.keys(variants)) {
        if (!nextBucket[vk]) nextBucket[vk] = {};
        for (const kind of SOIL_KINDS) {
          try {
            nextBucket[vk][kind] = await fetchPreviewDataUrl(
              `${base}/preprocess/soilplus-saved-img/${projectId}?variant=${vk}&kind=${kind}`,
              token
            );
          } catch {
            /* optional thumb */
          }
        }
      }
      setClientSoilImgUrls(nextBucket);
    } catch (e) {
      setSoilError(formatApiErrorDetail(e));
      setClientSoilSummary(null);
      setClientSoilImgUrls({ fast: {}, matlab: {} });
    } finally {
      setSoilLoading(false);
    }
  }, [projectId, token]);

  const loadSeriesForSensor = useCallback(
    async (sensor, selection = {}) => {
      if (!projectId || !token) return null;
      const adaptedData = adaptedRef.current;
      if (!adaptedData) return null;
      const roiPoints = Array.isArray(selection?.roiSelection?.polygon_points)
        ? selection.roiSelection.polygon_points.map((p) => ({
            x: Number(p.x),
            y: Number(p.y),
          }))
        : [];
      const roiPayload = roiPoints.length >= 3 ? { polygon_points: roiPoints } : null;
      const selectionKey = JSON.stringify({
        p: selection?.pointSelection || null,
        r: selection?.roiSelection || null,
      });
      const cacheKey = `${sensor}|${projectId}|${selectionKey}`;
      if (seriesCache.current.has(cacheKey)) return seriesCache.current.get(cacheKey);

      setAuthToken(token);
      let data = null;
      if (sensor === "s1") {
        const res = await api.post("/preprocess/s1-sar-time-series", {
          project_id: Number(projectId),
          roi_selection: roiPayload,
        });
        data = res.data;
      } else {
        const pv = sensor === "ps" ? "ps" : "s2";
        const res = await api.post("/preprocess/vegetation-time-series", {
          project_id: Number(projectId),
          pipeline_variant: pv,
          max_pixel_series: 1800,
          random_seed: 42,
          roi_selection: roiPayload,
        });
        data = res.data;
      }
      seriesCache.current.set(cacheKey, data);
      return data;
    },
    [projectId, token]
  );

  const loadSeries = useCallback(
    async (selection = {}) => {
      if (!projectId || !token) return;
      setSeriesLoading(true);
      setSeriesError("");
      try {
        setAuthToken(token);
        // Cada sensor por separado: un fallo S1/S2 no debe bloquear PS ni el clima.
        const settled = await Promise.allSettled([
          loadSeriesForSensor("s1", selection),
          loadSeriesForSensor("s2", selection),
          loadSeriesForSensor("ps", selection),
        ]);
        const pick = (i) => (settled[i].status === "fulfilled" ? settled[i].value : null);
        setSeriesBySensor({ s1: pick(0), s2: pick(1), ps: pick(2) });
        const seriesErrs = settled
          .map((r, i) => (r.status === "rejected" ? `${["s1", "s2", "ps"][i]}: ${r.reason?.message || r.reason}` : null))
          .filter(Boolean);
        if (seriesErrs.length === 3) {
          setSeriesError(seriesErrs.join(" | "));
        }
      } catch (e) {
        setSeriesError(formatApiErrorDetail(e));
      }

      // Agroclima siempre (Open-Meteo), aunque fallen las series de índices.
      try {
        setAuthToken(token);
        const c = await api.get("/preprocess/agroclimate-series", {
          params: { project_id: Number(projectId) },
        });
        setClimateBySensor({
          s1: c.data?.by_sensor?.s1 || [],
          s2: c.data?.by_sensor?.s2 || [],
          ps: c.data?.by_sensor?.ps || [],
        });
      } catch {
        setClimateBySensor({ s1: [], s2: [], ps: [] });
      } finally {
        setSeriesLoading(false);
      }
    },
    [projectId, token, loadSeriesForSensor]
  );

  const load = useCallback(async () => {
    if (!projectId || !token) return;
    setLoading(true);
    setError("");
    try {
      setAuthToken(token);
      const [s1Inv, s2Inv, psInv, s2Rec, psRec, s1PrepVv, s1PrepVh, layersRes] = await Promise.all([
        api.get(`/preprocess/s1-sar-index-stacks-inventory/${projectId}`),
        api.get(`/preprocess/index-stacks-inventory/${projectId}?pipeline_variant=s2`),
        api.get(`/preprocess/index-stacks-inventory/${projectId}?pipeline_variant=ps`),
        api.get(`/preprocess/recortes-inventory/${projectId}?pipeline_variant=s2`).catch(() => ({ data: { items: [] } })),
        api.get(`/preprocess/recortes-inventory/${projectId}?pipeline_variant=ps`).catch(() => ({ data: { items: [] } })),
        api.get(`/preprocess/s1-preproceso-sigma0-vv-inventory/${projectId}?pol=vv`).catch(() => ({ data: { items: [] } })),
        api.get(`/preprocess/s1-preproceso-sigma0-vv-inventory/${projectId}?pol=vh`).catch(() => ({ data: { items: [] } })),
        api.get(`/layers/${projectId}`).catch(() => ({ data: [] })),
      ]);

      const nextAdapted = adaptInventories({
        s1Items: s1Inv.data?.items || [],
        s2Items: s2Inv.data?.items || [],
        psItems: psInv.data?.items || [],
        s2Recortes: s2Rec.data?.items || [],
        psRecortes: psRec.data?.items || [],
        s1PrepVv: s1PrepVv.data?.items || [],
        s1PrepVh: s1PrepVh.data?.items || [],
      });
      setAdapted(nextAdapted);
      adaptedRef.current = nextAdapted;

      const vectorLayer = (layersRes.data || []).find((l) => l.geom_type === "Vector") || layersRes.data?.[0];
      if (vectorLayer?.id) {
        try {
          const gj = await api.get(`/layers/${projectId}/${vectorLayer.id}/geojson`);
          setAoiGeojson(gj.data);
        } catch {
          setAoiGeojson(null);
        }
      } else {
        setAoiGeojson(null);
      }

      void loadClusters();
      void loadSmartClusters();
      void loadSoil();
      void loadSeries();
    } catch (e) {
      setError(formatApiErrorDetail(e));
      setAdapted(null);
    } finally {
      setLoading(false);
    }
  }, [projectId, token, loadClusters, loadSmartClusters, loadSoil, loadSeries]);

  useEffect(() => {
    previewCache.current.clear();
    seriesCache.current.clear();
    void load();
  }, [load]);

  const getCachedPreview = useCallback(async (cacheKey, fetcher) => {
    if (previewCache.current.has(cacheKey)) return previewCache.current.get(cacheKey);
    const url = await fetcher();
    previewCache.current.set(cacheKey, url);
    return url;
  }, []);

  const extras = {
    clusterBySensor,
    clustersLoading,
    clustersError,
    psStClusters,
    clientSoilSummary,
    clientSoilImgUrls,
    soilLoading,
    soilError,
    seriesBySensor,
    climateBySensor,
    seriesLoading,
    seriesError,
    hasGeofisica: !!(clientSoilSummary && Object.keys(clientSoilSummary).length),
    reloadSeries: loadSeries,
  };

  return {
    loading,
    error,
    adapted,
    aoiGeojson,
    extras,
    reload: load,
    getCachedPreview,
  };
}
