/** Iconos MapLibre: estrellas de 5 puntas para hotspots FIRMS. */

export const FIRE_HOTSPOT_STAR_IMAGE_ID = "fire-hotspot-star";
export const FIRE_HOTSPOT_STAR_24H_ID = "fire-hotspot-star-24h";
export const FIRE_HOTSPOT_STAR_48H_ID = "fire-hotspot-star-48h";

const STAR_STYLES = {
  [FIRE_HOTSPOT_STAR_IMAGE_ID]: { fill: "#ff0000", stroke: "#ffffff" },
  [FIRE_HOTSPOT_STAR_24H_ID]: { fill: "#2563eb", stroke: "#1e3a8a" },
  [FIRE_HOTSPOT_STAR_48H_ID]: { fill: "#7c3aed", stroke: "#4c1d95" },
};

function starPath(cx, cy, spikes, outerR, innerR) {
  const pts = [];
  let rot = (Math.PI / 2) * 3;
  const step = Math.PI / spikes;
  for (let i = 0; i < spikes; i += 1) {
    pts.push([cx + Math.cos(rot) * outerR, cy + Math.sin(rot) * outerR]);
    rot += step;
    pts.push([cx + Math.cos(rot) * innerR, cy + Math.sin(rot) * innerR]);
    rot += step;
  }
  pts.push(pts[0]);
  return pts;
}

function addStarImage(map, imageId, fill, stroke) {
  if (!map) return imageId;
  // Reemplazar si ya existe para aplicar color vivo actualizado.
  if (map.hasImage(imageId)) {
    try {
      map.removeImage(imageId);
    } catch (_) {
      return imageId;
    }
  }

  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return imageId;

  ctx.clearRect(0, 0, size, size);
  // Desactivar suavizado excesivo: relleno opaco sólido.
  ctx.imageSmoothingEnabled = false;
  const pts = starPath(size / 2, size / 2, 5, 30, 12);
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = stroke;
  ctx.stroke();
  // Segundo relleno para asegurar opacidad plena en el núcleo.
  ctx.fillStyle = fill;
  ctx.fill();

  const imageData = ctx.getImageData(0, 0, size, size);
  // Forzar alpha=255 en píxeles con color (evita halo semitransparente).
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] > 30) data[i + 3] = 255;
    else data[i + 3] = 0;
  }
  map.addImage(
    imageId,
    {
      width: size,
      height: size,
      data: new Uint8Array(imageData.data.buffer),
    },
    { pixelRatio: 2 }
  );
  return imageId;
}

/** Estrella roja (capa histórica pipeline FIRMS). */
export function ensureFireHotspotStarIcon(map) {
  const style = STAR_STYLES[FIRE_HOTSPOT_STAR_IMAGE_ID];
  return addStarImage(map, FIRE_HOTSPOT_STAR_IMAGE_ID, style.fill, style.stroke);
}

/** Registra estrellas azul (24h) y violeta (48h). */
export function ensureFireLiveHotspotIcons(map) {
  const s24 = STAR_STYLES[FIRE_HOTSPOT_STAR_24H_ID];
  const s48 = STAR_STYLES[FIRE_HOTSPOT_STAR_48H_ID];
  addStarImage(map, FIRE_HOTSPOT_STAR_24H_ID, s24.fill, s24.stroke);
  addStarImage(map, FIRE_HOTSPOT_STAR_48H_ID, s48.fill, s48.stroke);
  return { star24: FIRE_HOTSPOT_STAR_24H_ID, star48: FIRE_HOTSPOT_STAR_48H_ID };
}

/** Resuelve el image-id MapLibre según metadata / opción symbol. */
export function resolveFireStarImageId(symbolOrRole) {
  const key = String(symbolOrRole || "");
  if (key === "star-24h" || key === "hotspot-24h") return FIRE_HOTSPOT_STAR_24H_ID;
  if (key === "star-48h" || key === "hotspot-48h") return FIRE_HOTSPOT_STAR_48H_ID;
  return FIRE_HOTSPOT_STAR_IMAGE_ID;
}
