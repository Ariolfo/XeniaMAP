import { useEffect, useState } from "react";
import api, { setAuthToken } from "../api";

/**
 * Descarga Sentinel-1/2: estado, polling de progreso y disparo de download.
 */
export default function useSentinelDownloads({
  token,
  projectId,
  downloadSource,
  requireAdminAction,
  addMapLayer,
  setTargetRasterId,
  setMessage,
  setLoading,
}) {
  const [s2Download, setS2Download] = useState(null);
  const [s1Download, setS1Download] = useState(null);

  useEffect(() => {
    setS2Download(null);
    setS1Download(null);
  }, [projectId]);

  useEffect(() => {
    if (!s2Download || s2Download.ui_status !== "downloading" || !projectId || !token) {
      return undefined;
    }
    const rasterId = s2Download.rasterId;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/sentinel-status/${projectId}/${rasterId}`);
        const st = r.data.ui_status;
        setS2Download((prev) => {
          if (!prev || prev.rasterId !== rasterId) return prev;
          return {
            ...prev,
            progress: r.data.progress ?? prev.progress,
            message: r.data.message ?? prev.message,
            ui_status: st,
            totalDownloaded: r.data.total_downloaded ?? prev.totalDownloaded,
            totalSizeMb: r.data.total_size_mb ?? prev.totalSizeMb,
          };
        });
        if (st === "completed") {
          const parts = [`Sentinel-2: descarga terminada.`];
          if (r.data.total_downloaded != null) parts.push(` Archivos: ${r.data.total_downloaded}.`);
          if (r.data.skipped_high_cloud != null) parts.push(` Omitidas por nube AOI: ${r.data.skipped_high_cloud}.`);
          if (r.data.skipped_low_coverage != null) parts.push(` Omitidas por cobertura: ${r.data.skipped_low_coverage}.`);
          setMessage(parts.join(""));
        } else if (st === "failed") {
          setMessage(`Sentinel-2: ${r.data.message || "Error"}`);
        }
      } catch (_) {
        /* ignore transient errors */
      }
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => clearInterval(iv);
  }, [s2Download?.rasterId, s2Download?.ui_status, projectId, token]);

  useEffect(() => {
    if (!s1Download || s1Download.ui_status !== "downloading" || !projectId || !token) {
      return undefined;
    }
    const rasterId = s1Download.rasterId;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/sentinel-status/${projectId}/${rasterId}`);
        const st = r.data.ui_status;
        setS1Download((prev) => {
          if (!prev || prev.rasterId !== rasterId) return prev;
          return {
            ...prev,
            progress: r.data.progress ?? prev.progress,
            message: r.data.message ?? prev.message,
            ui_status: st,
            totalDownloaded: r.data.total_downloaded ?? prev.totalDownloaded,
            totalSizeMb: r.data.total_size_mb ?? prev.totalSizeMb,
            selectedRelativeOrbit: r.data.selected_relative_orbit ?? prev.selectedRelativeOrbit,
            selectedPassShort: r.data.selected_pass_short ?? prev.selectedPassShort,
            dateRangeStart: r.data.date_range_start ?? prev.dateRangeStart,
            dateRangeEnd: r.data.date_range_end ?? prev.dateRangeEnd,
            csvPath: r.data.csv_path ?? prev.csvPath,
          };
        });
        if (st === "completed") {
          const orb = r.data.selected_relative_orbit != null ? ` Órbita relativa ${r.data.selected_relative_orbit}` : "";
          const pass = r.data.selected_pass_short ? `, paso ${r.data.selected_pass_short}` : "";
          const dr =
            r.data.date_range_start && r.data.date_range_end
              ? ` Rango adquisición: ${r.data.date_range_start} → ${r.data.date_range_end}.`
              : "";
          setMessage(
            `Sentinel-1: descarga terminada.${orb}${pass}.${dr}${
              r.data.total_downloaded != null ? ` Productos: ${r.data.total_downloaded}.` : ""
            }`
          );
        } else if (st === "failed") {
          setMessage(`Sentinel-1: ${r.data.message || "Error"}`);
        }
      } catch (_) {
        /* ignore transient errors */
      }
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => clearInterval(iv);
  }, [s1Download?.rasterId, s1Download?.ui_status, projectId, token]);

  async function preprocessDownload(
    startDate,
    endDate,
    layerId,
    s1AoiFile,
    s1ImagesPerMonth = 0,
    downloadSubpath
  ) {
    if (!requireAdminAction()) return;
    if (!token || !projectId) {
      setMessage("Error: debes iniciar sesion y crear proyecto.");
      return;
    }
    if (
      (downloadSource === "sentinel-1" || downloadSource === "sentinel-2") &&
      !(downloadSubpath && String(downloadSubpath).startsWith("ext:"))
    ) {
      setMessage("Error: elige la carpeta de destino en el disco externo.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      if (downloadSource === "sentinel-1") {
        const fd = new FormData();
        fd.append("project_id", String(projectId));
        fd.append("start_date", startDate);
        fd.append("end_date", endDate);
        if (layerId) {
          fd.append("layer_id", String(layerId));
        }
        if (s1AoiFile) {
          fd.append("aoi_file", s1AoiFile);
        }
        fd.append("images_per_month", String(Number(s1ImagesPerMonth) || 0));
        fd.append("download_subpath", String(downloadSubpath));
        const res = await api.post("/preprocess/sentinel1-download", fd);
        if (res.data.status === "downloading") {
          setS1Download({
            rasterId: res.data.raster_layer_id,
            taskId: res.data.task_id,
            progress: 0,
            message: "Iniciando descarga Sentinel-1 (GRD IW, Copernicus)…",
            ui_status: "downloading",
          });
          setMessage(
            `Descarga Sentinel-1 en curso (registro #${res.data.raster_layer_id})${
              res.data.output_dir ? ` → ${res.data.output_dir}` : ""
            }`
          );
        }
        return;
      }

      const body = {
        project_id: Number(projectId),
        source: downloadSource,
      };
      if (downloadSource === "sentinel-2") {
        body.start_date = startDate;
        body.end_date = endDate;
        body.download_subpath = String(downloadSubpath);
      }
      if (layerId) {
        body.layer_id = Number(layerId);
      }
      const res = await api.post("/preprocess/download", body);
      if (downloadSource !== "sentinel-2") {
        setTargetRasterId(String(res.data.raster_layer_id));
        addMapLayer(`${downloadSource}.tif`, "raster", null, res.data.raster_layer_id);
      }
      if (res.data.status === "downloading" && downloadSource === "sentinel-2") {
        setS2Download({
          rasterId: res.data.raster_layer_id,
          taskId: res.data.task_id,
          progress: 0,
          message: "Iniciando descarga Sentinel-2...",
          ui_status: "downloading",
        });
        setMessage(
          `Descarga Sentinel-2 en curso (raster #${res.data.raster_layer_id})${
            res.data.output_dir ? ` → ${res.data.output_dir}` : ""
          }`
        );
      } else if (res.data.status === "downloading") {
        setMessage(`Descarga iniciada. Raster ID: ${res.data.raster_layer_id}`);
      } else {
        setMessage(`Descarga completada. Raster ID: ${res.data.raster_layer_id}`);
      }
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error en descarga";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  return {
    s2Download,
    setS2Download,
    s1Download,
    setS1Download,
    preprocessDownload,
  };
}
