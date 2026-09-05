import { useEffect, useState } from "react";
import ProjectList from "./ProjectList";
import LayersPanel from "./LayersPanel";
import UploadPanel from "./UploadPanel";
import PreprocessPanel from "./PreprocessPanel";
import Sentinel1Panel from "./Sentinel1Panel";
import BrandHeader from "./BrandHeader";
import { getClientBrand } from "../branding";

function normalizeUserRole(role) {
  const value = String(role || "").trim().toLowerCase();
  if (value === "client") return "cliente";
  return value;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  recorteLayerId,
  setRecorteLayerId,
  preproGalleryKick,
  preproClusterVizKick,
  preproClusterVizKickPs = 0,
  onOpenPreproGallery,
  onOpenPreproClusterViz,
  token,
  userRole,
  email,
  loading,
  message,
  projects,
  projectId,
  projectName,
  projectStudyDateStart = "",
  projectStudyDateEnd = "",
  setProjectName,
  mapLayers,
  targetRasterId,
  setTargetRasterId,
  loteFile,
  setLoteFile,
  rasterFile,
  setRasterFile,
  downloadSource,
  setDownloadSource,
  selectedIndices,
  setSelectedIndices,
  indexStacksBusy,
  visualIndexGalleryKick = 0,
  stackMode,
  setStackMode,
  onLogout,
  onOpenStudyRequest,
  onOpenStudyOrders,
  onOpenShareProject,
  onSelectProject,
  onCreateProject,
  onUpdateProject,
  onDeleteProject,
  onToggleVisibility,
  onZoomToLayer,
  onHideLayer,
  onOpenClientDashboard,
  onOpenClientLanding,
  onOpenClientVisualization,
  onOpenSmartCluster,
  onOpenSmartSoil,
  onOpenMarkdownReports,
  onOpenUserManagement,
  onUploadLote,
  onUploadRaster,
  onRunAI,
  onDownload,
  recortePipelineBusy,
  onS2L2aRecortes,
  onPsL2aRecortes,
  onS1GrdRecortes,
  onS1SarIndexStacks,
  s1SarStacksBusy = false,
  onS2IndexStacks,
  onPsIndexStacks,
  clusterElbowLoading,
  clusterGmmLoading,
  clusterElbowResults,
  clusterGmmResults,
  onClusterElbow,
  onClusterGmm,
  onClusterElbowPs,
  onClusterGmmPs,
  onClusterElbowS1,
  onClusterGmmS1,
  onLoadPersistedClusterGmm,
  onLoadPersistedClusterGmmPs,
  onLoadPersistedClusterGmmS1,
  onPsPlanetExtract,
  onPsRecorteClip,
  s2Download,
  s1Download,
  visualIndexGalleryKickPs = 0,
  clusterElbowResultsPs,
  clusterGmmResultsPs,
  clusterElbowResultsS1,
  clusterGmmResultsS1,
}) {
  const [panelOpen, setPanelOpen] = useState(true);
  const [layersPanelOpen, setLayersPanelOpen] = useState(false);

  useEffect(() => {
    if (!visualIndexGalleryKick) return;
    setActiveTab("prepro");
    setPanelOpen(true);
    setLayersPanelOpen(false);
  }, [visualIndexGalleryKick]);

  useEffect(() => {
    if (!visualIndexGalleryKickPs) return;
    setActiveTab("ps");
    setPanelOpen(true);
    setLayersPanelOpen(false);
  }, [visualIndexGalleryKickPs]);

  const normalizedRole = normalizeUserRole(userRole);
  const isAdmin = !!token && normalizedRole === "admin";
  const isCliente = !!token && normalizedRole === "cliente";
  const showStudyCta = !!token && isCliente;
  const canShowAdminTabs = isAdmin;
  const brand = getClientBrand(email);
  /** Capas admin se controla desde el submenú Agro (DomainMenu), no desde pestañas del panel. */
  const layersOpen = layersPanelOpen || (isAdmin && activeTab === "capas");

  useEffect(() => {
    if (!isAdmin) return;
    if (activeTab === "capas") {
      setLayersPanelOpen(true);
      setPanelOpen(false);
    } else {
      setLayersPanelOpen(false);
      setPanelOpen(true);
    }
  }, [activeTab, isAdmin]);

  return (
    <aside className="panel">
      <BrandHeader email={email} />
      {/* Cliente: Proyectos + Capas. Admin: navegación solo en submenú Agro (DomainMenu). */}
      {isCliente ? (
        <div className="top-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={panelOpen && activeTab === "dashboard"}
            className={panelOpen && activeTab === "dashboard" ? "active" : ""}
            onClick={() => {
              setActiveTab("dashboard");
              setPanelOpen(true);
              setLayersPanelOpen(false);
            }}
          >
            Proyectos
          </button>
          <button
            role="tab"
            aria-selected={layersPanelOpen}
            className={layersPanelOpen ? "tab-toggle active" : "tab-toggle"}
            onClick={() => {
              setLayersPanelOpen((p) => {
                if (!p) setPanelOpen(false);
                return !p;
              });
            }}
            title={layersPanelOpen ? "Cerrar capas" : "Abrir capas"}
          >
            Capas
          </button>
        </div>
      ) : null}

      {layersOpen ? (
        <LayersPanel
          mapLayers={mapLayers}
          onToggleVisibility={onToggleVisibility}
          onZoomToLayer={onZoomToLayer}
          onHideLayer={onHideLayer}
        />
      ) : null}

      {!token && panelOpen && !layersPanelOpen ? (
        <div className="projects-empty">
          Use el módulo <strong>Ingreso</strong> para iniciar sesión. Luego vuelva a Agro.
        </div>
      ) : null}

      {panelOpen && !layersPanelOpen && activeTab === "admin" && isAdmin ? (
        <>
          <div className="session-info">
            <span>
              {email} ({userRole || "sin rol"})
            </span>
            <button onClick={onLogout} disabled={loading} className="btn-link">
              Cerrar sesion
            </button>
          </div>
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenUserManagement?.()}
            disabled={loading}
            title="Abrir gestion de usuarios y roles"
          >
            Gestion Usuario
          </button>
          <button
            type="button"
            className="layers-dashboard-btn study-orders-btn"
            onClick={() => onOpenStudyOrders?.()}
            disabled={loading}
            title="Ver solicitudes AgroGeoFísico"
          >
            Gestion de ordenes
          </button>
          <div className="admin-project-field">
            <label className="admin-project-label" htmlFor="admin-project-select">
              Proyecto de trabajo
            </label>
            <select
              id="admin-project-select"
              className="admin-project-select"
              value={projectId != null && projectId !== "" ? String(projectId) : ""}
              onChange={(e) => {
                const v = e.target.value;
                if (v) onSelectProject(Number(v));
              }}
              disabled={loading || !projects?.length}
            >
              <option value="">— Elija proyecto —</option>
              {(projects || []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.status ?? "—"})
                </option>
              ))}
            </select>
            {!projects?.length ? (
              <p className="admin-project-hint">
                No hay proyectos. Los clientes crean proyectos al solicitar un estudio.
              </p>
            ) : null}
            <button
              type="button"
              className="layers-dashboard-btn share-project-btn"
              onClick={() => onOpenShareProject?.()}
              disabled={loading || !projectId}
              title={
                projectId
                  ? "Dar acceso de lectura a otro usuario cliente"
                  : "Seleccione un proyecto primero"
              }
            >
              Compartir proyecto con usuario
            </button>
            <button
              type="button"
              className="layers-dashboard-btn admin-project-delete-btn"
              onClick={() => {
                if (projectId) onDeleteProject(Number(projectId));
              }}
              disabled={loading || !projectId}
              title={
                projectId
                  ? "Eliminar el proyecto seleccionado y todas sus capas"
                  : "Seleccione un proyecto primero"
              }
            >
              Eliminar proyecto
            </button>
          </div>
        </>
      ) : null}

      {panelOpen && !layersPanelOpen && activeTab === "dashboard" && isCliente ? (
        <>
          {showStudyCta ? (
            <button
              type="button"
              className="study-primary-cta"
              onClick={() => onOpenStudyRequest?.()}
              disabled={loading}
            >
              Solicitar estudio AgroGeoFísico
            </button>
          ) : null}
          <ProjectList
            projects={projects}
            projectId={projectId}
            projectName={projectName}
            setProjectName={setProjectName}
            loading={loading}
            onSelectProject={onSelectProject}
            onCreateProject={onCreateProject}
            onUpdateProject={onUpdateProject}
            onDeleteProject={onDeleteProject}
            onLogout={onLogout}
            email={email}
            readOnly
            allowDelete
            title="Mis proyectos Agro"
          />
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenClientDashboard?.()}
            disabled={loading || !projectId}
            title={
              !projectId
                ? "Seleccione un proyecto en la lista"
                : "Abrir dashboard con resultados publicados"
            }
          >
            Abrir dashboard de resultados
          </button>
          <button
            type="button"
            className="layers-dashboard-btn landing-narrative-btn"
            onClick={() => onOpenClientLanding?.()}
            disabled={loading || !projectId}
            title={
              projectId
                ? "Abrir informe narrativo del proyecto (vista landing)"
                : "Seleccione un proyecto en la lista"
            }
          >
            Informe narrativo
          </button>
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenClientVisualization?.()}
            disabled={loading || !projectId}
            title={
              !projectId
                ? "Seleccione un proyecto en la lista"
                : "Abrir visualización Sentinel-1, Sentinel-2 y alta resolución"
            }
          >
            Ver
          </button>
        </>
      ) : null}

      {canShowAdminTabs && panelOpen && !layersPanelOpen && activeTab === "s1" ? (
        <Sentinel1Panel
          token={token}
          projectId={projectId}
          projectName={projectName}
          loading={loading}
          mapLayers={mapLayers}
          recorteLayerId={recorteLayerId}
          setRecorteLayerId={setRecorteLayerId}
          stackMode={stackMode}
          setStackMode={setStackMode}
          onOpenPreproGallery={onOpenPreproGallery}
          onOpenPreproClusterViz={onOpenPreproClusterViz}
          recortePipelineBusy={recortePipelineBusy}
          s1SarStacksBusy={s1SarStacksBusy}
          onS1GrdRecortes={onS1GrdRecortes}
          onS1SarIndexStacks={onS1SarIndexStacks}
          clusterElbowLoading={clusterElbowLoading}
          clusterGmmLoading={clusterGmmLoading}
          clusterElbowResults={clusterElbowResultsS1}
          clusterGmmResults={clusterGmmResultsS1}
          onClusterElbow={onClusterElbowS1}
          onClusterGmm={onClusterGmmS1}
          onLoadPersistedClusterGmm={onLoadPersistedClusterGmmS1}
        />
      ) : null}

      {canShowAdminTabs && panelOpen && !layersPanelOpen && activeTab === "cargar" ? (
        <UploadPanel
          token={token}
          projectId={projectId}
          loading={loading}
          defaultStartDate={projectStudyDateStart}
          defaultEndDate={projectStudyDateEnd}
          targetRasterId={targetRasterId}
          setTargetRasterId={setTargetRasterId}
          onUploadLote={onUploadLote}
          onUploadRaster={onUploadRaster}
          onRunAI={onRunAI}
          onDownload={onDownload}
          loteFile={loteFile}
          setLoteFile={setLoteFile}
          rasterFile={rasterFile}
          setRasterFile={setRasterFile}
          downloadSource={downloadSource}
          setDownloadSource={setDownloadSource}
          mapLayers={mapLayers}
          s2Download={s2Download}
          s1Download={s1Download}
        />
      ) : null}

      {canShowAdminTabs && panelOpen && !layersPanelOpen && activeTab === "prepro" ? (
        <PreprocessPanel
          token={token}
          projectId={projectId}
          projectName={projectName}
          loading={loading}
          selectedIndices={selectedIndices}
          setSelectedIndices={setSelectedIndices}
          stackMode={stackMode}
          setStackMode={setStackMode}
          mapLayers={mapLayers}
          recortePipelineBusy={recortePipelineBusy}
          indexStacksBusy={indexStacksBusy}
          visualIndexGalleryKick={visualIndexGalleryKick}
          recorteLayerId={recorteLayerId}
          setRecorteLayerId={setRecorteLayerId}
          preproGalleryKick={preproGalleryKick}
          preproClusterVizKick={preproClusterVizKick}
          onS2L2aRecortes={onS2L2aRecortes}
          onS2IndexStacks={onS2IndexStacks}
          clusterElbowLoading={clusterElbowLoading}
          clusterGmmLoading={clusterGmmLoading}
          clusterElbowResults={clusterElbowResults}
          clusterGmmResults={clusterGmmResults}
          onClusterElbow={onClusterElbow}
          onClusterGmm={onClusterGmm}
          onLoadPersistedClusterGmm={onLoadPersistedClusterGmm}
          pipelineVariant="s2"
        />
      ) : null}

      {canShowAdminTabs && panelOpen && !layersPanelOpen && activeTab === "ps" ? (
        <PreprocessPanel
          token={token}
          projectId={projectId}
          projectName={projectName}
          loading={loading}
          selectedIndices={selectedIndices}
          setSelectedIndices={setSelectedIndices}
          stackMode={stackMode}
          setStackMode={setStackMode}
          mapLayers={mapLayers}
          recortePipelineBusy={recortePipelineBusy}
          indexStacksBusy={indexStacksBusy}
          visualIndexGalleryKick={visualIndexGalleryKickPs}
          recorteLayerId={recorteLayerId}
          setRecorteLayerId={setRecorteLayerId}
          preproGalleryKick={preproGalleryKick}
          preproClusterVizKick={preproClusterVizKickPs}
          onS2L2aRecortes={onPsL2aRecortes}
          onS2IndexStacks={onPsIndexStacks}
          clusterElbowLoading={clusterElbowLoading}
          clusterGmmLoading={clusterGmmLoading}
          clusterElbowResults={clusterElbowResultsPs}
          clusterGmmResults={clusterGmmResultsPs}
          onClusterElbow={onClusterElbowPs}
          onClusterGmm={onClusterGmmPs}
          onLoadPersistedClusterGmm={onLoadPersistedClusterGmmPs}
          pipelineVariant="ps"
          onPsPlanetExtract={onPsPlanetExtract}
          onPsRecorteClip={onPsRecorteClip}
        />
      ) : null}

      {canShowAdminTabs && panelOpen && !layersPanelOpen && activeTab === "smart" ? (
        <>
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenSmartCluster?.()}
            disabled={loading || !projectId}
            title={!projectId ? "Seleccione un proyecto en la lista" : "Generar/ver clusters Smart guardados"}
          >
            Smart Cluster
          </button>
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenSmartSoil?.()}
            disabled={loading || !projectId}
            title={!projectId ? "Seleccione un proyecto en la lista" : "Abrir Smart Soil"}
          >
            Smart Soil
          </button>
          <button
            type="button"
            className="layers-dashboard-btn"
            onClick={() => onOpenMarkdownReports?.()}
            disabled={loading || !projectId}
            title={
              !projectId
                ? "Seleccione un proyecto en la lista"
                : "Generar/descargar los Markdown narrativos (PS, S1, S2)"
            }
          >
            Markdown
          </button>
        </>
      ) : null}

      {message && (
        <div className="status-msg">{loading ? "Procesando..." : message}</div>
      )}
      <div className="powered-by">
        <span>Powered by</span>
        <div className="powered-by-logos">
          <img
            src={brand.poweredByLogoSrc || "/logo-xenia-positivo.png"}
            alt={brand.poweredByLogoAlt || "Xenia"}
          />
          <img
            src={brand.poweredByLogoSecondarySrc || "/logo-teraval.png"}
            alt={brand.poweredByLogoSecondaryAlt || "Teraval"}
          />
        </div>
      </div>
    </aside>
  );
}
