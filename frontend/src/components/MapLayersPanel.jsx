import { useEffect, useMemo, useState } from "react";
import api, { setAuthToken } from "../api";

function formatHa(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} ha`;
}

function formatKm2(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toLocaleString("es-CO", { maximumFractionDigits: 3 })} km²`;
}

const BASEMAP_OPTIONS = [
  { id: "vectorial", label: "Vectorial" },
  { id: "satelital", label: "Satelital" },
  { id: "hibrido", label: "Híbrido" },
];

/**
 * Panel derecho de capas (todas las vistas): capas del mapa + basemap al final.
 * En Fire reutiliza agrupación dNBR y bloque de estadísticas.
 */
export default function MapLayersPanel({
  layers = [],
  onToggle,
  onToggleDnbrGroup,
  baseStyle = "vectorial",
  onBaseStyleChange,
  orderTitle = "",
  orderId = null,
  token = "",
  loading = false,
  title = "Capas",
  emptyHint = "Sin capas de proyecto. Puede activar el mapa base abajo.",
  showFireStats = false,
}) {
  const items = Array.isArray(layers) ? layers : [];
  const [stats, setStats] = useState([]);
  const [statsLoading, setStatsLoading] = useState(false);

  const { roots, childrenByParent } = useMemo(() => {
    const children = items
      .filter((l) => l.metadata?.fireDnbrGroupChild)
      .sort(
        (a, b) =>
          Number(a.metadata?.fireSeverityClass || 0) -
          Number(b.metadata?.fireSeverityClass || 0)
      );
    const byParent = new Map();
    for (const ch of children) {
      const key = ch.metadata?.fireParentArtifact || "Fire_dNBR.tif";
      if (!byParent.has(key)) byParent.set(key, []);
      byParent.get(key).push(ch);
    }
    const childIds = new Set(children.map((c) => c.id));
    const rootsList = items
      .filter((l) => !childIds.has(l.id))
      .slice()
      .sort((a, b) => {
        const aSat = a.metadata?.fireBasemapSatellite ? 1 : 0;
        const bSat = b.metadata?.fireBasemapSatellite ? 1 : 0;
        return aSat - bSat;
      });
    return { roots: rootsList, childrenByParent: byParent };
  }, [items]);

  useEffect(() => {
    let cancelled = false;
    if (!showFireStats || !orderId || !token) {
      setStats([]);
      return undefined;
    }
    (async () => {
      setStatsLoading(true);
      try {
        setAuthToken(token);
        const res = await api.get(`/fire-orders/${orderId}/results/stats`);
        if (!cancelled) setStats(Array.isArray(res.data?.layers) ? res.data.layers : []);
      } catch (_) {
        if (!cancelled) setStats([]);
      } finally {
        if (!cancelled) setStatsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showFireStats, orderId, token]);

  function renderLayerRow(layer, { nested = false } = {}) {
    const color = layer.metadata?.fireClassColor;
    return (
      <li
        key={layer.id}
        className={`map-layers-item${nested ? " map-layers-item--nested" : ""}`}
      >
        <label className="map-layers-label">
          <input
            type="checkbox"
            checked={!!layer.visible}
            onChange={() => onToggle?.(layer.id)}
          />
          {color ? (
            <span
              className="map-layers-swatch"
              style={{ background: color }}
              aria-hidden
            />
          ) : null}
          <span className="map-layers-name" title={layer.displayName || layer.name}>
            {layer.displayName || layer.name}
          </span>
          <span className={`map-layers-kind map-layers-kind--${layer.kind || "vector"}`}>
            {layer.kind === "raster" ? "R" : "V"}
          </span>
        </label>
      </li>
    );
  }

  return (
    <aside className="map-layers-panel" aria-label="Capas del mapa">
      <div className={`map-layers-panel-top${showFireStats ? "" : " map-layers-panel-top--full"}`}>
        <div className="map-layers-panel-head">
          <h3 className="map-layers-panel-title">{title}</h3>
          {orderTitle ? <p className="map-layers-panel-sub">{orderTitle}</p> : null}
        </div>
        {loading ? <div className="map-layers-empty">Cargando capas…</div> : null}
        {!loading && items.length === 0 ? (
          <div className="map-layers-empty">{emptyHint}</div>
        ) : null}
        <ul className="map-layers-list">
          {roots.map((layer) => {
            const isGroup = !!layer.metadata?.fireDnbrGroupRoot;
            const kids = isGroup
              ? childrenByParent.get(layer.metadata?.fireArtifact || "Fire_dNBR.tif") || []
              : [];
            if (!isGroup) {
              return renderLayerRow(layer);
            }
            const childOn = kids.filter((k) => k.visible).length;
            const allOn = kids.length > 0 && childOn === kids.length;
            const someOn = childOn > 0;
            const groupChecked = !!layer.visible || allOn || someOn;
            return (
              <li key={layer.id} className="map-layers-group">
                <label className="map-layers-label map-layers-label--group">
                  <input
                    type="checkbox"
                    checked={groupChecked}
                    ref={(el) => {
                      if (el) el.indeterminate = someOn && !allOn && !layer.visible;
                    }}
                    onChange={() => {
                      if (onToggleDnbrGroup) {
                        onToggleDnbrGroup(layer.id, kids.map((k) => k.id));
                      } else {
                        onToggle?.(layer.id);
                      }
                    }}
                  />
                  <span className="map-layers-name" title={layer.displayName || layer.name}>
                    {layer.displayName || layer.name}
                  </span>
                  <span className="map-layers-kind map-layers-kind--raster">R</span>
                </label>
                {kids.length ? (
                  <ul className="map-layers-sublist">
                    {kids.map((ch) => renderLayerRow(ch, { nested: true }))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="map-layers-basemap" aria-label="Mapa base">
        <h4 className="map-layers-basemap-title">Mapa base</h4>
        <ul className="map-layers-list">
          {BASEMAP_OPTIONS.map((opt) => (
            <li key={opt.id} className="map-layers-item">
              <label className="map-layers-label">
                <input
                  type="checkbox"
                  checked={baseStyle === opt.id}
                  onChange={() => {
                    if (baseStyle === opt.id) return;
                    onBaseStyleChange?.(opt.id);
                  }}
                />
                <span className="map-layers-name">{opt.label}</span>
                <span className="map-layers-kind map-layers-kind--base">B</span>
              </label>
            </li>
          ))}
        </ul>
      </div>

      {showFireStats ? (
        <div className="map-layers-panel-bottom">
          <h4 className="map-layers-stats-title">Estadísticas</h4>
          {statsLoading ? <div className="map-layers-empty">Calculando áreas…</div> : null}
          {!statsLoading && stats.length === 0 ? (
            <div className="map-layers-empty">Sin estadísticas de área disponibles.</div>
          ) : null}
          <ul className="map-layers-stats-list">
            {stats.map((row) => (
              <li key={row.filename} className="map-layers-stats-item">
                <div className="map-layers-stats-label">{row.label}</div>
                {row.available ? (
                  <div className="map-layers-stats-values">
                    <span>{formatHa(row.area_ha)}</span>
                    <span>{formatKm2(row.area_km2)}</span>
                    {row.feature_count != null ? (
                      <span className="map-layers-stats-count">
                        {row.feature_count}{" "}
                        {row.area_ha == null &&
                        String(row.filename || "")
                          .toLowerCase()
                          .includes("hotspot")
                          ? "puntos"
                          : "políg."}
                      </span>
                    ) : null}
                  </div>
                ) : (
                  <div className="map-layers-empty">No disponible</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  );
}
