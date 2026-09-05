import { useEffect, useState } from "react";
import { API_URL } from "../../api";
import { fetchPreviewDataUrl } from "../previewUtils";

/**
 * Agrogeofísica: mosaico 2×2
 * 1.1 DEM (solo valores válidos) | 1.2 DEM con paleta de altura + barra
 * 2.1 CV                         | 2.2 Clusters
 */
export default function LandingSoilSection({
  projectId,
  token,
  clientSoilSummary,
  loading,
  error,
  hideTitle = false,
}) {
  const [mosaicUrl, setMosaicUrl] = useState("");
  const [mosaicError, setMosaicError] = useState("");
  const [mosaicLoading, setMosaicLoading] = useState(false);

  const hasMatlab = !!(clientSoilSummary?.matlab && !clientSoilSummary.matlab.error);
  const hasFast = !!(clientSoilSummary?.fast && !clientSoilSummary.fast.error);
  const preferredVariant = hasMatlab ? "matlab" : hasFast ? "fast" : "";

  useEffect(() => {
    let cancelled = false;
    if (!projectId || !token || !preferredVariant) {
      setMosaicUrl("");
      setMosaicError("");
      return undefined;
    }
    setMosaicLoading(true);
    setMosaicError("");
    const base = API_URL.replace(/\/$/, "");
    void fetchPreviewDataUrl(
      `${base}/preprocess/soilplus-landing-mosaic/${projectId}?variant=${encodeURIComponent(preferredVariant)}`,
      token
    )
      .then((url) => {
        if (!cancelled) setMosaicUrl(url);
      })
      .catch((e) => {
        if (!cancelled) {
          setMosaicUrl("");
          setMosaicError(e?.message || "No se pudo cargar el mosaico de Agrogeofísica.");
        }
      })
      .finally(() => {
        if (!cancelled) setMosaicLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, token, preferredVariant]);

  const busy = loading || mosaicLoading;
  const hasData = !!mosaicUrl;

  return (
    <div className="landing-subsection landing-subsection--soil">
      {!hideTitle ? <h3 className="landing-subsection-title">AgroGeoFísica</h3> : null}
      {busy ? <p className="landing-hint">Cargando mosaico Agrogeofísica…</p> : null}
      {error ? <p className="landing-error">{error}</p> : null}
      {mosaicError ? <p className="landing-error">{mosaicError}</p> : null}
      {!busy && !error && !mosaicError && !hasData ? (
        <p className="landing-hint">
          No hay resultados guardados de Soil Plus. El equipo XeniaMAP puede generarlos desde el dashboard técnico.
        </p>
      ) : null}
      {hasData ? (
        <div className="landing-soil-mosaic-wrap">
          <p className="landing-soil-mosaic-caption">
            Mosaico 2×2 ({preferredVariant === "matlab" ? "Mat" : "Fast"}): DEM válido · DEM
            altura · CV · Clusters con puntos de muestreo
          </p>
          <img
            className="landing-soil-mosaic-img"
            src={mosaicUrl}
            alt="Mosaico Agrogeofísica 2x2: DEM, DEM altura, CV y clusters"
          />
        </div>
      ) : null}
    </div>
  );
}
