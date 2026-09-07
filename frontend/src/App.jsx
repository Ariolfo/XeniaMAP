import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api, { setAuthToken } from "./api";
import { useAuthSession } from "./features/auth";
import {
  useProjectWorkspace,
  usePreprocessJobs,
  INDEX_CATALOG,
  INDEX_CATALOG_PS,
} from "./features/agro";
import { useFireMap, FirePanel } from "./features/fire";
import {
  useMapLayers,
  usePaintLayerOnMap,
  MapView,
  MapErrorBoundary,
  MapLayersPanel,
  bboxFromGeojson,
  bboxFromBoundsWgs84,
} from "./shared/map";
import { kmlToGeojson, kmzToGeojson } from "./utils/geo";
import Sidebar from "./components/Sidebar";
import DomainMenu, { DOMAIN_OPTIONS } from "./components/DomainMenu";
import IngresoPanel from "./components/IngresoPanel";
import BrandHeader from "./components/BrandHeader";
import AdvancedDashboard from "./components/dashboard/AdvancedDashboard";
import SmartClusterModal from "./components/dashboard/SmartClusterModal";
import SmartSoilModal from "./components/dashboard/SmartSoilModal";
import MarkdownReportsModal from "./components/dashboard/MarkdownReportsModal";
import UserManagementModal from "./components/UserManagementModal";
import StudyRequestModal from "./components/StudyRequestModal";
import AdminStudyOrdersModal from "./components/AdminStudyOrdersModal";
import ShareProjectModal from "./components/ShareProjectModal";
import ClientVisualizationModal from "./components/ClientVisualizationModal";

const INDEX_IDS_S2 = new Set(
  INDEX_CATALOG.filter((o) => o.id !== "TODOS").map((o) => o.id)
);
const INDEX_IDS_PS = new Set(
  INDEX_CATALOG_PS.filter((o) => o.id !== "TODOS").map((o) => o.id)
);

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const mapRef = useRef(null);
  const fetchProjectsRef = useRef(async () => []);
  const selectProjectRef = useRef(async () => {});
  const fireFocusSetterRef = useRef(() => {});

  const [projectId, setProjectId] = useState("");
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [baseStyle, setBaseStyle] = useState("vectorial");
  const [projectName, setProjectName] = useState("");
  const [loteFile, setLoteFile] = useState(null);
  const [rasterFile, setRasterFile] = useState(null);
  const [downloadSource, setDownloadSource] = useState("sentinel-1");
  const [selectedIndices, setSelectedIndices] = useState([]);
  const [stackMode, setStackMode] = useState("visual-rgb");
  const [targetRasterId, setTargetRasterId] = useState("");
  const [sidebarTab, setSidebarTab] = useState("admin");
  const [activeDomain, setActiveDomain] = useState("ingreso");
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [smartClusterOpen, setSmartClusterOpen] = useState(false);
  const [smartSoilOpen, setSmartSoilOpen] = useState(false);
  const [markdownReportsOpen, setMarkdownReportsOpen] = useState(false);
  const [userMgmtOpen, setUserMgmtOpen] = useState(false);
  const [studyRequestOpen, setStudyRequestOpen] = useState(false);
  const [studyOrdersOpen, setStudyOrdersOpen] = useState(false);
  const [shareProjectOpen, setShareProjectOpen] = useState(false);
  const [clientVizModalOpen, setClientVizModalOpen] = useState(false);
  const [smartFocus] = useState("cluster");
  const [studyDraw, setStudyDraw] = useState(null);

  const {
    mapLayers,
    mapLayersRef,
    setPendingDeletes,
    setDirty,
    addMapLayer,
    toggleLayerVisibility,
    setLayerVisibility,
    patchMapLayer,
    clearAllMapLayers,
  } = useMapLayers(mapRef);

  const paintLayerOnMap = usePaintLayerOnMap(mapRef);

  const tokenRef = useRef("");
  const isAdminRef = useRef(false);

  const requireAdminAction = useCallback(() => {
    if (!tokenRef.current) {
      setMessage("Debes iniciar sesion.");
      return false;
    }
    if (!isAdminRef.current) {
      setMessage("Acceso restringido: esta accion requiere rol admin.");
      return false;
    }
    return true;
  }, []);

  const { fetchProjects, selectProject, zoomToLayer, updateProjectName, deleteProject } =
    useProjectWorkspace({
      mapRef,
      getToken: () => tokenRef.current,
      projects,
      setProjects,
      projectId,
      setProjectId,
      setTargetRasterId,
      mapLayersRef,
      addMapLayer,
      clearAllMapLayers,
      setPendingDeletes,
      setDirty,
      paintLayerOnMap,
      setMessage,
      setLoading,
      requireAdminAction,
    });

  fetchProjectsRef.current = fetchProjects;
  selectProjectRef.current = selectProject;

  const auth = useAuthSession({
    navigate,
    location,
    fetchProjects: (...args) => fetchProjectsRef.current(...args),
    selectProject: (...args) => selectProjectRef.current(...args),
    clearAllMapLayers,
    setProjectId,
    setProjects,
    setTargetRasterId,
    setFireFocusOrderId: (v) => fireFocusSetterRef.current(v),
    setActiveDomain,
    setSidebarTab,
    setUserMgmtOpen,
    setStudyRequestOpen,
    setStudyOrdersOpen,
    setStudyDraw,
    setMessage,
    setLoading,
  });

  const {
    token,
    email,
    setEmail,
    password,
    setPassword,
    authStep,
    otpDebug,
    otpHint,
    normalizedUserRole,
    isAdmin,
    isCliente,
    loginWithCredentials,
    resetEmailAuthStep,
    continueEmailFlow,
    verifyOtpRegister,
    logoutSession,
  } = auth;

  tokenRef.current = token;
  isAdminRef.current = isAdmin;

  const {
    fireFocusOrderId,
    setFireFocusOrderId,
    toggleFireDnbrGroup,
    toggleFireLayerVisibility,
    clearFireMap,
    loadFireOrderOnMap,
  } = useFireMap({
    mapRef,
    token,
    mapLayersRef,
    addMapLayer,
    toggleLayerVisibility,
    setLayerVisibility,
    patchMapLayer,
    clearAllMapLayers,
    setPendingDeletes,
    setDirty,
    paintLayerOnMap,
    setProjectId,
    setMessage,
    setLoading,
  });

  fireFocusSetterRef.current = setFireFocusOrderId;

  const {
    s2Download,
    s1Download,
    recorteTaskId,
    indexStacksTaskId,
    psExtractTaskId,
    s1SarStacksTaskId,
    visualIndexGalleryKick,
    visualIndexGalleryKickPs,
    recorteLayerId,
    setRecorteLayerId,
    preproGalleryKick,
    setPreproGalleryKick,
    preproClusterVizKick,
    setPreproClusterVizKick,
    preproClusterVizKickPs,
    clusterElbowLoading,
    clusterGmmLoading,
    clusterElbowResults,
    clusterGmmResults,
    clusterElbowResultsPs,
    clusterGmmResultsPs,
    clusterElbowResultsS1,
    clusterGmmResultsS1,
    preprocessDownload,
    runS2L2aRecortes,
    runS1GrdRecortes,
    runPsPlanetExtract,
    runPsRecorteClip,
    runS2IndexStacks,
    runS1SarIndexStacks,
    runClusterElbow,
    runClusterGmm,
    loadPersistedClusterGmm,
  } = usePreprocessJobs({
    token,
    projectId,
    downloadSource,
    selectedIndices,
    requireAdminAction,
    selectProject,
    addMapLayer,
    setTargetRasterId,
    setStackMode,
    setSidebarTab,
    setMessage,
    setLoading,
  });


  const selectedProject = projects.find((p) => Number(p.id) === Number(projectId));
  const projectStudyDateStart = selectedProject?.study_date_start?.slice(0, 10) || "";
  const projectStudyDateEnd = selectedProject?.study_date_end?.slice(0, 10) || "";

  const finalizeStudyPolygon = useCallback(() => {
    setStudyDraw((d) => {
      if (!d?.active || d.mode !== "polygon") return d;
      return { ...d, finalizePolygonKey: (d.finalizePolygonKey || 0) + 1 };
    });
  }, []);

  useEffect(() => {
    setDashboardOpen(false);
    setSmartClusterOpen(false);
    setSmartSoilOpen(false);
    setUserMgmtOpen(false);
    setStudyRequestOpen(false);
    setStudyOrdersOpen(false);
    setClientVizModalOpen(false);
    setStudyDraw(null);
  }, [projectId]);

  useEffect(() => {
    if (sidebarTab === "prepro") {
      setSelectedIndices((prev) =>
        prev.filter((id) => id === "TODOS" || INDEX_IDS_S2.has(id))
      );
    } else if (sidebarTab === "ps") {
      setSelectedIndices((prev) =>
        prev.filter((id) => id === "TODOS" || INDEX_IDS_PS.has(id))
      );
    }
  }, [sidebarTab]);

  useEffect(() => {
    if (stackMode === "visual-s1-vh" || stackMode === "visual-s1-index") {
      setStackMode("visual-s1-vv");
    }
  }, [stackMode]);

  async function createProject() {
    if (!requireAdminAction()) return;
    const finalName = projectName.trim();
    if (!finalName) {
      setMessage("Error: ingresa un nombre para el proyecto.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const res = await api.post("/projects", { name: finalName });
      await fetchProjects(token);
      setProjectName("");
      await selectProject(res.data.id, token);
      setMessage(`Proyecto "${finalName}" creado y seleccionado.`);
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al crear proyecto";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  async function uploadLote() {
    if (!requireAdminAction()) return null;
    if (!token || !projectId || !loteFile) {
      setMessage("Error: debes iniciar sesion, crear proyecto y seleccionar archivo de lote.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const form = new FormData();
      form.append("file", loteFile);
      const res = await api.post(`/upload-shapefile?project_id=${projectId}`, form);
      const layerId = res.data.layer_id;
      const fname = loteFile.name.toLowerCase();
      let geojson = null;
      try {
        if (fname.endsWith(".geojson") || fname.endsWith(".json")) {
          const text = await loteFile.text();
          geojson = JSON.parse(text);
        } else if (fname.endsWith(".kml")) {
          const text = await loteFile.text();
          geojson = kmlToGeojson(text);
        } else if (fname.endsWith(".kmz")) {
          geojson = await kmzToGeojson(loteFile);
        }
      } catch (_) {}
      if (!geojson) {
        geojson = await (async () => {
          try {
            setAuthToken(token);
            const r = await api.get(`/layers/${projectId}/${layerId}/geojson`);
            return r.data;
          } catch (_) {
            return null;
          }
        })();
      }
      const lid = addMapLayer(loteFile.name, "vector", geojson, layerId);
      if (geojson) {
        paintLayerOnMap(lid, geojson);
        const bbox = bboxFromGeojson(geojson);
        if (bbox && mapRef.current) mapRef.current.fitBounds(bbox, { padding: 60, maxZoom: 17 });
      }
      setLoteFile(null);
      setMessage(`Lote cargado correctamente. Layer ID: ${layerId}`);
      return layerId;
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al subir lote";
      setMessage(`Error: ${detail}`);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function uploadRaster() {
    if (!requireAdminAction()) return;
    if (!token || !projectId || !rasterFile) {
      setMessage("Error: debes iniciar sesion, crear proyecto y seleccionar raster.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const form = new FormData();
      form.append("file", rasterFile);
      const res = await api.post(`/upload-raster?project_id=${projectId}`, form);
      const layers = res.data.layers;
      if (Array.isArray(layers) && layers.length > 0) {
        layers.forEach((L) => {
          if (mapLayersRef.current.some((x) => x.serverId === L.id)) return;
          const rbbox = bboxFromBoundsWgs84(L.metadata?.bounds_wgs84);
          addMapLayer(L.name, "raster", null, L.id, rbbox ? { bbox: rbbox } : {});
        });
        const nir = layers.find((x) => x.composite === "nir");
        const pick = nir || layers[layers.length - 1];
        setTargetRasterId(String(pick.id));
        setMessage(
          `Sentinel-2: 2 capas (${layers.map((x) => x.name).join(", ")}). TIF 4 bandas B04-B03-B02-B08 guardado en el proyecto; vistas RGB y NIR derivadas de ese archivo. Objetivo: NIR.`
        );
      } else {
        setTargetRasterId(String(res.data.raster_layer_id));
        const meta = res.data.metadata || {};
        const rbbox = bboxFromBoundsWgs84(meta.bounds_wgs84);
        addMapLayer(rasterFile.name, "raster", null, res.data.raster_layer_id, rbbox ? { bbox: rbbox } : {});
        setMessage(
          rbbox
            ? `Raster cargado correctamente (ID ${res.data.raster_layer_id}).`
            : `Raster registrado (ID ${res.data.raster_layer_id}). Sin CRS en el archivo: no se podrá acercar ni superponer hasta georreferenciar.`
        );
      }
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al subir raster";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  async function runAI() {
    if (!requireAdminAction()) return;
    if (!projectId || !targetRasterId) {
      setMessage("Error: define un raster objetivo para ejecutar IA.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      await api.post("/ai/predict", {
        project_id: Number(projectId),
        raster_layer_id: Number(targetRasterId),
        model_type: "ndvi-segmentation",
      });
      await api.get(`/ai/results/${projectId}`);
      setMessage("Inferencia ejecutada.");
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al ejecutar IA";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  const dashboardProjectStatus = useMemo(() => {
    const p = projects.find((x) => Number(x.id) === Number(projectId));
    return p?.status;
  }, [projects, projectId]);
  const dashboardProjectName = useMemo(() => {
    const p = projects.find((x) => Number(x.id) === Number(projectId));
    return p?.name || "";
  }, [projects, projectId]);

  function selectDomain(domainId) {
    const domain = DOMAIN_OPTIONS.find((d) => d.id === domainId);
    if (!domain) return;
    if (domainId !== activeDomain && (activeDomain === "fire" || domainId === "fire")) {
      clearAllMapLayers();
      setFireFocusOrderId(null);
    }
    setActiveDomain(domainId);
    if (!domain.ready) {
      setMessage(
        `Módulo ${domain.label} (${domain.title}) en preparación. Por ahora el flujo disponible es Agro.`
      );
    } else if (domainId === "ingreso") {
      setMessage("Ingreso: inicie sesión o gestione su sesión activa.");
    } else if (domainId === "fire") {
      setMessage("Módulo Fire: severidad de incendios (solicitudes + descarga S2).");
      if (token && isCliente) {
        fetchProjects(token);
        setSidebarTab("dashboard");
      }
    } else if (domainId === "agro" && token && isCliente) {
      fetchProjects(token);
      setSidebarTab("dashboard");
    } else if (domainId === "agro" && token && isAdmin) {
      fetchProjects(token);
      setSidebarTab("admin");
      setMessage("Agro: use el submenú (Gestión, S2, PS…) bajo Agro.");
    } else if (domainId === "agro" && !token) {
      setMessage("Use el módulo Ingreso para iniciar sesión. Luego entre a Agro.");
    }
  }

  function selectAgroSub(item) {
    if (!item) return;
    if (item.action === "dashboard") {
      if (token) fetchProjects(token);
      if (!projectId) {
        setMessage("Seleccione un proyecto publicado para abrir el dashboard de resultados.");
        return;
      }
      setDashboardOpen(true);
      return;
    }
    if (item.action === "informe") {
      if (!projectId) {
        setMessage("Seleccione un proyecto para editar el informe narrativo.");
        return;
      }
      navigate(`/admin/informe/${projectId}`);
      return;
    }
    setActiveDomain("agro");
    // Capas: segundo clic cierra y vuelve a Gestión
    if (item.id === "capas" && sidebarTab === "capas") {
      setSidebarTab("admin");
      return;
    }
    setSidebarTab(item.id);
    if (
      (item.id === "prepro" || item.id === "ps") &&
      String(stackMode || "").startsWith("visual-s1")
    ) {
      setStackMode("visual-rgb");
    }
  }

  return (
    <div
      className={`layout layout-domain-${activeDomain} layout--map-layers${
        token && isAdmin && activeDomain === "agro" ? " layout--agro-admin" : ""
      }`}
    >
      <DomainMenu
        activeDomain={activeDomain}
        onSelectDomain={selectDomain}
        isAdmin={!!token && isAdmin}
        agroSubTab={sidebarTab}
        onSelectAgroSub={selectAgroSub}
        agroActionsDisabled={loading || !projectId}
      />
      {activeDomain === "ingreso" ? (
        <IngresoPanel
          token={token}
          userRole={normalizedUserRole}
          email={email}
          setEmail={setEmail}
          password={password}
          setPassword={setPassword}
          loading={loading}
          authStep={authStep}
          otpDebug={otpDebug}
          otpHint={otpHint}
          onContinueEmail={continueEmailFlow}
          onVerifyOtp={verifyOtpRegister}
          onResetEmailStep={resetEmailAuthStep}
          onLogin={loginWithCredentials}
          onLogout={logoutSession}
        />
      ) : activeDomain === "agro" ? (
      <Sidebar
        activeTab={sidebarTab}
        setActiveTab={setSidebarTab}
        recorteLayerId={recorteLayerId}
        setRecorteLayerId={setRecorteLayerId}
        preproGalleryKick={preproGalleryKick}
        preproClusterVizKick={preproClusterVizKick}
        preproClusterVizKickPs={preproClusterVizKickPs}
        onOpenPreproGallery={() => {
          setSidebarTab("prepro");
          setPreproGalleryKick((k) => k + 1);
        }}
        onOpenPreproClusterViz={() => {
          setSidebarTab("prepro");
          setPreproClusterVizKick((k) => k + 1);
        }}
        token={token}
        userRole={normalizedUserRole}
        email={email}
        loading={loading}
        message={message}
        projects={projects}
        projectId={projectId}
        projectName={projectName}
        projectStudyDateStart={projectStudyDateStart}
        projectStudyDateEnd={projectStudyDateEnd}
        setProjectName={setProjectName}
        mapLayers={mapLayers}
        targetRasterId={targetRasterId}
        setTargetRasterId={setTargetRasterId}
        loteFile={loteFile}
        setLoteFile={setLoteFile}
        rasterFile={rasterFile}
        setRasterFile={setRasterFile}
        downloadSource={downloadSource}
        setDownloadSource={setDownloadSource}
        selectedIndices={selectedIndices}
        setSelectedIndices={setSelectedIndices}
        stackMode={stackMode}
        setStackMode={setStackMode}
        onLogout={logoutSession}
        onSelectProject={(id) => selectProject(id, token)}
        onCreateProject={createProject}
        onUpdateProject={updateProjectName}
        onDeleteProject={deleteProject}
        onToggleVisibility={toggleLayerVisibility}
        onZoomToLayer={zoomToLayer}
        onHideLayer={(lid) => setLayerVisibility(lid, false)}
        onOpenClientDashboard={() => {
          if (token) fetchProjects(token);
          if (!projectId) {
            setMessage("Seleccione un proyecto publicado para abrir el dashboard de resultados.");
            return;
          }
          setDashboardOpen(true);
        }}
        onOpenClientLanding={() => {
          if (!projectId) {
            setMessage("Seleccione un proyecto en la lista para abrir el informe narrativo.");
            return;
          }
          navigate(`/cliente/${projectId}`);
        }}
        onOpenClientVisualization={() => setClientVizModalOpen(true)}
        onOpenSmartCluster={() => {
          if (!isAdmin) {
            setMessage("Acceso restringido: Smart solo para admin.");
            return;
          }
          setSmartClusterOpen(true);
        }}
        onOpenSmartSoil={() => {
          if (!isAdmin) {
            setMessage("Acceso restringido: Smart solo para admin.");
            return;
          }
          setSmartSoilOpen(true);
        }}
        onOpenMarkdownReports={() => {
          if (!isAdmin) {
            setMessage("Acceso restringido: Smart solo para admin.");
            return;
          }
          setMarkdownReportsOpen(true);
        }}
        onOpenUserManagement={() => {
          if (!isAdmin) {
            setMessage("Acceso restringido: Gestion de usuarios solo para admin.");
            return;
          }
          setUserMgmtOpen(true);
        }}
        onOpenStudyRequest={() => {
          if (!token) {
            setMessage("Debe iniciar sesión.");
            return;
          }
          setStudyRequestOpen(true);
        }}
        onOpenStudyOrders={() => {
          if (!isAdmin) {
            setMessage("Solo administradores.");
            return;
          }
          setStudyOrdersOpen(true);
        }}
        onOpenShareProject={() => {
          if (!isAdmin) {
            setMessage("Solo administradores.");
            return;
          }
          if (!projectId) {
            setMessage("Seleccione un proyecto en la lista antes de compartir.");
            return;
          }
          setShareProjectOpen(true);
        }}
        onUploadLote={uploadLote}
        onUploadRaster={uploadRaster}
        onRunAI={runAI}
        onDownload={preprocessDownload}
        recortePipelineBusy={!!recorteTaskId}
        indexStacksBusy={!!indexStacksTaskId || !!s1SarStacksTaskId || !!psExtractTaskId}
        visualIndexGalleryKick={visualIndexGalleryKick}
        visualIndexGalleryKickPs={visualIndexGalleryKickPs}
        onS2L2aRecortes={(layerId, names, sub) => runS2L2aRecortes(layerId, names, sub, "s2")}
        onPsL2aRecortes={(layerId, names, sub) => runS2L2aRecortes(layerId, names, sub, "ps")}
        onS1GrdRecortes={runS1GrdRecortes}
        onS1SarIndexStacks={runS1SarIndexStacks}
        s1SarStacksBusy={!!s1SarStacksTaskId}
        onS2IndexStacks={(ids, opts) => runS2IndexStacks(ids, { ...opts, pipelineVariant: "s2" })}
        onPsIndexStacks={(ids, opts) => runS2IndexStacks(ids, { ...opts, pipelineVariant: "ps" })}
        clusterElbowLoading={clusterElbowLoading}
        clusterGmmLoading={clusterGmmLoading}
        clusterElbowResults={clusterElbowResults}
        clusterGmmResults={clusterGmmResults}
        clusterElbowResultsPs={clusterElbowResultsPs}
        clusterGmmResultsPs={clusterGmmResultsPs}
        clusterElbowResultsS1={clusterElbowResultsS1}
        clusterGmmResultsS1={clusterGmmResultsS1}
        onClusterElbow={() => runClusterElbow("s2")}
        onClusterGmm={(k) => runClusterGmm(k, "s2")}
        onClusterElbowPs={() => runClusterElbow("ps")}
        onClusterGmmPs={(k) => runClusterGmm(k, "ps")}
        onClusterElbowS1={(dates) => runClusterElbow("s1", dates)}
        onClusterGmmS1={(k, dates) => runClusterGmm(k, "s1", dates)}
        onLoadPersistedClusterGmm={() => loadPersistedClusterGmm("s2")}
        onLoadPersistedClusterGmmPs={() => loadPersistedClusterGmm("ps")}
        onLoadPersistedClusterGmmS1={() => loadPersistedClusterGmm("s1")}
        onPsPlanetExtract={runPsPlanetExtract}
        onPsRecorteClip={runPsRecorteClip}
        s2Download={s2Download}
        s1Download={s1Download}
      />
      ) : activeDomain === "fire" ? (
        <FirePanel
          token={token}
          isAdmin={isAdmin}
          email={email}
          onStatusMessage={setMessage}
          onFireOrderFocus={loadFireOrderOnMap}
          onClearFireMap={clearFireMap}
          onProjectsRefresh={() => {
            if (token) fetchProjects(token, "fire");
          }}
        />
      ) : (
        <aside className="panel domain-placeholder" aria-live="polite">
          <BrandHeader email={email} />
          <h2 className="domain-placeholder-title">
            {DOMAIN_OPTIONS.find((d) => d.id === activeDomain)?.label || "Módulo"}
          </h2>
          <p className="domain-placeholder-text">
            {DOMAIN_OPTIONS.find((d) => d.id === activeDomain)?.title}. En preparación.
          </p>
          <p className="domain-placeholder-hint">
            Elige <strong>Agro</strong> en el menú izquierdo para usar el flujo actual de XeniaMAP.
          </p>
          <button type="button" className="domain-placeholder-btn" onClick={() => selectDomain("agro")}>
            Ir a Agro
          </button>
        </aside>
      )}
      <MapErrorBoundary>
        <MapView
          mapRef={mapRef}
          mapLayers={mapLayers}
          mapLayersRef={mapLayersRef}
          projectId={projectId}
          token={token}
          baseStyle={baseStyle}
          studyDraw={studyDraw}
        />
      </MapErrorBoundary>
      <MapLayersPanel
        title={activeDomain === "fire" ? "Capas Fire" : "Capas"}
        layers={
          activeDomain === "fire"
            ? mapLayers.filter((l) => l.metadata?.fireLayer)
            : mapLayers.filter((l) => !l.metadata?.fireLayer)
        }
        onToggle={activeDomain === "fire" ? toggleFireLayerVisibility : toggleLayerVisibility}
        onToggleDnbrGroup={activeDomain === "fire" ? toggleFireDnbrGroup : undefined}
        baseStyle={baseStyle}
        onBaseStyleChange={setBaseStyle}
        orderTitle={
          activeDomain === "fire"
            ? mapLayers
                .find((l) => l.metadata?.fireRole === "aoi")
                ?.displayName?.replace(/^Polígono ·\s*/, "") || ""
            : ""
        }
        orderId={activeDomain === "fire" ? fireFocusOrderId : null}
        token={token}
        loading={
          activeDomain === "fire" &&
          loading &&
          mapLayers.filter((l) => l.metadata?.fireLayer).length === 0
        }
        showFireStats={
          activeDomain === "fire" && mapLayers.some((l) => l.metadata?.fireLayer)
        }
        emptyHint={
          activeDomain === "fire"
            ? "Sin capas Fire. Abra un municipio o complete dNBR / FIRMS. El mapa base está abajo."
            : "Sin capas de proyecto. Puede activar el mapa base abajo."
        }
      />
      <AdvancedDashboard
        open={dashboardOpen && !!token && !!projectId && (isAdmin || isCliente)}
        onClose={() => setDashboardOpen(false)}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
        isCliente={isCliente}
        viewerEmail={email}
        initialSmartFocus={smartFocus}
        projectStatus={dashboardProjectStatus}
        onOpenClientVisualization={isCliente ? () => setClientVizModalOpen(true) : undefined}
      />
      <SmartClusterModal
        open={smartClusterOpen && !!token && !!projectId && isAdmin}
        onClose={() => setSmartClusterOpen(false)}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
      />
      <SmartSoilModal
        open={smartSoilOpen && !!token && !!projectId && isAdmin}
        onClose={() => setSmartSoilOpen(false)}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
      />
      <MarkdownReportsModal
        open={markdownReportsOpen && !!token && !!projectId && isAdmin}
        onClose={() => setMarkdownReportsOpen(false)}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
      />
      <ClientVisualizationModal
        open={clientVizModalOpen && isCliente && !!token}
        onClose={() => setClientVizModalOpen(false)}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
        onStatusMessage={setMessage}
      />
      <UserManagementModal
        open={userMgmtOpen && isAdmin}
        token={token}
        onClose={() => setUserMgmtOpen(false)}
        onStatusMessage={(msg) => setMessage(msg)}
      />
      <StudyRequestModal
        open={studyRequestOpen && !!token}
        token={token}
        onOrderSuccess={() => {
          if (token) fetchProjects(token);
        }}
        onClose={() => {
          setStudyRequestOpen(false);
          setStudyDraw(null);
        }}
        addMapLayer={addMapLayer}
        paintLayerOnMap={paintLayerOnMap}
        mapRef={mapRef}
        bboxFromGeojson={bboxFromGeojson}
        setStudyDraw={setStudyDraw}
        finalizeStudyPolygon={finalizeStudyPolygon}
        setMessage={setMessage}
        drawMode={studyDraw?.mode}
      />
      <AdminStudyOrdersModal
        open={studyOrdersOpen && isAdmin}
        token={token}
        onClose={() => setStudyOrdersOpen(false)}
        onStatusMessage={(msg) => setMessage(msg)}
      />
      <ShareProjectModal
        open={shareProjectOpen && isAdmin && !!token && !!projectId}
        token={token}
        projectId={projectId}
        projectName={dashboardProjectName}
        onClose={() => setShareProjectOpen(false)}
        onStatusMessage={(msg) => setMessage(msg)}
      />
    </div>
  );
}
