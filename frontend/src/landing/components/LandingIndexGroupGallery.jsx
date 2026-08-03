import { useState } from "react";
import { copyForIndex } from "../interpretations";
import { indexNarrativeKey } from "../landingSectionKeys";
import LandingEmbeddedGallery from "./LandingEmbeddedGallery";
import LandingIndexTheoryBox from "./LandingIndexTheoryBox";
import LandingSectionNarrative from "./LandingSectionNarrative";

/**
 * Galería de índices de un grupo + explicación teórica + narrativa editable por índice.
 * La narrativa mostrada sigue al índice activo (misma pestaña que la teoría).
 */
export default function LandingIndexGroupGallery({
  sensorKey,
  projectId,
  token,
  projectName,
  galleryVisualMode,
  pipelineVariant,
  allowedIndexKeys,
  initialIndexKey,
  editMode = false,
  narrative = null,
}) {
  const keys = allowedIndexKeys || [];
  const [activeIndexKey, setActiveIndexKey] = useState(
    () => initialIndexKey || keys[0] || "NDVI"
  );

  const activeKey = indexNarrativeKey(sensorKey, activeIndexKey);
  const activeCopy = copyForIndex(activeIndexKey);
  const activeDisplayBody = narrative?.bodyForDisplay?.(activeKey) ?? "";
  const showActiveNarrative = editMode || !!(activeDisplayBody || "").trim();

  return (
    <div className="landing-index-group-block">
      <LandingEmbeddedGallery
        projectId={projectId}
        token={token}
        projectName={projectName}
        galleryVisualMode={galleryVisualMode}
        pipelineVariant={pipelineVariant}
        allowedIndexKeys={keys}
        initialIndexKey={initialIndexKey}
        onActiveIndexChange={setActiveIndexKey}
      />
      <LandingIndexTheoryBox indexKey={activeIndexKey} />

      {showActiveNarrative ? (
        <aside className="landing-index-theory landing-index-narrative-box" aria-live="polite">
          <h5 className="landing-index-theory-title">
            {activeCopy.title || String(activeIndexKey).toUpperCase()}{" "}
            <strong className="landing-index-theory-badge">(Interpretación agricola)</strong>
          </h5>
          <LandingSectionNarrative
            sectionKey={activeKey}
            editMode={editMode}
            draftValue={narrative?.byKey?.[activeKey]?.draft_body ?? ""}
            onDraftChange={(v) => narrative?.setDraft?.(activeKey, v)}
            displayBody={activeDisplayBody}
            disabled={narrative?.saving}
            allowImages={Boolean(editMode)}
            projectId={projectId}
            token={token}
            label={`Narrativa de ${String(activeIndexKey).toUpperCase()} (Markdown)`}
          />
        </aside>
      ) : null}
    </div>
  );
}
