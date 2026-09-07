import { useCallback } from "react";
import {
  ensureFireHotspotStarIcon,
  ensureFireLiveHotspotIcons,
  FIRE_HOTSPOT_STAR_IMAGE_ID,
  resolveFireStarImageId,
} from "../utils/fireMapIcons";
import { LAYER_MVT_SOURCE_LAYER } from "../utils/layerMvt";

/**
 * Pinta vectores en MapLibre: GeoJSON in-memory o tiles MVT (PostGIS).
 * Compartido por Agro (selectProject) y Fire.
 */
export default function usePaintLayerOnMap(mapRef) {
  return useCallback((lid, geojsonData, options = {}) => {
    const map = mapRef.current;
    const tileTemplate = options.tileTemplate || null;
    if (!map || (!geojsonData && !tileTemplate)) return;
    const visible = options.visible !== false;
    const symbol = options.symbol || null;
    const fillColor = options.fillColor || "#2d6cdf";
    const lineColor = options.lineColor || "#1a3f8c";
    const fillOpacity = options.fillOpacity ?? 0.35;
    const lineWidth = options.lineWidth ?? 2;
    const sourceLayer = options.sourceLayer || LAYER_MVT_SOURCE_LAYER;
    const tryPaint = () => {
      if (map.getSource(lid)) return;
      if (tileTemplate) {
        map.addSource(lid, {
          type: "vector",
          tiles: [tileTemplate],
          minzoom: 0,
          maxzoom: 22,
        });
        map.addLayer({
          id: lid,
          type: "fill",
          source: lid,
          "source-layer": sourceLayer,
          paint: { "fill-color": fillColor, "fill-opacity": fillOpacity },
          layout: { visibility: visible ? "visible" : "none" },
        });
        map.addLayer({
          id: lid + "_outline",
          type: "line",
          source: lid,
          "source-layer": sourceLayer,
          paint: { "line-color": lineColor, "line-width": lineWidth, "line-opacity": 1 },
          layout: { visibility: visible ? "visible" : "none" },
        });
        return;
      }
      map.addSource(lid, { type: "geojson", data: geojsonData });
      if (symbol) {
        ensureFireHotspotStarIcon(map);
        ensureFireLiveHotspotIcons(map);
        const iconId = resolveFireStarImageId(symbol);
        const iconSize = options.iconSize ?? (symbol === "star" ? 0.9 : 0.7);
        const iconOpacity = options.iconOpacity ?? 1;
        map.addLayer({
          id: lid,
          type: "symbol",
          source: lid,
          layout: {
            "icon-image": iconId || FIRE_HOTSPOT_STAR_IMAGE_ID,
            "icon-size": iconSize,
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
            visibility: visible ? "visible" : "none",
          },
          paint: {
            "icon-opacity": iconOpacity,
          },
        });
        return;
      }
      map.addLayer({
        id: lid,
        type: "fill",
        source: lid,
        paint: { "fill-color": fillColor, "fill-opacity": fillOpacity },
        layout: { visibility: visible ? "visible" : "none" },
      });
      map.addLayer({
        id: lid + "_outline",
        type: "line",
        source: lid,
        paint: { "line-color": lineColor, "line-width": lineWidth, "line-opacity": 1 },
        layout: { visibility: visible ? "visible" : "none" },
      });
    };
    if (map.isStyleLoaded()) tryPaint();
    else map.once("style.load", tryPaint);
  }, [mapRef]);
}
