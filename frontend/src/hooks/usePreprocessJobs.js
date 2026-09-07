import useSentinelDownloads from "./useSentinelDownloads";
import usePreprocessCeleryJobs from "./usePreprocessCeleryJobs";
import useClusterAnalysisJobs from "./useClusterAnalysisJobs";

/**
 * Jobs Agro preprocess: descarga S1/S2, recortes, stacks índices, clusters.
 * Composer: merge de useSentinelDownloads + usePreprocessCeleryJobs + useClusterAnalysisJobs.
 */
export default function usePreprocessJobs({
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
}) {
  const downloads = useSentinelDownloads({
    token,
    projectId,
    downloadSource,
    requireAdminAction,
    addMapLayer,
    setTargetRasterId,
    setMessage,
    setLoading,
  });

  const celery = usePreprocessCeleryJobs({
    token,
    projectId,
    selectedIndices,
    requireAdminAction,
    selectProject,
    setStackMode,
    setSidebarTab,
    setMessage,
    setLoading,
  });

  const cluster = useClusterAnalysisJobs({
    token,
    projectId,
    requireAdminAction,
    setMessage,
  });

  return {
    ...downloads,
    ...celery,
    ...cluster,
  };
}
