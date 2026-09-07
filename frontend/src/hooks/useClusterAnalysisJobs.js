import { useEffect, useState } from "react";
import api, { formatApiErrorDetail, setAuthToken } from "../api";

/**
 * Cluster analysis (elbow + GMM) para pipelines S2 / PS / S1.
 */
export default function useClusterAnalysisJobs({
  token,
  projectId,
  requireAdminAction,
  setMessage,
}) {
  const [clusterElbowLoading, setClusterElbowLoading] = useState(false);
  const [clusterGmmLoading, setClusterGmmLoading] = useState(false);
  const [clusterElbowResults, setClusterElbowResults] = useState(null);
  const [clusterGmmResults, setClusterGmmResults] = useState(null);
  const [clusterElbowResultsPs, setClusterElbowResultsPs] = useState(null);
  const [clusterGmmResultsPs, setClusterGmmResultsPs] = useState(null);
  const [clusterElbowResultsS1, setClusterElbowResultsS1] = useState(null);
  const [clusterGmmResultsS1, setClusterGmmResultsS1] = useState(null);

  useEffect(() => {
    setClusterElbowResults(null);
    setClusterGmmResults(null);
    setClusterElbowResultsPs(null);
    setClusterGmmResultsPs(null);
    setClusterElbowResultsS1(null);
    setClusterGmmResultsS1(null);
  }, [projectId]);

  async function runClusterElbow(pipelineVariant = "s2", selectedDates = []) {
    if (!requireAdminAction()) return;
    if (!token || !projectId) {
      setMessage("Error: define proyecto.");
      return;
    }
    const pv = pipelineVariant === "ps" ? "ps" : pipelineVariant === "s1" ? "s1" : "s2";
    const pickedDates = Array.isArray(selectedDates)
      ? [...new Set(selectedDates.map((d) => String(d).slice(0, 10)).filter(Boolean))]
      : [];
    setClusterElbowLoading(true);
    if (pv === "ps") setClusterGmmResultsPs(null);
    else if (pv === "s1") setClusterGmmResultsS1(null);
    else setClusterGmmResults(null);
    setMessage("");
    try {
      setAuthToken(token);
      const res = await api.post("/cluster-analysis/elbow", {
        project_id: Number(projectId),
        pipeline_variant: pv,
        selected_dates: pickedDates.length ? pickedDates : undefined,
        k_min: 1,
        k_max: 10,
        max_samples: 100_000,
        random_state: 42,
      });
      if (pv === "ps") setClusterElbowResultsPs(res.data);
      else if (pv === "s1") setClusterElbowResultsS1(res.data);
      else setClusterElbowResults(res.data);
      const n = res.data.datasets?.length ?? 0;
      setMessage(
        n > 0
          ? `Método del codo listo (${n} dataset(s)). Ajusta K y ejecuta GMM.`
          : "Sin resultados de codo."
      );
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
    } finally {
      setClusterElbowLoading(false);
    }
  }

  async function runClusterGmm(kByKey, pipelineVariant = "s2", selectedDates = []) {
    if (!requireAdminAction()) return;
    if (!token || !projectId) {
      setMessage("Error: define proyecto.");
      return;
    }
    const pv = pipelineVariant === "ps" ? "ps" : pipelineVariant === "s1" ? "s1" : "s2";
    const pickedDates = Array.isArray(selectedDates)
      ? [...new Set(selectedDates.map((d) => String(d).slice(0, 10)).filter(Boolean))]
      : [];
    setClusterGmmLoading(true);
    setMessage("");
    try {
      setAuthToken(token);
      const res = await api.post("/cluster-analysis/gmm", {
        project_id: Number(projectId),
        pipeline_variant: pv,
        selected_dates: pickedDates.length ? pickedDates : undefined,
        k_by_key: kByKey,
        max_samples: 100_000,
        random_state: 42,
      });
      if (pv === "ps") setClusterGmmResultsPs(res.data);
      else if (pv === "s1") setClusterGmmResultsS1(res.data);
      else setClusterGmmResults(res.data);
      setMessage(`GMM terminado. Salidas en ${res.data.output_dir}`);
    } catch (error) {
      setMessage(`Error: ${formatApiErrorDetail(error)}`);
    } finally {
      setClusterGmmLoading(false);
    }
  }

  /** Resultados GMM ya guardados en ``cluster_gmm/`` o ``ClusterPS/`` (p. ej. otra sesión o tras reiniciar). */
  async function loadPersistedClusterGmm(pipelineVariant = "s2") {
    if (!token || !projectId) return null;
    const pv = pipelineVariant === "ps" ? "ps" : pipelineVariant === "s1" ? "s1" : "s2";
    setAuthToken(token);
    const res = await api.get(
      `/cluster-analysis/gmm-results/${projectId}?pipeline_variant=${encodeURIComponent(pv)}`
    );
    const data = res.data;
    if (data?.results?.length) {
      if (pv === "ps") setClusterGmmResultsPs(data);
      else if (pv === "s1") setClusterGmmResultsS1(data);
      else setClusterGmmResults(data);
    } else {
      if (pv === "ps") setClusterGmmResultsPs(null);
      else if (pv === "s1") setClusterGmmResultsS1(null);
      else setClusterGmmResults(null);
    }
    return data;
  }

  return {
    clusterElbowLoading,
    clusterGmmLoading,
    clusterElbowResults,
    clusterGmmResults,
    clusterElbowResultsPs,
    clusterGmmResultsPs,
    clusterElbowResultsS1,
    clusterGmmResultsS1,
    runClusterElbow,
    runClusterGmm,
    loadPersistedClusterGmm,
  };
}
