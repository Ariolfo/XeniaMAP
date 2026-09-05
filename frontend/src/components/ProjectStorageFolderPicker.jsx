import { useCallback, useEffect, useRef, useState } from "react";
import api, { formatApiErrorDetail, setAuthToken } from "../api";

/**
 * Selector de carpeta origen:
 * - Disco externo (montado; sin copiar)
 * - almacenamiento del proyecto
 * - carpeta del computador (sube a local_import/…)
 */
export default function ProjectStorageFolderPicker({
  open,
  projectId,
  token,
  title = "Elegir carpeta de origen",
  initialPath = "",
  kind = "s2",
  externalOnly = false,
  allowCreateFolder = false,
  confirmLabel = "Usar esta carpeta",
  onSelect,
  onCancel,
}) {
  const [mode, setMode] = useState(externalOnly ? "external" : "external"); // external | project | local
  const [externalEnabled, setExternalEnabled] = useState(false);
  const [browsePath, setBrowsePath] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [localFiles, setLocalFiles] = useState([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0, current: "" });
  const [newFolderName, setNewFolderName] = useState("");
  const [mkdirBusy, setMkdirBusy] = useState(false);
  const fileInputRef = useRef(null);

  const isExt = (p) => typeof p === "string" && p.startsWith("ext:");
  const stripExt = (p) => (isExt(p) ? p.slice(4) : p || "");

  const loadExternal = useCallback(
    async (path) => {
      if (!token) return;
      setLoading(true);
      setError("");
      try {
        setAuthToken(token);
        const r = await api.get(`/raster/external-data-browse`, {
          params: { path: path || "" },
        });
        setData(r.data);
        setBrowsePath(r.data?.relative_path ?? path ?? "");
      } catch (e) {
        setError(formatApiErrorDetail(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  const loadProject = useCallback(
    async (path) => {
      if (!projectId || !token) return;
      setLoading(true);
      setError("");
      try {
        setAuthToken(token);
        const r = await api.get(`/raster/project-storage-browse/${projectId}`, {
          params: { path: path || "" },
        });
        setData(r.data);
        setBrowsePath(r.data?.relative_path ?? path ?? "");
      } catch (e) {
        setError(formatApiErrorDetail(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [projectId, token]
  );

  useEffect(() => {
    if (!open) return;
    setLocalFiles([]);
    setError("");
    setNewFolderName("");
    setUploadProgress({ done: 0, total: 0, current: "" });
    let cancelled = false;
    (async () => {
      try {
        setAuthToken(token);
        const st = await api.get(`/raster/external-data-status`);
        const enabled = Boolean(st.data?.enabled);
        if (cancelled) return;
        setExternalEnabled(enabled);
        if (externalOnly) {
          setMode("external");
          if (!enabled) {
            setError("Disco externo no está montado. Revisa EXTERNAL_DATA_HOST_PATH en Docker.");
            setData(null);
            return;
          }
          await loadExternal(stripExt(initialPath));
          return;
        }
        const startExternal = enabled && (isExt(initialPath) || !initialPath || initialPath === "downloads");
        if (startExternal) {
          setMode("external");
          await loadExternal(stripExt(initialPath));
        } else {
          setMode("project");
          await loadProject(isExt(initialPath) ? "" : initialPath || "");
        }
      } catch {
        if (cancelled) return;
        setExternalEnabled(false);
        if (externalOnly) {
          setError("No se pudo acceder al disco externo.");
          setData(null);
          return;
        }
        setMode("project");
        await loadProject(isExt(initialPath) ? "" : initialPath || "");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, initialPath, token, loadExternal, loadProject, externalOnly]);

  async function createFolderHere() {
    const name = (newFolderName || "").trim();
    if (!name || !token) return;
    setMkdirBusy(true);
    setError("");
    try {
      setAuthToken(token);
      const fd = new FormData();
      fd.append("name", name);
      fd.append("parent_path", data?.relative_path || "");
      const r = await api.post(`/raster/external-data-mkdir`, fd);
      setNewFolderName("");
      const rel = r.data?.relative_path || "";
      await loadExternal(rel);
    } catch (e) {
      setError(formatApiErrorDetail(e));
    } finally {
      setMkdirBusy(false);
    }
  }

  async function uploadLocalFolderAndSelect() {
    if (!projectId || !token || !localFiles.length) return;
    setUploadBusy(true);
    setError("");
    setUploadProgress({ done: 0, total: localFiles.length, current: "" });
    let batchId = null;
    let sourceSubpath = null;
    try {
      setAuthToken(token);
      for (let i = 0; i < localFiles.length; i += 1) {
        const file = localFiles[i];
        const rel = file.webkitRelativePath || file.name;
        setUploadProgress({ done: i, total: localFiles.length, current: rel });
        const fd = new FormData();
        fd.append("kind", kind);
        fd.append("relative_path", rel);
        fd.append("file", file);
        if (batchId) fd.append("batch_id", batchId);
        const r = await api.post(`/raster/project-local-folder-import/${projectId}`, fd, {
          timeout: 0,
          headers: { "Content-Type": "multipart/form-data" },
        });
        batchId = r.data?.batch_id || batchId;
        sourceSubpath = r.data?.source_subpath || sourceSubpath;
      }
      setUploadProgress({ done: localFiles.length, total: localFiles.length, current: "" });
      if (!sourceSubpath) {
        throw new Error("No se obtuvo la carpeta de destino tras la subida.");
      }
      onSelect?.(sourceSubpath);
    } catch (e) {
      setError(formatApiErrorDetail(e) || String(e?.message || e));
    } finally {
      setUploadBusy(false);
    }
  }

  if (!open) return null;

  const dirs = (data?.entries || []).filter((e) => e.kind === "dir");
  const files = (data?.entries || []).filter((e) => e.kind === "file");
  const cwd = data?.relative_path || "";
  const localBytes = localFiles.reduce((acc, f) => acc + (Number(f.size) || 0), 0);
  const localMb = (localBytes / (1024 * 1024)).toFixed(1);

  function selectCurrentBrowse() {
    if (mode === "external") {
      onSelect?.(data?.source_subpath || `ext:${cwd}`);
      return;
    }
    onSelect?.(cwd);
  }

  function goUp() {
    const parent = data?.parent_subpath ?? "";
    if (mode === "external") void loadExternal(parent);
    else void loadProject(parent);
  }

  function enterDir(rel) {
    if (mode === "external") void loadExternal(rel);
    else void loadProject(rel);
  }

  return (
    <div
      className="index-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="project-folder-picker-title"
      onClick={() => (!uploadBusy ? onCancel?.() : null)}
    >
      <div className="index-modal l2a-downloads-modal" onClick={(e) => e.stopPropagation()}>
        <div className="index-modal-header">
          <h3 id="project-folder-picker-title">{title}</h3>
          <button
            type="button"
            className="index-modal-close"
            onClick={() => (!uploadBusy ? onCancel?.() : null)}
            aria-label="Cerrar"
            disabled={uploadBusy}
          >
            ×
          </button>
        </div>
        <div className="index-modal-body l2a-downloads-body">
          <div className="l2a-downloads-actions" style={{ marginBottom: 10, flexWrap: "wrap" }}>
            {externalOnly ? null : (
              <>
                {externalEnabled ? (
                  <button
                    type="button"
                    className={mode === "external" ? "rgb-gallery-btn-primary" : "rgb-gallery-btn-secondary"}
                    disabled={uploadBusy}
                    onClick={() => {
                      setMode("external");
                      void loadExternal(isExt(initialPath) ? stripExt(initialPath) : "");
                    }}
                  >
                    Disco externo
                  </button>
                ) : null}
                <button
                  type="button"
                  className={mode === "project" ? "rgb-gallery-btn-primary" : "rgb-gallery-btn-secondary"}
                  disabled={uploadBusy}
                  onClick={() => {
                    setMode("project");
                    void loadProject(isExt(initialPath) ? "" : initialPath || "");
                  }}
                >
                  En el proyecto
                </button>
                <button
                  type="button"
                  className={mode === "local" ? "rgb-gallery-btn-primary" : "rgb-gallery-btn-secondary"}
                  disabled={uploadBusy}
                  onClick={() => setMode("local")}
                >
                  Subir desde PC
                </button>
              </>
            )}
          </div>

          {mode === "external" || mode === "project" ? (
            <>
              <p className="l2a-browse-cwd">
                {mode === "external" ? (
                  <>
                    Disco externo: <code>{cwd || "(raíz)"}</code>
                    <span className="l2a-downloads-hint"> — lectura directa, sin copiar</span>
                  </>
                ) : (
                  <>
                    Carpeta actual: <code>{cwd || "(raíz del proyecto)"}</code>
                  </>
                )}
              </p>
              {loading ? <p className="l2a-downloads-status">Cargando…</p> : null}
              {error ? <p className="rgb-gallery-error">{error}</p> : null}
              {!loading && data ? (
                <ul className="l2a-browse-list">
                  {cwd ? (
                    <li>
                      <button type="button" className="l2a-browse-up" onClick={goUp}>
                        ↑ Subir
                      </button>
                    </li>
                  ) : null}
                  {dirs.map((d) => (
                    <li key={d.relative_path}>
                      <button
                        type="button"
                        className="l2a-browse-row l2a-browse-row--dir"
                        onClick={() => enterDir(d.relative_path)}
                      >
                        📁 {d.name}
                      </button>
                    </li>
                  ))}
                  {files.map((f) => (
                    <li key={f.relative_path}>
                      <span className="l2a-browse-row l2a-browse-row--file" title={f.name}>
                        📄 {f.name}
                      </span>
                    </li>
                  ))}
                  {!dirs.length && !files.length ? (
                    <li>
                      <p className="l2a-downloads-empty">Carpeta vacía.</p>
                    </li>
                  ) : null}
                </ul>
              ) : null}
              {mode === "external" && allowCreateFolder ? (
                <div className="l2a-downloads-actions" style={{ marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
                  <input
                    type="text"
                    placeholder="Nueva carpeta (ej. PASTOS_3)"
                    value={newFolderName}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    disabled={mkdirBusy || loading}
                    style={{ flex: "1 1 160px", minWidth: 140 }}
                  />
                  <button
                    type="button"
                    className="rgb-gallery-btn-secondary"
                    disabled={mkdirBusy || loading || !(newFolderName || "").trim()}
                    onClick={() => void createFolderHere()}
                  >
                    {mkdirBusy ? "Creando…" : "Crear carpeta"}
                  </button>
                </div>
              ) : null}
              <div className="l2a-downloads-actions">
                <button type="button" className="rgb-gallery-btn-secondary" onClick={() => onCancel?.()}>
                  Cancelar
                </button>
                <button
                  type="button"
                  className="rgb-gallery-btn-primary"
                  disabled={loading || !data}
                  onClick={selectCurrentBrowse}
                >
                  {confirmLabel}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="l2a-downloads-intro">
                Alternativa: subir una carpeta del PC a <code>local_import/{kind}/…</code>. Para
                datos grandes en el disco, usa el <strong>disco externo</strong>.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                style={{ display: "none" }}
                webkitdirectory=""
                directory=""
                multiple
                onChange={(e) => {
                  const list = Array.from(e.target.files || []).filter((f) => {
                    const n = f.name || "";
                    return n && !n.startsWith(".");
                  });
                  setLocalFiles(list);
                  setError("");
                  e.target.value = "";
                }}
              />
              <div className="l2a-downloads-actions" style={{ marginBottom: 10 }}>
                <button
                  type="button"
                  className="rgb-gallery-btn-secondary"
                  disabled={uploadBusy}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Seleccionar carpeta del computador
                </button>
              </div>
              {localFiles.length ? (
                <p className="l2a-downloads-hint">
                  Seleccionados: <strong>{localFiles.length}</strong> archivo(s) (~{localMb} MB)
                </p>
              ) : (
                <p className="l2a-downloads-empty">Aún no hay carpeta seleccionada.</p>
              )}
              {uploadBusy ? (
                <p className="l2a-downloads-status">
                  Subiendo {uploadProgress.done + 1}/{uploadProgress.total}
                  {uploadProgress.current ? `: ${uploadProgress.current}` : "…"}
                </p>
              ) : null}
              {error ? <p className="rgb-gallery-error">{error}</p> : null}
              <div className="l2a-downloads-actions">
                <button
                  type="button"
                  className="rgb-gallery-btn-secondary"
                  disabled={uploadBusy}
                  onClick={() => onCancel?.()}
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  className="rgb-gallery-btn-primary"
                  disabled={uploadBusy || localFiles.length === 0}
                  onClick={() => void uploadLocalFolderAndSelect()}
                >
                  {uploadBusy ? "Subiendo…" : "Subir y usar como origen"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
