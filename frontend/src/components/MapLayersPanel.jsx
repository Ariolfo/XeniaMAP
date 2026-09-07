import { useEffect, useMemo, useRef, useState } from "react";
import api, { setAuthToken } from "../api";
import {
  defaultFillMode,
  defaultLayerOpacity,
  defaultLineColor,
  layerStyleCapabilities,
} from "../utils/layerPaintStyle";

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

function StyleSlidersIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden focusable="false">
      <path
        fill="currentColor"
        d="M2.5 4.25h5.1a1.75 1.75 0 0 0 3.3 0H13.5a.75.75 0 0 0 0-1.5h-2.6a1.75 1.75 0 0 0-3.3 0H2.5a.75.75 0 0 0 0 1.5Zm0 4.5h1.85a1.75 1.75 0 0 0 3.3 0H13.5a.75.75 0 0 0 0-1.5H7.65a1.75 1.75 0 0 0-3.3 0H2.5a.75.75 0 0 0 0 1.5Zm0 4.5h4.35a1.75 1.75 0 0 0 3.3 0H13.5a.75.75 0 0 0 0-1.5h-3.35a1.75 1.75 0 0 0-3.3 0H2.5a.75.75 0 0 0 0 1.5Z"
      />
    </svg>
  );
}

function canStyleLayer(layer) {
  const caps = layerStyleCapabilities(layer);
  return caps.opacity || caps.fillMode;
}

function LayerStyleTrigger({ open, disabled, onToggle }) {
  return (
    <button
      type="button"
      className={`map-layers-style-trigger${open ? " is-open" : ""}`}
      title="Apariencia de la capa"
      aria-label="Apariencia de la capa"
      aria-expanded={open}
      disabled={disabled}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle?.();
      }}
    >
      <StyleSlidersIcon />
    </button>
  );
}

function LayerStylePanel({ layer, onStyleChange }) {
  const caps = layerStyleCapabilities(layer);
  const opacity = Math.round(defaultLayerOpacity(layer) * 100);
  const fillMode = defaultFillMode(layer);
  const lineColor = defaultLineColor(layer);
  const showLineColor = caps.lineColor && fillMode === "outline";

  return (
    <div
      className="map-layers-style-panel"
      role="dialog"
      aria-label="Apariencia de la capa"
      onClick={(e) => e.stopPropagation()}
    >
      <p className="map-layers-style-popover-title">Apariencia</p>
      <div className="map-layers-style">
        {caps.opacity ? (
          <label className="map-layers-style-row" title="Transparencia">
            <span className="map-layers-style-label">Opacidad</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={opacity}
              onChange={(e) =>
                onStyleChange?.(layer.id, { opacity: Number(e.target.value) / 100 })
              }
            />
            <span className="map-layers-style-value">{opacity}%</span>
          </label>
        ) : null}
        {caps.fillMode ? (
          <div className="map-layers-style-row map-layers-style-row--modes">
            <span className="map-layers-style-label">Estilo</span>
            <div className="map-layers-style-modes" role="group" aria-label="Estilo de relleno">
              <button
                type="button"
                className={`map-layers-style-mode${fillMode === "fill" ? " is-active" : ""}`}
                onClick={() => onStyleChange?.(layer.id, { fillMode: "fill" })}
                title="Relleno y borde"
              >
                Relleno
              </button>
              <button
                type="button"
                className={`map-layers-style-mode${fillMode === "outline" ? " is-active" : ""}`}
                onClick={() => onStyleChange?.(layer.id, { fillMode: "outline" })}
                title="Solo borde"
              >
                Contorno
              </button>
            </div>
          </div>
        ) : null}
        {showLineColor ? (
          <label className="map-layers-style-row" title="Color del borde">
            <span className="map-layers-style-label">Borde</span>
            <input
              type="color"
              className="map-layers-style-color"
              value={/^#[0-9a-fA-F]{6}$/.test(lineColor) ? lineColor : "#1a3f8c"}
              onChange={(e) => onStyleChange?.(layer.id, { lineColor: e.target.value })}
            />
            <span className="map-layers-style-value map-layers-style-value--hex">{lineColor}</span>
          </label>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Panel derecho de capas (todas las vistas): capas del mapa + basemap al final.
 * En Fire reutiliza agrupación dNBR y bloque de estadísticas.
 */
export default function MapLayersPanel({
  layers = [],
  onToggle,
  onToggleDnbrGroup,
  onLayerStyleChange,
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
  const [styleEditorId, setStyleEditorId] = useState(null);
  const [collapsedGroups, setCollapsedGroups] = useState(() => new Set());
  const listRef = useRef(null);

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

  useEffect(() => {
    if (!styleEditorId) return;
    if (!items.some((l) => l.id === styleEditorId)) setStyleEditorId(null);
  }, [items, styleEditorId]);

  useEffect(() => {
    if (!styleEditorId) return undefined;
    const onDoc = (e) => {
      if (listRef.current && !listRef.current.contains(e.target)) {
        setStyleEditorId(null);
      }
    };
    const onKey = (e) => {
      if (e.key === "Escape") setStyleEditorId(null);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [styleEditorId]);

  function renderLayerRow(layer, { nested = false } = {}) {
    const color = layer.metadata?.fireClassColor;
    const styleOpen = styleEditorId === layer.id;
    const showStyle = onLayerStyleChange && canStyleLayer(layer);
    return (
      <li
        key={layer.id}
        className={`map-layers-item${nested ? " map-layers-item--nested" : ""}${
          styleOpen ? " is-style-open" : ""
        }`}
      >
        <div className="map-layers-item-main">
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
          </label>
          <div className="map-layers-row-actions">
            {showStyle ? (
              <LayerStyleTrigger
                open={styleOpen}
                disabled={!layer.visible}
                onToggle={() =>
                  setStyleEditorId((cur) => (cur === layer.id ? null : layer.id))
                }
              />
            ) : null}
            <span className={`map-layers-kind map-layers-kind--${layer.kind || "vector"}`}>
              {layer.kind === "raster" ? "R" : "V"}
            </span>
          </div>
        </div>
        {showStyle && styleOpen ? (
          <LayerStylePanel layer={layer} onStyleChange={onLayerStyleChange} />
        ) : null}
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
        <ul className="map-layers-list" ref={listRef}>
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
            const styleOpen = styleEditorId === layer.id;
            const showStyle = onLayerStyleChange && canStyleLayer(layer);
            const expanded = !collapsedGroups.has(layer.id);
            return (
              <li
                key={layer.id}
                className={`map-layers-group${styleOpen ? " is-style-open" : ""}${
                  expanded ? " is-expanded" : " is-collapsed"
                }`}
              >
                <div className="map-layers-item-main">
                  {kids.length ? (
                    <button
                      type="button"
                      className="map-layers-group-toggle"
                      title={expanded ? "Compactar subniveles" : "Expandir subniveles"}
                      aria-label={expanded ? "Compactar subniveles" : "Expandir subniveles"}
                      aria-expanded={expanded}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setCollapsedGroups((prev) => {
                          const next = new Set(prev);
                          if (next.has(layer.id)) next.delete(layer.id);
                          else next.add(layer.id);
                          return next;
                        });
                      }}
                    >
                      {expanded ? "−" : "+"}
                    </button>
                  ) : (
                    <span className="map-layers-group-toggle map-layers-group-toggle--spacer" aria-hidden />
                  )}
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
                    {kids.length ? (
                      <span className="map-layers-group-count" title={`${kids.length} subniveles`}>
                        {kids.length}
                      </span>
                    ) : null}
                  </label>
                  <div className="map-layers-row-actions">
                    {showStyle ? (
                      <LayerStyleTrigger
                        open={styleOpen}
                        disabled={!layer.visible}
                        onToggle={() =>
                          setStyleEditorId((cur) => (cur === layer.id ? null : layer.id))
                        }
                      />
                    ) : null}
                    <span className="map-layers-kind map-layers-kind--raster">R</span>
                  </div>
                </div>
                {showStyle && styleOpen ? (
                  <LayerStylePanel layer={layer} onStyleChange={onLayerStyleChange} />
                ) : null}
                {kids.length && expanded ? (
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
