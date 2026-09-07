/** Normalización de rol de usuario (cliente/admin). */
export function normalizeUserRole(role) {
  const value = String(role || "").trim().toLowerCase();
  if (value === "client") return "cliente";
  return value;
}

/** Sentinel-2 ZIP antiguo: una capa por banda (B02…B08). Ocultar; solo vistas RGB/NIR. */
export function isLegacyS2ZipBandRaster(meta) {
  if (!meta) return false;
  return !!(meta.s2_band_pack && meta.band && !meta.composite_kind);
}
