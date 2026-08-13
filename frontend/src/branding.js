/**
 * Branding temporal por cliente.
 * Para caugusto.vargas@gmail.com: sin logos BioAgro, solo «Geovisor Agricola».
 */

const SK_EMAIL = "bioagromap_email";

/** Correos con marca alternativa (temporal). */
export const GEOVISOR_BRAND_EMAILS = new Set(["caugusto.vargas@gmail.com"]);

export const DEFAULT_BRAND = {
  hideLogo: false,
  logoSrc: "/logo-xenia.png",
  logoAlt: "Xenia MAP",
  poweredByLogoSrc: "/logo-xenia-positivo.png",
  poweredByLogoAlt: "Xenia",
  poweredByLogoSecondarySrc: "/logo-teraval.png",
  poweredByLogoSecondaryAlt: "Teraval",
  productName: "BioAgroMap",
  tagline: "Agricultura más Inteligente con Xenia & Teraval",
  footerLine: "Agricultura más inteligente con Xenia & Teraval",
  dashboardTitle: "BioAgroMap → Dashboard multisensor Espectral-Espacio-Temporal",
  dashboardAria: "BioAgroMap, dashboard multisensor espectral-espacio-temporal",
};

export const GEOVISOR_BRAND = {
  hideLogo: true,
  logoSrc: "",
  logoAlt: "Geovisor Agricola",
  poweredByLogoSrc: "/logo-xenia-positivo.png",
  poweredByLogoAlt: "Xenia",
  poweredByLogoSecondarySrc: "/logo-teraval.png",
  poweredByLogoSecondaryAlt: "Teraval",
  productName: "Geovisor Agricola",
  tagline: "Geovisor Agricola",
  footerLine: "Geovisor Agricola",
  dashboardTitle: "Geovisor Agricola → Dashboard multisensor Espectral-Espacio-Temporal",
  dashboardAria: "Geovisor Agricola, dashboard multisensor espectral-espacio-temporal",
};

export function normalizeEmail(email) {
  return String(email || "")
    .trim()
    .toLowerCase();
}

export function persistViewerEmail(email) {
  const e = normalizeEmail(email);
  try {
    if (e) sessionStorage.setItem(SK_EMAIL, e);
    else sessionStorage.removeItem(SK_EMAIL);
  } catch {
    /* ignore */
  }
}

export function clearViewerEmail() {
  try {
    sessionStorage.removeItem(SK_EMAIL);
  } catch {
    /* ignore */
  }
}

export function loadViewerEmail(explicit) {
  const fromProp = normalizeEmail(explicit);
  if (fromProp) return fromProp;
  try {
    return normalizeEmail(sessionStorage.getItem(SK_EMAIL));
  } catch {
    return "";
  }
}

export function usesGeovisorBrand(email) {
  return GEOVISOR_BRAND_EMAILS.has(loadViewerEmail(email));
}

/** Marca visible según el usuario autenticado (o email explícito). */
export function getClientBrand(email) {
  return usesGeovisorBrand(email) ? GEOVISOR_BRAND : DEFAULT_BRAND;
}
