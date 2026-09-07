import {
  SENSOR_META,
  buildSensorInventory,
  mergeS1InteractiveVisuals,
  normIso,
} from "./previewUtils";

export function normalizeProjectSlug(name) {
  return String(name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function resolveProjectFromParam(projects, param) {
  if (!param || !projects?.length) return null;
  const raw = String(param).trim();
  if (/^\d+$/.test(raw)) {
    return projects.find((p) => Number(p.id) === Number(raw)) || null;
  }
  const slug = normalizeProjectSlug(raw);
  return projects.find((p) => normalizeProjectSlug(p.name) === slug) || null;
}

export function isProjectPublished(project) {
  const st = String(project?.status || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
  return st === "publicado";
}

export function adaptInventories({
  s1Items = [],
  s2Items = [],
  psItems = [],
  s2Recortes = [],
  psRecortes = [],
  s1PrepVv = [],
  s1PrepVh = [],
}) {
  const s1Base = buildSensorInventory(s1Items, "s1");
  const sensorData = {
    s1: mergeS1InteractiveVisuals(s1Base, s1PrepVv, s1PrepVh),
    s2: buildSensorInventory(s2Items, "s2"),
    ps: buildSensorInventory(psItems, "ps"),
  };
  return {
    sensorData,
    recorteInventory: { s2: s2Recortes, ps: psRecortes },
    s1PrepSigmaItems: s1PrepVv,
    s1PrepSigmaItemsVh: s1PrepVh,
  };
}

export function buildLandingMeta(project, adapted) {
  const { sensorData, recorteInventory } = adapted;
  const dates = [];
  for (const s of ["s1", "s2", "ps"]) {
    for (const frames of Object.values(sensorData[s]?.framesByIndex || {})) {
      for (const f of frames) dates.push(normIso(f.date));
    }
    for (const r of recorteInventory[s] || []) {
      const sk = normIso(r.sort_key);
      if (sk) dates.push(sk);
    }
  }
  const sorted = [...new Set(dates.filter(Boolean))].sort();
  const sceneCounts = {
    s1: countScenes(sensorData.s1),
    s2: Math.max(countScenes(sensorData.s2), (recorteInventory.s2 || []).length),
    ps: Math.max(countScenes(sensorData.ps), (recorteInventory.ps || []).length),
  };
  return {
    projectName: project?.name || "Proyecto",
    status: project?.status || "",
    studyDateStart: project?.study_date_start?.slice(0, 10) || sorted[0] || "",
    studyDateEnd: project?.study_date_end?.slice(0, 10) || sorted[sorted.length - 1] || "",
    dateRangeLabel: formatRange(sorted[0], sorted[sorted.length - 1]),
    sceneCounts,
    totalScenes: sceneCounts.s1 + sceneCounts.s2 + sceneCounts.ps,
    sensorsAvailable: ["s1", "s2", "ps"].filter((k) => sceneCounts[k] > 0 || (sensorData[k]?.indices?.length || 0) > 0),
  };
}

function countScenes(sensorBlock) {
  if (!sensorBlock?.framesByIndex) return 0;
  const dates = new Set();
  for (const frames of Object.values(sensorBlock.framesByIndex)) {
    for (const f of frames) dates.add(normIso(f.date));
  }
  return dates.size;
}

function formatRange(start, end) {
  if (!start && !end) return "—";
  const fmt = (iso) => {
    if (!iso) return "—";
    const [y, m] = iso.split("-");
    const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
    return `${months[Number(m) - 1] || m}/${y?.slice(2) || y}`;
  };
  if (start === end) return fmt(start);
  return `${fmt(start)} – ${fmt(end)}`;
}

export function pickDefaultSensor(sensorsAvailable) {
  if (sensorsAvailable.includes("ps")) return "ps";
  if (sensorsAvailable.includes("s2")) return "s2";
  if (sensorsAvailable.includes("s1")) return "s1";
  return "ps";
}

export function sensorLabel(sensorId) {
  return SENSOR_META[sensorId]?.title || sensorId;
}
