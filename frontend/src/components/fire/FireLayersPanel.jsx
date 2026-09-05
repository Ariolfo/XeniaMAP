import { useEffect, useMemo, useState } from "react";
import api, { setAuthToken } from "../../api";

function formatHa(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} ha`;
}

function formatKm2(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toLocaleString("es-CO", { maximumFractionDigits: 3 })} km²`;
}

/**
 * Panel derecho Fire: 70% capas / 30% estadísticas de área.
 * dNBR agrupa clases de severidad 1–7 como subniveles.
 */
export default function FireLayersPanel({
  layers = [],
  onToggle,
  onToggleDnbrGroup,
  orderTitle = "",
  orderId = null,
  token = "",
  loading = false,
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
    if (!orderId || !token) {
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
  }, [orderId, token]);

  function renderLayerRow(layer, { nested = false } = {}) {
    const color = layer.metadata?.fireClassColor;
    return (
      <li
        key={layer.id}
        className={`fire-layers-item${nested ? " fire-layers-item--nested" : ""}`}
      >
        <label className="fire-layers-label">
          <input
            type="checkbox"
            checked={!!layer.visible}
            onChange={() => onToggle?.(layer.id)}
          />
          {color ? (
            <span
              className="fire-layers-swatch"
              style={{ background: color }}
              aria-hidden
            />
          ) : null}
          <span className="fire-layers-name" title={layer.displayName || layer.name}>
            {layer.displayName || layer.name}
          </span>
          <span className={`fire-layers-kind fire-layers-kind--${layer.kind || "vector"}`}>
            {layer.kind === "raster" ? "R" : "V"}
          </span>
        </label>
      </li>
    );
  }

  return (
    <aside className="fire-layers-panel" aria-label="Capas Fire">
      <div className="fire-layers-panel-top">
        <div className="fire-layers-panel-head">
          <h3 className="fire-layers-panel-title">Capas Fire</h3>
          {orderTitle ? <p className="fire-layers-panel-sub">{orderTitle}</p> : null}
        </div>
        {loading ? <div className="fire-layers-empty">Cargando capas…</div> : null}
        {!loading && items.length === 0 ? (
          <div className="fire-layers-empty">
            Sin capas aún. Abra un municipio para ver el AOI y hotspots FIRMS en vivo (24 h / 48 h),
            o complete dNBR / FIRMS para capas de salida.
          </div>
        ) : null}
        <ul className="fire-layers-list">
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
              <li key={layer.id} className="fire-layers-group">
                <label className="fire-layers-label fire-layers-label--group">
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
                  <span className="fire-layers-name" title={layer.displayName || layer.name}>
                    {layer.displayName || layer.name}
                  </span>
                  <span className="fire-layers-kind fire-layers-kind--raster">R</span>
                </label>
                {kids.length ? (
                  <ul className="fire-layers-sublist">
                    {kids.map((ch) => renderLayerRow(ch, { nested: true }))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="fire-layers-panel-bottom">
        <h4 className="fire-layers-stats-title">Estadísticas</h4>
        {statsLoading ? <div className="fire-layers-empty">Calculando áreas…</div> : null}
        {!statsLoading && stats.length === 0 ? (
          <div className="fire-layers-empty">Sin estadísticas de área disponibles.</div>
        ) : null}
        <ul className="fire-layers-stats-list">
          {stats.map((row) => (
            <li key={row.filename} className="fire-layers-stats-item">
              <div className="fire-layers-stats-label">{row.label}</div>
              {row.available ? (
                <div className="fire-layers-stats-values">
                  <span>{formatHa(row.area_ha)}</span>
                  <span>{formatKm2(row.area_km2)}</span>
                  {row.feature_count != null ? (
                    <span className="fire-layers-stats-count">
                      {row.feature_count}{" "}
                      {row.area_ha == null && String(row.filename || "").toLowerCase().includes("hotspot")
                        ? "puntos"
                        : "políg."}
                    </span>
                  ) : null}
                </div>
              ) : (
                <div className="fire-layers-empty">No disponible</div>
              )}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
