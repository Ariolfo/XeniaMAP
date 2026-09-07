import { useEffect, useRef, useState } from "react";
import api, { formatApiErrorDetail, setAuthToken } from "../api";

/**
 * Jobs Celery Agro preprocess: recortes, stacks índices, extracción PS, kicks de galería.
 */
export default function usePreprocessCeleryJobs({
  token,
  projectId,
  selectedIndices,
  requireAdminAction,
  selectProject,
  setStackMode,
  setSidebarTab,
  setMessage,
  setLoading,
}) {
  const indexStacksVariantRef = useRef("s2");

  const [recorteTaskId, setRecorteTaskId] = useState("");
  /** "s1" | "s2" | "ps" | "" */
  const [recorteKind, setRecorteKind] = useState("");
  const [indexStacksTaskId, setIndexStacksTaskId] = useState("");
  const [psExtractTaskId, setPsExtractTaskId] = useState("");
  const [s1SarStacksTaskId, setS1SarStacksTaskId] = useState("");
  const [visualIndexGalleryKick, setVisualIndexGalleryKick] = useState(0);
  const [visualIndexGalleryKickPs, setVisualIndexGalleryKickPs] = useState(0);
  const [recorteLayerId, setRecorteLayerId] = useState("");
  const [preproGalleryKick, setPreproGalleryKick] = useState(0);
  const [preproClusterVizKick, setPreproClusterVizKick] = useState(0);
  const [preproClusterVizKickPs, setPreproClusterVizKickPs] = useState(0);

  useEffect(() => {
    setRecorteLayerId("");
    setRecorteKind("");
    setPsExtractTaskId("");
    setRecorteTaskId("");
    setIndexStacksTaskId("");
    setS1SarStacksTaskId("");
  }, [projectId]);

  useEffect(() => {
    if (!recorteTaskId || !token || !projectId) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/task-status/${recorteTaskId}`);
        if (cancelled) return;
        if (r.data.ready && r.data.state === "SUCCESS") {
          const result = r.data.result || {};
          const pipeline = result.pipeline || "s2_l2a";
          const n = result.processed ?? 0;
          const errs = (result.errors || []).filter(Boolean);
          const errTxt = errs.length ? ` Detalle por producto: ${errs.join(" | ")}` : "";
          setRecorteTaskId("");
          setRecorteKind("");
          await selectProject(projectId, token);
          if (pipeline === "s1_grd") {
            const aoi = result.aoi || {};
            const aoiTxt =
              aoi.layer_name != null && String(aoi.layer_name).trim()
                ? ` Polígono: «${aoi.layer_name}».`
                : aoi.mode === "union_all_project_vectors"
                  ? " Polígono: unión de todos los lotes del proyecto."
                  : "";
            const engines = [
              ...new Set((result.results || []).map((x) => x && x.clip_engine).filter(Boolean)),
            ];
            const engTxt = engines.length ? ` Motor: ${engines.join(", ")}.` : "";
            const um = (result.user_message || "").trim();
            const polyOut = result.polygon_outside_scene === true;
            let head = "Proceso de recorte Sentinel-1 terminado. ";
            if (um) {
              head += um;
            } else if (polyOut) {
              head +=
                "El polígono no está dentro de la imagen (o la escena no cubre el lote) para al menos un producto.";
            } else if (n > 0) {
              head += `${n} GeoTIFF en recortes/S1/.`;
            } else {
              head += "Sin recortes nuevos.";
            }
            setMessage(`${head}${aoiTxt}${engTxt}${errTxt}`.trim());
          } else if (pipeline === "ps_recorte_clip") {
            const src = result.source || "recortesPS";
            setMessage(
              n > 0
                ? `Recorte PS terminado: ${n} GeoTIFF desde ${src}/ → recortesPS/.${errTxt}`
                : `${result.message || "Recorte PS terminado sin archivos."}${errTxt}`
            );
          } else {
            setMessage(
              n > 0
                ? `Proceso de recorte L2A terminado. ${n} GeoTIFF de 6 bandas añadido(s) como capa(s).${errTxt}`
                : `Proceso de recorte L2A terminado. Sin nuevas capas.${errTxt || " Comprueba inventario L2A y polígono."}`
            );
          }
        } else if (r.data.ready && r.data.state === "FAILURE") {
          setRecorteTaskId("");
          setRecorteKind("");
          setMessage(`Proceso de recorte terminado con error: ${r.data.error || "fallo"}`);
        } else if (!r.data.ready) {
          const st = r.data.state || "PENDING";
          const label =
            recorteKind === "s1"
              ? "Recorte Sentinel-1"
              : recorteKind === "ps"
                ? "Recorte PS (recortesPS/)"
                : recorteKind === "s2"
                  ? "Recorte Sentinel-2 L2A"
                  : "Recorte";
          setMessage(
            `${label} en curso (Celery: ${st}). Al terminar se mostrará el resultado aquí. Tarea: ${recorteTaskId}`
          );
        }
      } catch (_) {
        /* ignorar errores transitorios al consultar Celery */
      }
    };
    poll();
    const iv = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [recorteTaskId, projectId, token]);

  useEffect(() => {
    if (!indexStacksTaskId || !token || !projectId) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/task-status/${indexStacksTaskId}`);
        if (cancelled) return;
        if (r.data.ready && r.data.state === "SUCCESS") {
          const result = r.data.result || {};
          const outs = result.outputs || {};
          const errList = result.errors || [];
          const parts = Object.entries(outs).map(([k, v]) => `${k}: ${v}`);
          const errTxt =
            errList.length > 0
              ? ` Escenas con avisos: ${errList.length}.`
              : "";
          setIndexStacksTaskId("");
          const pv = indexStacksVariantRef.current === "ps" ? "ps" : "s2";
          const idxNote = pv === "ps" ? " (indecesPS/)" : "";
          setMessage(
            Object.keys(outs).length > 0
              ? `Stacks de índices generados${idxNote} (${result.scene_count ?? "?"} escenas). ${parts.join(" | ")}${errTxt}`
              : `${result.message || "Sin archivos de salida; comprueba recortes L2A."}${errTxt}`
          );
          if (Object.keys(outs).length > 0) {
            setStackMode("visual-index");
            if (pv === "ps") {
              setSidebarTab("ps");
              setVisualIndexGalleryKickPs((k) => k + 1);
            } else {
              setSidebarTab("prepro");
              setVisualIndexGalleryKick((k) => k + 1);
            }
            await selectProject(projectId, token);
          }
        } else if (r.data.ready && r.data.state === "FAILURE") {
          setIndexStacksTaskId("");
          setMessage(`Error en stacks de índices: ${r.data.error || "fallo"}`);
        }
      } catch (_) {
        /* ignorar errores transitorios */
      }
    };
    poll();
    const iv = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [indexStacksTaskId, projectId, token]);

  useEffect(() => {
    if (!psExtractTaskId || !token || !projectId) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/task-status/${psExtractTaskId}`);
        if (cancelled) return;
        if (r.data.ready && r.data.state === "SUCCESS") {
          const result = r.data.result || {};
          const errs = (result.errors || []).filter(Boolean);
          const errTxt = errs.length ? ` Avisos: ${errs.join(" | ")}` : "";
          setPsExtractTaskId("");
          const n = result.processed ?? 0;
          const ok = result.ok !== false && n > 0;
          setMessage(
            ok
              ? `Extracción Planet PS terminada: ${n} composite(s) en rasterPS/ (originales). Usa «Recortar TIF» → recortesPS/.${errTxt}`
              : `${result.message || "Sin composites extraídos; revisa zips en rasterPS/."}${errTxt}`
          );
          if (ok) await selectProject(projectId, token);
        } else if (r.data.ready && r.data.state === "FAILURE") {
          setPsExtractTaskId("");
          setMessage(`Extracción PS falló: ${r.data.error || "error"}`);
        }
      } catch (_) {
        /* ignorar */
      }
    };
    poll();
    const iv = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [psExtractTaskId, projectId, token]);

  useEffect(() => {
    if (!s1SarStacksTaskId || !token || !projectId) {
      return undefined;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        setAuthToken(token);
        const r = await api.get(`/preprocess/task-status/${s1SarStacksTaskId}`);
        if (cancelled) return;
        if (r.data.ready && r.data.state === "SUCCESS") {
          const result = r.data.result || {};
          const outs = result.outputs || {};
          const errList = result.errors || [];
          const parts = Object.entries(outs).map(([k, v]) => `${k}: ${v}`);
          const errTxt = errList.length > 0 ? ` Escenas con avisos: ${errList.length}.` : "";
          setS1SarStacksTaskId("");
          setMessage(
            Object.keys(outs).length > 0
              ? `Stacks de índices SAR listos (${result.scene_count ?? "?"} escenas). ${parts.join(" | ")}${errTxt}`
              : `${result.message || "Sin archivos de salida; comprueba s1preproceso/ (VV+VH dB)."}${errTxt}`
          );
          if (Object.keys(outs).length > 0) {
            setStackMode("visual-s1-sar-indices");
            await selectProject(projectId, token);
          }
        } else if (r.data.ready && r.data.state === "FAILURE") {
          setS1SarStacksTaskId("");
          setMessage(`Error en índices SAR: ${r.data.error || "fallo"}`);
        }
      } catch (_) {
        /* ignorar errores transitorios */
      }
    };
    poll();
    const iv = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, [s1SarStacksTaskId, projectId, token]);

  async function runS2L2aRecortes(layerId, productNames, sourceSubpath, pipelineVariant = "s2") {
    if (!requireAdminAction()) return false;
    if (!token || !projectId) {
      setMessage("Error: inicia sesion y selecciona un proyecto.");
      return false;
    }
    const names = Array.isArray(productNames)
      ? [...new Set(productNames.map((s) => String(s).trim()).filter(Boolean))]
      : [];
    if (names.length === 0) {
      setMessage("Selecciona al menos un producto L2A (.zip o carpeta .SAFE) en la lista.");
      return false;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const body = {
        project_id: Number(projectId),
        product_names: names,
        pipeline_variant: pipelineVariant === "ps" ? "ps" : "s2",
      };
      if (sourceSubpath !== undefined) {
        body.source_subpath = sourceSubpath;
      }
      if (layerId != null && layerId !== "") {
        const n = Number(layerId);
        if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1) {
          setMessage(
            "Error: el polígono elegido no tiene ID de capa válido en el servidor. Vuelve a cargar el proyecto o sube de nuevo el lote."
          );
          return false;
        }
        body.layer_id = n;
      }
      const res = await api.post("/preprocess/s2-l2a-recortes", body);
      setRecorteKind(pipelineVariant === "ps" ? "ps" : "s2");
      setRecorteTaskId(res.data.task_id);
      setMessage(
        `Recorte L2A en cola (tarea ${res.data.task_id}). Seguimiento: estado Celery cada pocos segundos hasta terminar.`
      );
      return true;
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function runS1GrdRecortes(layerId, productPaths, sourceSubpath) {
    if (!requireAdminAction()) return false;
    if (!token || !projectId) {
      setMessage("Error: inicia sesion y selecciona un proyecto.");
      return false;
    }
    const paths = Array.isArray(productPaths)
      ? [...new Set(productPaths.map((s) => String(s).trim()).filter(Boolean))]
      : [];
    if (paths.length === 0) {
      setMessage("Selecciona al menos un producto Sentinel-1 (.zip o ruta .SAFE) en la lista.");
      return false;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const body = {
        project_id: Number(projectId),
        product_paths: paths,
      };
      if (sourceSubpath !== undefined) {
        body.source_subpath = sourceSubpath;
      }
      if (layerId != null && layerId !== "") {
        const n = Number(layerId);
        if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1) {
          setMessage(
            "Error: el polígono elegido no tiene ID de capa válido en el servidor. Vuelve a cargar el proyecto o sube de nuevo el lote."
          );
          return false;
        }
        body.layer_id = n;
      }
      const res = await api.post("/preprocess/sentinel1-recortes", body);
      setRecorteKind("s1");
      setRecorteTaskId(res.data.task_id);
      setMessage(
        `Recorte Sentinel-1 en cola (tarea ${res.data.task_id}). Se avisará al terminar (polígono fuera de escena, SNAP, etc.).`
      );
      return true;
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function runPsPlanetExtract(sourceSubpath) {
    if (!requireAdminAction()) return false;
    if (!token || !projectId) {
      setMessage("Error: inicia sesión y selecciona un proyecto.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const body = { project_id: Number(projectId) };
      if (sourceSubpath !== undefined) {
        body.source_subpath = sourceSubpath;
      }
      const res = await api.post("/preprocess/ps-planetscope-zip-extract", body);
      setPsExtractTaskId(res.data.task_id);
      setMessage(`Extracción Planet PS en cola (tarea ${res.data.task_id}).`);
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function runPsRecorteClip(layerId, filenames, source = "rasterPS", aoiFile = null) {
    if (!requireAdminAction()) return false;
    if (!token || !projectId) {
      setMessage("Error: inicia sesión y selecciona un proyecto.");
      return false;
    }
    const names = Array.isArray(filenames)
      ? [...new Set(filenames.map((s) => String(s).trim()).filter(Boolean))]
      : [];
    if (names.length === 0) {
      setMessage("Selecciona al menos un GeoTIFF PlanetScope en la lista.");
      return false;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const fd = new FormData();
      fd.append("project_id", String(projectId));
      fd.append("source", source === "rasterPS" ? "rasterPS" : "recortesPS");
      fd.append("filenames_json", JSON.stringify(names));
      if (aoiFile) {
        fd.append("aoi_file", aoiFile);
      } else if (layerId != null && layerId !== "") {
        const n = Number(layerId);
        if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1) {
          setMessage(
            "Error: el polígono elegido no tiene ID de capa válido en el servidor. Vuelve a cargar el proyecto o sube de nuevo el lote."
          );
          return false;
        }
        fd.append("layer_id", String(n));
      }
      const res = await api.post("/preprocess/ps-recorte-clip", fd);
      setRecorteKind("ps");
      setRecorteTaskId(res.data.task_id);
      setMessage(
        `Recorte PS en cola (tarea ${res.data.task_id}). Origen ${source === "rasterPS" ? "rasterPS" : "recortesPS"} → salida en recortesPS/.`
      );
      return true;
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function runS2IndexStacks(explicitRasterIds, opts = {}) {
    if (!requireAdminAction()) return false;
    const pipelineVariant = opts.pipelineVariant === "ps" ? "ps" : "s2";
    const recorteFilenames = Array.isArray(opts?.recorteFilenames)
      ? [...new Set(opts.recorteFilenames.map((s) => String(s).trim()).filter(Boolean))]
      : [];
    if (!token || !projectId) {
      setMessage("Error: inicia sesión y selecciona un proyecto.");
      return;
    }
    const indicesPayload = selectedIndices.length > 0 ? selectedIndices : [];
    if (!indicesPayload.length) {
      setMessage(
        "Selecciona al menos un índice en la ventana «Seleccionar escenas e estimar índices»."
      );
      return;
    }
    const ids = Array.isArray(explicitRasterIds)
      ? [...new Set(explicitRasterIds.map((x) => Number(x)).filter((n) => Number.isFinite(n) && n >= 1))]
      : [];
    if (ids.length === 0 && recorteFilenames.length === 0) {
      setMessage(
        "Abre «Seleccionar escenas e estimar índices», marca escenas (archivos en recortes/) y pulsa Estimar índice."
      );
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const body = {
        project_id: Number(projectId),
        indices: indicesPayload,
        pipeline_variant: pipelineVariant,
      };
      if (recorteFilenames.length > 0) {
        body.recorte_filenames = recorteFilenames;
      } else {
        body.raster_layer_ids = ids;
      }
      indexStacksVariantRef.current = pipelineVariant;
      const res = await api.post("/preprocess/s2-index-stacks", body);
      setIndexStacksTaskId(res.data.task_id);
      setMessage(`Stacks de índices en cola (tarea ${res.data.task_id}).`);
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function runS1SarIndexStacks({ sceneVvRelpaths, indices }) {
    if (!requireAdminAction()) return false;
    const paths = Array.isArray(sceneVvRelpaths)
      ? [...new Set(sceneVvRelpaths.map((s) => String(s).trim().replace(/\\/g, "/")).filter(Boolean))]
      : [];
    const idx = Array.isArray(indices)
      ? [...new Set(indices.map((s) => String(s).trim()).filter(Boolean))]
      : [];
    if (!token || !projectId) {
      setMessage("Error: inicia sesión y selecciona un proyecto.");
      return;
    }
    if (!idx.length) {
      setMessage("Selecciona al menos un índice SAR (o TODOS) en la ventana de estimación.");
      return;
    }
    if (!paths.length) {
      setMessage("Selecciona al menos una escena (miniatura) con par VV+VH en s1preproceso/.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const res = await api.post("/preprocess/s1-sar-index-stacks", {
        project_id: Number(projectId),
        indices: idx,
        scene_vv_relpaths: paths,
      });
      setS1SarStacksTaskId(res.data.task_id);
      setMessage(`Índices SAR en cola (tarea ${res.data.task_id}).`);
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
    } finally {
      setLoading(false);
    }
  }

  return {
    recorteTaskId,
    recorteKind,
    indexStacksTaskId,
    psExtractTaskId,
    s1SarStacksTaskId,
    visualIndexGalleryKick,
    setVisualIndexGalleryKick,
    visualIndexGalleryKickPs,
    setVisualIndexGalleryKickPs,
    recorteLayerId,
    setRecorteLayerId,
    preproGalleryKick,
    setPreproGalleryKick,
    preproClusterVizKick,
    setPreproClusterVizKick,
    preproClusterVizKickPs,
    setPreproClusterVizKickPs,
    runS2L2aRecortes,
    runS1GrdRecortes,
    runPsPlanetExtract,
    runPsRecorteClip,
    runS2IndexStacks,
    runS1SarIndexStacks,
  };
}
