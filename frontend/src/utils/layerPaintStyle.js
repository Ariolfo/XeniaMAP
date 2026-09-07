/**
 * Estilo de pintura editable desde el panel Capas (opacidad / relleno / borde).
 */

export function clamp01(v, fallback = 0.5) {
  const n = Number(v);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(1, Math.max(0, n));
}

export function defaultLayerOpacity(layer) {
  const meta = layer?.metadata || {};
  if (meta.uiOpacity != null) return clamp01(meta.uiOpacity, 0.5);
  if (layer?.kind === "raster") {
    if (meta.fireBasemapSatellite) return 1;
    return 0.85;
  }
  if (meta.fireSymbol) return clamp01(meta.fireIconOpacity ?? 1, 1);
  return clamp01(meta.fireFillOpacity ?? 0.35, 0.35);
}

export function defaultFillMode(layer) {
  const meta = layer?.metadata || {};
  return meta.uiFillMode === "outline" ? "outline" : "fill";
}

export function defaultLineColor(layer) {
  const meta = layer?.metadata || {};
  return meta.uiLineColor || meta.fireLineColor || "#1a3f8c";
}

/** Controles UI: vector polígono, raster, o símbolo (solo opacidad). */
export function layerStyleCapabilities(layer) {
  const meta = layer?.metadata || {};
  if (meta.fireBasemapSatellite) {
    return { opacity: true, fillMode: false, lineColor: false };
  }
  if (meta.fireSymbol) {
    return { opacity: true, fillMode: false, lineColor: false };
  }
  if (layer?.kind === "raster") {
    return { opacity: true, fillMode: false, lineColor: false };
  }
  if (layer?.kind === "vector") {
    return { opacity: true, fillMode: true, lineColor: true };
  }
  return { opacity: false, fillMode: false, lineColor: false };
}

/**
 * Aplica metadata uiOpacity / uiFillMode / uiLineColor al MapLibre layer.
 */
export function applyLayerStyleToMap(map, layer) {
  if (!map || !layer?.id) return;
  const lid = layer.id;
  const meta = layer.metadata || {};
  const opacity = defaultLayerOpacity(layer);
  const fillMode = defaultFillMode(layer);
  const lineColor = defaultLineColor(layer);

  try {
    if (layer.kind === "raster" && map.getLayer(lid)) {
      map.setPaintProperty(lid, "raster-opacity", opacity);
      return;
    }

    if (meta.fireSymbol && map.getLayer(lid)) {
      map.setPaintProperty(lid, "icon-opacity", opacity);
      return;
    }

    if (map.getLayer(lid)) {
      const type = map.getLayer(lid)?.type;
      if (type === "fill") {
        map.setPaintProperty(lid, "fill-opacity", fillMode === "outline" ? 0 : opacity);
      } else if (type === "raster") {
        map.setPaintProperty(lid, "raster-opacity", opacity);
      } else if (type === "symbol") {
        map.setPaintProperty(lid, "icon-opacity", opacity);
      }
    }

    const outlineId = `${lid}_outline`;
    if (map.getLayer(outlineId)) {
      map.setPaintProperty(outlineId, "line-color", lineColor);
      // En solo-borde mantener el contorno legible aunque la opacidad del relleno sea baja.
      const lineOp = fillMode === "outline" ? Math.max(opacity, 0.55) : Math.min(1, opacity + 0.35);
      map.setPaintProperty(outlineId, "line-opacity", lineOp);
    }
  } catch (_) {
    /* style not ready */
  }
}
