/** Claves canónicas de subsección (alineadas con backend landing_texts). */

import { LANDING_INDEX_GROUPS, indexKeysForLandingGroup } from "./interpretations";

export const LANDING_SECTION_SUFFIXES = [
  "interactive",
  "rgb",
  "rgb-vv",
  "rgb-vh",
  "indices",
  "clusters",
  "smart-clusters",
  "agrogeofisica",
  "ia",
];

export const LANDING_SENSOR_KEYS = ["ps", "s1", "s2"];

export function sectionKey(sensorKey, suffix) {
  return `landing-${sensorKey}-${suffix}`;
}

/** Narrativa editable por índice: landing-ps-index-NDVI */
export function indexNarrativeKey(sensorKey, indexKey) {
  const ik = String(indexKey || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_]/g, "");
  return `landing-${sensorKey}-index-${ik || "INDEX"}`;
}

export function parseIndexNarrativeKey(sectionKey) {
  const m = String(sectionKey || "").match(/^landing-(ps|s1|s2)-index-([A-Za-z0-9_]+)$/);
  if (!m) return null;
  return { sensorKey: m[1], indexKey: m[2] };
}

export function allIndexKeysForSensor(sensorKey) {
  const out = [];
  const seen = new Set();
  for (const g of LANDING_INDEX_GROUPS) {
    for (const ik of indexKeysForLandingGroup(g.id, sensorKey)) {
      const u = String(ik).toUpperCase();
      if (seen.has(u)) continue;
      seen.add(u);
      out.push(ik);
    }
  }
  return out;
}

export function allLandingSectionKeys() {
  const keys = [];
  for (const sensor of LANDING_SENSOR_KEYS) {
    for (const suffix of LANDING_SECTION_SUFFIXES) {
      // Informe inteligente solo en Alta resolución (PS)
      if (suffix === "ia" && sensor !== "ps") continue;
      // Narrativas VV/VH solo en Sentinel-1
      if ((suffix === "rgb-vv" || suffix === "rgb-vh") && sensor !== "s1") continue;
      // En S1 la narrativa RGB se divide en rgb-vv / rgb-vh
      if (suffix === "rgb" && sensor === "s1") continue;
      keys.push(sectionKey(sensor, suffix));
    }
    for (const ik of allIndexKeysForSensor(sensor)) {
      keys.push(indexNarrativeKey(sensor, ik));
    }
  }
  return keys;
}

/**
 * Proyectos donde el cliente no debe ver «Informe inteligente» (sí admin en edición).
 * Temporalmente desactivado: Palm_10años (id 14) vuelve a mostrar la sección 1.7.
 */
export function shouldHideIaForClient(_project) {
  return false;
}
