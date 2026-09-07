import { useEffect, useMemo, useState } from "react";
import SensorTimelapseViewer from "../../components/dashboard/SensorTimelapseViewer";
import ResultSection from "../components/ResultSection";
import { FUNCTIONAL_GROUPS, copyForIndex, groupForIndex } from "../interpretations";
import { SENSOR_META, resolveInventoryIndexKey } from "../previewUtils";
import { sensorLabel } from "../dataAdapter";

const CULTIVO_INDICES = ["NDVI", "KNDVI", "NDRE", "RSTRUCTURE", "EVI", "MSAVI2", "VARI", "GIYI", "MCARI", "CIre"];

export default function CultivoAnalysisSection({
  projectId: _projectId,
  token: _token,
  adapted,
  sensor,
  onSensorChange,
  indexSrc,
  rgbSrc,
  loadingPreview,
  previewError,
  onFrameChange,
  onIndexChange,
  onPlayStateChange,
}) {
  const sensorBlock = adapted?.sensorData?.[sensor];
  const availableIndices = sensorBlock?.indices || [];
  const [selectedIndex, setSelectedIndex] = useState("");
  const [frameIdx, setFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    const preferred =
      resolveInventoryIndexKey(availableIndices, SENSOR_META[sensor]?.defaultIndex) ||
      resolveInventoryIndexKey(availableIndices, "NDVI") ||
      availableIndices[0] ||
      "";
    setSelectedIndex(preferred);
    setFrameIdx(0);
    setIsPlaying(false);
  }, [sensor, availableIndices.join("|")]);

  const frames = useMemo(
    () => sensorBlock?.framesByIndex?.[selectedIndex] || [],
    [sensorBlock, selectedIndex]
  );

  useEffect(() => {
    if (frameIdx >= frames.length) setFrameIdx(0);
  }, [frames.length, frameIdx]);

  useEffect(() => {
    if (!isPlaying || frames.length < 2) return undefined;
    const t = window.setInterval(() => {
      setFrameIdx((i) => (i + 1) % frames.length);
    }, 1400);
    return () => window.clearInterval(t);
  }, [isPlaying, frames.length]);

  useEffect(() => {
    const frame = frames[frameIdx];
    if (frame) onFrameChange?.(sensor, selectedIndex, frame, frameIdx);
  }, [sensor, selectedIndex, frameIdx, frames, onFrameChange]);

  useEffect(() => {
    if (selectedIndex) onIndexChange?.(sensor, selectedIndex);
  }, [sensor, selectedIndex, onIndexChange]);

  const indexCopy = copyForIndex(selectedIndex);
  const functionalGroup = groupForIndex(selectedIndex);

  const indexOptions = availableIndices.filter((k) =>
    CULTIVO_INDICES.some((c) => String(c).toUpperCase() === String(k).toUpperCase())
  );
  const pickerIndices = indexOptions.length ? indexOptions : availableIndices;

  return (
    <div className="landing-cultivo">
      <nav className="landing-pillar-nav" aria-label="Análisis principal">
        <span className="landing-pillar-nav-item active">Análisis de cultivo</span>
        <span className="landing-pillar-nav-item muted">Análisis hídrico</span>
        <span className="landing-pillar-nav-item muted">Análisis de suelo</span>
      </nav>

      <ResultSection
        id="analisis-cultivo"
        title="¿Qué tan sano está el dosel de su cultivo?"
        subtitle="Compare la foto satelital (RGB) con el índice de vegetación en el mismo día."
        badge={sensorLabel(sensor)}
        visual={
          <div className="landing-cultivo-controls">
            <div className="landing-sensor-tabs" role="tablist" aria-label="Fuente satelital">
              {["ps", "s2", "s1"].map((s) => {
                const hasData = (adapted?.sensorData?.[s]?.indices?.length || 0) > 0;
                return (
                  <button
                    key={s}
                    type="button"
                    role="tab"
                    aria-selected={sensor === s}
                    className={`landing-sensor-tab${sensor === s ? " active" : ""}`}
                    disabled={!hasData}
                    onClick={() => onSensorChange?.(s)}
                  >
                    {SENSOR_META[s].title}
                  </button>
                );
              })}
            </div>
            <div className="landing-index-picker">
              <label htmlFor="landing-index-select">Índice</label>
              <select
                id="landing-index-select"
                value={selectedIndex}
                onChange={(e) => {
                  setSelectedIndex(e.target.value);
                  setFrameIdx(0);
                }}
              >
                {pickerIndices.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>
            {loadingPreview ? <p className="landing-hint">Cargando imagen…</p> : null}
            {previewError ? <p className="landing-error">{previewError}</p> : null}
            <SensorTimelapseViewer
              sensorTitle={SENSOR_META[sensor].title}
              omitSensorTitle
              indices={pickerIndices}
              selectedIndex={selectedIndex}
              onChangeIndex={(k) => {
                setSelectedIndex(k);
                setFrameIdx(0);
              }}
              frames={frames}
              currentIdx={frameIdx}
              onChangeFrameIdx={setFrameIdx}
              isPlaying={isPlaying}
              onPlayPause={() => {
                setIsPlaying((p) => {
                  const next = !p;
                  onPlayStateChange?.(next);
                  return next;
                });
              }}
              onStop={() => {
                setIsPlaying(false);
                setFrameIdx(0);
                onPlayStateChange?.(false);
              }}
              imageSrc={indexSrc}
              imageAlt={`${selectedIndex} ${frames[frameIdx]?.date || ""}`}
              dualPaneRgb={sensor !== "s1"}
              rgbImageSrc={rgbSrc}
              rgbAlt={`RGB ${frames[frameIdx]?.date || ""}`}
              rightPaneLabel="RGB visible"
              rgbEmptyMessage={
                sensor === "s1"
                  ? "Vista radar (VV) disponible en panel derecho cuando hay escenas S1."
                  : "Sin recorte RGB para esta fecha."
              }
              opacity={100}
              onOpacity={() => {}}
            />
          </div>
        }
        interpretation={`${indexCopy.interpretation}${
          functionalGroup ? ` Pertenece al grupo «${functionalGroup.title}»: ${functionalGroup.meaning}` : ""
        }`}
        howToRead={indexCopy.howToRead}
        action={functionalGroup?.action || "Recorra el timelapse: si el problema se repite en las mismas zonas, programe inspección focalizada."}
      />

      <aside className="landing-functional-groups">
        <h3>Grupos funcionales de índices</h3>
        <ul>
          {FUNCTIONAL_GROUPS.map((g) => (
            <li key={g.id}>
              <strong>{g.title}</strong>
              <span>{g.indices.join(", ")}</span>
              <p>{g.meaning}</p>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
