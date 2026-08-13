import { useEffect, useMemo, useRef, useState } from "react";
import api, { API_URL, formatApiErrorDetail, loadStoredAuth, setAuthToken } from "../../api";
import { getClientBrand } from "../../branding";
import SensorTimelapseViewer from "./SensorTimelapseViewer";
import ClientSoilViewModal from "./ClientSoilViewModal";
import DemRoiEditor, { defaultRoi, soilRoiToQueryParam } from "./DemRoiEditor";
import VegetationTimeSeriesCharts from "../VegetationTimeSeriesCharts";
import ClimateTimeSeriesChart, { CLIMATE_SERIES_COLORS } from "./ClimateTimeSeriesChart";
import DashboardIaAnalysisModal, { DigitalBrainIcon } from "./DashboardIaAnalysisModal";

const SENSOR_META = {
  s1: { title: "Sentinel-1", variant: "s1", defaultIndex: "RVI" },
  s2: { title: "Sentinel-2", variant: "s2", defaultIndex: "NDVI" },
  ps: { title: "PlanetScope", variant: "ps", defaultIndex: "NDVI" },
};

/** Alinea índice elegido con claves del inventario (misma capitalización que el API, p. ej. CIre). */
function resolveInventoryIndexKey(indices, preferred) {
  if (!indices?.length) return null;
  if (preferred != null && preferred !== "" && indices.includes(preferred)) return preferred;
  if (preferred != null && preferred !== "") {
    const u = String(preferred).toUpperCase();
    for (const k of indices) {
      if (String(k).toUpperCase() === u) return k;
    }
  }
  return indices[0] ?? null;
}

function normIso(s) {
  return String(s || "").slice(0, 10);
}

/** Primeros YYYY-MM-DD de sort_key (p. ej. Planet con sufijo). */
function dateKeyFromSortKey(sortKey) {
  const m = String(sortKey || "").match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : "";
}

function findRecortePathForSceneDate(items, sceneIso) {
  const t = normIso(sceneIso);
  if (!t || !items?.length) return null;
  for (const it of items) {
    if (dateKeyFromSortKey(it.sort_key) === t) return it.relative_path;
  }
  for (const it of items) {
    const sk = String(it.sort_key || "");
    if (sk.startsWith(t)) return it.relative_path;
  }
  /* PlanetScope: PS_dd-mm-yy.tif frente a sort_key ISO */
  const [y, mo, d] = t.split("-");
  if (y?.length === 4 && mo && d) {
    const yy = y.slice(2);
    const psNeedle = `${d}-${mo}-${yy}`;
    const compact = `${y}${mo}${d}`;
    for (const it of items) {
      const hay = `${it.basename || ""} ${it.relative_path || ""}`.toLowerCase();
      if (hay.includes(psNeedle) || hay.includes(compact)) return it.relative_path;
    }
  }
  return null;
}

function buildRecorteRgbEndpoint(projectId, relativePath, pipelineVariant) {
  const base = API_URL.replace(/\/$/, "");
  return `${base}/preprocess/recortes-preview/${projectId}?path=${encodeURIComponent(
    relativePath
  )}&pipeline_variant=${encodeURIComponent(pipelineVariant)}`;
}

/** Vista tipo «RGB» para S1: Sigma0 VV (SNAP/ENVI) bajo s1preproceso/. */
function buildS1Sigma0PreviewEndpoint(projectId, relativePath) {
  const base = API_URL.replace(/\/$/, "");
  return `${base}/preprocess/s1-preproceso-sigma0-vv-preview/${projectId}?path=${encodeURIComponent(
    relativePath
  )}&pol=vv&palette=spectral`;
}

function isS1RecorteItem(item) {
  const rp = String(item?.relative_path || "").replace(/\\/g, "/");
  return rp.startsWith("S1/") || rp.includes("/S1/");
}

function buildPreviewEndpoint(sensor, projectId, frame) {
  const base = API_URL.replace(/\/$/, "");
  if (sensor === "s1") {
    return `${base}/preprocess/s1-sar-index-stacks-preview/${projectId}?path=${encodeURIComponent(
      frame.relativePath
    )}&band=${frame.band}&index_palette=1`;
  }
  const pv = sensor === "ps" ? "ps" : "s2";
  return `${base}/preprocess/index-stacks-preview/${projectId}?path=${encodeURIComponent(
    frame.relativePath
  )}&band=${frame.band}&index_palette=1&pipeline_variant=${encodeURIComponent(pv)}`;
}

/**
 * Descarga el PNG del preview vía axios (mismo interceptor 401/refresh que el resto de la app).
 * `fetch` directo dejaba previews en blanco si el token del prop estaba desfasado respecto a sessionStorage.
 */
async function fetchPreviewObjectUrl(fullUrl, token) {
  const url = String(fullUrl || "").trim();
  if (!url) throw new Error("URL de preview vacía");
  const { access } = loadStoredAuth();
  const tok = access || token;
  if (tok) setAuthToken(tok);
  // 1) Preferimos axios para aprovechar interceptor de refresh.
  try {
    const resp = await api.get(url, { responseType: "blob" });
    const blob = resp?.data instanceof Blob ? resp.data : new Blob([resp?.data ?? ""]);
    if (blob.size > 0) {
      const ab = await blob.arrayBuffer();
      const bytes = new Uint8Array(ab);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
      const b64 = btoa(binary);
      // Forzamos MIME de imagen para evitar data:application/octet-stream no renderizable en <img>.
      return `data:image/png;base64,${b64}`;
    }
  } catch {
    // 2) Fallback directo por si hay edge-cases con axios + absolute URL.
  }
  const resp = await fetch(url, {
    headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`Preview ${resp.status}`);
  const blob = await resp.blob();
  if (!blob || blob.size === 0) throw new Error("Preview vacío");
  const ab = await blob.arrayBuffer();
  const bytes = new Uint8Array(ab);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  const b64 = btoa(binary);
  return `data:image/png;base64,${b64}`;
}

function safeRevokePreviewUrl(url) {
  if (typeof url !== "string" || !url.startsWith("blob:")) return;
  URL.revokeObjectURL(url);
}

const SOIL_CLUSTER_BAR_COLORS = [
  "#e41a1c",
  "#377eb8",
  "#4daf4a",
  "#984ea3",
  "#ff7f00",
  "#ffff33",
  "#a65628",
  "#f781bf",
];

function SoilClusterSampleBars({ samples, totalSamples, clusterCount, compact = false, thumb = false }) {
  const arr = Array.isArray(samples) ? samples : [];
  const k = Math.max(1, Number(clusterCount) || arr.length || 1);
  const total = Math.max(1, Number(totalSamples) || 1);
  let barW;
  let gap;
  let svgW;
  let maxH;
  let baseY;
  let svgH;
  let fs;
  let labelY;
  let rx;
  let minBar;
  if (thumb) {
    barW = Math.min(22, Math.floor(165 / Math.max(k, 1)));
    gap = 4;
    svgW = Math.min(260, 14 + k * (barW + gap));
    maxH = 36;
    baseY = 56;
    svgH = 68;
    fs = 7;
    labelY = 64;
    rx = 3;
    minBar = 5;
  } else if (compact) {
    barW = Math.min(40, Math.floor(280 / Math.max(k, 1)));
    gap = 6;
    svgW = Math.min(360, 28 + k * (barW + gap));
    maxH = 56;
    baseY = 88;
    svgH = 108;
    fs = 9;
    labelY = 102;
    rx = 4;
    minBar = 6;
  } else {
    barW = Math.min(64, Math.floor(340 / Math.max(k, 1)));
    gap = 10;
    svgW = Math.min(420, 28 + k * (barW + gap));
    maxH = 150;
    baseY = 180;
    svgH = 230;
    fs = 11;
    labelY = 196;
    rx = 6;
    minBar = 8;
  }
  return (
    <svg
      viewBox={`0 0 ${svgW} ${svgH}`}
      className={`adv-soilplus-svg${compact ? " adv-soilplus-svg--compact" : ""}${thumb ? " adv-soilplus-svg--thumb" : ""}`}
      role="img"
      aria-label="Muestras por cluster"
    >
      {Array.from({ length: k }, (_, i) => {
        const count = Number(arr[i]) || 0;
        const bh = Math.max(minBar, (count / total) * maxH);
        const x = 14 + i * (barW + gap);
        const y = baseY - bh;
        const fill = SOIL_CLUSTER_BAR_COLORS[i % SOIL_CLUSTER_BAR_COLORS.length];
        return (
          <g key={`cbar-${i}`}>
            <rect x={x} y={y} width={barW} height={bh} fill={fill} rx={rx} />
            <text x={x + barW / 2} y={labelY} textAnchor="middle" fontSize={fs}>
              C{i + 1}
            </text>
            <text x={x + barW / 2} y={Math.max(10, y - 3)} textAnchor="middle" fontSize={fs}>
              {count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function SoilFcmSampleTriangles({ points, viewWidth, viewHeight }) {
  const w = Math.max(1, Number(viewWidth) || 1);
  const h = Math.max(1, Number(viewHeight) || 1);
  const s = Math.max(0.2, Math.min(w, h) / 880);
  const arr = Array.isArray(points) ? points : [];
  if (!arr.length || !Number.isFinite(w) || !Number.isFinite(h)) return null;
  return (
    <svg
      className="adv-soilplus-sample-overlay"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden
    >
      {arr.map((p) => {
        const cx = Number(p.col);
        const cy = Number(p.row);
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        const cid =
          p.cluster != null && Number.isFinite(Number(p.cluster)) ? Number(p.cluster) : 0;
        const fill = SOIL_CLUSTER_BAR_COLORS[cid % SOIL_CLUSTER_BAR_COLORS.length];
        const pts = `${cx},${cy - s} ${cx - s * 0.92},${cy + s * 0.58} ${cx + s * 0.92},${cy + s * 0.58}`;
        return (
          <polygon
            key={`sp-${p.index}-${p.row}-${p.col}`}
            points={pts}
            fill={fill}
            fillOpacity={0.92}
            stroke="#fff"
            strokeWidth={Math.max(0.1, s * 0.35)}
            strokeLinejoin="round"
          />
        );
      })}
    </svg>
  );
}

function SoilQCurveChart({ data }) {
  if (!data?.k_values?.length) return <p className="adv-soilplus-image-empty">Pulsa Ejecutar.</p>;
  const pts = [];
  for (let i = 0; i < data.k_values.length; i += 1) {
    const q = data.q_values[i];
    if (q != null && Number.isFinite(Number(q))) pts.push({ k: Number(data.k_values[i]), q: Number(q) });
  }
  if (!pts.length) return <p className="adv-soilplus-image-empty">Sin valores Q válidos.</p>;

  const W = 280;
  const H = 148;
  const pl = 46;
  const pr = 14;
  const pt = 16;
  const pb = 34;
  const kMin = Math.min(...pts.map((p) => p.k));
  const kMax = Math.max(...pts.map((p) => p.k));
  const qMin = Math.min(...pts.map((p) => p.q));
  const qMax = Math.max(...pts.map((p) => p.q));
  const qPad = Math.max((qMax - qMin) * 0.1, 0.015);
  const yLo = qMin - qPad;
  const yHi = qMax + qPad;
  const xScale = (k) => pl + ((k - kMin) / Math.max(kMax - kMin, 1)) * (W - pl - pr);
  const yScale = (q) => pt + (1 - (q - yLo) / Math.max(yHi - yLo, 1e-9)) * (H - pt - pb);
  const linePts = pts.map((p) => `${xScale(p.k)},${yScale(p.q)}`).join(" ");

  const xTicks = [...new Set(pts.map((p) => p.k))].sort((a, b) => a - b);
  const ySpan = yHi - yLo;
  const nY = 5;
  const yTicks =
    ySpan < 1e-12
      ? [yLo]
      : Array.from({ length: nY }, (_, i) => yLo + (i / (nY - 1)) * ySpan);
  const qDecimals = ySpan < 0.08 ? 3 : ySpan < 0.25 ? 3 : 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="adv-soilplus-q-chart" role="img" aria-label="Curva Q versus número de clusters">
      <line x1={pl} y1={pt} x2={pl} y2={H - pb} stroke="#cbd5e1" strokeWidth="1" />
      <line x1={pl} y1={H - pb} x2={W - pr} y2={H - pb} stroke="#cbd5e1" strokeWidth="1" />
      {yTicks.map((qv) => {
        const y = yScale(qv);
        if (!Number.isFinite(y)) return null;
        return (
          <g key={`qyt-${qv}`}>
            <line x1={pl - 4} y1={y} x2={pl} y2={y} stroke="#94a3b8" strokeWidth="1" />
            <text x={pl - 6} y={y + 3} textAnchor="end" fontSize="8" fill="#64748b">
              {Number(qv.toFixed(6)).toFixed(qDecimals)}
            </text>
          </g>
        );
      })}
      {xTicks.map((k) => {
        const x = xScale(k);
        if (!Number.isFinite(x)) return null;
        return (
          <g key={`qxt-${k}`}>
            <line x1={x} y1={H - pb} x2={x} y2={H - pb + 4} stroke="#94a3b8" strokeWidth="1" />
            <text x={x} y={H - pb + 13} textAnchor="middle" fontSize="8" fill="#64748b">
              {String(k)}
            </text>
          </g>
        );
      })}
      <polyline fill="none" stroke="#2563eb" strokeWidth="1.6" strokeDasharray="6 4" points={linePts} />
      {pts.map((p) => (
        <circle key={`qk-${p.k}`} cx={xScale(p.k)} cy={yScale(p.q)} r={4.5} fill="#2563eb" stroke="#1d4ed8" strokeWidth="0.9" />
      ))}
      <text x={(pl + W - pr) / 2} y={H - 4} textAnchor="middle" fontSize="9" fill="#475569">
        Número de clusters (K)
      </text>
      <text x={10} y={(pt + H - pb) / 2} textAnchor="middle" fontSize="9" fill="#475569" transform={`rotate(-90 10 ${(pt + H - pb) / 2})`}>
        Q
      </text>
    </svg>
  );
}

export default function AdvancedDashboard({
  open,
  onClose,
  token,
  projectId,
  projectName = "",
  isCliente = false,
  viewerEmail = "",
  initialSmartFocus = "cluster",
  projectStatus,
  onOpenClientVisualization,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sensorData, setSensorData] = useState({ s1: null, s2: null, ps: null });
  const [sensorActive, setSensorActive] = useState("s2");
  const [dateIdxBySensor, setDateIdxBySensor] = useState({ s1: 0, s2: 0, ps: 0 });
  const [indexBySensor, setIndexBySensor] = useState({ s1: "RVI", s2: "NDVI", ps: "NDVI" });
  const [playingBySensor, setPlayingBySensor] = useState({ s1: false, s2: false, ps: false });
  const [opacityBySensor, setOpacityBySensor] = useState({ s1: 1, s2: 1, ps: 1 });
  const [srcBySensor, setSrcBySensor] = useState({ s1: "", s2: "", ps: "" });
  const [rgbSrcBySensor, setRgbSrcBySensor] = useState({ s1: "", s2: "", ps: "" });
  const [recorteInventory, setRecorteInventory] = useState({ s2: [], ps: [] });
  const [s1PrepSigmaItems, setS1PrepSigmaItems] = useState([]);
  const [clusterBySensor, setClusterBySensor] = useState({ s1: [], s2: [], ps: [] });
  const [clusterVisible, setClusterVisible] = useState(false);
  const [selectedClusterKey, setSelectedClusterKey] = useState({ s1: "", s2: "", ps: "" });
  const [pointSelection, setPointSelection] = useState(null);
  const [roiSelection, setRoiSelection] = useState(null);
  const [roiMode, setRoiMode] = useState(false);
  const [seriesBySensor, setSeriesBySensor] = useState({ s1: null, s2: null, ps: null });
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [climateBySensor, setClimateBySensor] = useState({ s1: [], s2: [], ps: [] });
  const [climateVars, setClimateVars] = useState({
    precip: true,
    temp: true,
    humidity: false,
    radiation: false,
  });
  /** Mapas KMeans espacio-temporal PS: smart1 / smart2 / smart3. */
  const [psStCluster1Preview, setPsStCluster1Preview] = useState("");
  const [psStCluster1Busy, setPsStCluster1Busy] = useState(false);
  const [psStCluster1Error, setPsStCluster1Error] = useState("");
  const [psStCluster2Preview, setPsStCluster2Preview] = useState("");
  const [psStCluster2Busy, setPsStCluster2Busy] = useState(false);
  const [psStCluster2Error, setPsStCluster2Error] = useState("");
  const [psStCluster3Preview, setPsStCluster3Preview] = useState("");
  const [psStCluster3Busy, setPsStCluster3Busy] = useState(false);
  const [psStCluster3Error, setPsStCluster3Error] = useState("");
  /** Slot del cluster cuyo panel «Índices usados» está abierto (1, 2, 3 o null). */
  const [openClusterInfo, setOpenClusterInfo] = useState(null);
  const [iaReportOpen, setIaReportOpen] = useState(false);
  /** Popover «¿Qué es AGRO Geofísica?» en la cabecera de la sección. */
  const [geofisicaInfoOpen, setGeofisicaInfoOpen] = useState(false);
  const [geofisicaZoomOpen, setGeofisicaZoomOpen] = useState(false);
  const [soilPlusOpen, setSoilPlusOpen] = useState(false);
  const [soilPlusBusy, setSoilPlusBusy] = useState(false);
  const [soilPlusError, setSoilPlusError] = useState("");
  const [soilSampleCount, setSoilSampleCount] = useState(60);
  const [soilWindowSize, setSoilWindowSize] = useState(13);
  const [soilClusterCount, setSoilClusterCount] = useState(4);
  const [soilVars, setSoilVars] = useState({ f1: null, f2: null, f3: null });
  const [soilDemInfo, setSoilDemInfo] = useState(null);
  const [soilDemPreview, setSoilDemPreview] = useState("");
  const [soilCvPreview, setSoilCvPreview] = useState("");
  const [soilAspectPreview, setSoilAspectPreview] = useState("");
  const [soilSlopePreview, setSoilSlopePreview] = useState("");
  const [soilClusterPreview, setSoilClusterPreview] = useState("");
  const [soilSamplingPlan, setSoilSamplingPlan] = useState(null);
  const [soilQCurve, setSoilQCurve] = useState(null);
  const [soilClusterZoom, setSoilClusterZoom] = useState(1);
  const [soilClusterPan, setSoilClusterPan] = useState({ x: 0, y: 0 });
  const [soilClusterDragging, setSoilClusterDragging] = useState(false);
  const [soilClusterNaturalSize, setSoilClusterNaturalSize] = useState({ w: 0, h: 0 });
  const [soilRoi, setSoilRoi] = useState(() => defaultRoi());
  const [soilCvColormap, setSoilCvColormap] = useState("jet");
  const [soilFishnetStep, setSoilFishnetStep] = useState(5);
  const [soilCvEngineActive, setSoilCvEngineActive] = useState("fast");
  const [clientSoilSummary, setClientSoilSummary] = useState(null);
  const [clientSoilImgUrls, setClientSoilImgUrls] = useState({ fast: {}, matlab: {} });
  const clientSoilImgRevokeRef = useRef({ fast: {}, matlab: {} });
  const previewCacheRef = useRef(new Map());
  const seriesCacheRef = useRef(new Map());
  const recortesCacheRef = useRef({ s2: null, ps: null });
  const loadedProjectRef = useRef(null);
  const soilDragRef = useRef({ dragging: false, startX: 0, startY: 0, panX: 0, panY: 0 });
  const effectiveToken = token || loadStoredAuth().access || "";
  const isAdminView = !isCliente;

  const clientDashboardBlocked = useMemo(() => {
    if (!isCliente) return false;
    if (projectStatus == null || String(projectStatus).trim() === "") return false;
    const n = String(projectStatus).trim().toLowerCase().replace(/\s+/g, " ");
    return n !== "publicado";
  }, [isCliente, projectStatus]);

  /**
   * Hay resultados Smart Soil persistidos (Fast o Mat) cuando alguna variante tiene `saved_at`
   * o al menos una imagen DEM/CV/FCM cargada. En ese caso ocultamos el placeholder de la
   * sección «AGRO Geofísica» y mostramos los resultados; sin resultados, solo el placeholder.
   */
  const hasGeofisicaResults = useMemo(() => {
    const variants = ["fast", "matlab"];
    for (const vk of variants) {
      if (clientSoilSummary?.[vk]?.saved_at) return true;
      const urls = clientSoilImgUrls?.[vk] || {};
      if (Object.values(urls).some((u) => !!u)) return true;
    }
    return false;
  }, [clientSoilSummary, clientSoilImgUrls]);

  const clientSoilZoomInitialVariant = useMemo(() => {
    if (clientSoilSummary?.fast) return "fast";
    if (clientSoilSummary?.matlab) return "matlab";
    const hasFast = Object.values(clientSoilImgUrls?.fast || {}).some(Boolean);
    if (hasFast) return "fast";
    return "matlab";
  }, [clientSoilSummary, clientSoilImgUrls]);

  useEffect(() => {
    if (!open) {
      setGeofisicaZoomOpen(false);
      setGeofisicaInfoOpen(false);
    }
  }, [open]);

  const frameFor = (sensor) => {
    const sd = sensorData[sensor];
    if (!sd) return null;
    const idxKey = indexBySensor[sensor] || sd.indices[0];
    const frames = sd.framesByIndex[idxKey] || [];
    return frames[dateIdxBySensor[sensor]] || null;
  };

  const framesFor = (sensor) => {
    const sd = sensorData[sensor];
    if (!sd) return [];
    const idxKey = indexBySensor[sensor] || sd.indices[0];
    return sd.framesByIndex[idxKey] || [];
  };

  // Evita estados fuera de rango (p. ej. recarga de inventario con menos escenas),
  // que podían dejar frame=null y vaciar previews ya cargados.
  useEffect(() => {
    if (!open) return;
    setDateIdxBySensor((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const sensor of ["s1", "s2", "ps"]) {
        const frames = framesFor(sensor);
        const maxIdx = Math.max(frames.length - 1, 0);
        const cur = Number(prev[sensor] ?? 0);
        const clamped = Math.min(Math.max(cur, 0), maxIdx);
        if (clamped !== cur) {
          next[sensor] = clamped;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [open, sensorData, indexBySensor]);

  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    const load = async () => {
      if (clientDashboardBlocked) {
        for (const [, url] of previewCacheRef.current.entries()) safeRevokePreviewUrl(url);
        previewCacheRef.current.clear();
        setSrcBySensor({ s1: "", s2: "", ps: "" });
        setRgbSrcBySensor({ s1: "", s2: "", ps: "" });
        setSensorData({ s1: null, s2: null, ps: null });
        setRecorteInventory({ s2: [], ps: [] });
        setS1PrepSigmaItems([]);
        recortesCacheRef.current = { s2: null, ps: null };
        setPsStCluster1Preview("");
        setPsStCluster1Error("");
        setPsStCluster2Preview("");
        setPsStCluster2Error("");
        setPsStCluster3Preview("");
        setPsStCluster3Error("");
        setPsStCluster1Busy(false);
        setPsStCluster2Busy(false);
        setPsStCluster3Busy(false);
        setClusterBySensor({ s1: [], s2: [], ps: [] });
        setSelectedClusterKey({ s1: "", s2: "", ps: "" });
        setSeriesBySensor({ s1: null, s2: null, ps: null });
        setClimateBySensor({ s1: [], s2: [], ps: [] });
        setError("");
        setLoading(false);
        loadedProjectRef.current = projectId;
        return;
      }
      setLoading(true);
      setError("");
      const projectChanged = loadedProjectRef.current !== projectId;
      if (projectChanged) {
        for (const [, url] of previewCacheRef.current.entries()) safeRevokePreviewUrl(url);
        previewCacheRef.current.clear();
        setSrcBySensor({ s1: "", s2: "", ps: "" });
        setRgbSrcBySensor({ s1: "", s2: "", ps: "" });
        setSensorData({ s1: null, s2: null, ps: null });
        setRecorteInventory({ s2: [], ps: [] });
        setS1PrepSigmaItems([]);
        recortesCacheRef.current = { s2: null, ps: null };
        setPsStCluster1Preview("");
        setPsStCluster1Error("");
        setPsStCluster2Preview("");
        setPsStCluster2Error("");
        setPsStCluster3Preview("");
        setPsStCluster3Error("");
        setPsStCluster1Busy(false);
        setPsStCluster2Busy(false);
        setPsStCluster3Busy(false);
      }
      try {
        if (effectiveToken) setAuthToken(effectiveToken);
        const [s1Inv, s2Inv, psInv, s2Rec, psRec, s1PrepVv, c1, c2, c3] = await Promise.all([
          api.get(`/preprocess/s1-sar-index-stacks-inventory/${projectId}`),
          api.get(`/preprocess/index-stacks-inventory/${projectId}?pipeline_variant=s2`),
          api.get(`/preprocess/index-stacks-inventory/${projectId}?pipeline_variant=ps`),
          api.get(`/preprocess/recortes-inventory/${projectId}?pipeline_variant=s2`).catch(() => ({ data: { items: [] } })),
          api.get(`/preprocess/recortes-inventory/${projectId}?pipeline_variant=ps`).catch(() => ({ data: { items: [] } })),
          api.get(`/preprocess/s1-preproceso-sigma0-vv-inventory/${projectId}?pol=vv`).catch(() => ({ data: { items: [] } })),
          api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=s1`).catch(() => ({ data: { results: [] } })),
          api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=s2`).catch(() => ({ data: { results: [] } })),
          api.get(`/cluster-analysis/gmm-results/${projectId}?pipeline_variant=ps`).catch(() => ({ data: { results: [] } })),
        ]);
        if (cancelled) return;

        function buildSensorInventory(rows, sensor) {
          const byIndex = {};
          for (const row of rows || []) {
            const key = String(row.index_key || "").trim();
            const dates = Array.isArray(row.band_dates) ? row.band_dates.map(normIso) : [];
            if (!key || !dates.length || !row.relative_path) continue;
            const current = byIndex[key];
            if (current && (current._score || 0) >= dates.length) continue;
            byIndex[key] = {
              _score: dates.length,
              frames: dates.map((d, i) => ({
                id: `${sensor}:${key}:${i + 1}:${row.relative_path}`,
                date: d,
                band: i + 1,
                relativePath: row.relative_path,
              })),
            };
          }
          const indices = Object.keys(byIndex).sort();
          const framesByIndex = Object.fromEntries(indices.map((k) => [k, byIndex[k].frames]));
          return { indices, framesByIndex };
        }

        const s1 = buildSensorInventory(s1Inv.data?.items || [], "s1");
        const s2 = buildSensorInventory(s2Inv.data?.items || [], "s2");
        const ps = buildSensorInventory(psInv.data?.items || [], "ps");
        const s2Items = s2Rec.data?.items || [];
        const psItems = psRec.data?.items || [];
        recortesCacheRef.current.s2 = s2Items.map((x) => x.relative_path).filter(Boolean);
        recortesCacheRef.current.ps = psItems.map((x) => x.relative_path).filter(Boolean);
        setRecorteInventory({ s2: s2Items, ps: psItems });
        setS1PrepSigmaItems(s1PrepVv.data?.items || []);
        setSensorData({ s1, s2, ps });
        setIndexBySensor((prev) => ({
          s1: resolveInventoryIndexKey(s1.indices, prev.s1) ?? s1.indices[0] ?? SENSOR_META.s1.defaultIndex,
          s2: resolveInventoryIndexKey(s2.indices, prev.s2) ?? s2.indices[0] ?? SENSOR_META.s2.defaultIndex,
          ps: resolveInventoryIndexKey(ps.indices, prev.ps) ?? ps.indices[0] ?? SENSOR_META.ps.defaultIndex,
        }));
        setClusterBySensor({
          s1: c1.data?.results || [],
          s2: c2.data?.results || [],
          ps: c3.data?.results || [],
        });
        setSelectedClusterKey({
          s1: c1.data?.results?.[0]?.key || "",
          s2: c2.data?.results?.[0]?.key || "",
          ps: c3.data?.results?.[0]?.key || "",
        });
        loadedProjectRef.current = projectId;
      } catch (e) {
        if (!cancelled) setError(formatApiErrorDetail(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [open, projectId, effectiveToken, clientDashboardBlocked]);

  const loadSmartClusterPreviews = async () => {
    if (!projectId || !effectiveToken || clientDashboardBlocked) return;
    const base = API_URL.replace(/\/$/, "");
    const slot = (preset) =>
      preset === "smart3"
        ? {
            setBusy: setPsStCluster3Busy,
            setErr: setPsStCluster3Error,
            setPreview: setPsStCluster3Preview,
          }
        : preset === "smart2"
          ? {
              setBusy: setPsStCluster2Busy,
              setErr: setPsStCluster2Error,
              setPreview: setPsStCluster2Preview,
            }
          : {
              setBusy: setPsStCluster1Busy,
              setErr: setPsStCluster1Error,
              setPreview: setPsStCluster1Preview,
            };
    if (effectiveToken) setAuthToken(effectiveToken);
    for (const preset of ["smart1", "smart2", "smart3"]) {
      const { setBusy, setErr, setPreview } = slot(preset);
      setBusy(true);
      setErr("");
      try {
        const dataUrl = await fetchPreviewObjectUrl(
          `${base}/preprocess/ps-spatiotemporal-cluster-preview/${projectId}?preset=${encodeURIComponent(preset)}`,
          effectiveToken
        );
        setPreview(dataUrl);
      } catch (e) {
        setPreview("");
        setErr(formatApiErrorDetail(e));
      } finally {
        setBusy(false);
      }
    }
  };

  useEffect(() => {
    if (!open) return;
    void loadSmartClusterPreviews();
  }, [open, projectId, effectiveToken, clientDashboardBlocked]);

  useEffect(() => {
    if (!open) return;
    if (initialSmartFocus === "soil") {
      setSoilPlusOpen(true);
    }
  }, [open, initialSmartFocus]);

  useEffect(() => {
    if (!open) return;
    const timers = [];
    for (const sensor of ["s1", "s2", "ps"]) {
      if (!playingBySensor[sensor]) continue;
      const t = window.setInterval(() => {
        const frames = framesFor(sensor);
        if (!frames.length) return;
        setDateIdxBySensor((prev) => ({
          ...prev,
          [sensor]: (prev[sensor] + 1) % frames.length,
        }));
      }, 1400);
      timers.push(t);
    }
    return () => timers.forEach((t) => window.clearInterval(t));
  }, [open, playingBySensor, sensorData, indexBySensor]);

  useEffect(() => {
    if (!open || !projectId || clientDashboardBlocked) return undefined;
    let cancelled = false;
    async function loadCurrentFrame(sensor) {
      const frame = frameFor(sensor);
      if (!frame) {
        // No limpiar en transiciones breves; conserva la última imagen válida.
        return;
      }
      const cacheKey = `${projectId}|idx|${sensor}|${frame.id}`;
      if (previewCacheRef.current.has(cacheKey)) {
        setSrcBySensor((p) => ({ ...p, [sensor]: previewCacheRef.current.get(cacheKey) || "" }));
        return;
      }
      try {
        const endpoint = buildPreviewEndpoint(sensor, projectId, frame);
        const objectUrl = await fetchPreviewObjectUrl(endpoint, effectiveToken);
        if (cancelled) {
          safeRevokePreviewUrl(objectUrl);
          return;
        }
        previewCacheRef.current.set(cacheKey, objectUrl);
        setSrcBySensor((p) => ({ ...p, [sensor]: objectUrl }));
      } catch (e) {
        if (!cancelled) {
          setSrcBySensor((p) => ({ ...p, [sensor]: "" }));
          setError((prev) => prev || `No se pudo cargar preview de índice (${sensor}): ${formatApiErrorDetail(e)}`);
        }
      }
    }
    void loadCurrentFrame("s1");
    void loadCurrentFrame("s2");
    void loadCurrentFrame("ps");
    return () => {
      cancelled = true;
    };
  }, [open, projectId, sensorData, indexBySensor, dateIdxBySensor, loading, effectiveToken, clientDashboardBlocked]);

  useEffect(() => {
    if (!open || !projectId || clientDashboardBlocked) return undefined;
    let cancelled = false;
    async function loadRgbPreview(sensor) {
      const frame = frameFor(sensor);
      if (!frame) {
        // No limpiar en transiciones breves; conserva la última imagen válida.
        return;
      }

      if (sensor === "s1") {
        const relSigma = findRecortePathForSceneDate(s1PrepSigmaItems, frame.date);
        if (relSigma) {
          const cacheKey = `${projectId}|s1sigma|${relSigma}`;
          if (previewCacheRef.current.has(cacheKey)) {
            setRgbSrcBySensor((p) => ({ ...p, s1: previewCacheRef.current.get(cacheKey) || "" }));
            return;
          }
          try {
            const endpoint = buildS1Sigma0PreviewEndpoint(projectId, relSigma);
            const objectUrl = await fetchPreviewObjectUrl(endpoint, effectiveToken);
            if (cancelled) {
              safeRevokePreviewUrl(objectUrl);
              return;
            }
            previewCacheRef.current.set(cacheKey, objectUrl);
            setRgbSrcBySensor((p) => ({ ...p, s1: objectUrl }));
            return;
          } catch (e) {
            if (!cancelled) {
              setRgbSrcBySensor((p) => ({ ...p, s1: "" }));
              setError((prev) => prev || `No se pudo cargar preview RGB (${sensor}): ${formatApiErrorDetail(e)}`);
            }
          }
        }
        const s1RecItems = (recorteInventory.s2 || []).filter(isS1RecorteItem);
        const relGeo = findRecortePathForSceneDate(s1RecItems, frame.date);
        if (!relGeo) {
          if (!cancelled) setRgbSrcBySensor((p) => ({ ...p, s1: "" }));
          return;
        }
        const cacheKey = `${projectId}|rgb|s2|${relGeo}`;
        if (previewCacheRef.current.has(cacheKey)) {
          setRgbSrcBySensor((p) => ({ ...p, s1: previewCacheRef.current.get(cacheKey) || "" }));
          return;
        }
        try {
          const endpoint = buildRecorteRgbEndpoint(projectId, relGeo, "s2");
          const objectUrl = await fetchPreviewObjectUrl(endpoint, effectiveToken);
          if (cancelled) {
            safeRevokePreviewUrl(objectUrl);
            return;
          }
          previewCacheRef.current.set(cacheKey, objectUrl);
          setRgbSrcBySensor((p) => ({ ...p, s1: objectUrl }));
        } catch (e) {
          if (!cancelled) {
            setRgbSrcBySensor((p) => ({ ...p, s1: "" }));
            setError((prev) => prev || `No se pudo cargar preview RGB (${sensor}): ${formatApiErrorDetail(e)}`);
          }
        }
        return;
      }

      const items = recorteInventory[sensor] || [];
      const rel = findRecortePathForSceneDate(items, frame.date);
      if (!rel) {
        setRgbSrcBySensor((p) => ({ ...p, [sensor]: "" }));
        return;
      }
      const pv = sensor === "ps" ? "ps" : "s2";
      const cacheKey = `${projectId}|rgb|${pv}|${rel}`;
      if (previewCacheRef.current.has(cacheKey)) {
        setRgbSrcBySensor((p) => ({ ...p, [sensor]: previewCacheRef.current.get(cacheKey) || "" }));
        return;
      }
      try {
        const endpoint = buildRecorteRgbEndpoint(projectId, rel, pv);
        const objectUrl = await fetchPreviewObjectUrl(endpoint, effectiveToken);
        if (cancelled) {
          safeRevokePreviewUrl(objectUrl);
          return;
        }
        previewCacheRef.current.set(cacheKey, objectUrl);
        setRgbSrcBySensor((p) => ({ ...p, [sensor]: objectUrl }));
      } catch (e) {
        if (!cancelled) {
          setRgbSrcBySensor((p) => ({ ...p, [sensor]: "" }));
          setError((prev) => prev || `No se pudo cargar preview RGB (${sensor}): ${formatApiErrorDetail(e)}`);
        }
      }
    }
    void loadRgbPreview("s1");
    void loadRgbPreview("s2");
    void loadRgbPreview("ps");
    return () => {
      cancelled = true;
    };
  }, [
    open,
    projectId,
    sensorData,
    indexBySensor,
    dateIdxBySensor,
    recorteInventory,
    s1PrepSigmaItems,
    loading,
    effectiveToken,
    clientDashboardBlocked,
  ]);

  useEffect(() => {
    if (!open) return;
    return () => {
      for (const [, url] of previewCacheRef.current.entries()) safeRevokePreviewUrl(url);
      previewCacheRef.current.clear();
      setSrcBySensor({ s1: "", s2: "", ps: "" });
      setRgbSrcBySensor({ s1: "", s2: "", ps: "" });
    };
  }, [open]);

  const selectionKey = useMemo(
    () => JSON.stringify({ p: pointSelection, r: roiSelection }),
    [pointSelection, roiSelection]
  );
  const runSoilPlusSave = async (cv_engine) => {
    if (!projectId || clientDashboardBlocked) return;
    setSoilPlusBusy(true);
    setSoilPlusError("");
    const eng = cv_engine === "matlab" ? "matlab" : "fast";
    setSoilCvEngineActive(eng);
    try {
      if (effectiveToken) setAuthToken(effectiveToken);
      const base = API_URL.replace(/\/$/, "");
      const roiQ = soilRoiToQueryParam(soilRoi);
      const params = {
        window_size: soilWindowSize,
        cv_engine: eng,
        n_clusters: soilClusterCount,
        fishnet_step: soilFishnetStep,
        total_samples: soilSampleCount,
        cmap: soilCvColormap,
        m: 2.0,
      };
      if (roiQ) params.roi_polygon = roiQ;
      const { data } = await api.post(`/preprocess/soilplus-execute-save/${projectId}`, null, {
        params,
      });

      const vk = eng === "matlab" ? "matlab" : "fast";
      const kinds = ["dem", "cv", "fcm", "aspect", "slope"];
      const imgEntries = await Promise.all(
        kinds.map(async (kind) => [kind, await fetchPreviewObjectUrl(`${base}/preprocess/soilplus-saved-img/${projectId}?variant=${vk}&kind=${kind}`, effectiveToken)])
      );
      const imgMap = Object.fromEntries(imgEntries);
      const tr = data?.terrain ?? {};
      setSoilVars({
        f1: Number(tr?.f1 ?? 0),
        f2: Number(tr?.f2 ?? 0),
        f3: Number(tr?.f3 ?? 0),
      });
      setSoilDemInfo({
        project_id: data?.project_id,
        input_image_path: data?.dem_input_image_path ?? "",
        window_size: data?.window_size,
        roi_pixel_count: data?.roi_pixel_count,
        roi_polygon_applied: data?.roi_polygon_applied,
        polygon_area_ha: data?.polygon_area_ha,
        suggested_sample_count: data?.total_samples,
        dem_mean: data?.dem_mean_snapshot,
        dem_roi_mean: data?.dem_roi_mean_snapshot,
        cv_mean: data?.cv_mean_snapshot,
        cv_run: data?.cv_run,
      });
      setSoilDemPreview(imgMap.dem || "");
      setSoilCvPreview(imgMap.cv || "");
      setSoilAspectPreview(imgMap.aspect || "");
      setSoilSlopePreview(imgMap.slope || "");
      setSoilClusterPreview(imgMap.fcm || "");
      setSoilSamplingPlan({
        samples_per_cluster: data?.samples_per_cluster,
        samples_requested_per_cluster: data?.samples_requested_per_cluster,
        total_samples: data?.total_samples,
        total_samples_placed: data?.total_samples_placed,
        total_samples_inferred: data?.total_samples_inferred,
        sample_points: data?.sample_points,
        raster_shape: data?.raster_shape,
        n_clusters: data?.n_clusters,
        fishnet_step: data?.fishnet_step,
        cv_run: data?.cv_run,
        window_size: data?.window_size,
      });
      setSoilQCurve(data?.q_curve ?? null);
      setSoilClusterZoom(1);
      setSoilClusterPan({ x: 0, y: 0 });
    } catch (e) {
      setSoilPlusError(formatApiErrorDetail(e));
    } finally {
      setSoilPlusBusy(false);
    }
  };

  useEffect(() => {
    setSoilRoi(defaultRoi());
    setSoilSamplingPlan(null);
    setSoilQCurve(null);
    setSoilAspectPreview("");
    setSoilSlopePreview("");
  }, [projectId]);

  useEffect(() => {
    if (!soilPlusOpen || !projectId || clientDashboardBlocked || !effectiveToken) return;
    if (!soilRoi?.closed || !Array.isArray(soilRoi.points) || soilRoi.points.length < 3) return;
    const roiQ = soilRoiToQueryParam(soilRoi);
    if (!roiQ) return;
    let cancelled = false;
    const t = setTimeout(() => {
      (async () => {
        try {
          setAuthToken(effectiveToken);
          const { data } = await api.get(`/preprocess/soilplus-dem-input/${projectId}`, {
            params: { window_size: soilWindowSize, roi_polygon: roiQ, cv_engine: soilCvEngineActive },
          });
          const s = data?.suggested_sample_count;
          if (!cancelled && s != null) setSoilSampleCount(Math.max(1, Math.round(Number(s))));
        } catch {
          /* ignore */
        }
      })();
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [soilPlusOpen, projectId, clientDashboardBlocked, effectiveToken, soilRoi.closed, soilRoi.points, soilWindowSize, soilCvEngineActive]);

  useEffect(() => {
    if (!soilPlusOpen || !projectId || clientDashboardBlocked || !effectiveToken) return;
    let cancelled = false;
    (async () => {
      try {
        setAuthToken(effectiveToken);
        const base = API_URL.replace(/\/$/, "");
        const demPng = await fetchPreviewObjectUrl(`${base}/preprocess/soilplus-dem-preview/${projectId}`, effectiveToken);
        if (!cancelled) setSoilDemPreview(demPng || "");
      } catch {
        if (!cancelled) setSoilDemPreview("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [soilPlusOpen, projectId, clientDashboardBlocked, effectiveToken]);

  useEffect(() => {
    const revokeBuckets = (b) => {
      if (!b) return;
      for (const vk of ["fast", "matlab"]) {
        const bucket = b[vk] || {};
        for (const url of Object.values(bucket)) safeRevokePreviewUrl(url);
      }
    };

    if (!open || !projectId || clientDashboardBlocked || !effectiveToken) {
      revokeBuckets(clientSoilImgRevokeRef.current);
      clientSoilImgRevokeRef.current = { fast: {}, matlab: {} };
      setClientSoilImgUrls({ fast: {}, matlab: {} });
      setClientSoilSummary(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        setAuthToken(effectiveToken);
        const { data } = await api.get(`/preprocess/soilplus-saved-summary/${projectId}`);
        if (cancelled) return;
        const variants = data?.variants || {};
        setClientSoilSummary(variants);
        const base = API_URL.replace(/\/$/, "");
        const nextBucket = { fast: {}, matlab: {} };
        for (const vk of ["fast", "matlab"]) {
          if (!variants[vk]) continue;
          for (const kind of ["dem", "cv", "fcm"]) {
            try {
              nextBucket[vk][kind] = await fetchPreviewObjectUrl(
                `${base}/preprocess/soilplus-saved-img/${projectId}?variant=${vk}&kind=${kind}`,
                effectiveToken
              );
            } catch {
              nextBucket[vk][kind] = "";
            }
          }
        }
        if (cancelled) {
          revokeBuckets(nextBucket);
          return;
        }
        revokeBuckets(clientSoilImgRevokeRef.current);
        clientSoilImgRevokeRef.current = nextBucket;
        setClientSoilImgUrls(nextBucket);
      } catch {
        if (!cancelled) {
          revokeBuckets(clientSoilImgRevokeRef.current);
          clientSoilImgRevokeRef.current = { fast: {}, matlab: {} };
          setClientSoilImgUrls({ fast: {}, matlab: {} });
          setClientSoilSummary(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, projectId, clientDashboardBlocked, effectiveToken]);

  useEffect(() => {
    setSoilClusterNaturalSize({ w: 0, h: 0 });
  }, [soilClusterPreview]);

  const soilClusterViewW =
    soilClusterNaturalSize.w || Number(soilSamplingPlan?.raster_shape?.width) || 0;
  const soilClusterViewH =
    soilClusterNaturalSize.h || Number(soilSamplingPlan?.raster_shape?.height) || 0;

  const handleSoilClusterWheel = (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    setSoilClusterZoom((prev) => {
      const next = Math.max(1, Math.min(6, Number((prev + delta).toFixed(2))));
      if (next === 1) setSoilClusterPan({ x: 0, y: 0 });
      return next;
    });
  };

  const handleSoilClusterMouseDown = (e) => {
    if (!soilClusterPreview) return;
    soilDragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      panX: soilClusterPan.x,
      panY: soilClusterPan.y,
    };
    setSoilClusterDragging(true);
  };

  const handleSoilClusterMouseMove = (e) => {
    if (!soilDragRef.current.dragging) return;
    const dx = e.clientX - soilDragRef.current.startX;
    const dy = e.clientY - soilDragRef.current.startY;
    setSoilClusterPan({
      x: soilDragRef.current.panX + dx,
      y: soilDragRef.current.panY + dy,
    });
  };

  const handleSoilClusterMouseUp = () => {
    if (!soilDragRef.current.dragging) return;
    soilDragRef.current.dragging = false;
    setSoilClusterDragging(false);
  };

  async function ensureRecortes(sensor) {
    if (sensor !== "s2" && sensor !== "ps") return [];
    if (recortesCacheRef.current[sensor]) return recortesCacheRef.current[sensor];
    const pv = sensor === "ps" ? "ps" : "s2";
    if (effectiveToken) setAuthToken(effectiveToken);
    const inv = await api.get(`/preprocess/recortes-inventory/${projectId}?pipeline_variant=${pv}`);
    const paths = (inv.data?.items || []).map((x) => x.relative_path).filter(Boolean);
    recortesCacheRef.current[sensor] = paths;
    return paths;
  }

  async function loadSeriesForSensor(sensor, options = {}) {
    const { forceRefresh = false } = options;
    const key = `${sensor}|${projectId}|${selectionKey}`;
    if (!forceRefresh && seriesCacheRef.current.has(key)) return seriesCacheRef.current.get(key);
    if (effectiveToken) setAuthToken(effectiveToken);
    const roiPoints = Array.isArray(roiSelection?.polygon_points)
      ? roiSelection.polygon_points.map((p) => ({ x: Number(p.x), y: Number(p.y) }))
      : [];
    const roiPayload = roiPoints.length >= 3 ? { polygon_points: roiPoints } : null;
    try {
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
      seriesCacheRef.current.set(key, data);
      return data;
    } catch {
      return null;
    }
  }

  async function loadAllSeries(options = {}) {
    const { forceRefresh = false } = options;
    if (!open || !projectId || clientDashboardBlocked) return;
    setSeriesLoading(true);
    try {
      // Un fallo S1/S2 (sin stacks) no debe bloquear PS ni Open-Meteo.
      const settled = await Promise.allSettled([
        loadSeriesForSensor("s1", { forceRefresh }),
        loadSeriesForSensor("s2", { forceRefresh }),
        loadSeriesForSensor("ps", { forceRefresh }),
      ]);
      const pick = (i) => (settled[i].status === "fulfilled" ? settled[i].value : null);
      setSeriesBySensor({ s1: pick(0), s2: pick(1), ps: pick(2) });
    } catch {
      /* ignore — climate se carga abajo de todos modos */
    }

    try {
      if (effectiveToken) setAuthToken(effectiveToken);
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
  }

  useEffect(() => {
    // Cargar series/clima con cualquier sensor disponible (no exigir S1).
    const hasAnySensor = !!(sensorData?.s1 || sensorData?.s2 || sensorData?.ps);
    if (!open || !projectId || !hasAnySensor || clientDashboardBlocked) return;
    void loadAllSeries();
  }, [open, projectId, sensorData, effectiveToken, clientDashboardBlocked]);

  const activeCluster = (clusterBySensor[sensorActive] || []).find((c) => c.key === selectedClusterKey[sensorActive]);

  const iaContext = useMemo(() => {
    const sd = sensorData[sensorActive];
    const idxKey = sd ? indexBySensor[sensorActive] || sd.indices?.[0] : null;
    const frames = sd && idxKey ? sd.framesByIndex[idxKey] || [] : [];
    const af = frames[dateIdxBySensor[sensorActive]] || null;
    return {
      projectId,
      projectName,
      sensorData,
      indexBySensor,
      seriesBySensor,
      climateBySensor,
      clusterBySensor,
      psStClusters: {
        1: { preview: !!psStCluster1Preview, busy: psStCluster1Busy, error: psStCluster1Error },
        2: { preview: !!psStCluster2Preview, busy: psStCluster2Busy, error: psStCluster2Error },
        3: { preview: !!psStCluster3Preview, busy: psStCluster3Busy, error: psStCluster3Error },
      },
      clientSoilSummary,
      hasGeofisica: hasGeofisicaResults,
      soilDemInfo,
      activeSceneDate: af?.date ?? null,
      activeSensorKey: sensorActive,
      activeIndexKey: indexBySensor[sensorActive] ?? "",
    };
  }, [
    projectId,
    projectName,
    sensorData,
    indexBySensor,
    seriesBySensor,
    climateBySensor,
    clusterBySensor,
    psStCluster1Preview,
    psStCluster1Busy,
    psStCluster1Error,
    psStCluster2Preview,
    psStCluster2Busy,
    psStCluster2Error,
    psStCluster3Preview,
    psStCluster3Busy,
    psStCluster3Error,
    clientSoilSummary,
    hasGeofisicaResults,
    soilDemInfo,
    sensorActive,
    dateIdxBySensor,
  ]);

  const handleMediaMouseMove = () => {};

  const handleMediaMouseDown = () => {};

  const handleMediaMouseUp = () => {};

  const handleMediaClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / Math.max(rect.width, 1)));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / Math.max(rect.height, 1)));
    if (roiMode) {
      setRoiSelection((prev) => {
        const current = Array.isArray(prev?.polygon_points) ? prev.polygon_points : [];
        return {
          polygon_points: [...current, { x, y }],
        };
      });
      return;
    }
    setPointSelection({ x, y });
  };

  if (!open) return null;

  const s = sensorActive;
  const brand = getClientBrand(viewerEmail);
  return (
    <>
    <div className="adv-dashboard-overlay" role="dialog" aria-modal="true" aria-label={brand.dashboardAria}>
      <div className="adv-dashboard-backdrop" onClick={onClose} />
      <div className="adv-dashboard-window">
        <div className="adv-dashboard-header">
          <h2>{brand.dashboardTitle}</h2>
          <span className="adv-dashboard-project-pill">
            Proyecto: {projectName || `ID ${projectId || "—"}`}
          </span>
          <div className="adv-dashboard-header-actions">
            <button
              type="button"
              onClick={() => void loadAllSeries({ forceRefresh: true })}
              disabled={clientDashboardBlocked || seriesLoading || loading}
            >
              {seriesLoading ? "…" : "Actualizar series"}
            </button>
            <button type="button" className="adv-close-btn" onClick={onClose} aria-label="Cerrar">
              ×
            </button>
          </div>
        </div>

        {error ? <p className="adv-dashboard-error">{error}</p> : null}

        {clientDashboardBlocked ? (
          <div className="adv-dashboard-notice-pending" role="status" aria-live="polite">
            <strong>Resultados no publicados</strong>
            <span>
              Su orden o proyecto aún no está en estado <strong>publicado</strong>. Cuando el administrador publique los
              resultados, podrá ver aquí el dashboard completo (inventarios, series y mapas). El estado actual del proyecto
              en la lista es: <strong>{String(projectStatus || "").trim() || "—"}</strong>.
            </span>
          </div>
        ) : null}

        <div className={`adv-main-split${clientDashboardBlocked ? " adv-main-split--blocked" : ""}`}>
          <div className="adv-timelapse-column">
            <div className="adv-timelapse-main">
              <div className="adv-sensor-tabs" role="tablist" aria-label="Sensor">
                {(["s1", "s2", "ps"]).map((key) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={sensorActive === key}
                    className={`adv-sensor-tab${sensorActive === key ? " adv-sensor-tab--active" : ""}`}
                    onClick={() => setSensorActive(key)}
                  >
                    {SENSOR_META[key].title}
                  </button>
                ))}
              </div>
              <div className="adv-timelapse-toolbar">
                <label className="adv-timelapse-toolbar-field">
                  <span className="adv-timelapse-toolbar-label">Cluster</span>
                  <select
                    value={selectedClusterKey[sensorActive] || ""}
                    onChange={(e) =>
                      setSelectedClusterKey((p) => ({
                        ...p,
                        [sensorActive]: e.target.value,
                      }))
                    }
                  >
                    {(clusterBySensor[sensorActive] || []).map((r) => (
                      <option key={r.key} value={r.key}>
                        {r.label || r.key}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="adv-inline-check adv-timelapse-toolbar-check">
                  <input
                    type="checkbox"
                    checked={clusterVisible}
                    onChange={(e) => setClusterVisible(e.target.checked)}
                  />
                  Overlay
                </label>
              </div>
              <SensorTimelapseViewer
                sensorTitle={SENSOR_META[s].title}
                omitSensorTitle
                indices={sensorData[s]?.indices || []}
                selectedIndex={indexBySensor[s]}
                onChangeIndex={(k) => {
                  setIndexBySensor((p) => ({ ...p, [s]: k }));
                  setDateIdxBySensor((p) => ({ ...p, [s]: 0 }));
                }}
                frames={framesFor(s)}
                currentIdx={dateIdxBySensor[s]}
                onChangeFrameIdx={(idx) => setDateIdxBySensor((p) => ({ ...p, [s]: idx }))}
                isPlaying={playingBySensor[s]}
                onPlayPause={() => setPlayingBySensor((p) => ({ ...p, [s]: !p[s] }))}
                onStop={() => {
                  setPlayingBySensor((p) => ({ ...p, [s]: false }));
                }}
                imageSrc={srcBySensor[s]}
                imageAlt={`${SENSOR_META[s].title} ${indexBySensor[s]} ${frameFor(s)?.date || ""}`}
                dualPaneRgb
                rgbImageSrc={rgbSrcBySensor[s]}
                rgbAlt={
                  s === "s1"
                    ? `SAR VV ${SENSOR_META[s].title} ${frameFor(s)?.date || ""}`
                    : `RGB ${SENSOR_META[s].title} ${frameFor(s)?.date || ""}`
                }
                rightPaneLabel={s === "s1" ? "SAR VV" : "RGB"}
                rgbEmptyMessage={
                  s === "s1"
                    ? "Sin Sigma0 VV (s1preproceso) ni recorte S1 para esta fecha."
                    : "Sin recorte RGB para esta fecha."
                }
                opacity={opacityBySensor[s]}
                onOpacity={(v) => setOpacityBySensor((p) => ({ ...p, [s]: v }))}
                onOpenClientVisualization={onOpenClientVisualization}
                interactive
                roiMode={roiMode}
                onToggleRoi={() => setRoiMode((v) => !v)}
                onClearRoi={() => {
                  setRoiSelection(null);
                }}
                roiSelection={roiSelection}
                clusterPreviewB64={activeCluster?.preview_png_base64 || null}
                clusterVisible={clusterVisible}
                onToggleClusterVisible={(v) => setClusterVisible(!!v)}
                clusterOptions={clusterBySensor[sensorActive] || []}
                selectedClusterKey={selectedClusterKey[sensorActive] || ""}
                onChangeClusterKey={(k) =>
                  setSelectedClusterKey((p) => ({ ...p, [sensorActive]: k }))
                }
                onMediaMouseMove={handleMediaMouseMove}
                onMediaMouseDown={handleMediaMouseDown}
                onMediaMouseUp={handleMediaMouseUp}
                onMediaClick={handleMediaClick}
              />
            </div>
            <section className="adv-timelapse-geofisica" aria-label="Geofísica y modelado de suelo">
              <div className="adv-timelapse-geofisica-head">
                <div className="adv-timelapse-geofisica-title-wrap">
                  <h3 className="adv-timelapse-geofisica-title">AGRO Geofisica - Modelado del suelo agricola</h3>
                  <button
                    type="button"
                    className={`adv-smart-cluster-info-btn${geofisicaInfoOpen ? " is-open" : ""}`}
                    aria-label="Información sobre AGRO Geofísica"
                    aria-expanded={geofisicaInfoOpen}
                    aria-controls="adv-geofisica-info-pop"
                    title="¿Qué muestra esta sección?"
                    onClick={() => setGeofisicaInfoOpen((v) => !v)}
                  >
                    i
                  </button>
                  {geofisicaInfoOpen ? (
                    <div
                      id="adv-geofisica-info-pop"
                      className="adv-smart-cluster-info-pop adv-geofisica-info-pop"
                      role="dialog"
                      aria-label="Información sobre AGRO Geofísica"
                    >
                      <div className="adv-smart-cluster-info-pop-head">
                        <strong>Smart Soil — resultados guardados (Fast / Mat)</strong>
                        <button
                          type="button"
                          className="adv-smart-cluster-info-close"
                          aria-label="Cerrar"
                          onClick={() => setGeofisicaInfoOpen(false)}
                        >
                          ×
                        </button>
                      </div>
                      <p className="adv-geofisica-info-text">
                        Mapas DEM / CV / FCM persistidos tras ejecutar Fast o Mat desde el editor. Solo visualización en dashboard.
                      </p>
                    </div>
                  ) : null}
                  {hasGeofisicaResults ? (
                    <button
                      type="button"
                      className="adv-geofisica-zoom-btn"
                      onClick={() => setGeofisicaZoomOpen(true)}
                      title="Ampliar vista Smart Soil (solo lectura, como tras Ejecutar en el editor admin)"
                    >
                      <svg
                        className="adv-geofisica-zoom-icon"
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        aria-hidden
                      >
                        <circle cx="10" cy="10" r="6" />
                        <path d="M16 16l6 6" />
                      </svg>
                      Zoom
                    </button>
                  ) : null}
                </div>
                {isAdminView ? (
                  <button type="button" className="adv-soilplus-btn" onClick={() => setSoilPlusOpen(true)}>
                    Editor Soil+
                  </button>
                ) : null}
              </div>
              {!hasGeofisicaResults ? (
                <div className="adv-timelapse-geofisica-frame">
                  <img
                    src={`${import.meta.env.BASE_URL}dashboard-geofisica-modelado-suelo.png`}
                    alt="Modelado geofísico del suelo agrícola"
                  />
                </div>
              ) : null}
              {hasGeofisicaResults ? (
                <div className="adv-smart-soil-dashboard">
                  {(["fast", "matlab"]).map((vk) => {
                    const variantHasData =
                      !!clientSoilSummary?.[vk]?.saved_at ||
                      Object.values(clientSoilImgUrls?.[vk] || {}).some((u) => !!u);
                    if (!variantHasData) return null;
                    return (
                      <div key={vk} className="adv-smart-soil-variant">
                        <h5 className="adv-smart-cluster-heading">{vk === "fast" ? "Fast (CVE rápido, guardado)" : "Mat (CV tipo MATLAB, guardado)"}</h5>
                        {clientSoilSummary?.[vk]?.saved_at ? (
                          <p className="adv-soilplus-dem-meta">
                            Guardado {String(clientSoilSummary[vk].saved_at)}
                            {" · "}
                            muestras {clientSoilSummary[vk]?.total_samples_placed ?? "—"} / objetivo {clientSoilSummary[vk]?.total_samples ?? "—"}
                            {" · K="}
                            {clientSoilSummary[vk]?.n_clusters ?? "—"}
                          </p>
                        ) : null}
                        <div className="adv-smart-soil-thumbs">
                          {(["dem", "cv", "fcm"]).map((kind) =>
                            clientSoilImgUrls?.[vk]?.[kind] ? (
                              <div key={`${vk}-${kind}`} className="adv-smart-soil-thumb-cell">
                                <span className="adv-smart-soil-thumb-label">{kind.toUpperCase()}</span>
                                <img className="adv-smart-soil-thumb-img" src={clientSoilImgUrls[vk][kind]} alt={`${vk} ${kind}`} />
                              </div>
                            ) : null
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </section>
          </div>

          <div className="adv-series-column">
            <div className="adv-series-column-inner">
              <div className="adv-series-primary">
                {seriesBySensor[sensorActive] ? (
                  <VegetationTimeSeriesCharts
                    data={seriesBySensor[sensorActive]}
                    onlyIndexKey={indexBySensor[sensorActive]}
                    activeSceneDate={frameFor(sensorActive)?.date || null}
                    chartPixelHeight={300}
                  />
                ) : (
                  <p className="adv-series-empty">Sin serie para este sensor.</p>
                )}
                <div className="adv-climate-panel adv-climate-panel--inline">
                  <ClimateTimeSeriesChart
                    data={climateBySensor[sensorActive]}
                    activeVars={climateVars}
                    activeSceneDate={frameFor(sensorActive)?.date || null}
                    chartHeight={252}
                  />
                </div>
                <div className="adv-climate-toggles adv-climate-toggles--compact">
                  {[
                    ["precip", "Precipitación"],
                    ["temp", "Temperatura"],
                    ["humidity", "Humedad"],
                    ["radiation", "Radiación solar"],
                  ].map(([k, label]) => (
                    <label key={k}>
                      <input
                        type="checkbox"
                        checked={!!climateVars[k]}
                        onChange={(e) => setClimateVars((p) => ({ ...p, [k]: e.target.checked }))}
                      />
                      <span
                        className="adv-climate-toggle-line"
                        style={{ "--climate-toggle-color": CLIMATE_SERIES_COLORS[k] }}
                        aria-hidden="true"
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
              <section className="adv-smart-clusters-panel" aria-label="Smart Agro dashboard">
                <div className="adv-smart-clusters-grid">
                  {[
                    {
                      slot: 1,
                      title: "cluster Smart 1",
                      indices: ["NDVI", "NDRE", "NDWI", "VARI"],
                      preview: psStCluster1Preview,
                      busy: psStCluster1Busy,
                      error: psStCluster1Error,
                      emptyMsg: "Sin mapa (índices NDVI, NDRE, NDWI, VARI en indecesPS).",
                    },
                    {
                      slot: 2,
                      title: "cluster Smart 2",
                      indices: ["EVI", "NDRE", "NDWI", "VARI"],
                      preview: psStCluster2Preview,
                      busy: psStCluster2Busy,
                      error: psStCluster2Error,
                      emptyMsg: "Sin mapa (requiere EVI y resto en indecesPS).",
                    },
                    {
                      slot: 3,
                      title: "cluster Smart 3",
                      indices: ["KNDVI", "MCARI", "NDWI", "VARI"],
                      preview: psStCluster3Preview,
                      busy: psStCluster3Busy,
                      error: psStCluster3Error,
                      emptyMsg: "Sin mapa (KNDVI, MCARI, NDWI, VARI en indecesPS).",
                    },
                  ].map((c) => {
                    const infoOpen = openClusterInfo === c.slot;
                    const infoId = `adv-smart-cluster-info-${c.slot}`;
                    return (
                      <div key={c.slot} className="adv-smart-cluster-cell">
                        <div className="adv-smart-cluster-heading-row">
                          <h4 className="adv-smart-cluster-heading">{c.title}</h4>
                          <button
                            type="button"
                            className={`adv-smart-cluster-info-btn${infoOpen ? " is-open" : ""}`}
                            aria-label={`Ver índices usados en ${c.title}`}
                            aria-expanded={infoOpen}
                            aria-controls={infoId}
                            title="Ver índices usados"
                            onClick={() => setOpenClusterInfo((prev) => (prev === c.slot ? null : c.slot))}
                          >
                            i
                          </button>
                          {infoOpen ? (
                            <div
                              id={infoId}
                              className="adv-smart-cluster-info-pop"
                              role="dialog"
                              aria-label={`Índices usados en ${c.title}`}
                            >
                              <div className="adv-smart-cluster-info-pop-head">
                                <strong>Índices usados</strong>
                                <button
                                  type="button"
                                  className="adv-smart-cluster-info-close"
                                  aria-label="Cerrar"
                                  onClick={() => setOpenClusterInfo(null)}
                                >
                                  ×
                                </button>
                              </div>
                              <ul className="adv-smart-cluster-info-list">
                                {c.indices.map((idx) => (
                                  <li key={idx}>{idx}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                        <div className="adv-smart-cluster-frame">
                          {c.error ? (
                            <p className="adv-smart-cluster-msg adv-smart-cluster-msg--err">{c.error}</p>
                          ) : null}
                          {c.busy ? (
                            <p className="adv-smart-cluster-msg">Calculando cluster…</p>
                          ) : c.preview ? (
                            <img
                              className="adv-smart-cluster-map"
                              src={c.preview}
                              alt={`Mapa clusters PS preset ${c.indices.join(", ")}`}
                            />
                          ) : (
                            <p className="adv-smart-cluster-msg">{c.emptyMsg}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>

              {!loading && !clientDashboardBlocked && !sensorData.s1 && !sensorData.s2 && !sensorData.ps ? (
                <p className="adv-smart-cluster-msg">
                  El proyecto seleccionado no tiene inventarios procesados todavía (S1/S2/PS) para mostrar en el dashboard.
                </p>
              ) : null}

              <div className="adv-ia-launch-row">
                <button
                  type="button"
                  className="adv-ver-analisis-btn"
                  disabled={clientDashboardBlocked}
                  aria-label="Abrir informe técnico de análisis"
                  title={
                    clientDashboardBlocked
                      ? "Disponible cuando el proyecto esté publicado"
                      : "Abrir ventana con informe técnico (Planet, clusters, clima)"
                  }
                  onClick={() => setIaReportOpen(true)}
                >
                  <span className="adv-ver-analisis-label">ver analisis</span>
                  <DigitalBrainIcon className="adv-ver-analisis-brain" size={24} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      {soilPlusOpen ? (
        <div className="adv-soilplus-overlay" role="dialog" aria-modal="true" aria-label="Soil Plus">
          <div className="adv-soilplus-backdrop" onClick={() => setSoilPlusOpen(false)} />
          <div className="adv-soilplus-window">
            <div className="adv-soilplus-header">
              <h3>Soil+ | Flujo agrogeofísica</h3>
              <button type="button" className="adv-close-btn" onClick={() => setSoilPlusOpen(false)} aria-label="Cerrar">
                ×
              </button>
            </div>
            <p className="adv-soilplus-note">
              Entrada: DEM. Ejecutar <strong>Fast</strong>: CV por sumas en caja (windowSize = lado impar en px). Ejecutar <strong>Mat</strong>: igual que{' '}
              <code>CV.m</code> (windowSize = parámetro <code>ws</code>, ventana (2×ws+1)² con <code>nonzeros</code>). Los dos modos guardan JSON y PNG bajo{' '}
              <code>dem/soilplus_saved_*</code> y aparecen en <strong>AGRO Geofísica</strong> del dashboard para el cliente.
            </p>
            <div className="adv-soilplus-controls">
              <button
                type="button"
                className="adv-soilplus-run-btn"
                onClick={() => void runSoilPlusSave("fast")}
                disabled={soilPlusBusy}
              >
                {soilPlusBusy ? "Ejecutando…" : "Ejecutar Fast"}
              </button>
              <button
                type="button"
                className="adv-soilplus-run-btn adv-soilplus-run-btn--mat"
                onClick={() => void runSoilPlusSave("matlab")}
                disabled={soilPlusBusy}
              >
                {soilPlusBusy ? "Ejecutando…" : "Ejecutar Mat"}
              </button>
              <label>
                # muestra (SNC)
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={soilSampleCount}
                  onChange={(e) => setSoilSampleCount(Math.max(1, Number(e.target.value) || 1))}
                />
              </label>
              <label>
                Window / ws
                <input
                  type="number"
                  min={1}
                  max={101}
                  step={1}
                  value={soilWindowSize}
                  onChange={(e) => setSoilWindowSize(Math.max(1, Number(e.target.value) || 1))}
                />
              </label>
              <label>
                fishNet step
                <input
                  type="number"
                  min={1}
                  max={80}
                  step={1}
                  value={soilFishnetStep}
                  onChange={(e) => setSoilFishnetStep(Math.max(1, Number(e.target.value) || 1))}
                />
              </label>
              <label>
                Paleta CV
                <select value={soilCvColormap} onChange={(e) => setSoilCvColormap(e.target.value)}>
                  <option value="jet">jet</option>
                  <option value="spectral">spectral</option>
                  <option value="turbo">turbo</option>
                  <option value="viridis">viridis</option>
                  <option value="plasma">plasma</option>
                </select>
              </label>
              <label>
                Numero de cluster
                <input
                  type="number"
                  min={2}
                  max={30}
                  step={1}
                  value={soilClusterCount}
                  onChange={(e) => setSoilClusterCount(Math.max(2, Number(e.target.value) || 2))}
                />
              </label>
              {soilPlusBusy ? <span className="adv-soilplus-badge">Calculando…</span> : null}
              {soilPlusError ? <span className="adv-soilplus-badge adv-soilplus-badge--err">{soilPlusError}</span> : null}
            </div>
            <p className="adv-soilplus-dem-path">
              Imagen de entrada:{" "}
              <code>
                {soilDemInfo?.input_image_path ||
                  `/home/deep/Documentos/XeniaMAP/data/storage/tenant_activo/project_${projectId || "?"}/dem/band_1.tif`}
              </code>
            </p>
            <div className="adv-soilplus-window-scroll">
              <div className="adv-soilplus-top-row">
                <section className="adv-soilplus-card adv-soilplus-card--dem-top">
                  <h4>DEM de entrada (band_1.img / .tif)</h4>
                  <p className="adv-soilplus-dem-meta">
                    {soilDemInfo
                      ? `windowSize: ${soilDemInfo.window_size} | Media DEM: ${Number(soilDemInfo.dem_mean || 0).toFixed(3)} | Std: ${Number(
                          soilDemInfo.dem_std || 0
                        ).toFixed(3)} | Min: ${Number(soilDemInfo.dem_min || 0).toFixed(3)} | Max: ${Number(
                          soilDemInfo.dem_max || 0
                        ).toFixed(3)} | CV mean: ${Number(soilDemInfo.cv_mean || 0).toFixed(4)} ${
                          soilDemInfo.roi_polygon_applied
                            ? `(ROI ${soilDemInfo.roi_pixel_count ?? 0} px; DEM ROI μ ${Number(soilDemInfo.dem_roi_mean || 0).toFixed(3)})`
                            : "(toda la mascara DEM)"
                        }${
                          soilVars.f1 != null
                            ? ` | f1 ${Number(soilVars.f1).toFixed(4)} | f2 ${Number(soilVars.f2).toFixed(4)} | f3 ${Number(soilVars.f3).toFixed(4)}`
                            : ""
                        }`
                      : "Dibuja un polígono opcional sobre el DEM; pulsa Ejecutar para estadísticos y CV."}
                  </p>
                  <div className="adv-soilplus-image-frame adv-soilplus-image-frame--dem-roi">
                    <DemRoiEditor imageUrl={soilDemPreview} disabled={soilPlusBusy} value={soilRoi} onChange={setSoilRoi} />
                  </div>
                </section>
                <section className="adv-soilplus-card adv-soilplus-card--final-zoning">
                <h4>Zonificación final — FCM sobre CV (K={soilClusterCount})</h4>
                <p className="adv-soilplus-dem-meta">
                  Clases difusas (exponente m=2) solo sobre el CV normalizado; triángulos = muestras repartidas por zona (coordenadas de píxel del raster).
                </p>
                <div className="adv-soilplus-zoom-tools">
                  <button
                    type="button"
                    onClick={() =>
                      setSoilClusterZoom((z) => {
                        const next = Math.max(1, Number((z - 0.25).toFixed(2)));
                        if (next === 1) setSoilClusterPan({ x: 0, y: 0 });
                        return next;
                      })
                    }
                    disabled={!soilClusterPreview}
                  >
                    -
                  </button>
                  <input
                    type="range"
                    min={1}
                    max={4}
                    step={0.1}
                    value={soilClusterZoom}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      setSoilClusterZoom(next);
                      if (next === 1) setSoilClusterPan({ x: 0, y: 0 });
                    }}
                    disabled={!soilClusterPreview}
                  />
                  <button
                    type="button"
                    onClick={() => setSoilClusterZoom((z) => Math.min(4, Number((z + 0.25).toFixed(2))))}
                    disabled={!soilClusterPreview}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSoilClusterZoom(1);
                      setSoilClusterPan({ x: 0, y: 0 });
                    }}
                    disabled={!soilClusterPreview}
                  >
                    Reset
                  </button>
                  <span>{Math.round(soilClusterZoom * 100)}%</span>
                </div>
                <div className="adv-soilplus-image-frame adv-soilplus-image-frame--cluster">
                  <div
                    className={`adv-soilplus-cluster-scroll${soilClusterDragging ? " is-dragging" : ""}${soilClusterZoom > 1.01 ? " allow-pan-overflow" : ""}`}
                    onWheel={handleSoilClusterWheel}
                    onMouseDown={handleSoilClusterMouseDown}
                    onMouseMove={handleSoilClusterMouseMove}
                    onMouseUp={handleSoilClusterMouseUp}
                    onMouseLeave={handleSoilClusterMouseUp}
                    title="Ctrl + rueda para zoom; click y arrastre para navegar"
                  >
                    {soilClusterPreview ? (
                      <div
                        className="adv-soilplus-cluster-zoom-inner"
                        style={{
                          transform: `translate(${soilClusterPan.x}px, ${soilClusterPan.y}px) scale(${soilClusterZoom})`,
                          transformOrigin: "center center",
                        }}
                      >
                        <div className="adv-soilplus-cluster-img-lock">
                          <img
                            src={soilClusterPreview}
                            alt="Zonificación FCM sobre CV"
                            className={`adv-soilplus-image adv-soilplus-image--zoomable${soilClusterDragging ? " is-dragging" : ""}`}
                            draggable={false}
                            onLoad={(e) => {
                              const im = e.currentTarget;
                              setSoilClusterNaturalSize({ w: im.naturalWidth, h: im.naturalHeight });
                            }}
                          />
                          <SoilFcmSampleTriangles
                            points={soilSamplingPlan?.sample_points}
                            viewWidth={soilClusterViewW}
                            viewHeight={soilClusterViewH}
                          />
                        </div>
                      </div>
                    ) : (
                      <p className="adv-soilplus-image-empty">Sin imagen de cluster. Pulsa Ejecutar.</p>
                    )}
                  </div>
                </div>
                </section>
              </div>
              <div className="adv-soilplus-bottom-strip">
                <section className="adv-soilplus-card adv-soilplus-thumb">
                  <h4>
                    CV local ({soilCvColormap}) · {soilCvEngineActive === "matlab" ? "Mat" : "Fast"}
                  </h4>
                  <p className="adv-soilplus-dem-meta">Coef. variación (ventana {soilWindowSize}).</p>
                  <div className="adv-soilplus-image-frame">
                    {soilCvPreview ? (
                      <img src={soilCvPreview} alt="CV local" className="adv-soilplus-image" />
                    ) : (
                      <p className="adv-soilplus-image-empty">Ejecutar</p>
                    )}
                  </div>
                </section>
                <section className="adv-soilplus-card adv-soilplus-thumb">
                  <h4>Aspecto (°)</h4>
                  <p className="adv-soilplus-dem-meta">Mapa direccional; paleta HSV.</p>
                  <div className="adv-soilplus-image-frame">
                    {soilAspectPreview ? (
                      <img src={soilAspectPreview} alt="Aspecto terreno" className="adv-soilplus-image" />
                    ) : (
                      <p className="adv-soilplus-image-empty">Ejecutar</p>
                    )}
                  </div>
                </section>
                <section className="adv-soilplus-card adv-soilplus-thumb">
                  <h4>Pendiente (°)</h4>
                  <p className="adv-soilplus-dem-meta">Gradiente DEM; paleta inferno.</p>
                  <div className="adv-soilplus-image-frame">
                    {soilSlopePreview ? (
                      <img src={soilSlopePreview} alt="Pendiente terreno" className="adv-soilplus-image" />
                    ) : (
                      <p className="adv-soilplus-image-empty">Ejecutar</p>
                    )}
                  </div>
                </section>
                <section className="adv-soilplus-card adv-soilplus-thumb">
                  <h4>Muestras por cluster</h4>
                  <p className="adv-soilplus-dem-meta">
                    {soilSamplingPlan
                      ? `Colocadas ${soilSamplingPlan.total_samples_placed ?? soilSamplingPlan.total_samples}${soilSamplingPlan.total_samples_placed !== soilSamplingPlan.total_samples ? ` (objetivo ${soilSamplingPlan.total_samples})` : ""}`
                      : "SNC"}
                  </p>
                  {soilSamplingPlan?.samples_per_cluster ? (
                    <SoilClusterSampleBars
                      samples={soilSamplingPlan.samples_per_cluster}
                      totalSamples={soilSamplingPlan.total_samples_placed ?? soilSamplingPlan.total_samples ?? soilSampleCount}
                      clusterCount={soilClusterCount}
                      thumb
                    />
                  ) : (
                    <p className="adv-soilplus-image-empty">Ejecutar</p>
                  )}
                </section>
                <section className="adv-soilplus-card adv-soilplus-thumb">
                  <h4>Paso 3 — curva Q (K = 2…11)</h4>
                  <p className="adv-soilplus-dem-meta">FCM sobre CV en ROI; Q = 1 − Σ n_k·var_k / (N·var total).</p>
                  <div className="adv-soilplus-image-frame adv-soilplus-image-frame--qchart">
                    <SoilQCurveChart data={soilQCurve} />
                  </div>
                </section>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
    {iaReportOpen ? (
      <DashboardIaAnalysisModal
        open={iaReportOpen}
        onClose={() => setIaReportOpen(false)}
        iaContext={iaContext}
        viewerEmail={viewerEmail}
      />
    ) : null}
    <ClientSoilViewModal
      open={geofisicaZoomOpen}
      onClose={() => setGeofisicaZoomOpen(false)}
      token={effectiveToken}
      projectId={projectId}
      projectName={projectName}
      initialVariant={clientSoilZoomInitialVariant}
    />
    </>
  );
}
