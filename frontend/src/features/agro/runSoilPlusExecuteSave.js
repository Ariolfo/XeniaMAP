/**
 * Encola SoilPlus execute-save y espera a Celery; luego carga el JSON guardado.
 * Liberá el request HTTP de la API (GIS pesado en worker-agro).
 */
import api from "../../api";

const POLL_MS = 3000;
const MAX_POLLS = 120; // ~6 min

export async function runSoilPlusExecuteSaveAndLoad({
  projectId,
  params,
  onStatus,
}) {
  const { data: queued } = await api.post(
    `/preprocess/soilplus-execute-save/${projectId}`,
    null,
    { params }
  );
  const taskId = queued?.task_id;
  if (!taskId) {
    throw new Error("Sin task_id de SoilPlus");
  }
  const eng = queued?.cv_engine === "matlab" ? "matlab" : "fast";
  const vk = eng === "matlab" ? "matlab" : "fast";

  for (let i = 0; i < MAX_POLLS; i += 1) {
    onStatus?.(`Procesando Soil+… (${i === 0 ? "encolado" : "en curso"})`);
    // eslint-disable-next-line no-await-in-loop
    await new Promise((r) => setTimeout(r, i === 0 ? 800 : POLL_MS));
    // eslint-disable-next-line no-await-in-loop
    const st = await api.get(`/preprocess/task-status/${taskId}`);
    const { state, ready, result, error } = st.data || {};
    if (!ready) continue;
    if (state === "FAILURE" || error) {
      throw new Error(error || "SoilPlus falló en el worker");
    }
    if (state === "SUCCESS") {
      if (result && result.ok === false) {
        throw new Error(result.message || "SoilPlus terminó con error");
      }
      const variant = result?.variant || vk;
      // eslint-disable-next-line no-await-in-loop
      const { data } = await api.get(`/preprocess/soilplus-saved-json/${projectId}`, {
        params: { variant },
      });
      return { data, variant, eng };
    }
  }
  throw new Error("Timeout esperando SoilPlus (worker agro / Redis)");
}
