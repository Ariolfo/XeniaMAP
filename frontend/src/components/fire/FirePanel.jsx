import { useCallback, useEffect, useMemo, useState } from "react";
import api, { setAuthToken } from "../../api";
import OrderPreviewMap from "../OrderPreviewMap";
import BrandHeader from "../BrandHeader";
import ProjectList from "../ProjectList";

function todayIso() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function groupOrdersByClient(orders) {
  const map = new Map();
  for (const row of orders || []) {
    const email = String(row.applicant_email || "").trim().toLowerCase() || "sin-email";
    if (!map.has(email)) {
      map.set(email, {
        email,
        name: row.applicant_name || email,
        orders: [],
      });
    }
    const g = map.get(email);
    g.orders.push(row);
    if (row.applicant_name && (!g.name || g.name === email)) {
      g.name = row.applicant_name;
    }
  }
  return Array.from(map.values()).sort((a, b) =>
    String(a.name || a.email).localeCompare(String(b.name || b.email), "es")
  );
}

export default function FirePanel({
  token,
  isAdmin,
  email,
  onStatusMessage,
  onSelectProject,
  onProjectsRefresh,
}) {
  const [rows, setRows] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [preStart, setPreStart] = useState("2026-07-01");
  const [preEnd, setPreEnd] = useState("2026-07-31");
  const [postStart, setPostStart] = useState("2026-08-08");
  const [postEnd, setPostEnd] = useState(todayIso());
  const [maxCloud, setMaxCloud] = useState(95);
  const [fireStart, setFireStart] = useState("2026-08-01");
  const [fireEnd, setFireEnd] = useState(todayIso());
  const [pollMsg, setPollMsg] = useState("");
  /** Admin: null = lista de clientes; string = email del cliente seleccionado */
  const [selectedClientEmail, setSelectedClientEmail] = useState(null);
  /** Cliente: proyectos Fire (mismo patrón que Agro ProjectList) */
  const [fireProjects, setFireProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);

  const clientGroups = useMemo(() => groupOrdersByClient(rows), [rows]);
  const selectedClient = useMemo(() => {
    if (!selectedClientEmail) return null;
    return (
      clientGroups.find((g) => g.email === String(selectedClientEmail).trim().toLowerCase()) || null
    );
  }, [clientGroups, selectedClientEmail]);
  const visibleOrders = useMemo(() => {
    if (!isAdmin) return rows;
    if (!selectedClient) return [];
    return selectedClient.orders;
  }, [isAdmin, rows, selectedClient]);

  const orderByProjectId = useMemo(() => {
    const m = new Map();
    for (const o of rows || []) {
      if (o.project_id != null) m.set(Number(o.project_id), o);
    }
    return m;
  }, [rows]);

  const clientProjectList = useMemo(() => {
    // Preferir /projects?module=fire; enriquecer status con fire-order si existe.
    if (fireProjects.length) {
      return fireProjects.map((p) => {
        const o = orderByProjectId.get(Number(p.id));
        return {
          ...p,
          status: o?.status || p.status,
          fire_order_id: o?.id ?? null,
          request_name: o?.request_name || p.name,
        };
      });
    }
    // Fallback: construir desde fire-orders
    return (rows || [])
      .filter((o) => o.project_id)
      .map((o) => ({
        id: o.project_id,
        name: o.project_name || `Fire — ${o.request_name}`,
        status: o.status,
        fire_order_id: o.id,
        request_name: o.request_name,
      }));
  }, [fireProjects, rows, orderByProjectId]);

  const loadList = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      setAuthToken(token);
      const res = await api.get("/fire-orders");
      const list = Array.isArray(res.data) ? res.data : [];
      setRows(list);
      if (!isAdmin) {
        try {
          const pr = await api.get("/projects", { params: { module: "fire" } });
          setFireProjects(Array.isArray(pr.data) ? pr.data : []);
        } catch (_) {
          setFireProjects([]);
        }
        onStatusMessage?.(
          list.length
            ? `Fire: ${list.length} proyecto(s) / solicitud(es) en su cuenta.`
            : "Fire: no hay proyectos asignados a su cuenta."
        );
        onProjectsRefresh?.();
      }
      return list;
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Error al cargar solicitudes Fire");
      return [];
    } finally {
      setLoading(false);
    }
  }, [token, isAdmin, onStatusMessage, onProjectsRefresh]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      const list = await loadList();
      if (cancelled || isAdmin || !list?.length) return;
      const first = list.find((o) => o.project_id) || list[0];
      if (!first) return;
      try {
        setAuthToken(token);
        const res = await api.get(`/fire-orders/${first.id}`);
        if (cancelled) return;
        const d = res.data;
        setDetail(d);
        if (d?.project_id) {
          setSelectedProjectId(d.project_id);
          onSelectProject?.(d.project_id);
        }
      } catch (_) {
        /* ignore auto-open errors */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, isAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

  function backToClients() {
    setSelectedClientEmail(null);
    setDetail(null);
    setPollMsg("");
    setBusy("");
  }

  function openClient(group) {
    setSelectedClientEmail(group.email);
    setDetail(null);
    setPollMsg("");
    setBusy("");
    onStatusMessage?.(
      `Fire · cliente ${group.name || group.email}: ${group.orders.length} solicitud(es).`
    );
  }

  async function openDetail(id) {
    setError("");
    setPollMsg("");
    try {
      setAuthToken(token);
      const res = await api.get(`/fire-orders/${id}`);
      const d = res.data;
      setDetail(d);
      setPreStart(d.pre_start || "2026-07-01");
      setPreEnd(d.pre_end || "2026-07-31");
      setPostStart(d.post_start || "2026-08-08");
      setPostEnd(d.post_end || todayIso());
      setMaxCloud(Number(d.max_cloud_cover ?? 95));
      setFireStart(d.pre_end || "2026-08-01");
      setFireEnd(d.post_end || todayIso());
      if (d?.project_id) {
        setSelectedProjectId(d.project_id);
        if (!isAdmin && onSelectProject) onSelectProject(d.project_id);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Error al cargar detalle");
    }
  }

  async function openClientProject(projectId) {
    setSelectedProjectId(projectId);
    onSelectProject?.(projectId);
    const order = orderByProjectId.get(Number(projectId));
    if (order?.id) {
      await openDetail(order.id);
      return;
    }
    // Sin fire-order vinculado: solo capas del proyecto
    setDetail(null);
    setError("");
  }

  async function pollPipeline(orderId, doneStatuses) {
    try {
      setAuthToken(token);
      const res = await api.get(`/fire-orders/${orderId}/pipeline-status`);
      const d = res.data?.order;
      if (d) {
        setDetail(d);
        setRows((prev) => prev.map((r) => (r.id === d.id ? { ...r, status: d.status } : r)));
        const msg = d.firms_message || d.process_message || d.download_message || "";
        setPollMsg(msg);
      }
      if (doneStatuses.includes(String(d?.status || ""))) {
        setBusy("");
        onStatusMessage?.(`Fire #${orderId}: ${d.status}`);
        return true;
      }
      if (d?.status === "error") {
        setBusy("");
        setError(d.firms_message || d.process_message || d.download_message || "Error en pipeline");
        return true;
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Error consultando estado");
      setBusy("");
      return true;
    }
    return false;
  }

  function startPolling(orderId, doneStatuses) {
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      const done = await pollPipeline(orderId, doneStatuses);
      if (done || tries > 300) {
        clearInterval(timer);
        if (tries > 300) setBusy("");
      }
    }, 4000);
  }

  async function startDownload() {
    if (!detail || !isAdmin) return;
    setBusy("download");
    setError("");
    setPollMsg("Encolando descarga...");
    try {
      setAuthToken(token);
      const res = await api.post(`/fire-orders/${detail.id}/download-s2`, {
        pre_start: preStart,
        pre_end: preEnd,
        post_start: postStart,
        post_end: postEnd,
        max_cloud_cover: Number(maxCloud),
      });
      const d = res.data?.order;
      if (d) {
        setDetail(d);
        setRows((prev) => prev.map((r) => (r.id === d.id ? { ...r, status: d.status } : r)));
      }
      onStatusMessage?.(`Fire #${detail.id}: descarga S2 iniciada`);
      startPolling(detail.id, ["descargado"]);
    } catch (e) {
      setBusy("");
      setError(e?.response?.data?.detail || e?.message || "No se pudo iniciar la descarga");
    }
  }

  async function startProcess() {
    if (!detail || !isAdmin) return;
    setBusy("process");
    setError("");
    setPollMsg("Encolando dNBR...");
    try {
      setAuthToken(token);
      const res = await api.post(`/fire-orders/${detail.id}/process-dnbr`);
      const d = res.data?.order;
      if (d) {
        setDetail(d);
        setRows((prev) => prev.map((r) => (r.id === d.id ? { ...r, status: d.status } : r)));
      }
      onStatusMessage?.(`Fire #${detail.id}: dNBR iniciado`);
      startPolling(detail.id, ["procesado"]);
    } catch (e) {
      setBusy("");
      setError(e?.response?.data?.detail || e?.message || "No se pudo iniciar dNBR");
    }
  }

  async function startFirms() {
    if (!detail || !isAdmin) return;
    setBusy("firms");
    setError("");
    setPollMsg("Encolando FIRMS...");
    try {
      setAuthToken(token);
      const res = await api.post(`/fire-orders/${detail.id}/validate-firms`, {
        fire_start: fireStart,
        fire_end: fireEnd,
      });
      const d = res.data?.order;
      if (d) {
        setDetail(d);
        setRows((prev) => prev.map((r) => (r.id === d.id ? { ...r, status: d.status } : r)));
      }
      onStatusMessage?.(`Fire #${detail.id}: FIRMS iniciado`);
      startPolling(detail.id, ["validado"]);
    } catch (e) {
      setBusy("");
      setError(e?.response?.data?.detail || e?.message || "No se pudo iniciar FIRMS");
    }
  }

  if (!token) {
    return (
      <aside className="panel domain-placeholder fire-panel">
        <BrandHeader email={email} />
        <h2 className="domain-placeholder-title">Fire</h2>
        <p className="domain-placeholder-text">
          Inicie sesión (menú <strong>Ingreso</strong>) para ver sus polígonos de incendios.
        </p>
      </aside>
    );
  }

  const canProcess =
    !!detail?.data_root && ["descargado", "procesado", "validado", "error"].includes(detail?.status);
  const canFirms =
    !!detail?.results_root || detail?.status === "procesado" || detail?.status === "validado";

  const showAdminClientPicker = isAdmin && !selectedClient;
  const showOrderList = isAdmin && !!selectedClient;

  return (
    <aside className="panel fire-panel">
      <BrandHeader email={email} />
      <div className="fire-panel-head">
        <div>
          <h2 className="fire-panel-title">Fire — severidad de incendios</h2>
          <p className="fire-panel-sub">
            {isAdmin
              ? showAdminClientPicker
                ? "Seleccione un cliente para ver y procesar sus solicitudes municipales."
                : `Cliente: ${selectedClient?.name || selectedClient?.email || "—"}. Pipeline: 01 S2 → 02 dNBR → 03 FIRMS.`
              : "Sus proyectos Fire. Seleccione uno para ver el polígono y el estado del análisis."}
          </p>
        </div>
        <button type="button" className="fire-btn" onClick={loadList} disabled={loading}>
          {loading ? "Cargando…" : "Actualizar"}
        </button>
      </div>

      {error ? <div className="warn-msg">{String(error)}</div> : null}
      {pollMsg && isAdmin ? <div className="status-msg">{pollMsg}</div> : null}

      {!isAdmin ? (
        <div className="fire-split">
          <div className="fire-list fire-client-projects">
            <ProjectList
              projects={clientProjectList}
              projectId={selectedProjectId}
              projectName=""
              setProjectName={() => {}}
              loading={loading}
              onSelectProject={openClientProject}
              onCreateProject={async () => false}
              onUpdateProject={async () => false}
              onDeleteProject={async () => false}
              onLogout={() => {}}
              email={email}
              readOnly
              allowDelete={false}
              title="Mis proyectos Fire"
              hideSessionHeader
            />
          </div>
          <div className="fire-detail">
            {!detail ? (
              <div className="status-msg">
                {clientProjectList.length
                  ? "Seleccione un proyecto Fire para ver el polígono y el estado."
                  : "Aún no tiene proyectos Fire asignados."}
              </div>
            ) : (
              <>
                <h3 className="fire-detail-title">{detail.request_name}</h3>
                <div className="fire-meta-grid">
                  <div>
                    <strong>Proyecto</strong>
                    <div>{detail.project_name || `Fire — ${detail.request_name}`}</div>
                    <div className="muted">{detail.applicant_email}</div>
                  </div>
                  <div>
                    <strong>Estado</strong>
                    <div>{detail.status}</div>
                    <div className="muted">
                      PRE {detail.pre_start} → {detail.pre_end}
                      <br />
                      POST {detail.post_start} → {detail.post_end}
                    </div>
                  </div>
                </div>
                <div className="fire-map-wrap">
                  <OrderPreviewMap geojson={detail.geometry} />
                </div>
                <div className="fire-download-box">
                  <p className="fire-hint">
                    El polígono también queda en Capas del mapa al seleccionar el proyecto. Los
                    resultados del pipeline (dNBR / FIRMS) aparecerán cuando el administrador los
                    complete.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      ) : (
      <div className="fire-split">
        <div className="fire-list">
          {showAdminClientPicker ? (
            <>
              <div className="fire-list-title">Clientes</div>
              {loading ? <div className="status-msg">Cargando…</div> : null}
              {!loading && clientGroups.length === 0 ? (
                <div className="status-msg">Sin clientes con solicitudes Fire.</div>
              ) : null}
              <ul className="fire-order-list">
                {clientGroups.map((g) => {
                  const statuses = g.orders.reduce((acc, o) => {
                    const s = o.status || "pendiente";
                    acc[s] = (acc[s] || 0) + 1;
                    return acc;
                  }, {});
                  const statusSummary = Object.entries(statuses)
                    .map(([s, n]) => `${n} ${s}`)
                    .join(" · ");
                  return (
                    <li key={g.email}>
                      <button
                        type="button"
                        className="fire-order-item fire-client-item"
                        onClick={() => openClient(g)}
                      >
                        <span className="fire-order-name">{g.name || g.email}</span>
                        <span className="fire-order-meta">{g.email}</span>
                        <span className="fire-order-meta">
                          {g.orders.length} solicitud(es)
                          {statusSummary ? ` · ${statusSummary}` : ""}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          ) : null}

          {showOrderList ? (
            <>
              <div className="fire-list-title-row">
                <button type="button" className="fire-btn fire-btn-back" onClick={backToClients}>
                  ← Clientes
                </button>
                <div className="fire-list-title">
                  Solicitudes · {selectedClient?.name || selectedClient?.email || ""}
                </div>
              </div>
              {loading ? <div className="status-msg">Cargando…</div> : null}
              {!loading && visibleOrders.length === 0 ? (
                <div className="status-msg">Este cliente no tiene solicitudes Fire.</div>
              ) : null}
              <ul className="fire-order-list">
                {visibleOrders.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className={`fire-order-item${detail?.id === r.id ? " active" : ""}`}
                      onClick={() => openDetail(r.id)}
                    >
                      <span className="fire-order-name">{r.request_name}</span>
                      <span className="fire-order-meta">
                        #{r.id} · {r.status}
                        {r.project_name ? ` · ${r.project_name}` : ""}
                        {r.department ? ` · ${r.department}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>

        <div className="fire-detail">
          {showAdminClientPicker ? (
            <div className="status-msg">
              Elija un cliente a la izquierda para ver sus municipios y ejecutar el pipeline.
            </div>
          ) : !detail ? (
            <div className="status-msg">Seleccione una solicitud para ver el polígono.</div>
          ) : (
            <>
              <h3 className="fire-detail-title">{detail.request_name}</h3>
              <div className="fire-meta-grid">
                <div>
                  <strong>Solicitante</strong>
                  <div>{detail.applicant_name}</div>
                  <div className="muted">{detail.applicant_email}</div>
                </div>
                <div>
                  <strong>Estado</strong>
                  <div>{detail.status}</div>
                  <div className="muted">
                    {detail.project_name ||
                      detail.results_root ||
                      detail.data_root ||
                      "Sin resultados aún"}
                  </div>
                </div>
              </div>

              <div className="fire-map-wrap">
                <OrderPreviewMap geojson={detail.geometry} />
              </div>

              <div className="fire-download-box">
                <h4>1. Descargar Sentinel-2 L2A</h4>
                <div className="fire-dates-grid">
                  <label>
                    PRE inicio
                    <input type="date" value={preStart} onChange={(e) => setPreStart(e.target.value)} />
                  </label>
                  <label>
                    PRE fin
                    <input type="date" value={preEnd} onChange={(e) => setPreEnd(e.target.value)} />
                  </label>
                  <label>
                    POST inicio
                    <input type="date" value={postStart} onChange={(e) => setPostStart(e.target.value)} />
                  </label>
                  <label>
                    POST fin
                    <input type="date" value={postEnd} onChange={(e) => setPostEnd(e.target.value)} />
                  </label>
                  <label>
                    MAX_CLOUD_COVER (%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={maxCloud}
                      onChange={(e) => setMaxCloud(e.target.value)}
                    />
                  </label>
                </div>
                <button
                  type="button"
                  className="fire-btn fire-btn-primary"
                  disabled={!!busy}
                  onClick={startDownload}
                >
                  {busy === "download" ? "Descargando…" : "Descargar S2"}
                </button>
                {detail.download_message ? <pre className="fire-log">{detail.download_message}</pre> : null}
              </div>

              <div className="fire-download-box" style={{ marginTop: 10 }}>
                <h4>2. Procesar dNBR / severidad</h4>
                <p className="fire-hint">
                  Metodología script 02: MNDWI agua PRE, mediana NBR, dNBR, severidad, candidatos ≥0.15 /
                  ≥2 ha, RGB COG.
                </p>
                <button
                  type="button"
                  className="fire-btn fire-btn-primary"
                  disabled={!!busy || !canProcess}
                  onClick={startProcess}
                  title={!canProcess ? "Requiere descarga S2 completada" : "Ejecutar dNBR"}
                >
                  {busy === "process" ? "Procesando…" : "Procesar dNBR"}
                </button>
                {detail.process_message ? <pre className="fire-log">{detail.process_message}</pre> : null}
              </div>

              <div className="fire-download-box" style={{ marginTop: 10 }}>
                <h4>3. Validar con FIRMS / VIIRS</h4>
                <p className="fire-hint">
                  Metodología script 03: hotspots VIIRS como evidencia positiva (no veto). Requiere{" "}
                  <code>FIRMS_MAP_KEY</code>.
                </p>
                <div className="fire-dates-grid">
                  <label>
                    FIRMS inicio
                    <input type="date" value={fireStart} onChange={(e) => setFireStart(e.target.value)} />
                  </label>
                  <label>
                    FIRMS fin
                    <input type="date" value={fireEnd} onChange={(e) => setFireEnd(e.target.value)} />
                  </label>
                </div>
                <button
                  type="button"
                  className="fire-btn fire-btn-primary"
                  disabled={!!busy || !canFirms}
                  onClick={startFirms}
                  title={!canFirms ? "Requiere dNBR procesado" : "Ejecutar FIRMS"}
                >
                  {busy === "firms" ? "Validando…" : "Validar FIRMS"}
                </button>
                {detail.firms_message ? <pre className="fire-log">{detail.firms_message}</pre> : null}
              </div>
            </>
          )}
        </div>
      </div>
      )}
    </aside>
  );
}
