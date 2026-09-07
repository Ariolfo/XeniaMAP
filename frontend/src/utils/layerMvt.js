/** Plantilla MapLibre ``tiles`` MVT para capas Agro publicadas (Bearer vía MapView). */
import { API_URL } from "../api";

/** source-layer fijo del protobuf (backend ``MVT_SOURCE_LAYER``). */
export const LAYER_MVT_SOURCE_LAYER = "published";

export function layerMvtTilesTemplate(projectId, layerId) {
  const base = String(API_URL || "").replace(/\/$/, "");
  return `${base}/layers/${projectId}/${layerId}/tiles/{z}/{x}/{y}.mvt`;
}
