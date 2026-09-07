import api, { API_URL, authFetchInit, loadStoredAuth, setAuthToken } from "../api";

export const SENSOR_META = {
  s1: { id: "s1", title: "Sentinel-1", variant: "s1", defaultIndex: "RVI", kind: "radar" },
  s2: { id: "s2", title: "Sentinel-2", variant: "s2", defaultIndex: "NDVI", kind: "optical" },
  ps: { id: "ps", title: "Alta resolución", variant: "ps", defaultIndex: "NDVI", kind: "optical" },
};

export function normIso(s) {
  return String(s || "").slice(0, 10);
}

export function resolveInventoryIndexKey(indices, preferred) {
  if (!indices || !indices.length) return null;
  if (preferred != null && preferred !== "" && indices.includes(preferred)) return preferred;
  if (preferred != null && preferred !== "") {
    const u = String(preferred).toUpperCase();
    for (let i = 0; i < indices.length; i += 1) {
      if (String(indices[i]).toUpperCase() === u) return indices[i];
    }
  }
  return indices[0] || null;
}

function dateKeyFromSortKey(sortKey) {
  const m = String(sortKey || "").match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : "";
}

export function findRecortePathForSceneDate(items, sceneIso) {
  const t = normIso(sceneIso);
  if (!t || !items || !items.length) return null;
  for (let i = 0; i < items.length; i += 1) {
    if (dateKeyFromSortKey(items[i].sort_key) === t) return items[i].relative_path;
  }
  for (let i = 0; i < items.length; i += 1) {
    const sk = String(items[i].sort_key || "");
    if (sk.startsWith(t)) return items[i].relative_path;
  }
  const parts = t.split("-");
  const y = parts[0];
  const mo = parts[1];
  const d = parts[2];
  if (y && y.length === 4 && mo && d) {
    const yy = y.slice(2);
    const psNeedle = `${d}-${mo}-${yy}`;
    const compact = `${y}${mo}${d}`;
    for (let i = 0; i < items.length; i += 1) {
      const hay = `${items[i].basename || ""} ${items[i].relative_path || ""}`.toLowerCase();
      if (hay.includes(psNeedle) || hay.includes(compact)) return items[i].relative_path;
    }
  }
  return null;
}

export function buildRecorteRgbEndpoint(projectId, relativePath, pipelineVariant) {
  const base = API_URL.replace(/\/$/, "");
  return `${base}/preprocess/recortes-preview/${projectId}?path=${encodeURIComponent(
    relativePath
  )}&pipeline_variant=${encodeURIComponent(pipelineVariant)}`;
}

/** Claves pseudo-índice para stacks sigma0 en la vista interactiva S1. */
export const S1_SIGMA_VISUAL_VV = "VV";
export const S1_SIGMA_VISUAL_VH = "VH";

/** Orden preferido del selector S1: 5 índices SAR + solo VV + solo VH. */
export const S1_INTERACTIVE_INDEX_ORDER = [
  "RVI",
  "RFDI",
  "VV_VH",
  "VH_VV",
  "NRPB",
  S1_SIGMA_VISUAL_VV,
  S1_SIGMA_VISUAL_VH,
];

export function isS1SigmaVisualKey(key) {
  const k = String(key || "").toUpperCase();
  return k === S1_SIGMA_VISUAL_VV || k === S1_SIGMA_VISUAL_VH;
}

/** Etiqueta del selector (índices SAR + polarizaciones). */
export function labelInteractiveIndexOption(key) {
  const k = String(key || "");
  if (k === S1_SIGMA_VISUAL_VV || k.toUpperCase() === "VV") return "solo VV";
  if (k === S1_SIGMA_VISUAL_VH || k.toUpperCase() === "VH") return "solo VH";
  if (k === "VV_VH") return "VV/VH";
  if (k === "VH_VV") return "VH/VV";
  return k;
}

export function buildS1Sigma0PreviewEndpoint(projectId, relativePath, pol = "vv") {
  const base = API_URL.replace(/\/$/, "");
  const p = String(pol || "vv").trim().toLowerCase() === "vh" ? "vh" : "vv";
  return `${base}/preprocess/s1-preproceso-sigma0-vv-preview/${projectId}?path=${encodeURIComponent(
    relativePath
  )}&pol=${encodeURIComponent(p)}&palette=spectral`;
}

/**
 * Frames temporales desde inventario de Sigma0_VV/VH_db.img (una escena = un archivo).
 * @param {"vv"|"vh"} pol
 */
export function buildS1SigmaVisualFrames(items, pol) {
  const p = String(pol || "vv").trim().toLowerCase() === "vh" ? "vh" : "vv";
  const key = p === "vh" ? S1_SIGMA_VISUAL_VH : S1_SIGMA_VISUAL_VV;
  const frames = [];
  for (let i = 0; i < (items || []).length; i += 1) {
    const row = items[i];
    const date = normIso(row.sort_key);
    if (!date || !row.relative_path) continue;
    frames.push({
      id: `s1:${key}:1:${row.relative_path}`,
      date,
      band: 1,
      relativePath: row.relative_path,
      kind: "s1-sigma",
      pol: p,
    });
  }
  frames.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  return frames;
}

/** Une índices SAR con opciones solo VV / solo VH y ordena el selector. */
export function mergeS1InteractiveVisuals(s1Block, s1PrepVv = [], s1PrepVh = []) {
  const framesByIndex = { ...(s1Block?.framesByIndex || {}) };
  const vvFrames = buildS1SigmaVisualFrames(s1PrepVv, "vv");
  const vhFrames = buildS1SigmaVisualFrames(s1PrepVh, "vh");
  if (vvFrames.length) framesByIndex[S1_SIGMA_VISUAL_VV] = vvFrames;
  if (vhFrames.length) framesByIndex[S1_SIGMA_VISUAL_VH] = vhFrames;

  const present = new Set(Object.keys(framesByIndex));
  const preferred = S1_INTERACTIVE_INDEX_ORDER.filter((k) => present.has(k));
  const rest = [...present].filter((k) => !S1_INTERACTIVE_INDEX_ORDER.includes(k)).sort();
  return { indices: [...preferred, ...rest], framesByIndex };
}

export function buildIndexPreviewEndpoint(sensor, projectId, frame) {
  const base = API_URL.replace(/\/$/, "");
  if (sensor === "s1") {
    if (frame?.kind === "s1-sigma") {
      return buildS1Sigma0PreviewEndpoint(projectId, frame.relativePath, frame.pol);
    }
    return `${base}/preprocess/s1-sar-index-stacks-preview/${projectId}?path=${encodeURIComponent(
      frame.relativePath
    )}&band=${frame.band}&index_palette=1`;
  }
  const pv = sensor === "ps" ? "ps" : "s2";
  return `${base}/preprocess/index-stacks-preview/${projectId}?path=${encodeURIComponent(
    frame.relativePath
  )}&band=${frame.band}&index_palette=1&pipeline_variant=${encodeURIComponent(pv)}`;
}

export async function fetchPreviewDataUrl(fullUrl, token) {
  const url = String(fullUrl || "").trim();
  if (!url) throw new Error("URL de preview vacía");
  const stored = loadStoredAuth();
  const tok = stored.access || token;
  if (tok) setAuthToken(tok);
  try {
    const resp = await api.get(url, { responseType: "blob" });
    const raw = resp && resp.data;
    const blob = raw instanceof Blob ? raw : new Blob([raw || ""]);
    if (blob.size > 0) {
      const ab = await blob.arrayBuffer();
      const bytes = new Uint8Array(ab);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
      return `data:image/png;base64,${btoa(binary)}`;
    }
  } catch {
    /* fallback fetch */
  }
  const resp = await fetch(url, authFetchInit(tok, { cache: "no-store" }));
  if (!resp.ok) throw new Error(`Preview ${resp.status}`);
  const blob = await resp.blob();
  const ab = await blob.arrayBuffer();
  const bytes = new Uint8Array(ab);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return `data:image/png;base64,${btoa(binary)}`;
}

/**
 * Descarga una imagen protegida (JWT/cookie) y la devuelve como data-URL con su mime real.
 * Acepta rutas relativas tipo /api/v1/... (se resuelven contra el backend configurado).
 */
export async function fetchAuthedImageDataUrl(pathOrUrl, token) {
  const src = String(pathOrUrl || "").trim();
  if (!src) throw new Error("URL de imagen vacía");
  const stored = loadStoredAuth();
  const tok = stored.access || token;
  let url = src;
  if (!/^https?:\/\//i.test(src)) {
    const backendRoot = API_URL.replace(/\/api\/v1$/i, "");
    url = `${backendRoot}${src.startsWith("/") ? "" : "/"}${src}`;
  }
  const resp = await fetch(url, authFetchInit(tok, { cache: "no-store" }));
  if (!resp.ok) throw new Error(`Imagen ${resp.status}`);
  const blob = await resp.blob();
  return await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result));
    fr.onerror = () => reject(new Error("No se pudo leer la imagen"));
    fr.readAsDataURL(blob);
  });
}

export function buildSensorInventory(rows, sensor) {
  const byIndex = {};
  const list = rows || [];
  for (let i = 0; i < list.length; i += 1) {
    const row = list[i];
    const key = String(row.index_key || "").trim();
    const dates = Array.isArray(row.band_dates) ? row.band_dates.map(normIso) : [];
    if (!key || !dates.length || !row.relative_path) continue;
    const current = byIndex[key];
    if (current && (current._score || 0) >= dates.length) continue;
    byIndex[key] = {
      _score: dates.length,
      frames: dates.map((d, bandIdx) => ({
        id: `${sensor}:${key}:${bandIdx + 1}:${row.relative_path}`,
        date: d,
        band: bandIdx + 1,
        relativePath: row.relative_path,
      })),
    };
  }
  const indices = Object.keys(byIndex).sort();
  const framesByIndex = {};
  for (let i = 0; i < indices.length; i += 1) {
    const k = indices[i];
    framesByIndex[k] = byIndex[k].frames;
  }
  return { indices, framesByIndex };
}
