/** Helpers YA/COG: preview Fire + tiles XYZ + GeoJSON bajo demanda. */
import api, { API_URL } from "../api";

/**
 * Plantilla MapLibre ``tiles`` (auth vía cookies HttpOnly + credentials en MapView).
 */
export function fireRasterTilesTemplate(orderId, filename, severityClass = null) {
  const base = String(API_URL || "").replace(/\/$/, "");
  const q = new URLSearchParams({ name: filename });
  if (severityClass != null) q.set("severity_class", String(severityClass));
  return `${base}/fire-orders/${orderId}/results/tiles/{z}/{x}/{y}.png?${q.toString()}`;
}

/**
 * Meta (bounds) para fuente raster XYZ. Fallback: preview PNG blob legacy.
 */
export async function fetchFireRasterMapPayload(orderId, filename, severityClass = null) {
  const metaParams = { name: filename, format: "meta" };
  if (severityClass != null) metaParams.severity_class = severityClass;
  const metaRes = await api.get(`/fire-orders/${orderId}/results/preview`, {
    params: metaParams,
  });
  const bounds = metaRes.data?.bounds;
  if (!Array.isArray(bounds) || bounds.length < 4) {
    throw new Error("preview sin bounds");
  }
  return {
    bounds,
    tileTemplate: fireRasterTilesTemplate(orderId, filename, severityClass),
  };
}

/**
 * PNG binario (+ bounds). Preferir fetchFireRasterMapPayload + tiles.
 */
export async function fetchFirePreviewBlob(orderId, filename, severityClass = null) {
  const pngParams = { name: filename, format: "png" };
  if (severityClass != null) pngParams.severity_class = severityClass;
  const pngRes = await api.get(`/fire-orders/${orderId}/results/preview`, {
    params: pngParams,
    responseType: "blob",
  });
  const headerBounds = pngRes.headers?.["x-fire-bounds"] || pngRes.headers?.["X-Fire-Bounds"];
  let bounds = null;
  if (typeof headerBounds === "string" && headerBounds.trim()) {
    const parts = headerBounds.split(",").map((x) => Number(String(x).trim()));
    if (parts.length >= 4 && parts.every((n) => Number.isFinite(n))) {
      bounds = parts.slice(0, 4);
    }
  }
  if (!bounds) {
    const metaParams = { name: filename, format: "meta" };
    if (severityClass != null) metaParams.severity_class = severityClass;
    const metaRes = await api.get(`/fire-orders/${orderId}/results/preview`, {
      params: metaParams,
    });
    bounds = metaRes.data?.bounds;
  }
  if (!Array.isArray(bounds) || bounds.length < 4) {
    throw new Error("preview sin bounds");
  }
  const blobUrl = URL.createObjectURL(pngRes.data);
  return { bounds, blobUrl };
}

export async function fetchFireResultGeojson(orderId, filename) {
  const res = await api.get(`/fire-orders/${orderId}/results/geojson`, {
    params: { name: filename },
  });
  return res.data;
}

export async function fetchFirmsLive(orderId, hours = 48) {
  const res = await api.get(`/fire-orders/${orderId}/firms-live`, {
    params: { hours },
  });
  return res.data;
}
