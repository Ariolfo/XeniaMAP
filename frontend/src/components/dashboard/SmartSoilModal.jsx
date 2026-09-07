import { useEffect, useRef, useState } from "react";
import api, { API_URL, formatApiErrorDetail, loadStoredAuth, setAuthToken } from "../../api";
import DemRoiEditor, { defaultRoi, soilRoiToQueryParam } from "./DemRoiEditor";
import { runSoilPlusExecuteSaveAndLoad } from "../../features/agro/runSoilPlusExecuteSave";

async function fetchPreviewObjectUrl(fullUrl, token) {
  const url = String(fullUrl || "").trim();
  if (!url) throw new Error("URL de preview vacia");
  const { access } = loadStoredAuth();
  const tok = access || token;
  if (tok) setAuthToken(tok);
  const resp = await api.get(url, { responseType: "blob" });
  const blob = resp?.data instanceof Blob ? resp.data : new Blob([resp?.data ?? ""]);
  if (!blob || blob.size <= 0) throw new Error("Preview vacio");
  const ab = await blob.arrayBuffer();
  const bytes = new Uint8Array(ab);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return `data:image/png;base64,${btoa(binary)}`;
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

export function SoilClusterSampleBars({ samples, totalSamples, clusterCount, compact = false, thumb = false }) {
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

export function SoilFcmSampleTriangles({ points, viewWidth, viewHeight }) {
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

export function SoilQCurveChart({ data }) {
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

export default function SmartSoilModal({ open, onClose, token, projectId, projectName = "" }) {
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
  const soilDragRef = useRef({ dragging: false, startX: 0, startY: 0, panX: 0, panY: 0 });

  const effectiveToken = token || loadStoredAuth().access || "";

  useEffect(() => {
    setSoilClusterNaturalSize({ w: 0, h: 0 });
  }, [soilClusterPreview]);

  const soilClusterViewW =
    soilClusterNaturalSize.w || Number(soilSamplingPlan?.raster_shape?.width) || 0;
  const soilClusterViewH =
    soilClusterNaturalSize.h || Number(soilSamplingPlan?.raster_shape?.height) || 0;

  const runSoilPlusSave = async (cv_engine) => {
    if (!projectId) return;
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
      const { data, variant: vk } = await runSoilPlusExecuteSaveAndLoad({
        projectId,
        params,
      });
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
    if (!open || !projectId || !effectiveToken) return;
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
  }, [open, projectId, effectiveToken, soilRoi.closed, soilRoi.points, soilWindowSize, soilCvEngineActive]);

  useEffect(() => {
    if (!open || !projectId || !effectiveToken) return;
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
  }, [open, projectId, effectiveToken]);

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
    soilDragRef.current = { dragging: true, startX: e.clientX, startY: e.clientY, panX: soilClusterPan.x, panY: soilClusterPan.y };
    setSoilClusterDragging(true);
  };
  const handleSoilClusterMouseMove = (e) => {
    if (!soilDragRef.current.dragging) return;
    const dx = e.clientX - soilDragRef.current.startX;
    const dy = e.clientY - soilDragRef.current.startY;
    setSoilClusterPan({ x: soilDragRef.current.panX + dx, y: soilDragRef.current.panY + dy });
  };
  const handleSoilClusterMouseUp = () => {
    if (!soilDragRef.current.dragging) return;
    soilDragRef.current.dragging = false;
    setSoilClusterDragging(false);
  };

  if (!open) return null;

  return (
    <div className="adv-dashboard-overlay" role="dialog" aria-modal="true" aria-label="Smart Soil">
      <div className="adv-dashboard-backdrop" onClick={onClose} />
      <div className="adv-dashboard-window adv-dashboard-window--smart-soil">
        <div className="adv-dashboard-header">
          <h2>Smart Soil - {projectName || `Proyecto ${projectId}`}</h2>
          <div className="adv-dashboard-header-actions">
            <button type="button" className="adv-close-btn" onClick={onClose} aria-label="Cerrar">x</button>
          </div>
        </div>
        <p className="adv-soilplus-note">
          Fast = CV rápido (windowSize lado impar px). Mat = <code>CV.m</code> (windowSize = ws, ventana 2×ws+1). Todo se guarda en el servidor; en el dashboard el cliente lo ve en <strong>AGRO Geofísica</strong> (Smart Soil).
        </p>
        <div className="adv-soilplus-controls">
          <button type="button" className="adv-soilplus-run-btn" onClick={() => void runSoilPlusSave("fast")} disabled={soilPlusBusy}>
            {soilPlusBusy ? "Ejecutando..." : "Ejecutar Fast"}
          </button>
          <button type="button" className="adv-soilplus-run-btn adv-soilplus-run-btn--mat" onClick={() => void runSoilPlusSave("matlab")} disabled={soilPlusBusy}>
            {soilPlusBusy ? "Ejecutando..." : "Ejecutar Mat"}
          </button>
          <label># muestra (SNC)<input type="number" min={1} step={1} value={soilSampleCount} onChange={(e) => setSoilSampleCount(Math.max(1, Number(e.target.value) || 1))} /></label>
          <label>
            Window / ws
            <input type="number" min={1} max={101} step={1} value={soilWindowSize} onChange={(e) => setSoilWindowSize(Math.max(1, Number(e.target.value) || 1))} />
          </label>
          <label>
            fishNet<input type="number" min={1} max={80} step={1} value={soilFishnetStep} onChange={(e) => setSoilFishnetStep(Math.max(1, Number(e.target.value) || 1))} />
          </label>
          <label>Paleta CV
            <select value={soilCvColormap} onChange={(e) => setSoilCvColormap(e.target.value)}>
              <option value="jet">jet</option>
              <option value="spectral">spectral</option>
              <option value="turbo">turbo</option>
              <option value="viridis">viridis</option>
              <option value="plasma">plasma</option>
            </select>
          </label>
          <label>Numero de cluster<input type="number" min={2} max={30} step={1} value={soilClusterCount} onChange={(e) => setSoilClusterCount(Math.max(2, Number(e.target.value) || 2))} /></label>
          {soilPlusBusy ? <span className="adv-soilplus-badge">Calculando...</span> : null}
          {soilPlusError ? <span className="adv-soilplus-badge adv-soilplus-badge--err">{soilPlusError}</span> : null}
        </div>
        <p className="adv-soilplus-dem-path">
          Imagen de entrada: <code>{soilDemInfo?.input_image_path || `/home/deep/Documentos/XeniaMAP/data/storage/tenant_activo/project_${projectId || "?"}/dem/band_1.tif`}</code>
        </p>
        <div className="adv-dashboard-soil-body">
          <div className="adv-soilplus-top-row">
            <section className="adv-soilplus-card adv-soilplus-card--dem-top">
              <h4>DEM de entrada (band_1.img / .tif)</h4>
              <p className="adv-soilplus-dem-meta">
                Dibuja un polígono ROI opcional; el CV solo se muestra y estadifica dentro de él.
                {soilVars.f1 != null
                  ? ` f1 ${Number(soilVars.f1).toFixed(4)} | f2 ${Number(soilVars.f2).toFixed(4)} | f3 ${Number(soilVars.f3).toFixed(4)}`
                  : ""}
              </p>
              <div className="adv-soilplus-image-frame adv-soilplus-image-frame--dem-roi">
                <DemRoiEditor imageUrl={soilDemPreview} disabled={soilPlusBusy} value={soilRoi} onChange={setSoilRoi} />
              </div>
            </section>
            <section className="adv-soilplus-card adv-soilplus-card--final-zoning">
              <h4>Zonificación final — FCM sobre CV (K={soilClusterCount})</h4>
              <p className="adv-soilplus-dem-meta">
                FCM (exponente m=2) solo sobre CV normalizado; triángulos = muestras en píxeles del raster.
              </p>
              <div className="adv-soilplus-image-frame adv-soilplus-image-frame--cluster">
                <div
                  className={`adv-soilplus-cluster-scroll${soilClusterDragging ? " is-dragging" : ""}${soilClusterZoom > 1.01 ? " allow-pan-overflow" : ""}`}
                  onWheel={handleSoilClusterWheel}
                  onMouseDown={handleSoilClusterMouseDown}
                  onMouseMove={handleSoilClusterMouseMove}
                  onMouseUp={handleSoilClusterMouseUp}
                  onMouseLeave={handleSoilClusterMouseUp}
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
              <h4>CV local ({soilCvColormap}) · {soilCvEngineActive === "matlab" ? "Mat" : "Fast"}</h4>
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
              <p className="adv-soilplus-dem-meta">Paleta HSV cíclica.</p>
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
              <p className="adv-soilplus-dem-meta">Paleta inferno.</p>
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
  );
}
